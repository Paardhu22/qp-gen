"""Vision OCR for PDFs that carry no usable text layer.

Why this exists
---------------
Phone-scanned chapters (MLKit, CamScanner, Adobe Scan) are a stack of JPEGs
with an empty text layer. ``pdf_service.extract_text_from_pdf`` returns ``""``
for them, and before this module nothing downstream treated that as a failure:
ingestion fell through to its figure-only branch, stored N uncaptioned image
chunks, and ``chapter_markdown`` handed the generator a chapter whose entire
body was

    ## Figures in this chapter
    - **Figure 1** — page 1: (uncaptioned figure)
    ...

The generator then wrote the only questions that inventory can answer —
"Which figure is on page 7?", "How many figures are mentioned in the chapter?"
— and the teacher got a paper about page numbering instead of about Factors
and Multiples. OCR closes that hole at the source; ``has_usable_text`` is the
backstop for when OCR itself comes up empty.

Cost note: OCR only ever runs on pages whose own text layer is thin, so a
normal digital PDF costs nothing and ingestion stays GPT-free for it.
"""
from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Sequence, Tuple

from django.conf import settings

from services.openai_service import ocr_page_image
from services.pdf_service import _import_pymupdf

logger = logging.getLogger("[OCR_SERVICE]")

#: A page with fewer than this many characters of extracted text is treated as
#: un-extracted. Real textbook pages run to thousands; a scanned page yields 0
#: and a stray header/footer artefact a couple of dozen.
DEFAULT_MIN_PAGE_CHARS = 80

#: Whole-document gate. A chapter averaging less than this per page has not
#: been read, whatever the per-page numbers say.
DEFAULT_MIN_DOC_CHARS_PER_PAGE = 120


def _setting(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def page_needs_ocr(text: str) -> bool:
    """True when this page's text layer is too thin to be the real page."""
    return len((text or "").strip()) < _setting(
        "PDF_OCR_MIN_PAGE_CHARS", DEFAULT_MIN_PAGE_CHARS
    )


def has_usable_text(text: str, page_count: int) -> bool:
    """The hard gate: does this document carry enough text to build a paper?

    Scale-aware rather than a flat floor — 400 characters is a plausible
    one-page worksheet and an obviously failed 20-page chapter.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    if page_count <= 0:
        return len(stripped) >= DEFAULT_MIN_PAGE_CHARS
    per_page = _setting("PDF_MIN_DOC_CHARS_PER_PAGE", DEFAULT_MIN_DOC_CHARS_PER_PAGE)
    return len(stripped) >= per_page * page_count


def _render_page_jpeg(page, *, max_px: int) -> Optional[bytes]:
    """Render one page to JPEG bytes, capped at ``max_px`` on the long edge.

    The cap is about tokens, not disk: ``detail: "high"`` tiles the image at
    512px, so an uncapped 3400px scan costs several times what it needs to
    for text that is already legible at ~1800px.
    """
    fitz = _import_pymupdf()
    rect = page.rect
    longest = max(rect.width, rect.height) or 1.0
    # 72dpi is the PDF unit; scale up for legibility, but never past the cap.
    zoom = min(max_px / longest, 4.0)
    if zoom <= 0:
        return None
    matrix = fitz.Matrix(zoom, zoom)
    # alpha=False — JPEG has no alpha channel and PyMuPDF refuses the encode.
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    try:
        return pixmap.tobytes("jpeg", jpg_quality=80)
    except Exception:
        # Older PyMuPDF builds ship without the JPEG encoder.
        return pixmap.tobytes("png")


def _data_url(image_bytes: bytes) -> str:
    kind = "jpeg" if image_bytes[:2] == b"\xff\xd8" else "png"
    return f"data:image/{kind};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def ocr_pdf_pages(
    buffer: bytes,
    pages: Sequence[Dict[str, object]],
    *,
    user=None,
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    """OCR every page in ``pages`` whose text layer is thin.

    Returns ``(pages, stats)`` with OCR'd text merged into each page's
    ``content``. Pages that already have text are returned untouched, and a
    page whose OCR call fails keeps whatever it had — one unreadable page must
    not sink an otherwise fine chapter.
    """
    result = [dict(page) for page in pages]
    stats: Dict[str, object] = {"attempted": 0, "succeeded": 0, "failed": 0}

    if not getattr(settings, "PDF_OCR_ENABLED", True):
        stats["skipped"] = "disabled"
        return result, stats

    targets = [
        index
        for index, page in enumerate(result)
        if page_needs_ocr(str(page.get("content") or ""))
    ]
    if not targets:
        return result, stats

    max_pages = _setting("PDF_OCR_MAX_PAGES", 60)
    if len(targets) > max_pages:
        logger.warning(
            "OCR capped at %d of %d image-only pages; the rest stay empty.",
            max_pages,
            len(targets),
        )
        targets = targets[:max_pages]

    max_px = _setting("PDF_OCR_MAX_PIXELS", 1800)
    try:
        fitz = _import_pymupdf()
        doc = fitz.open(stream=buffer, filetype="pdf")
    except Exception as exc:
        logger.error("OCR could not open the PDF: %s", exc)
        stats["failed"] = len(targets)
        return result, stats

    # Rendering is CPU-bound and happens up front, single-threaded: it is fast
    # (~50ms/page) and keeps peak memory to one pixmap instead of one per
    # worker for a 60-page scan.
    renders: List[Tuple[int, str]] = []
    try:
        for index in targets:
            page_number = int(result[index].get("pageNumber") or (index + 1))
            try:
                image_bytes = _render_page_jpeg(
                    doc.load_page(page_number - 1), max_px=max_px
                )
            except Exception as exc:
                logger.warning("Could not render page %d for OCR: %s", page_number, exc)
                continue
            if image_bytes:
                renders.append((index, _data_url(image_bytes)))
    finally:
        doc.close()

    stats["attempted"] = len(renders)
    if not renders:
        return result, stats

    logger.info("OCR: transcribing %d image-only page(s).", len(renders))

    workers = max(1, _setting("PDF_OCR_CONCURRENCY", 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(ocr_page_image, data_url, user=user): index
            for index, data_url in renders
        }
        for future in as_completed(futures):
            index = futures[future]
            page_number = result[index].get("pageNumber")
            try:
                text = (future.result() or "").strip()
            except Exception as exc:
                stats["failed"] = int(stats["failed"]) + 1
                logger.warning("OCR failed on page %s: %s", page_number, exc)
                continue
            if not text:
                stats["failed"] = int(stats["failed"]) + 1
                logger.info("OCR returned nothing for page %s.", page_number)
                continue
            result[index]["content"] = text
            result[index]["ocr"] = True
            stats["succeeded"] = int(stats["succeeded"]) + 1

    logger.info(
        "OCR complete: %s/%s page(s) transcribed.",
        stats["succeeded"],
        stats["attempted"],
    )
    return result, stats
