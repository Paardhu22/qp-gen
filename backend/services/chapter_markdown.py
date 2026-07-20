"""Reconstruct a complete chapter as Markdown for Model 1.

Model 1 reads a WHOLE chapter in one pass rather than per-slot RAG snippets,
so it needs the chapter as a single coherent document. Nothing stores that
today: ingestion turns a PDF into ~60-100 `DocumentChunk` rows and the full
text is discarded.

Rather than add a `markdown_content` column (a migration + a backfill + a
re-upload for every PDF already sitting in production), this module
reconstructs the document from the chunks that are already there. That works
identically for user uploads and shared HSAT books, for rows ingested last
month and rows ingested next week.

Two chunk shapes have to be handled, because ingestion has two paths:

* `process_semantic_pipeline` (PDFs) — chunks carry `chapter`/`heading`
  metadata and embed a "# chapter / ## heading" prefix in their content.
  Non-overlapping, so they concatenate cleanly once the prefix is stripped.
* `chunk_text` (DOCX, txt, and the degenerate-PDF fallback) — plain 1000-char
  windows with 200 chars of deliberate overlap. Concatenating naively would
  duplicate a fifth of the chapter, so the overlap is detected and trimmed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from django.conf import settings
from django.core.cache import cache

from apps.documents.models import DocumentChunk

logger = logging.getLogger("[CHAPTER_MD]")

#: Hard ceiling on the reconstructed document. gpt-4.1-mini takes a very large
#: context, but a whole HSAT textbook is not a "chapter" and pushing one
#: through Model 1 wastes tokens for no pedagogical gain. ~240k chars ≈ 60k
#: tokens, comfortably more than any single CBSE chapter.
DEFAULT_MAX_CHARS = 240_000

#: The "# {chapter}\n## {heading}\n\n" preamble that build_semantic_chunks
#: stamps onto every semantic chunk. Stripped so headings can be re-emitted
#: once per section instead of once per chunk.
_SEMANTIC_PREFIX_RE = re.compile(r"\A#\s+.*?\n##\s+.*?\n\n", re.DOTALL)

#: Largest overlap `chunk_text` can introduce (its chunk_overlap default).
_MAX_OVERLAP = 200


@dataclass
class Figure:
    """A diagram extracted from the source document."""

    url: str
    caption: str
    page: Optional[int] = None
    source_pdf: str = ""

    def to_markdown(self) -> str:
        alt = self.caption or "Figure"
        page = f" (page {self.page})" if self.page else ""
        return f"![{alt}]({self.url}){page}"


@dataclass
class ChapterMarkdown:
    """The reconstructed chapter plus what Model 1 needs to reason about it."""

    markdown: str
    figures: List[Figure] = field(default_factory=list)
    chapter_titles: List[str] = field(default_factory=list)
    source_names: List[str] = field(default_factory=list)
    truncated: bool = False
    char_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.markdown.strip()

    @property
    def estimated_tokens(self) -> int:
        """~4 chars/token for English prose. Used for budgeting, not billing."""
        return self.char_count // 4


def _strip_semantic_prefix(content: str) -> str:
    return _SEMANTIC_PREFIX_RE.sub("", content, count=1)


def _trim_overlap(previous_tail: str, content: str) -> str:
    """Drop the leading slice of `content` that repeats the end of the previous
    chunk.

    `chunk_text` steps back `chunk_overlap` chars between windows, so
    consecutive chunks share a suffix/prefix. Longest match wins, so a chunk
    boundary that happens to land mid-sentence doesn't leave a stutter.
    """
    if not previous_tail or not content:
        return content
    limit = min(_MAX_OVERLAP, len(previous_tail), len(content))
    for size in range(limit, 20, -1):
        if previous_tail[-size:] == content[:size]:
            return content[size:]
    return content


def _is_image_chunk(metadata: dict) -> bool:
    return str(metadata.get("chunkType") or "") == "image"


def _collect_figures(image_chunks: Sequence[DocumentChunk]) -> List[Figure]:
    figures: List[Figure] = []
    for chunk in image_chunks:
        metadata = chunk.metadata or {}
        url = str(metadata.get("image_url") or "").strip()
        if not url:
            continue
        figures.append(
            Figure(
                url=url,
                caption=str(metadata.get("image_caption") or "").strip(),
                page=chunk.page,
                source_pdf=str(metadata.get("sourcePdf") or ""),
            )
        )
    return figures


def _render_text_chunks(text_chunks: Sequence[DocumentChunk]) -> tuple[str, List[str]]:
    """Join text chunks into Markdown, emitting each heading exactly once."""
    lines: List[str] = []
    chapter_titles: List[str] = []
    current_chapter: Optional[str] = None
    current_heading: Optional[str] = None
    previous_tail = ""

    for chunk in text_chunks:
        metadata = chunk.metadata or {}
        chapter = str(metadata.get("chapter") or "").strip()
        heading = str(metadata.get("heading") or "").strip()

        body = _strip_semantic_prefix(chunk.content or "")
        # Only the plain `chunk_text` path overlaps; semantic chunks are
        # disjoint and carry chapter metadata. Keying off that avoids
        # trimming a legitimately repeated sentence in a semantic chunk.
        if not chapter:
            body = _trim_overlap(previous_tail, body)
        body = body.strip()
        if not body:
            continue

        if chapter and chapter != current_chapter:
            current_chapter = chapter
            current_heading = None
            if chapter not in chapter_titles:
                chapter_titles.append(chapter)
            lines.append(f"\n# {chapter}\n")

        if heading and heading != current_heading:
            current_heading = heading
            lines.append(f"\n## {heading}\n")

        lines.append(body)
        previous_tail = body[-_MAX_OVERLAP:]

    return "\n".join(lines).strip(), chapter_titles


def _cache_key(pdf_source_ids: Sequence[str], hsat_source_ids: Sequence[str]) -> str:
    pdfs = ",".join(sorted(pdf_source_ids))
    hsats = ",".join(sorted(hsat_source_ids))
    return f"chapter_md:v1:{pdfs}|{hsats}"


def build_chapter_markdown(
    *,
    pdf_source_ids: Optional[Iterable[str]] = None,
    hsat_source_ids: Optional[Iterable[str]] = None,
    max_chars: Optional[int] = None,
    use_cache: bool = True,
) -> ChapterMarkdown:
    """Rebuild the selected sources as one Markdown document.

    Chunks are read in ingestion order (`chunk_index`), which is document
    order — the semantic pipeline assigns it sequentially while walking pages.

    Callers must scope `pdf_source_ids` to the requesting user BEFORE calling
    this; it does no ownership filtering of its own.
    """
    pdf_ids = [str(x) for x in (pdf_source_ids or []) if x]
    hsat_ids = [str(x) for x in (hsat_source_ids or []) if x]
    if not pdf_ids and not hsat_ids:
        return ChapterMarkdown(markdown="")

    limit = max_chars or int(getattr(settings, "CHAPTER_MD_MAX_CHARS", DEFAULT_MAX_CHARS))
    key = _cache_key(pdf_ids, hsat_ids)

    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached

    query = DocumentChunk.objects.none()
    if pdf_ids:
        query = query | DocumentChunk.objects.filter(pdf_source_id__in=pdf_ids)
    if hsat_ids:
        query = query | DocumentChunk.objects.filter(hsat_source_id__in=hsat_ids)

    # `.only()` keeps the 1536-dim embedding vector out of the result set —
    # fetching it for every chunk would move megabytes for no reason.
    chunks = list(
        query.only(
            "id", "content", "page", "chunk_index", "metadata",
            "pdf_source_id", "hsat_source_id",
        ).order_by("pdf_source_id", "hsat_source_id", "chunk_index")
    )

    if not chunks:
        logger.warning(
            "No chunks found for pdf=%s hsat=%s — chapter markdown is empty.",
            pdf_ids, hsat_ids,
        )
        return ChapterMarkdown(markdown="")

    text_chunks = [c for c in chunks if not _is_image_chunk(c.metadata or {})]
    image_chunks = [c for c in chunks if _is_image_chunk(c.metadata or {})]

    markdown, chapter_titles = _render_text_chunks(text_chunks)
    figures = _collect_figures(image_chunks)

    source_names: List[str] = []
    for chunk in chunks:
        name = str((chunk.metadata or {}).get("sourcePdf") or "").strip()
        if name and name not in source_names:
            source_names.append(name)

    # Figures are appended as a labelled inventory rather than interleaved:
    # their page numbers locate them well enough, and a trailing block keeps
    # the prose readable for the model while giving the image stage a clean
    # list to work from.
    if figures:
        figure_lines = ["\n\n## Figures in this chapter\n"]
        for index, figure in enumerate(figures, start=1):
            caption = figure.caption or "(uncaptioned figure)"
            page = f" — page {figure.page}" if figure.page else ""
            figure_lines.append(f"- **Figure {index}**{page}: {caption}")
        markdown = markdown + "\n".join(figure_lines)

    truncated = False
    if len(markdown) > limit:
        # Cut on a paragraph boundary so the model never sees a half sentence.
        cut = markdown.rfind("\n\n", 0, limit)
        markdown = markdown[: cut if cut > limit // 2 else limit]
        truncated = True
        logger.warning(
            "Chapter markdown truncated to %d chars (limit %d) for pdf=%s hsat=%s",
            len(markdown), limit, pdf_ids, hsat_ids,
        )

    result = ChapterMarkdown(
        markdown=markdown,
        figures=figures,
        chapter_titles=chapter_titles,
        source_names=source_names,
        truncated=truncated,
        char_count=len(markdown),
    )

    if use_cache:
        # 15 min: long enough that regenerating a paper from the same chapter
        # skips the rebuild, short enough that a re-ingested source is picked
        # up without an explicit bust.
        cache.set(key, result, timeout=900)

    return result


def infer_chapter_name(chapter: ChapterMarkdown, fallback: str = "") -> str:
    """Best-effort chapter label for grouping saved questions.

    Prefers a detected chapter heading, then the source filename with its
    extension stripped, then the caller's fallback (usually the topic field).
    """
    for title in chapter.chapter_titles:
        cleaned = title.strip()
        # "General Context" is build_semantic_chunks' placeholder for content
        # that appeared before any recognised chapter heading.
        if cleaned and cleaned.lower() not in {"general context", "visual source"}:
            return cleaned

    for name in chapter.source_names:
        stem = re.sub(r"\.(pdf|docx?|txt)$", "", name, flags=re.IGNORECASE).strip()
        if stem:
            return stem

    return fallback
