"""HSAT shared-textbook ingestion service.

Pipeline per book:
  1. Resolve catalog entry → list of S3 keys (chapters).
  2. For each chapter: download from S3 → reuse the same chunk pipeline
     used for user PDFs (text + figure extraction → embeddings).
  3. Persist chunks under the HsatSource FK so they're queryable by the
     existing retrieval layer with no per-user duplication.
  4. Track per-chapter errors so a single bad PDF never fails the whole
     book.

Ingestion runs at-most-once per (grade, subject, book): if the
HsatSource is already `ready`, the call is a no-op.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Sequence

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone as tz

from apps.documents.models import HsatSource
from services import hsat_catalog
from services.document_service import extract_and_persist_chunks
from services.s3_client import S3NotConfigured, download_to_buffer, is_configured

logger = logging.getLogger("[HSAT_SERVICE]")

# How many chapters to ingest in parallel inside one book. This only
# multiplies download / text-chunking work: vision captioning is gated by
# a PROCESS-WIDE semaphore (PDF_IMAGE_CAPTION_CONCURRENCY, default 3) in
# services.openai_service, so chapter parallelism can no longer multiply
# gpt-4o TPM pressure the way the old per-chapter 8-thread pools did
# (3 chapters × 8 threads = 24 in-flight calls → 30k TPM saturation).
HSAT_CHAPTER_CONCURRENCY_DEFAULT = 3

# At-most-one ingest per (grade, subject, book) at a time, even if the
# API is hit concurrently. The lock is per-process; the DB status guard
# below covers cross-process races.
_ingest_locks: Dict[str, threading.Lock] = {}
_ingest_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _ingest_locks_guard:
        lock = _ingest_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _ingest_locks[key] = lock
        return lock


def get_or_create_source(grade: str, subject: str, book: str) -> HsatSource:
    source, _ = HsatSource.objects.get_or_create(
        grade=grade,
        subject=subject,
        book=book,
        defaults={"status": "pending"},
    )
    return source


def get_source(grade: str, subject: str, book: str) -> Optional[HsatSource]:
    return HsatSource.objects.filter(
        grade=grade, subject=subject, book=book
    ).first()


def book_status(grade: str, subject: str, book: str) -> Dict[str, Any]:
    """Return a status dict suitable for the catalog API."""
    source = get_source(grade, subject, book)
    if source is None:
        return {"status": "not_ingested", "chunk_count": 0}
    return {
        "status": source.status,
        "chunk_count": source.chunk_count,
        "error": source.error,
        "processed_at": (
            source.processed_at.isoformat() if source.processed_at else None
        ),
        "chapter_errors": source.chapter_errors or {},
    }


def _humanize_chapter_label(s3_key: str) -> str:
    """Turn 'class 10/.../CH7 -  Madam Rides the Bus.pdf' into
    'Chapter 7: Madam Rides the Bus' so the UI doesn't expose
    bucket structure / file extensions."""
    import re

    base = os.path.basename(s3_key).removesuffix(".pdf")
    m = re.match(r"^\s*CH\s*(\d+)\s*-\s*(.+)$", base, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        return f"Chapter {num}: {title}"
    # NCERT Mathematics: jemh101 = Chapter 1, jemh114 = Chapter 14,
    # jemh1a1 / jemh1ps = appendices / proofs.
    m2 = re.match(r"^jemh1(\d{2})$", base)
    if m2:
        n = int(m2.group(1))
        return f"Chapter {n}"
    m3 = re.match(r"^jemh1(a\d+|an|ps)$", base, re.IGNORECASE)
    if m3:
        suffix = m3.group(1).lower()
        labels = {
            "a1": "Appendix 1: Proofs in Mathematics",
            "a2": "Appendix 2: Mathematical Modelling",
            "an": "Answers",
            "ps": "Proofs",
        }
        return labels.get(suffix, base.replace("_", " ").title())
    return re.sub(r"[_]+", " ", base).strip().title()


def book_chapters(
    grade: str, subject: str, book: str
) -> List[Dict[str, Any]]:
    """Return the per-chapter list for one book with display labels
    and individual status flags so the UI can let the user select a
    subset to ingest."""
    keys = hsat_catalog.get_book_keys(grade, subject, book)
    if not keys:
        return []
    source = get_source(grade, subject, book)
    chapter_errors = (source.chapter_errors if source else None) or {}
    # A chapter counts as "ready" if the book is ready and that key isn't
    # in chapter_errors. When the book is still processing or pending we
    # leave per-chapter status as "pending" so the UI shows progress, not
    # false-positive readies.
    book_ready = source is not None and source.status == "ready"
    rows = []
    for key in keys:
        if key in chapter_errors:
            chap_status = "error"
        elif book_ready:
            chap_status = "ready"
        elif source is None:
            chap_status = "not_ingested"
        else:
            chap_status = source.status
        rows.append(
            {
                "s3_key": key,
                "label": _humanize_chapter_label(key),
                "status": chap_status,
                "error": chapter_errors.get(key),
            }
        )
    return rows


def _ingest_one_chapter(
    *,
    s3_key: str,
    grade: str,
    subject: str,
    book: str,
    hsat_source_id: str,
) -> Dict[str, Any]:
    """
    Worker for a single chapter — runs inside a ThreadPoolExecutor pool.
    Always re-resolves the HsatSource via PK so we don't hold a stale ORM
    object across threads. close_old_connections() at the end keeps the
    per-thread DB connection from leaking back into the pool.
    """
    from apps.documents.models import HsatSource as _HS  # local: tests reset modules

    chapter_label = os.path.basename(s3_key) or s3_key
    chapter_start = time.perf_counter()
    try:
        buffer = download_to_buffer(s3_key)
        download_secs = time.perf_counter() - chapter_start

        source = _HS.objects.get(pk=hsat_source_id)
        stats = extract_and_persist_chunks(
            buffer=buffer,
            file_name=chapter_label,
            file_type="application/pdf",
            hsat_source=source,
            extra_metadata={
                "source_type": "hsat",
                "s3_key": s3_key,
                "hsat_grade": grade,
                "hsat_subject": subject,
                "hsat_book": book,
                "hsat_chapter": chapter_label,
            },
            user=None,
            mark_ready=False,
        )
        total = int(stats.get("total_chunks") or 0)
        logger.info(
            "ingest_hsat_book chapter ok: %s — %d chunks "
            "(%d text + %d image), download=%.2fs total=%.2fs",
            s3_key,
            total,
            stats.get("text_chunks") or 0,
            stats.get("image_chunks") or 0,
            download_secs,
            time.perf_counter() - chapter_start,
        )
        return {"s3_key": s3_key, "total_chunks": total, "error": None}
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        logger.exception("ingest_hsat_book chapter failed: %s — %s", s3_key, msg)
        return {"s3_key": s3_key, "total_chunks": 0, "error": msg}
    finally:
        close_old_connections()


def ingest_hsat_book(
    grade: str,
    subject: str,
    book: str,
    *,
    force: bool = False,
    chapter_keys: Optional[Sequence[str]] = None,
) -> HsatSource:
    """
    Ingest one HSAT book end-to-end. Idempotent — returns the existing
    HsatSource if it's already `ready` unless `force=True`.

    ``chapter_keys`` lets the caller restrict the run to a subset of S3
    keys (e.g. the chapters the user actually picked in the UI). The
    keys must already exist in the catalog for this book; unknown keys
    are ignored with a warning. When omitted, every chapter listed in
    the catalog is processed.

    Raises ValueError if the (grade, subject, book) is not in the
    catalog or S3 is not configured.
    """
    if not is_configured():
        raise S3NotConfigured(
            "AWS credentials / bucket are not configured. Set "
            "AWS_STORAGE_BUCKET_NAME / AWS_ACCESS_KEY_ID / "
            "AWS_SECRET_ACCESS_KEY in the backend .env."
        )

    all_keys = hsat_catalog.get_book_keys(grade, subject, book)
    if not all_keys:
        raise ValueError(
            f"Catalog has no book named {book!r} under {grade!r}/{subject!r}."
        )

    # Filter to the user-selected subset (preserving catalog order so the
    # download/log output is stable across runs).
    if chapter_keys:
        requested = set(chapter_keys)
        keys = [k for k in all_keys if k in requested]
        unknown = requested - set(all_keys)
        if unknown:
            logger.warning(
                "ingest_hsat_book ignoring %d unknown chapter key(s): %s",
                len(unknown), sorted(unknown)[:5],
            )
        if not keys:
            raise ValueError(
                "None of the requested chapter keys match this book's catalog."
            )
    else:
        keys = list(all_keys)

    lock_key = f"{grade}|{subject}|{book}"
    lock = _lock_for(lock_key)
    if not lock.acquire(blocking=False):
        # Another thread in this process is already ingesting. Return the
        # current state — the caller can poll.
        source = get_or_create_source(grade, subject, book)
        logger.info(
            "ingest_hsat_book skipped (already in flight): %s/%s/%s status=%s",
            grade, subject, book, source.status,
        )
        return source

    try:
        with transaction.atomic():
            source = (
                HsatSource.objects.select_for_update()
                .filter(grade=grade, subject=subject, book=book)
                .first()
            )
            # Because we already hold ``lock`` for this (grade, subject,
            # book), nobody else is racing us. A row that's currently
            # "processing" therefore means *we* are the worker — either
            # the async helper bumped it just before spawning us, or a
            # previous worker crashed and left it in that state. In
            # both cases we proceed; we don't bail out on
            # status == "processing".
            if source is None:
                source = HsatSource.objects.create(
                    grade=grade,
                    subject=subject,
                    book=book,
                    status="processing",
                )
            elif source.status == "ready" and not force:
                # Partial top-ups: if the user picked specific chapters and
                # any of them aren't represented yet, fall through and
                # ingest just those keys.
                if not chapter_keys:
                    logger.info(
                        "ingest_hsat_book no-op (already ready): %s/%s/%s",
                        grade, subject, book,
                    )
                    return source
                missing = _missing_chapter_keys(source, keys)
                if not missing:
                    logger.info(
                        "ingest_hsat_book no-op (chapters already ingested): "
                        "%s/%s/%s keys=%d",
                        grade, subject, book, len(keys),
                    )
                    return source
                keys = missing
                logger.info(
                    "ingest_hsat_book top-up: %s/%s/%s adding %d new chapter(s)",
                    grade, subject, book, len(keys),
                )
                source.status = "processing"
                source.error = None
                source.save(update_fields=["status", "error", "updated_at"])
            else:
                # Either the row was already "processing" (we own it via
                # ``lock``) or it was previously errored and is being
                # retried. Either way, reset the error state and clear
                # any per-chapter errors for the keys we're about to
                # re-attempt.
                source.status = "processing"
                source.error = None
                if not chapter_keys:
                    source.chapter_errors = {}
                source.save(
                    update_fields=["status", "error", "chapter_errors", "updated_at"]
                )

        # If forcing a re-ingest, wipe previously persisted chunks so we
        # don't double-count. Chunks cascade-delete on HsatSource deletion;
        # here we keep the row and only clear chunks.
        if force:
            source.chunks.all().delete()
            source.chunk_count = 0
            source.save(update_fields=["chunk_count", "updated_at"])

        # Per-chapter results — collected from the worker pool.
        chapter_errors: Dict[str, str] = dict(source.chapter_errors or {})
        # When (re-)ingesting a subset, drop any past error rows for those
        # specific keys so a successful re-run clears them.
        for k in keys:
            chapter_errors.pop(k, None)

        total_chunks_delta = 0
        book_start = time.perf_counter()
        outer_concurrency = max(
            1,
            int(
                getattr(
                    settings,
                    "HSAT_CHAPTER_CONCURRENCY",
                    HSAT_CHAPTER_CONCURRENCY_DEFAULT,
                )
            ),
        )
        outer_concurrency = min(outer_concurrency, len(keys))
        logger.info(
            "ingest_hsat_book start: %s/%s/%s (%d chapter(s), outer concurrency=%d)",
            grade, subject, book, len(keys), outer_concurrency,
        )

        if outer_concurrency == 1:
            results = [
                _ingest_one_chapter(
                    s3_key=s3_key,
                    grade=grade, subject=subject, book=book,
                    hsat_source_id=source.pk,
                )
                for s3_key in keys
            ]
        else:
            with ThreadPoolExecutor(
                max_workers=outer_concurrency,
                thread_name_prefix=f"hsat-{book}",
            ) as pool:
                futures = [
                    pool.submit(
                        _ingest_one_chapter,
                        s3_key=k, grade=grade, subject=subject, book=book,
                        hsat_source_id=source.pk,
                    )
                    for k in keys
                ]
                results = [f.result() for f in as_completed(futures)]

        for row in results:
            if row["error"]:
                chapter_errors[row["s3_key"]] = row["error"]
            else:
                total_chunks_delta += row["total_chunks"]

        # Reload the live row — chunk_count was being bumped from workers
        # via F('chunk_count') + N, so re-read to capture the final value.
        source.refresh_from_db()

        # Final status:
        # - "error"     iff every requested chapter failed AND no prior
        #               chunks exist (full failure).
        # - "ready"     otherwise (some chunks landed → useful for RAG).
        failed_now = sum(1 for r in results if r["error"])
        if failed_now == len(keys) and source.chunk_count == 0:
            final_status = "error"
            top_error = (
                "Every chapter failed to ingest. See chapter_errors for "
                "per-chapter details."
            )
        else:
            final_status = "ready"
            top_error = None

        source.status = final_status
        source.error = top_error
        source.chapter_errors = chapter_errors
        source.processed_at = tz.now()
        source.save(
            update_fields=[
                "status", "error", "chapter_errors",
                "processed_at", "updated_at",
            ]
        )

        logger.info(
            "ingest_hsat_book done: %s/%s/%s status=%s "
            "chunks_added=%d total=%d errors=%d/%d total_time=%.1fs",
            grade, subject, book, final_status,
            total_chunks_delta, source.chunk_count,
            failed_now, len(keys),
            time.perf_counter() - book_start,
        )
        return source
    except Exception as exc:  # noqa: BLE001
        # Hard failure outside the per-chapter loop — mark source errored
        # so the caller doesn't see a stuck "processing" row.
        logger.exception("ingest_hsat_book fatal: %s/%s/%s", grade, subject, book)
        try:
            HsatSource.objects.filter(
                grade=grade, subject=subject, book=book
            ).update(status="error", error=str(exc))
        except Exception:
            logger.exception("Could not mark HsatSource as errored after fatal")
        raise
    finally:
        lock.release()


def _missing_chapter_keys(
    source: HsatSource, requested: Sequence[str]
) -> List[str]:
    """Return the subset of ``requested`` whose chunks have not been
    persisted yet. Used to top-up a book that already has *some* chapters
    ingested without re-doing the ones that succeeded."""
    from apps.documents.models import DocumentChunk

    seen = set(
        DocumentChunk.objects.filter(
            hsat_source=source,
            metadata__s3_key__in=list(requested),
        ).values_list("metadata__s3_key", flat=True)
    )
    return [k for k in requested if k not in seen]


def ingest_hsat_book_async(
    grade: str,
    subject: str,
    book: str,
    *,
    force: bool = False,
    chapter_keys: Optional[Sequence[str]] = None,
) -> HsatSource:
    """
    Trigger ingestion in a background thread and return immediately with the
    current (pending/processing) source row.

    The spec calls for Celery if available, threading otherwise. A Celery
    task isn't installed in this project, so we use a daemon thread. The
    thread runs against the Django ORM, which is connection-pool safe.

    If the worker raises an unhandled exception it is logged AND the
    HsatSource status is forced to "error" with the message saved — no
    silent thread crashes that leave the row in "processing" forever.
    """
    source = get_or_create_source(grade, subject, book)

    # Fast path: full-book request and the book is already ready.
    if source.status == "ready" and not force and not chapter_keys:
        return source

    if source.status != "processing":
        source.status = "processing"
        source.error = None
        source.save(update_fields=["status", "error", "updated_at"])

    chapter_keys_snapshot = list(chapter_keys) if chapter_keys else None

    def _worker():
        try:
            ingest_hsat_book(
                grade, subject, book,
                force=force,
                chapter_keys=chapter_keys_snapshot,
            )
        except Exception as exc:
            logger.exception(
                "Background HSAT ingest failed: %s/%s/%s",
                grade, subject, book,
            )
            # Make sure the row never stays stuck in "processing" because of
            # an unhandled worker exception.
            try:
                HsatSource.objects.filter(
                    grade=grade, subject=subject, book=book
                ).update(status="error", error=f"{type(exc).__name__}: {exc}")
            except Exception:
                logger.exception(
                    "Could not write error status after worker crash"
                )
        finally:
            close_old_connections()

    thread = threading.Thread(
        target=_worker,
        name=f"hsat-ingest-{grade}-{subject}-{book}",
        daemon=True,
    )
    thread.start()
    return source
