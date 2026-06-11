import base64
import logging
import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Dict, List, Optional

from apps.documents.models import DocumentChunk, HsatSource, PdfSource
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from docx import Document as DocxDocument

from services.chunking_service import chunk_text
from services.embedding_service import generate_embeddings
from services.media_urls import stable_media_url
from services.openai_service import caption_image_for_embedding
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


def _process_pdf_internal(
    buffer: bytes, file_name: str, file_type: str, pdf_source: PdfSource, user
) -> None:
    """User-upload entry: process a PDF/DOCX/TXT into chunks under `pdf_source`."""
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

    image_chunks = _build_image_chunks(
        pdf_source=pdf_source,
        hsat_source=hsat_source,
        file_name=file_name,
        images=images,
        pages=pages,
        start_index=len(chunks),
        user=user,
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

    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        embeddings = generate_embeddings(
            [chunk.content for chunk in batch], user=user
        )

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


def _image_data_url(image: Dict[str, object]) -> str:
    extension = _normalise_image_extension(str(image.get("extension") or "png"))
    mime_type = str(image.get("mimeType") or f"image/{'jpeg' if extension == 'jpg' else extension}")
    payload = base64.b64encode(image.get("bytes") or b"").decode("ascii")
    return f"data:{mime_type};base64,{payload}"


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


def _caption_one_image(
    image: Dict[str, object], page_text: str, file_name: str, user
) -> tuple[str, bool]:
    """Caption a single image; tolerate API failures by falling back to a
    page-context summary so a partial vision outage never breaks ingestion.
    Returns (caption, succeeded) so the caller can report failure counts."""
    page_number = int(image.get("pageNumber") or 0)
    try:
        caption = caption_image_for_embedding(
            _image_data_url(image),
            page_context=page_text,
            user=user,
        )
        return caption, True
    except Exception as exc:
        logger.warning(
            "Image captioning failed for %s page %s: %s",
            file_name,
            page_number,
            exc,
        )
        return (
            f"Textbook visual from page {page_number}. Nearby text: {page_text[:500]}",
            False,
        )


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
    caption_limit = getattr(settings, "PDF_IMAGE_MAX_CAPTIONS", 40)
    usable_images = [image for image in images if _is_usable_image(image)][:caption_limit]
    if not usable_images:
        return []

    # Vision-API calls dominate ingestion latency. Profile against
    # trignometry.pdf showed ~11 s per call × 22 images ≈ 4 min serial.
    # Running the captioning loop on a ThreadPoolExecutor (I/O-bound,
    # GIL-friendly) cuts wall-clock to ceil(N / concurrency) × per-call ms.
    # The pool size here only bounds threads for THIS file — actual
    # vision-API concurrency is capped process-wide by the semaphore in
    # services.openai_service so parallel chapters can't multiply it.
    # See settings.PDF_IMAGE_CAPTION_CONCURRENCY for the knob.
    concurrency = max(
        1, int(getattr(settings, "PDF_IMAGE_CAPTION_CONCURRENCY", 3))
    )
    captions: List[str] = [""] * len(usable_images)

    # Per-chapter progress counters: the teacher-facing ingest log should
    # show steady forward motion, not just a wall of retry warnings.
    total_queued = len(usable_images)
    progress_lock = threading.Lock()
    done_count = 0
    failed_count = 0

    logger.info(
        "Captioning chapter %s: %d images queued, 0 done, 0 failed",
        file_name,
        total_queued,
    )

    def caption_at(index: int) -> None:
        nonlocal done_count, failed_count
        image = usable_images[index]
        nearby_text = page_text.get(int(image.get("pageNumber") or 0), "")
        caption, succeeded = _caption_one_image(image, nearby_text, file_name, user)
        captions[index] = caption
        with progress_lock:
            done_count += 1
            if not succeeded:
                failed_count += 1
            logger.info(
                "Captioning chapter %s: %d images queued, %d done, %d failed",
                file_name,
                total_queued,
                done_count,
                failed_count,
            )

    if concurrency == 1 or len(usable_images) == 1:
        for index in range(len(usable_images)):
            caption_at(index)
    else:
        with ThreadPoolExecutor(
            max_workers=min(concurrency, len(usable_images))
        ) as executor:
            list(executor.map(caption_at, range(len(usable_images))))

    chunks: List[SemanticChunk] = []
    for offset, image in enumerate(usable_images):
        page_number = int(image.get("pageNumber") or 0)
        image_url, image_storage_path = _store_extracted_image(
            image, pdf_source=pdf_source, hsat_source=hsat_source
        )
        nearby_text = page_text.get(page_number, "")
        caption = captions[offset]

        content = (
            "# Visual Source\n"
            f"Page: {page_number}\n"
            f"Hidden caption: {caption}\n"
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


def process_pdf_upload(file, user) -> PdfSource:
    """
    Upload and process a PDF/DOCX/TXT file into a PdfSource.

    This creates a PdfSource with its DocumentChunks and embeddings so that
    questions can later be generated from it via semantic retrieval.

    PdfSource is a temporary generation context — it is NOT automatically
    linked to the Question Bank or any Paper. Questions become persistent only
    when the user explicitly saves them.

    Returns the PdfSource; non-persistent `.warnings` attribute carries
    user-visible degradation notices (e.g. PyMuPDF unavailable → image
    extraction off) that the API layer should surface.
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
        logger.info("Duplicate PDF detected: reusing %s", existing.id)
        existing.warnings = []  # type: ignore[attr-defined]
        return existing

    # Scan with AV if configured
    is_safe, av_error = _scan_with_av(buffer, file_name)
    if not is_safe:
        raise ValueError(f"Upload blocked: {av_error}")

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
        logger.info("Duplicate PDF detected (from storage): reusing %s", existing.id)
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
