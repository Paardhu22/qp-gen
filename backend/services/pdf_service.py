from io import BytesIO
from typing import Dict, List

from pypdf import PdfReader


def extract_text_from_pdf(buffer: bytes) -> Dict[str, object]:
    reader = PdfReader(BytesIO(buffer))
    pages: List[Dict[str, object]] = []
    text_chunks: List[str] = []

    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        text_chunks.append(page_text)
        pages.append({"pageNumber": index, "content": page_text})

    return {
        "text": "\n".join(text_chunks),
        "metadata": {},
        "pages": pages,
    }
