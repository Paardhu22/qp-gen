import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Dict, List

from apps.documents.models import DocumentChunk, PdfSource
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from docx import Document as DocxDocument

from services.chunking_service import chunk_text
from services.embedding_service import generate_embeddings
from services.openai_service import caption_image_for_embedding
from services.pdf_service import extract_text_from_pdf
from services.semantic_pipeline import SemanticChunk, process_semantic_pipeline

logger = logging.getLogger("[DOCUMENT_SERVICE]")


def _extract_text_from_docx(buffer: bytes) -> str:
    doc = DocxDocument(BytesIO(buffer))
    return "\n".join(p.text for p in doc.paragraphs)


def _public_media_url(stored_path: str) -> str:
    media_url = default_storage.url(stored_path)
    public_base = getattr(settings, "AOS_PUBLIC_MEDIA_BASE_URL", "")
    if public_base:
        return f"{public_base}{media_url if media_url.startswith('/') else '/' + media_url}"
    return media_url


def _normalise_image_extension(extension: str) -> str:
    extension = (extension or "png").lower().lstrip(".")
    if extension == "jpeg":
        return "jpg"
    if extension not in {"png", "jpg", "webp", "gif"}:
        return "png"
    return extension


def _store_extracted_image(pdf_source: PdfSource, image: Dict[str, object]) -> tuple[str, str]:
    extension = _normalise_image_extension(str(image.get("extension") or "png"))
    page_number = int(image.get("pageNumber") or 0)
    image_index = int(image.get("imageIndex") or 0)
    stored_path = default_storage.save(
        f"pdf_images/{pdf_source.id}/page-{page_number}-image-{image_index}.{extension}",
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
) -> str:
    """Caption a single image; tolerate API failures by falling back to a
    page-context summary so a partial vision outage never breaks ingestion."""
    page_number = int(image.get("pageNumber") or 0)
    try:
        return caption_image_for_embedding(
            _image_data_url(image),
            page_context=page_text,
            user=user,
        )
    except Exception as exc:
        logger.warning(
            "Image captioning failed for %s page %s: %s",
            file_name,
            page_number,
            exc,
        )
        return f"Textbook visual from page {page_number}. Nearby text: {page_text[:500]}"


def _build_image_chunks(
    *,
    pdf_source: PdfSource,
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
    # See settings.PDF_IMAGE_CAPTION_CONCURRENCY for the knob.
    concurrency = max(
        1, int(getattr(settings, "PDF_IMAGE_CAPTION_CONCURRENCY", 8))
    )
    captions: List[str] = [""] * len(usable_images)

    def caption_at(index: int) -> None:
        image = usable_images[index]
        nearby_text = page_text.get(int(image.get("pageNumber") or 0), "")
        captions[index] = _caption_one_image(image, nearby_text, file_name, user)

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
        image_url, image_storage_path = _store_extracted_image(pdf_source, image)
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


def process_pdf_upload(file, user) -> PdfSource:  # noqa: C901
    """Returns the PdfSource; non-persistent `.warnings` attribute carries
    user-visible degradation notices (e.g. PyMuPDF unavailable → image
    extraction off) that the API layer should surface.
    """
    """
    Upload and process a PDF/DOCX/TXT file into a PdfSource.

    This creates a PdfSource with its DocumentChunks and embeddings so that
    questions can later be generated from it via semantic retrieval.

    PdfSource is a temporary generation context — it is NOT automatically
    linked to the Question Bank or any Paper. Questions become persistent only
    when the user explicitly saves them.
    """
    # PDF is the dominant upload path; DocumentUploadSerializer accepts other
    # file types but downstream extraction routes on the MIME type, so default
    # to application/pdf when the client (or the test framework) omits the
    # Content-Type header. This default also satisfies the NOT NULL constraint
    # on the legacy `content_type` column (see migration 0004).
    file_type = file.content_type or "application/pdf"
    file_name = file.name
    buffer = file.read()

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

    with transaction.atomic():
        pdf_source = PdfSource.objects.create(
            name=file_name,
            size=len(buffer),
            content_type=file_type,
            status="processing",
            user=user,
        )

        try:
            if pages:
                chunks = process_semantic_pipeline(pages)
            else:
                chunks = chunk_text(extracted_text)

            image_chunks = _build_image_chunks(
                pdf_source=pdf_source,
                file_name=file_name,
                images=images,
                pages=pages,
                start_index=len(chunks),
                user=user,
            )
            chunks.extend(image_chunks)

            if not chunks:
                raise ValueError("No searchable text or visual chunks could be extracted")

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
                            metadata={
                                **(getattr(chunk, "metadata", {}) or {}),
                                "sourcePdf": file_name,
                            },
                        )
                        for chunk, embedding in zip(batch, embeddings)
                    ]
                )

            pdf_source.status = "ready"
            pdf_source.save(update_fields=["status", "updated_at"])

        except Exception as exc:
            pdf_source.status = "error"
            pdf_source.error = str(exc)
            pdf_source.save(update_fields=["status", "error", "updated_at"])
            raise

    warnings: List[str] = []
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
    return pdf_source
