import logging
from io import BytesIO
from typing import Dict, List

from pypdf import PdfReader

logger = logging.getLogger("[PDF_SERVICE]")


def _import_pymupdf():
    """Return the PyMuPDF module under whichever name is available.

    Newer PyMuPDF (>=1.24) exposes `pymupdf`; older releases expose `fitz`.
    Recent versions ship both; very recent wheels may ship only `pymupdf`.
    """
    try:
        import pymupdf  # type: ignore
        return pymupdf
    except ImportError:
        import fitz  # type: ignore
        return fitz


def extract_text_from_pdf(buffer: bytes) -> Dict[str, object]:
    try:
        fitz = _import_pymupdf()
    except ImportError as exc:
        logger.error(
            "PyMuPDF is not installed; falling back to pypdf text-only parser. "
            "Image extraction and richer text layout will be unavailable. "
            "Install with: pip install 'PyMuPDF>=1.24,<1.27'. Reason: %s",
            exc,
        )
        return _extract_with_pypdf(
            buffer,
            degraded_reason="pymupdf_not_installed",
        )

    try:
        doc = fitz.open(stream=buffer, filetype="pdf")
        pages: List[Dict[str, object]] = []
        text_chunks: List[str] = []
        images: List[Dict[str, object]] = []
        seen_xrefs: set[int] = set()

        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            page_number = page_index + 1
            page_text = page.get_text("text") or ""
            text_chunks.append(page_text)
            pages.append({"pageNumber": page_number, "content": page_text})

            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                xref = int(image_info[0])
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    extracted = doc.extract_image(xref)
                except Exception as exc:
                    logger.debug("Skipping unreadable PDF image xref=%s: %s", xref, exc)
                    continue

                image_bytes = extracted.get("image") or b""
                if not image_bytes:
                    continue

                extension = str(extracted.get("ext") or "png").lower().lstrip(".")
                images.append(
                    {
                        "pageNumber": page_number,
                        "imageIndex": image_index,
                        "xref": xref,
                        "bytes": image_bytes,
                        "extension": extension,
                        "mimeType": f"image/{'jpeg' if extension in {'jpg', 'jpeg'} else extension}",
                        "width": int(extracted.get("width") or 0),
                        "height": int(extracted.get("height") or 0),
                    }
                )

        doc.close()
        return {
            "text": "\n".join(text_chunks),
            "metadata": {"parser": "pymupdf", "imageCount": len(images), "degraded": False},
            "pages": pages,
            "images": images,
        }
    except Exception as exc:
        logger.warning(
            "PyMuPDF extraction failed at runtime; falling back to pypdf text-only parser: %s",
            exc,
        )
        return _extract_with_pypdf(buffer, degraded_reason=f"pymupdf_runtime_error: {exc}")


def _extract_with_pypdf(buffer: bytes, *, degraded_reason: str) -> Dict[str, object]:
    reader = PdfReader(BytesIO(buffer))
    pages: List[Dict[str, object]] = []
    text_chunks: List[str] = []

    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        text_chunks.append(page_text)
        pages.append({"pageNumber": index, "content": page_text})

    return {
        "text": "\n".join(text_chunks),
        "metadata": {
            "parser": "pypdf",
            "imageCount": 0,
            "degraded": True,
            "degradedReason": degraded_reason,
        },
        "pages": pages,
        "images": [],
    }
