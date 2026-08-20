"""HSAT catalog / ingest / apply views.

These are mounted under `/api/hsat/` (see `config.urls`). All endpoints
require an authenticated user, but HSAT content itself is shared globally
across users — only the per-paper application (`PaperHsatSource`) is
user-scoped via `paper.user`.

Endpoints:
  GET  /api/hsat/catalog/       → tree + per-book status; also reports
                                  whether AWS is configured at all.
  POST /api/hsat/ingest/        → kick off background ingest (idempotent).
  POST /api/hsat/apply/         → link a book to a paper, triggering
                                  ingest if needed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import HsatSource, PaperHsatSource
from apps.projects.models import Paper
from services import hsat_catalog
from services.hsat_service import (
    book_chapters,
    book_status,
    get_or_create_source,
    get_source,
    ingest_hsat_book_async,
)
from services.s3_client import is_configured as s3_is_configured

logger = logging.getLogger("[HSAT_VIEWS]")


def _validate_book(grade: str, subject: str, book: str) -> Optional[Response]:
    if not (grade and subject and book):
        return Response(
            {"error": "grade, subject and book are required"}, status=400
        )
    if not hsat_catalog.book_exists(grade, subject, book):
        return Response(
            {
                "error": (
                    f"Unknown HSAT book: grade={grade!r} subject={subject!r} "
                    f"book={book!r}. See /api/hsat/catalog/ for the full list."
                )
            },
            status=404,
        )
    return None


class HsatCatalogView(APIView):
    """Return the catalog tree with per-book ingestion status."""

    def get(self, request):
        configured = s3_is_configured()
        # `include_chapters=1` returns the per-chapter list inside each book
        # so the UI can render the chapter checklist without a second round
        # trip. Default off to keep the payload small for the initial pull.
        include_chapters = str(
            request.query_params.get("include_chapters") or ""
        ).strip().lower() in {"1", "true", "yes"}

        tree: Dict[str, Any] = {}
        for grade, subject, book, _keys in hsat_catalog.iter_books():
            grade_node = tree.setdefault(grade, {})
            subject_node = grade_node.setdefault(subject, {})
            entry: Dict[str, Any] = {
                "chapter_count": len(_keys),
                **book_status(grade, subject, book),
            }
            if include_chapters:
                entry["chapters"] = book_chapters(grade, subject, book)
            subject_node[book] = entry
        return Response(
            {
                "enabled": configured,
                "tree": tree,
                "message": (
                    None
                    if configured
                    else (
                        "HSAT sources are unavailable: AWS S3 is not configured "
                        "on the backend (set AWS_STORAGE_BUCKET_NAME, "
                        "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)."
                    )
                ),
            }
        )


class HsatChaptersView(APIView):
    """Per-book chapter list with display labels + status flags."""

    def get(self, request):
        grade = str(request.query_params.get("grade") or "").strip()
        subject = str(request.query_params.get("subject") or "").strip()
        book = str(request.query_params.get("book") or "").strip()
        validation = _validate_book(grade, subject, book)
        if validation is not None:
            return validation
        return Response(
            {
                "grade": grade,
                "subject": subject,
                "book": book,
                "chapters": book_chapters(grade, subject, book),
                **book_status(grade, subject, book),
            }
        )


class HsatSourceStatusView(APIView):
    """Readiness of one already-applied book, by HsatSource id.

    The picker no longer blocks on ingestion — it applies the book and
    closes — so something has to tell the Sources panel when the chapters
    have landed. Polling ``/api/hsat/catalog/`` for that walked every book
    in the catalog and ran a status query per book; this is the same answer
    in one row lookup, which is what a 5-second poll should cost.
    """

    def get(self, request, source_id: str):
        source = HsatSource.objects.filter(id=source_id).first()
        if source is None:
            return Response({"error": "Unknown HSAT source."}, status=404)
        return Response(
            {
                "hsat_source_id": source.id,
                "grade": source.grade,
                "subject": source.subject,
                "book": source.book,
                "status": source.status,
                "chunk_count": source.chunk_count,
                "error": source.error,
            }
        )


class HsatIngestView(APIView):
    """Trigger ingestion of a single HSAT book."""

    def post(self, request):
        if not s3_is_configured():
            return Response(
                {
                    "error": (
                        "HSAT ingestion is unavailable because AWS S3 is not "
                        "configured on the backend."
                    )
                },
                status=503,
            )

        grade = str(request.data.get("grade") or "").strip()
        subject = str(request.data.get("subject") or "").strip()
        book = str(request.data.get("book") or "").strip()
        force = bool(request.data.get("force"))
        chapter_keys_raw = request.data.get("chapter_keys")
        chapter_keys: List[str] = []
        if isinstance(chapter_keys_raw, list):
            chapter_keys = [str(k) for k in chapter_keys_raw if str(k).strip()]
        elif isinstance(chapter_keys_raw, str) and chapter_keys_raw.strip():
            chapter_keys = [chapter_keys_raw.strip()]

        validation = _validate_book(grade, subject, book)
        if validation is not None:
            return validation

        try:
            source = ingest_hsat_book_async(
                grade, subject, book,
                force=force,
                chapter_keys=chapter_keys or None,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            logger.exception("HSAT ingest trigger failed")
            return Response({"error": str(exc)}, status=500)

        return Response(
            {
                "hsat_source_id": source.id,
                "grade": source.grade,
                "subject": source.subject,
                "book": source.book,
                "status": source.status,
                "chunk_count": source.chunk_count,
                "chapters_requested": len(chapter_keys) if chapter_keys else None,
            }
        )


class HsatApplyView(APIView):
    """Apply a book to a paper's RAG context (triggering ingest if needed)."""

    def post(self, request):
        if not s3_is_configured():
            return Response(
                {
                    "error": (
                        "HSAT sources are unavailable because AWS S3 is not "
                        "configured on the backend."
                    )
                },
                status=503,
            )

        paper_id = str(request.data.get("paper_id") or "").strip()
        grade = str(request.data.get("grade") or "").strip()
        subject = str(request.data.get("subject") or "").strip()
        book = str(request.data.get("book") or "").strip()
        chapter_keys_raw = request.data.get("chapter_keys")
        chapter_keys: List[str] = []
        if isinstance(chapter_keys_raw, list):
            chapter_keys = [str(k) for k in chapter_keys_raw if str(k).strip()]

        if not paper_id:
            return Response({"error": "paper_id is required"}, status=400)

        validation = _validate_book(grade, subject, book)
        if validation is not None:
            return validation

        paper = get_object_or_404(Paper, id=paper_id, user=request.user)

        source = get_source(grade, subject, book)
        if source is None or source.status not in {"ready", "processing"}:
            source = ingest_hsat_book_async(
                grade, subject, book, chapter_keys=chapter_keys or None
            )

        PaperHsatSource.objects.get_or_create(paper=paper, hsat_source=source)

        return Response(
            {
                "paper_id": paper.id,
                "hsat_source_id": source.id,
                "grade": source.grade,
                "subject": source.subject,
                "book": source.book,
                "status": source.status,
                "chunk_count": source.chunk_count,
            }
        )

    def delete(self, request):
        """Remove a previously applied book from a paper."""
        paper_id = str(request.data.get("paper_id") or "").strip()
        hsat_source_id = str(request.data.get("hsat_source_id") or "").strip()
        if not paper_id or not hsat_source_id:
            return Response(
                {"error": "paper_id and hsat_source_id are required"},
                status=400,
            )
        paper = get_object_or_404(Paper, id=paper_id, user=request.user)
        deleted, _ = PaperHsatSource.objects.filter(
            paper=paper, hsat_source_id=hsat_source_id
        ).delete()
        return Response({"deleted": deleted})


class HsatPaperSourcesView(APIView):
    """List HSAT sources currently applied to a paper."""

    def get(self, request, paper_id: str):
        paper = get_object_or_404(Paper, id=paper_id, user=request.user)
        rows: List[Dict[str, Any]] = []
        links = (
            PaperHsatSource.objects.filter(paper=paper)
            .select_related("hsat_source")
            .order_by("created_at")
        )
        for link in links:
            source = link.hsat_source
            rows.append(
                {
                    "hsat_source_id": source.id,
                    "grade": source.grade,
                    "subject": source.subject,
                    "book": source.book,
                    "status": source.status,
                    "chunk_count": source.chunk_count,
                }
            )
        return Response({"paper_id": paper.id, "sources": rows})
