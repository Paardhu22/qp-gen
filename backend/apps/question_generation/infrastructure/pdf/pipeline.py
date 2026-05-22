from dataclasses import dataclass
from typing import Dict, List, Optional

from services.pdf_service import extract_text_from_pdf
from services.semantic_pipeline import process_semantic_pipeline


@dataclass(frozen=True)
class MarkdownPage:
    page_number: int
    markdown: str
    metadata: Dict[str, object]


@dataclass(frozen=True)
class MarkdownDocument:
    markdown: str
    pages: List[MarkdownPage]


def extract_pdf_to_markdown(buffer: bytes) -> MarkdownDocument:
    pdf_data = extract_text_from_pdf(buffer)
    pages = pdf_data.get("pages", [])
    if not pages:
        return MarkdownDocument(markdown=pdf_data.get("text", ""), pages=[])

    semantic_chunks = process_semantic_pipeline(pages)
    page_map: Dict[int, List[str]] = {}
    for chunk in semantic_chunks:
        page_num = chunk.page or 0
        page_map.setdefault(page_num, []).append(chunk.content)

    markdown_pages: List[MarkdownPage] = []
    for page_num, texts in page_map.items():
        markdown_pages.append(
            MarkdownPage(
                page_number=page_num,
                markdown="\n\n".join(texts).strip(),
                metadata={},
            )
        )

    full_markdown = "\n\n".join(p.markdown for p in markdown_pages).strip()
    return MarkdownDocument(markdown=full_markdown, pages=markdown_pages)
