"""Chapter detection — turn uploaded documents into per-chapter objects.

The unit of question generation is a CHAPTER, never a file and never the whole
upload. This module reads the already-persisted `DocumentChunk` rows for the
selected sources and splits them into `Chapter` objects along detected chapter
boundaries. It works for BOTH:

* Case A — several single-chapter PDFs (each PDF ≈ one chapter).
* Case B — one textbook PDF holding many chapters.
* Case C — a mix of the two.

The system never assumes "one PDF == one chapter": boundaries come from the
content, not the file.

Detection reuses the `chapter` metadata the semantic pipeline already stamps on
every chunk (`services.semantic_pipeline` matches `Chapter|Unit|Module|Lesson N`
while walking pages) and hardens it here — placeholder-only leading groups are
merged forward, a source with no detected boundary becomes a single chapter
named after its file, and messy heading lines are parsed into a clean
number + title. Because it reads existing chunks, already-ingested sources work
with no re-ingestion.

Oversized chapters (larger than a configurable token threshold) are split into
semantic sections by `split_chapter` so a single Model 1 request never exceeds
the organisation's tokens-per-minute ceiling (TPM safety, STEP 8).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from django.conf import settings

from apps.documents.models import DocumentChunk
from services.chapter_markdown import (
    Figure,
    _collect_figures,
    _is_image_chunk,
    _render_text_chunks,
)

logger = logging.getLogger("[CHAPTERS]")

#: Placeholder "chapter" names the semantic pipeline emits for content that
#: appeared before any recognised chapter heading. Not real chapters.
_PLACEHOLDER_TITLES = {"", "general context", "introduction", "visual source", "general"}

#: Chapter-heading grammar, kept deliberately permissive so board-specific
#: formats (Chapter/Unit/Lesson/Module, and the Hindi अध्याय/पाठ) all parse.
_CHAPTER_LABEL_RE = re.compile(
    r"^\s*(?:#+\s*)?(chapter|unit|lesson|module|अध्याय|पाठ)\s*[:\-–—.)]?\s*(\d+|[IVXLCDM]+)\b",
    re.IGNORECASE,
)
_FALLBACK_SCAN_LINES = 8
_ROMAN_NUMERALS = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
    "XVI": 16,
    "XVII": 17,
    "XVIII": 18,
    "XIX": 19,
    "XX": 20,
}


def _default_threshold_chars() -> int:
    """Token threshold → char budget (~4 chars/token) for one Model 1 request."""
    tokens = int(getattr(settings, "POOL_CHAPTER_TOKEN_THRESHOLD", 20_000))
    return max(4_000, tokens) * 4


@dataclass
class Chapter:
    """One detected chapter: the Model 1 unit of work.

    Carries everything Model 1 and the bank need — the markdown, the figures
    that belong to THIS chapter (not the whole upload), and provenance
    (source PDF + page span) so every generated question can be traced back.
    """

    number: Optional[int]
    title: str
    markdown: str
    figures: List[Figure] = field(default_factory=list)
    source_pdfs: List[str] = field(default_factory=list)
    pages: List[int] = field(default_factory=list)
    char_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.markdown.strip()

    @property
    def estimated_tokens(self) -> int:
        return self.char_count // 4

    def question_metadata(self) -> Dict[str, Any]:
        """Provenance stamped onto every question generated from this chapter
        (STEP 5). Merged into `PoolQuestion.metadata` and persisted to the bank.
        """
        page_span: Optional[List[int]] = None
        if self.pages:
            page_span = [min(self.pages), max(self.pages)]
        source_pdf: Any = None
        if len(self.source_pdfs) == 1:
            source_pdf = self.source_pdfs[0]
        elif self.source_pdfs:
            source_pdf = list(self.source_pdfs)
        return {
            "chapterNumber": self.number,
            "chapterTitle": self.title,
            "sourcePdf": source_pdf,
            "sourcePages": page_span,
        }


def _parse_chapter_label(raw: str) -> tuple[Optional[int], str]:
    """Extract (number, clean short title) from a raw chapter-heading line.

    "Chapter 4. The pancreas secretes pancreatic juice which contains" →
    (4, "Chapter 4 · The pancreas secretes pancreatic juice"). Titles are
    trimmed to a readable length; the full heading survives in the markdown.
    """
    raw = (raw or "").strip()
    match = _CHAPTER_LABEL_RE.match(raw)
    number: Optional[int] = None
    if match:
        try:
            value = str(match.group(2) or "").upper()
            number = int(value) if value.isdigit() else _ROMAN_NUMERALS.get(value)
        except (TypeError, ValueError):
            number = None
    # Trim to the first sentence or ~64 chars so the label is UI-friendly.
    trimmed = re.split(r"(?<=[.!?])\s", raw, maxsplit=1)[0]
    if len(trimmed) > 64:
        trimmed = trimmed[:64].rstrip() + "…"
    return number, (trimmed or raw)


def _is_placeholder(title: str) -> bool:
    return (title or "").strip().lower() in _PLACEHOLDER_TITLES


def _fallback_chapter_key(content: str) -> str:
    """Recover a chapter heading from chunk text when metadata is absent.

    This is intentionally conservative: semantic metadata remains authoritative,
    and the fallback only trusts a recognised chapter/unit/module/lesson label
    near the start of a chunk. That catches older rows and plain-text uploads
    without inventing duplicate chapter logic for every heading-like line.
    """
    for line in (content or "").splitlines()[:_FALLBACK_SCAN_LINES]:
        candidate = line.strip()
        if _CHAPTER_LABEL_RE.match(candidate):
            return candidate.lstrip("#").strip()
    return ""


def _chunk_query(pdf_ids: Sequence[str], hsat_ids: Sequence[str]):
    query = DocumentChunk.objects.none()
    if pdf_ids:
        query = query | DocumentChunk.objects.filter(pdf_source_id__in=list(pdf_ids))
    if hsat_ids:
        query = query | DocumentChunk.objects.filter(hsat_source_id__in=list(hsat_ids))
    return (
        query.select_related("pdf_source", "hsat_source")
        .only(
            "id", "content", "page", "chunk_index", "metadata",
            "pdf_source_id", "hsat_source_id", "pdf_source__name", "hsat_source__book",
        )
        .order_by("pdf_source_id", "hsat_source_id", "chunk_index")
    )


@dataclass
class _Group:
    source_key: str
    chapter_key: str
    text_chunks: List[DocumentChunk] = field(default_factory=list)
    image_chunks: List[DocumentChunk] = field(default_factory=list)
    source_names: List[str] = field(default_factory=list)
    pages: List[int] = field(default_factory=list)


def _group_chunks(chunks: Sequence[DocumentChunk]) -> List[_Group]:
    """Walk chunks in document order, cutting a new group at every chapter change
    within a source. Image chunks attach to the current group."""
    groups: List[_Group] = []
    current: Optional[_Group] = None

    for chunk in chunks:
        meta = chunk.metadata or {}
        source_key = str(chunk.pdf_source_id or chunk.hsat_source_id or "")
        source_name = str(meta.get("sourcePdf") or "").strip()
        if not source_name:
            if chunk.pdf_source_id:
                source_name = str(getattr(chunk.pdf_source, "name", "") or "").strip()
            elif chunk.hsat_source_id:
                source_name = str(getattr(chunk.hsat_source, "book", "") or "").strip()

        if _is_image_chunk(meta):
            if current is None:
                current = _Group(source_key=source_key, chapter_key="")
                groups.append(current)
            current.image_chunks.append(chunk)
            if source_name and source_name not in current.source_names:
                current.source_names.append(source_name)
            if chunk.page:
                current.pages.append(int(chunk.page))
            continue

        chapter_key = str(meta.get("chapter") or "").strip()
        if not chapter_key:
            chapter_key = _fallback_chapter_key(chunk.content or "")
        # New group when the source changes or a real chapter boundary appears.
        boundary = (
            current is None
            or source_key != current.source_key
            or (chapter_key and chapter_key != current.chapter_key)
        )
        if boundary:
            current = _Group(source_key=source_key, chapter_key=chapter_key)
            groups.append(current)
        elif chapter_key and not current.chapter_key:
            current.chapter_key = chapter_key

        current.text_chunks.append(chunk)
        if source_name and source_name not in current.source_names:
            current.source_names.append(source_name)
        if chunk.page:
            current.pages.append(int(chunk.page))

    return groups


def _merge_leading_placeholders(groups: List[_Group]) -> List[_Group]:
    """Fold a source's leading placeholder group (front matter before the first
    real chapter heading) into the chapter that follows it in the same source."""
    merged: List[_Group] = []
    for group in groups:
        if (
            merged
            and _is_placeholder(group.chapter_key)
            and merged[-1].source_key == group.source_key
        ):
            # Placeholder AFTER a real chapter → continuation of it.
            if not _is_placeholder(merged[-1].chapter_key):
                merged[-1].text_chunks.extend(group.text_chunks)
                merged[-1].image_chunks.extend(group.image_chunks)
                merged[-1].pages.extend(group.pages)
                for name in group.source_names:
                    if name not in merged[-1].source_names:
                        merged[-1].source_names.append(name)
                continue
        if (
            merged
            and _is_placeholder(merged[-1].chapter_key)
            and merged[-1].source_key == group.source_key
            and not _is_placeholder(group.chapter_key)
        ):
            # Real chapter AFTER a leading placeholder → absorb the placeholder.
            group.text_chunks = merged[-1].text_chunks + group.text_chunks
            group.image_chunks = merged[-1].image_chunks + group.image_chunks
            group.pages = merged[-1].pages + group.pages
            for name in merged[-1].source_names:
                if name not in group.source_names:
                    group.source_names.append(name)
            merged[-1] = group
            continue
        merged.append(group)
    return merged


def _group_to_chapter(group: _Group) -> Optional[Chapter]:
    markdown, chapter_titles = _render_text_chunks(group.text_chunks)
    figures = _collect_figures(group.image_chunks)

    # Append the figure inventory so the diagram stage has a clean list.
    if figures:
        lines = ["\n\n## Figures in this chapter\n"]
        for index, figure in enumerate(figures, start=1):
            caption = figure.caption or "(figure — see nearby text)"
            page = f" — page {figure.page}" if figure.page else ""
            lines.append(f"- **Figure {index}**{page}: {caption}")
        markdown = (markdown + "\n".join(lines)).strip()

    if not markdown.strip():
        return None

    raw_title = group.chapter_key or (chapter_titles[0] if chapter_titles else "")
    if _is_placeholder(raw_title):
        # No heading detected — name the chapter after its source file.
        stem = ""
        if group.source_names:
            stem = re.sub(
                r"\.(pdf|docx?|txt)$", "", group.source_names[0], flags=re.IGNORECASE
            ).strip()
        raw_title = stem or "Chapter"
        number = None
        title = raw_title
    else:
        number, title = _parse_chapter_label(raw_title)

    return Chapter(
        number=number,
        title=title,
        markdown=markdown,
        figures=figures,
        source_pdfs=list(group.source_names),
        pages=sorted(set(group.pages)),
        char_count=len(markdown),
        metadata={"rawChapterKey": group.chapter_key},
    )


def build_chapters(
    *,
    pdf_source_ids: Optional[Iterable[str]] = None,
    hsat_source_ids: Optional[Iterable[str]] = None,
) -> List[Chapter]:
    """Detect and return every chapter across the selected sources.

    Callers must scope `pdf_source_ids` to the requesting user beforehand; this
    does no ownership filtering (readiness/ownership is enforced upstream).
    """
    pdf_ids = [str(x) for x in (pdf_source_ids or []) if x]
    hsat_ids = [str(x) for x in (hsat_source_ids or []) if x]
    if not pdf_ids and not hsat_ids:
        return []

    chunks = list(_chunk_query(pdf_ids, hsat_ids))
    if not chunks:
        logger.warning("No chunks for pdf=%s hsat=%s — no chapters.", pdf_ids, hsat_ids)
        return []

    groups = _merge_leading_placeholders(_group_chunks(chunks))
    chapters: List[Chapter] = []
    for group in groups:
        chapter = _group_to_chapter(group)
        if chapter is not None:
            chapters.append(chapter)

    logger.info(
        "Detected %d chapter(s) across %d source(s): %s",
        len(chapters),
        len(set(c.source_key for c in groups)),
        [f"{c.title} (~{c.estimated_tokens} tok)" for c in chapters],
    )
    return chapters


def _split_markdown(markdown: str, max_chars: int) -> List[str]:
    """Split markdown into parts ≤ max_chars, cutting only at heading/paragraph
    boundaries so no sentence is ever bisected."""
    if len(markdown) <= max_chars:
        return [markdown]

    def _hard_split(text: str) -> List[str]:
        """Last-resort split for extractor output with no paragraph breaks."""
        slices: List[str] = []
        remaining = text.strip()
        while len(remaining) > max_chars:
            cut = remaining.rfind(" ", 0, max_chars)
            if cut < max_chars // 2:
                cut = max_chars
            slices.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            slices.append(remaining)
        return slices

    # Prefer cutting at headings; fall back to blank lines, then a hard cut.
    blocks = re.split(r"(?=\n#{1,3}\s)", markdown)
    parts: List[str] = []
    current = ""
    for block in blocks:
        # Oversized blocks are checked FIRST. When this was the `elif` branch
        # any non-empty `current` sent an oversized block down the "start a new
        # part" path instead, so it was emitted whole and the cap silently did
        # not hold — a heading-less chapter (common in OCR'd textbook PDFs)
        # produced one Model 1 request far over the token budget, which fails
        # the whole batch rather than splitting.
        if len(block) > max_chars:
            # A single heading's body is itself too big — split on blank lines.
            for para in re.split(r"\n\s*\n", block):
                if len(para) > max_chars:
                    if current.strip():
                        parts.append(current.strip())
                        current = ""
                    parts.extend(_hard_split(para))
                    continue
                if current and len(current) + len(para) + 2 > max_chars:
                    parts.append(current)
                    current = para
                else:
                    current = f"{current}\n\n{para}" if current else para
        elif current and len(current) + len(block) > max_chars:
            parts.append(current)
            current = block
        else:
            current = f"{current}{block}" if current else block
    if current.strip():
        parts.append(current)
    return [p.strip() for p in parts if p.strip()] or [markdown[:max_chars]]


def split_chapter(chapter: Chapter, max_chars: Optional[int] = None) -> List[Chapter]:
    """Split an oversized chapter into section-sized sub-chapters (STEP 8).

    A chapter whose markdown exceeds the threshold would make a single Model 1
    request too large for the TPM ceiling. Splitting it into semantic sections
    keeps every request bounded; the section pools are merged back into one
    chapter pool downstream, so the chapter's questions stay together in the
    bank. Figures ride on the first part (the inventory is a trailing block).
    """
    budget = max_chars or _default_threshold_chars()
    if chapter.char_count <= budget:
        return [chapter]

    parts = _split_markdown(chapter.markdown, budget)
    if len(parts) <= 1:
        return [chapter]

    sections: List[Chapter] = []
    for index, part in enumerate(parts):
        sections.append(
            Chapter(
                number=chapter.number,
                title=(
                    chapter.title if len(parts) == 1
                    else f"{chapter.title} · Part {index + 1}"
                ),
                markdown=part,
                figures=chapter.figures if index == 0 else [],
                source_pdfs=list(chapter.source_pdfs),
                pages=list(chapter.pages),
                char_count=len(part),
                metadata={
                    **chapter.metadata,
                    "sectionIndex": index + 1,
                    "sectionCount": len(parts),
                    # Questions still bank under the parent chapter title.
                    "bankChapterTitle": chapter.title,
                },
            )
        )
    logger.info(
        "Split oversized chapter %r (~%d tok) into %d section(s).",
        chapter.title, chapter.estimated_tokens, len(sections),
    )
    return sections
