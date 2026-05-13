from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chunk:
    content: str
    chunk_index: int
    page: Optional[int] = None


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    page_number: Optional[int] = None,
    start_index: int = 0,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    current_pos = 0
    index = start_index

    while current_pos < len(text):
        end_pos = current_pos + chunk_size

        if end_pos < len(text):
            last_newline = text.rfind("\n", current_pos, end_pos)
            last_period = text.rfind(". ", current_pos, end_pos)
            break_pos = max(last_newline, last_period)

            if break_pos > current_pos + int(chunk_size * 0.5):
                end_pos = break_pos + 1

        content = text[current_pos:end_pos].strip()
        if content:
            chunks.append(Chunk(content=content, page=page_number, chunk_index=index))
            index += 1

        current_pos = end_pos - chunk_overlap
        if current_pos <= 0 and len(text) > chunk_size:
            current_pos = end_pos
        if end_pos >= len(text):
            break
        if current_pos <= (end_pos - chunk_size):
            current_pos = end_pos

    return chunks


def chunk_pages(pages: List[dict]) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    global_index = 0

    for page in pages:
        page_chunks = chunk_text(
            page.get("content", ""),
            page_number=page.get("pageNumber"),
            start_index=global_index,
        )
        all_chunks.extend(page_chunks)
        global_index += len(page_chunks)

    return all_chunks
