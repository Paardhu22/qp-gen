import logging
import hashlib
import os
import threading
from io import BytesIO
from typing import Dict, List, Optional

from apps.documents.models import DocumentChunk, HsatSource, PdfSource
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import close_old_connections, transaction
from docx import Document as DocxDocument

from services.chunking_service import chunk_text
from services.content_filters import strip_vi_blocks
from services.embedding_service import generate_embeddings
from services.ingest_concurrency import ingest_slot
from services.media_urls import stable_media_url
from services.pdf_service import extract_text_from_pdf
from services.semantic_pipeline import SemanticChunk, process_semantic_pipeline

logger = logging.getLogger("[DOCUMENT_SERVICE]")


def _compute_sha256(buffer: bytes) -> str:
    """Compute SHA256 hash of buffer content."""
    h = hashlib.sha256()
    h.update(buffer)
    return h.hexdigest()


def _scan_with_av(buffer: bytes, file_name: str) -> tuple[bool, Optional[str]]:
    """
    Scan buffer with antivirus if configured.
    Returns (is_safe, error_message) where is_safe=True means no threat detected.

    For now, this is a stub that always returns True (no AV configured by default).
    To enable, set CLAMAV_ENABLED=true and CLAMAV_HOST/CLAMAV_PORT in .env
    and integrate with clamd (pyclamd package).
    """
    av_enabled = os.environ.get("CLAMAV_ENABLED", "").lower() == "true"
    if not av_enabled:
        return True, None

    try:
        import pyclamd

        clam = pyclamd.ClamD(
            host=os.environ.get("CLAMAV_HOST", "localhost"),
            port=int(os.environ.get("CLAMAV_PORT", "3310")),
        )

        if not clam.ping():
            logger.warning("ClamAV unavailable; skipping virus scan")
            return True, None

        result = clam.scan_stream(buffer)
        if result:
            return False, f"Threat detected: {result}"
        return True, None

    except Exception as exc:
        logger.error("AV scan failed: %s", exc)
        # Fail open: if AV is configured but unavailable, allow upload
        # (set to False if you want to block uploads when AV is unavailable)
        return True, None


def _detect_and_store_subject(
    buffer: bytes, file_type: str, pdf_source: PdfSource
) -> None:
    """Record what subject this document looks like. Never fails an ingest.

    A wrong or missing answer here must cost the teacher nothing: the field is
    advisory, read only by the Sources panel to raise a dismissable warning
    when the chapter's subject disagrees with the paper's. So every failure
    path — no API key, no extractable text, a model timeout — leaves the
    columns null, which the UI reads as "no opinion".
    """
    if "pdf" not in (file_type or "").lower():
        # The detector reads pages out of a PDF; a DOCX/TXT upload has no
        # first pages to sample. Leaving it undetected is correct.
        return

    try:
        from services.subject_detection_service import detect_subject_from_pdf_buffer

        result = detect_subject_from_pdf_buffer(buffer)
    except Exception:
        logger.warning(
            "Subject detection raised for %s; continuing without it",
            pdf_source.id,
            exc_info=True,
        )
        return

    if not result.get("detected"):
        logger.debug(
            "No confident subject for %s: %s",
            pdf_source.id,
            result.get("error") or "low confidence",
        )
        return

    pdf_source.detected_subject = result.get("subject")
    pdf_source.subject_confidence = result.get("confidence")
    try:
        pdf_source.save(
            update_fields=["detected_subject", "subject_confidence", "updated_at"]
        )
    except Exception:
        logger.warning(
            "Could not persist detected subject for %s", pdf_source.id, exc_info=True
        )


def _process_pdf_internal(
    buffer: bytes, file_name: str, file_type: str, pdf_source: PdfSource, user
) -> None:
    """User-upload entry: process a PDF/DOCX/TXT into chunks under `pdf_source`."""
    # Classify before chunking, so the answer is on the row by the time the
    # status poll first reports "ready" and the Sources panel can warn in the
    # same tick it shows the upload as usable.
    _detect_and_store_subject(buffer, file_type, pdf_source)

    extract_and_persist_chunks(
        buffer=buffer,
        file_name=file_name,
        file_type=file_type,
        pdf_source=pdf_source,
        user=user,
        extra_metadata=None,
        mark_ready=True,
    )

    # Surface degradation warnings on the source (mirrors prior behaviour).
    warnings: List[str] = []
    pdf_metadata = getattr(pdf_source, "_pdf_metadata", {}) or {}
    if pdf_metadata.get("degraded"):
        reason = str(pdf_metadata.get("degradedReason") or "")
        if "pymupdf_not_installed" in reason:
            warnings.append(
                "PyMuPDF is not installed on the server. Falling back to text-only "
                "extraction — image extraction and figure captioning are disabled, "
                "which can reduce question-paper coverage. Install 'PyMuPDF>=1.24' "
                "on the backend to enable full extraction."
            )
        else:
            warnings.append(
                "PDF extraction degraded to text-only mode (no image extraction). "
                f"Reason: {reason or 'unknown'}."
            )
    pdf_source.warnings = warnings  # type: ignore[attr-defined]


def extract_and_persist_chunks(
    *,
    buffer: bytes,
    file_name: str,
    file_type: str,
    pdf_source: Optional[PdfSource] = None,
    hsat_source: Optional[HsatSource] = None,
    extra_metadata: Optional[Dict[str, object]] = None,
    user=None,
    mark_ready: bool = False,
) -> Dict[str, object]:
    """
    Polymorphic chunk pipeline shared by user-PDF and HSAT ingestion.

    Exactly one of ``pdf_source`` or ``hsat_source`` must be supplied —
    every persisted chunk gets that FK so the retrieval layer can filter
    by either source kind without changing chunk storage.

    Returns a small stats dict: {"text_chunks", "image_chunks", "metadata"}.
    """
    if (pdf_source is None) == (hsat_source is None):
        raise ValueError(
            "extract_and_persist_chunks needs exactly one of pdf_source / hsat_source"
        )

    extracted_text = ""
    pages = []
    images = []
    pdf_metadata: Dict[str, object] = {}

    if file_type == "application/pdf":
        pdf_data = extract_text_from_pdf(buffer)
        extracted_text = pdf_data.get("text", "")
        pages = pdf_data.get("pages", [])
        images = pdf_data.get("images", [])
        pdf_metadata = pdf_data.get("metadata") or {}
    elif (
        file_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        extracted_text = _extract_text_from_docx(buffer)
    else:
        extracted_text = buffer.decode("utf-8", errors="ignore")

    # Round-4: CBSE sample papers / HSAT books embed "Visually Impaired
    # Students only" alternate blocks. If those survive into chunks, the
    # retrieval context hands them to the LLM and they leak into standard
    # papers (s3b Q31/Q37). Strip them at the source so no chunk ever
    # stores one. (Generation-side scrubbing exists too, as defence for
    # chunks ingested before this fix.)
    extracted_text = strip_vi_blocks(extracted_text)
    if pages:
        pages = [
            {**page, "content": strip_vi_blocks(str(page.get("content") or ""))}
            for page in pages
        ]

    if not extracted_text.strip() and not images:
        raise ValueError("Failed to extract text from document")

    if pages:
        chunks = process_semantic_pipeline(pages)
        if not chunks and extracted_text.strip():
            # Degenerate structure (no headings/sections the semantic pass
            # can use) must not fail an ingest that plain chunking can
            # serve — the raw text is right there.
            chunks = chunk_text(extracted_text)
    else:
        chunks = chunk_text(extracted_text)

    text_chunk_count = len(chunks)

    # Figure chunks cost one S3 PUT each, up to PDF_IMAGE_MAX_CAPTIONS per
    # chapter, and they are the reason "apply this source" felt like an
    # upload rather than a selection. Nothing in the paper pipeline reads
    # them (see INGEST_EXTRACT_FIGURES), so by default we skip them —
    # unless the document has no extractable text at all, in which case the
    # figures ARE the document and dropping them would turn a scanned
    # chapter into a failed ingest.
    text_only = not extracted_text.strip()
    if getattr(settings, "INGEST_EXTRACT_FIGURES", False) or text_only:
        image_chunks = _build_image_chunks(
            pdf_source=pdf_source,
            hsat_source=hsat_source,
            file_name=file_name,
            images=images,
            pages=pages,
            start_index=len(chunks),
            user=user,
        )
    else:
        image_chunks = []
        if images:
            logger.debug(
                "Skipping %d figure(s) in %s — INGEST_EXTRACT_FIGURES is off.",
                len(images),
                file_name,
            )
    chunks.extend(image_chunks)

    if not chunks:
        raise ValueError("No searchable text or visual chunks could be extracted")

    metadata_overlay = {"sourcePdf": file_name, **(extra_metadata or {})}

    # Live chunk-count progress: after every batch we atomically bump the
    # parent's chunk_count via F('chunk_count') + N so the status endpoint
    # reflects real progress while a long book is still ingesting. Without
    # this, the user sees "0 chunks" for several minutes even though
    # DocumentChunk rows are being written.
    from django.db.models import F  # local import — avoids circular at top

    batch_size = int(getattr(settings, "INGEST_EMBED_BATCH_SIZE", 256))
    embed = bool(getattr(settings, "INGEST_EMBEDDINGS_ENABLED", True))
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        if embed:
            embeddings = generate_embeddings(
                [chunk.content for chunk in batch], user=user
            )
        else:
            embeddings = [None] * len(batch)

        DocumentChunk.objects.bulk_create(
            [
                DocumentChunk(
                    content=chunk.content,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    embedding=embedding,
                    pdf_source=pdf_source,
                    hsat_source=hsat_source,
                    metadata={
                        **(getattr(chunk, "metadata", {}) or {}),
                        **metadata_overlay,
                    },
                )
                for chunk, embedding in zip(batch, embeddings)
            ]
        )

        if hsat_source is not None:
            HsatSource.objects.filter(pk=hsat_source.pk).update(
                chunk_count=F("chunk_count") + len(batch),
            )

    if mark_ready and pdf_source is not None:
        pdf_source.status = "ready"
        pdf_source.save(update_fields=["status", "updated_at"])
        # Stash the extraction metadata so the upload entry point can build
        # user-visible degradation warnings without re-extracting.
        pdf_source._pdf_metadata = pdf_metadata  # type: ignore[attr-defined]

    return {
        "text_chunks": text_chunk_count,
        "image_chunks": len(image_chunks),
        "total_chunks": len(chunks),
        "metadata": pdf_metadata,
    }


def _extract_text_from_docx(buffer: bytes) -> str:
    doc = DocxDocument(BytesIO(buffer))
    return "\n".join(p.text for p in doc.paragraphs)


def _public_media_url(stored_path: str) -> str:
    # NEVER return default_storage.url() here: with S3 storage that is a
    # presigned URL (X-Amz-Expires=3600) and this value gets PERSISTED in
    # chunk metadata / PdfSource.url. By generation time the signature is
    # stale and OpenAI rejects the download with `invalid_image_url`.
    # We persist only the stable /media/<key> URL; apps.common.views
    # .serve_media redirects it to a freshly signed URL on every request.
    return stable_media_url(stored_path)


def _normalise_image_extension(extension: str) -> str:
    extension = (extension or "png").lower().lstrip(".")
    if extension == "jpeg":
        return "jpg"
    if extension not in {"png", "jpg", "webp", "gif"}:
        return "png"
    return extension


def _store_extracted_image(
    image: Dict[str, object],
    *,
    pdf_source: Optional[PdfSource] = None,
    hsat_source: Optional[HsatSource] = None,
) -> tuple[str, str]:
    extension = _normalise_image_extension(str(image.get("extension") or "png"))
    page_number = int(image.get("pageNumber") or 0)
    image_index = int(image.get("imageIndex") or 0)
    if pdf_source is not None:
        prefix = f"pdf_images/{pdf_source.id}"
    elif hsat_source is not None:
        # HSAT images live in a dedicated prefix so they're easy to inspect
        # without colliding with per-user PdfSource ids. The s3_key from
        # extra_metadata is not part of the prefix because we don't want odd
        # characters / accents in storage paths.
        prefix = f"hsat_images/{hsat_source.id}"
    else:
        raise ValueError("_store_extracted_image needs pdf_source or hsat_source")
    stored_path = default_storage.save(
        f"{prefix}/page-{page_number}-image-{image_index}.{extension}",
        ContentFile(image.get("bytes") or b""),
    )
    return _public_media_url(stored_path), stored_path


def _is_usable_image(image: Dict[str, object]) -> bool:
    image_bytes = image.get("bytes") or b""
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    min_bytes = getattr(settings, "PDF_IMAGE_MIN_BYTES", 8192)
    min_dimension = getattr(settings, "PDF_IMAGE_MIN_DIMENSION", 96)
    if len(image_bytes) < min_bytes:
        return False
    if width and height and (width < min_dimension or height < min_dimension):
        return False
    return True


def _build_image_chunks(
    *,
    pdf_source: Optional[PdfSource] = None,
    hsat_source: Optional[HsatSource] = None,
    file_name: str,
    images: List[Dict[str, object]],
    pages: List[dict],
    start_index: int,
    user,
) -> List[SemanticChunk]:
    page_text = {page.get("pageNumber"): str(page.get("content") or "") for page in pages}
    image_limit = getattr(settings, "PDF_IMAGE_MAX_CAPTIONS", 40)
    usable_images = [image for image in images if _is_usable_image(image)][:image_limit]
    if not usable_images:
        return []

    # STEP 7 — NO GPT CALLS DURING INGESTION.
    # Figures are still extracted and stored (the diagram-question stage runs
    # later, post-pool), but they are NOT captioned by a vision model. Vision
    # captioning was the only OpenAI call in ingestion and dominated its
    # latency (~11 s/image); removing it makes ingestion pure extraction →
    # chunk → embed → store. Each figure carries the surrounding textbook prose
    # as its retrieval context instead of an AI caption.
    logger.debug(
        "Extracting %d figure(s) from %s (ingestion is GPT-free — no captioning)",
        len(usable_images),
        file_name,
    )

    chunks: List[SemanticChunk] = []
    for offset, image in enumerate(usable_images):
        page_number = int(image.get("pageNumber") or 0)
        image_url, image_storage_path = _store_extracted_image(
            image, pdf_source=pdf_source, hsat_source=hsat_source
        )
        nearby_text = page_text.get(page_number, "")
        # No vision caption; retrieval leans on the nearby prose.
        caption = ""

        content = (
            "# Visual Source\n"
            f"Page: {page_number}\n"
            f"Nearby textbook text: {nearby_text[:900]}"
        ).strip()

        chunks.append(
            SemanticChunk(
                content=content,
                page=page_number,
                chunk_index=start_index + offset,
                metadata={
                    "chunkType": "image",
                    "chapter": "Visual Source",
                    "heading": f"Page {page_number} image",
                    "semanticSection": f"Visual Source - Page {page_number}",
                    "sourcePdf": file_name,
                    "image_url": image_url,
                    "image_storage_path": image_storage_path,
                    "mimeType": image.get("mimeType"),
                    "image_caption": caption,
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "requiresVision": True,
                },
            )
        )

    return chunks


def _spawn_pdf_worker(
    buffer: bytes, file_name: str, file_type: str, pdf_source: PdfSource, user
) -> None:
    """Run the heavy ingest (extract → caption → embed → write) off-request.

    Mirrors ``hsat_service.ingest_hsat_book_async``: a daemon thread against the
    Django ORM, guaranteeing the row never stays stuck in "processing" if the
    worker crashes. The PdfSource row must already be COMMITTED before this is
    called so the thread's own DB connection can see it.
    """
    source_id = pdf_source.id

    def _worker() -> None:
        try:
            # Bounded, and acquired HERE rather than around thread creation:
            # blocking the request thread would defeat the point of ingesting
            # in the background. Uploading fifteen chapters at once used to
            # start fifteen of these, which oversubscribes the write lock and
            # the embeddings quota simultaneously.
            with ingest_slot(f"pdf-{source_id}"):
                # Re-fetch inside the worker's connection so we mutate a row
                # this thread owns, not the parent request's (soon-closed)
                # instance. Done after the wait, so a queued job picks up the
                # row as it is when it actually starts.
                src = PdfSource.objects.get(id=source_id)
                _process_pdf_internal(buffer, file_name, file_type, src, user)
                warnings = getattr(src, "warnings", []) or []
                if warnings:
                    logger.info("PDF %s ingested with warnings: %s", source_id, warnings)
        except Exception as exc:
            logger.exception("Background PDF ingest failed for %s", source_id)
            try:
                PdfSource.objects.filter(id=source_id).update(
                    status="error", error=f"{type(exc).__name__}: {exc}"
                )
            except Exception:
                logger.exception("Could not write error status after PDF worker crash")
        finally:
            close_old_connections()

    thread = threading.Thread(target=_worker, name=f"pdf-ingest-{source_id}", daemon=True)
    thread.start()


def process_pdf_upload(file, user, *, background: bool = False) -> PdfSource:
    """
    Upload and process a PDF/DOCX/TXT file into a PdfSource.

    This creates a PdfSource with its DocumentChunks and embeddings so that
    questions can later be generated from it via semantic retrieval.

    PdfSource is a temporary generation context — it is NOT automatically
    linked to the Question Bank or any Paper. Questions become persistent only
    when the user explicitly saves them.

    ``background=False`` (default, used by tests) runs the whole ingest inside
    the call and returns a *ready* source. ``background=True`` (used by the
    upload API) returns immediately with a *processing* source and runs the
    heavy stages on a daemon thread; the client polls the status endpoint until
    ``ready``/``error``. Either way `.warnings` carries user-visible degradation
    notices (only populated on the synchronous path).
    """
    file_type = file.content_type or "application/pdf"
    file_name = file.name
    buffer = file.read()

    # Compute SHA256 for deduplication
    sha256_hash = _compute_sha256(buffer)

    # Check for duplicate (same hash, same user, ready status)
    existing = PdfSource.objects.filter(
        user=user, sha256=sha256_hash, status="ready"
    ).first()
    if existing:
        logger.debug("Duplicate PDF detected: reusing %s", existing.id)
        existing.warnings = []  # type: ignore[attr-defined]
        return existing

    # Scan with AV if configured
    is_safe, av_error = _scan_with_av(buffer, file_name)
    if not is_safe:
        raise ValueError(f"Upload blocked: {av_error}")

    if background:
        # Fast path: create + persist the raw file, COMMIT, then hand the heavy
        # ingest to a worker thread. The short atomic block ensures the row is
        # committed (visible to the worker's connection) before the thread runs.
        with transaction.atomic():
            pdf_source = PdfSource.objects.create(
                name=file_name,
                size=len(buffer),
                content_type=file_type,
                status="processing",
                user=user,
                sha256=sha256_hash,
                av_status="passed" if not getattr(settings, "CLAMAV_ENABLED", False) else "pending",
            )
            try:
                stored_path = default_storage.save(
                    f"uploads/{user.id}/pdfs/{pdf_source.id}/{file_name}", ContentFile(buffer)
                )
                pdf_source.url = _public_media_url(stored_path)
                pdf_source.save(update_fields=["url"])
            except Exception:
                logger.exception("Failed to save original PDF to storage for %s", pdf_source.id)

        _spawn_pdf_worker(buffer, file_name, file_type, pdf_source, user)
        pdf_source.warnings = []  # type: ignore[attr-defined]
        return pdf_source

    with transaction.atomic():
        pdf_source = PdfSource.objects.create(
            name=file_name,
            size=len(buffer),
            content_type=file_type,
            status="processing",
            user=user,
            sha256=sha256_hash,
            av_status="passed" if not getattr(settings, "CLAMAV_ENABLED", False) else "pending",
        )

        # Save the original uploaded file to the configured storage backend
        try:
            stored_path = default_storage.save(
                f"uploads/{user.id}/pdfs/{pdf_source.id}/{file_name}", ContentFile(buffer)
            )
            # Store a public-facing URL when available (e.g. S3 presigned URL or CDN base)
            pdf_source.url = _public_media_url(stored_path)
            pdf_source.save(update_fields=["url"])
        except Exception:
            # Non-fatal: if storing the raw PDF fails, continue processing
            logger.exception("Failed to save original PDF to storage for %s", pdf_source.id)

        try:
            _process_pdf_internal(buffer, file_name, file_type, pdf_source, user)
        except Exception as exc:
            pdf_source.status = "error"
            pdf_source.error = str(exc)
            pdf_source.save(update_fields=["status", "error", "updated_at"])
            raise

    return pdf_source


def process_pdf_from_storage(key: str, user, name: str, content_type: str) -> PdfSource:
    """
    Process a PDF already stored in S3/MinIO (presigned upload flow).

    Reads the file from storage, computes SHA256, checks for duplicates,
    and triggers normal processing without re-saving the file to storage.

    This avoids the double-save that would occur if we downloaded from
    storage and re-uploaded it.

    Args:
        key: storage key (e.g. 'uploads/user-id/uuid_filename.pdf')
        user: the requesting user
        name: friendly file name for display
        content_type: MIME type
    """
    # Read from storage
    if not default_storage.exists(key):
        raise ValueError(f"Object not found in storage: {key}")

    with default_storage.open(key, "rb") as f:
        buffer = f.read()

    # Compute SHA256 for deduplication
    sha256_hash = _compute_sha256(buffer)

    # Check for duplicate (same hash, same user, ready status)
    existing = PdfSource.objects.filter(
        user=user, sha256=sha256_hash, status="ready"
    ).first()
    if existing:
        logger.debug("Duplicate PDF detected (from storage): reusing %s", existing.id)
        existing.warnings = []  # type: ignore[attr-defined]
        return existing

    # Scan with AV if configured
    is_safe, av_error = _scan_with_av(buffer, name)
    if not is_safe:
        raise ValueError(f"Upload blocked: {av_error}")

    with transaction.atomic():
        pdf_source = PdfSource.objects.create(
            name=name,
            size=len(buffer),
            content_type=content_type,
            status="processing",
            user=user,
            sha256=sha256_hash,
            av_status="passed" if not getattr(settings, "CLAMAV_ENABLED", False) else "pending",
        )

        # Store the URL pointing to the already-uploaded object
        try:
            pdf_source.url = _public_media_url(key)
            pdf_source.save(update_fields=["url"])
        except Exception:
            logger.exception("Failed to set URL for %s", pdf_source.id)

        try:
            _process_pdf_internal(buffer, name, content_type, pdf_source, user)
        except Exception as exc:
            pdf_source.status = "error"
            pdf_source.error = str(exc)
            pdf_source.save(update_fields=["status", "error", "updated_at"])
            raise

    return pdf_source
