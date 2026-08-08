"""Deterministic text filters between LLM/PDF-extracted text and the editor.

Round-4 (s3b paper review) introduced this module as the single home for
content scrubbing. Everything here is pure string → string so both the
ingestion pipeline (document_service) and the generation pipeline
(generation_service) can share it, and unit tests can hit it directly.

Filters NEVER touch Unicode math symbols (√ ∞ ≠ ≤ ≥ π θ α β ∆ ∠ …) — that
is asserted by services/test_content_filters.py.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

# ── VI (visually impaired) alternate blocks ──────────────────────────────
#
# CBSE sample papers and HSAT textbook PDFs embed VI alternates as:
#     - - - - - - - - - - - - -
#     Note: The following question is for Visually Impaired Students only
#     in lieu of the visual question above.
#     <alternate question text>
#     - - - - - - - - - - - - -
# When such a block survives ingestion, retrieval hands it to the LLM and
# the LLM happily copies it into `content` (the s3b paper's Q31/Q37). VI
# text has no legitimate carrier anywhere in the pipeline, so any such block
# is always contamination and is stripped outright.

_DASHED_LINE_RE = re.compile(r"^[\s\-–—_]{3,}$")
_VI_NOTE_RE = re.compile(
    r"visually[\s\-]?impaired\s+students?\s+only|in\s+lieu\s+of\s+the\s+visual",
    re.IGNORECASE,
)
_VI_COORDS_RE = re.compile(
    r"explicit\s+coordinates?\s*\(\s*for\s+visual[\s\-]?impaired\s+alternative\s*\)\s*:?",
    re.IGNORECASE,
)
_VI_ANY_RE = re.compile(r"visually[\s\-]?impaired", re.IGNORECASE)

#: Hard cap on how many lines a VI block may swallow after its note line,
#: so a missing closing dash can never eat the rest of a real question.
_VI_BLOCK_MAX_LINES = 12


def strip_vi_blocks(text: str) -> str:
    """Remove embedded VI-alternate blocks from free text.

    Handles: dashed-delimited blocks containing the VI note, bare note
    lines followed by the alternate text, and "Explicit coordinates
    (for visual-impaired alternative):" blocks. Used at ingestion (so
    chunks are clean) AND on LLM output (so a contaminated retrieval
    context cannot leak through generation).
    """
    if not text or not _VI_ANY_RE.search(text) and not _VI_COORDS_RE.search(text):
        return text

    lines = text.split("\n")
    keep: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if _VI_COORDS_RE.search(line):
            # Skip the coords header + its block until a blank/dashed line.
            i += 1
            while i < len(lines) and lines[i].strip() and not _DASHED_LINE_RE.match(lines[i]):
                i += 1
            continue

        if _VI_NOTE_RE.search(line):
            # The note may be preceded by an opening dashed separator that
            # we already kept — drop it retroactively.
            if keep and _DASHED_LINE_RE.match(keep[-1]):
                keep.pop()
            # Skip the note line plus the alternate text, up to and
            # including the closing dashed line (bounded lookahead).
            i += 1
            consumed = 0
            while i < len(lines) and consumed < _VI_BLOCK_MAX_LINES:
                if _DASHED_LINE_RE.match(lines[i]):
                    i += 1  # consume the closing dashes too
                    break
                i += 1
                consumed += 1
            continue

        keep.append(line)
        i += 1

    cleaned = "\n".join(keep)
    # Belt and braces: any straggler sentence naming VI students.
    cleaned = "\n".join(
        l for l in cleaned.split("\n") if not _VI_NOTE_RE.search(l)
    )
    return _collapse_blank_lines(cleaned)


# ── Blueprint/instruction metadata leakage ───────────────────────────────
#
# The per-slot prompt tells the model things like "Add exactly one internal
# choice in `question.or_choice`". The s3b paper's Q34 ended with the
# model's paraphrase: "Internal choice — answer either (A) or (B) as given
# in the question content." None of these strings exist as question text in
# any legitimate paper; they are instruction echoes and must be dropped.

_BLUEPRINT_LEAK_RES: Sequence[re.Pattern] = (
    re.compile(r"internal\s+choice\s*[—–-]+\s*answer\s+either", re.IGNORECASE),
    re.compile(r"answer\s+either\s*\(?\s*a\s*\)?\s+or\s+\(?\s*b\s*\)?", re.IGNORECASE),
    re.compile(r"as\s+given\s+in\s+the\s+question\s+content", re.IGNORECASE),
    re.compile(r"question\.(?:or_choice|image_url|figure)", re.IGNORECASE),
    re.compile(r"\bor_choice\b", re.IGNORECASE),
    re.compile(r"do\s+not\s+output\s+the\s+or\s+alternative", re.IGNORECASE),
    re.compile(r"^\s*set\s+`?question\.", re.IGNORECASE),
    re.compile(r"slot\s+contract|json\s+schema", re.IGNORECASE),
)


def _leaks(text: str) -> bool:
    return any(rx.search(text) for rx in _BLUEPRINT_LEAK_RES)


def strip_blueprint_leakage(text: str) -> str:
    """Drop lines (or sentences within mixed lines) that echo slot
    instructions / field names into student-visible question text."""
    if not text:
        return text
    keep: List[str] = []
    for line in text.split("\n"):
        if not _leaks(line):
            keep.append(line)
            continue
        # Mixed line: keep the sentences that don't leak.
        sentences = re.split(r"(?<=[.!?])\s+", line)
        kept_sentences = [s for s in sentences if s and not _leaks(s)]
        if kept_sentences:
            keep.append(" ".join(kept_sentences))
    return _collapse_blank_lines("\n".join(keep))


# ── Orphan OR separators ─────────────────────────────────────────────────
#
# Valid OR placement is strictly BETWEEN two alternatives. The s3b paper's
# Q29 carried "stem:\nOR\n(A)…\nOR\n(B)…" — the first OR (between the stem
# and choice A) is an instruction-echo orphan.

DEFAULT_OR_LABELS = ("OR", "अथवा", "లేదా")

_CHOICE_MARKER_RE = re.compile(r"^\s*\(\s*[A-Da-d]\s*\)|^\s*[A-D][).]\s")


def _is_or_line(line: str, labels: Iterable[str]) -> bool:
    bare = line.strip().strip("*_ ").strip()
    return any(bare.casefold() == label.casefold() for label in labels)


def remove_orphan_or_tokens(
    text: str, or_labels: Sequence[str] = DEFAULT_OR_LABELS
) -> str:
    """Strip OR separator lines that don't sit between two alternatives.

    Rules:
      * when the text lists TWO OR MORE (A)/(B)-style choice markers, an
        OR line before the first marker is an orphan (the s3b Q29 shape:
        "stem:\\nOR\\n(A)…\\nOR\\n(B)…"). With fewer than two markers the
        rule stays off — a legitimate "<content>\\nOR\\n(B) …" assembly
        has one marker and its OR is the real separator;
      * an OR line with no non-empty line before it (leading) is orphan;
      * an OR line with no non-empty line after it (trailing) is orphan;
      * consecutive OR lines collapse to one.
    """
    if not text:
        return text
    lines = text.split("\n")

    marker_indices = [i for i, l in enumerate(lines) if _CHOICE_MARKER_RE.match(l)]
    first_marker = marker_indices[0] if len(marker_indices) >= 2 else None

    keep: List[str] = []
    pending_or: str | None = None  # OR line awaiting a following text line

    def has_text(seq: Iterable[str]) -> bool:
        return any(l.strip() for l in seq)

    for i, line in enumerate(lines):
        if _is_or_line(line, or_labels):
            if first_marker is not None and i < first_marker:
                continue  # orphan: before the first of several choices
            if not has_text(keep):
                continue  # orphan: nothing precedes it
            if not has_text(lines[i + 1 :]):
                continue  # orphan: nothing follows it
            pending_or = line  # collapse consecutive ORs: hold, emit once
            continue
        if line.strip() and pending_or is not None:
            keep.append(pending_or)
            pending_or = None
        keep.append(line)

    return _collapse_blank_lines("\n".join(keep))


# ── Bare (undelimited) LaTeX rescue ──────────────────────────────────────
#
# The typesetting contract demands \( ... \) delimiters, but models still
# occasionally emit bare commands ("\frac{11}{36}", "x^2", "sin^2\theta").
# The editor's buildInlineRun converts ONLY delimited spans, so bare
# commands reach students as raw markup (s3b Q6/Q14). Wrapping the bare
# token in \( \) is deterministic and safe: tokens are only wrapped when
# they contain a LaTeX command or caret exponent, and existing math spans
# are never touched.

_MATH_SPAN_RE = re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]", re.DOTALL)
_LATEX_COMMAND_RE = re.compile(r"\\[a-zA-Z]{2,}")
_CARET_USE_RE = re.compile(r"[\w)\]}]\^(?:\{[^{}]*\}|[\w(\[+\-])")
_TRAILING_PUNCT_RE = re.compile(r"[.,;:!?]+$")


def _wrap_token(token: str) -> str:
    # Unbalanced delimiter fragments are left alone — wrapping would nest.
    if "\\(" in token or "\\)" in token or "\\[" in token or "\\]" in token:
        return token
    if not (_LATEX_COMMAND_RE.search(token) or _CARET_USE_RE.search(token)):
        return token
    trail = ""
    m = _TRAILING_PUNCT_RE.search(token)
    if m:
        trail = m.group(0)
        token = token[: m.start()]
    if not token:
        return trail
    return f"\\({token}\\){trail}"


def _wrap_outside_segment(segment: str) -> str:
    # LaTeX spacing artifacts outside math read as stray backslashes.
    segment = re.sub(r"\\:", ":", segment)
    segment = re.sub(r"\\[,;]", " ", segment)
    return re.sub(r"\S+", lambda m: _wrap_token(m.group(0)), segment)


def wrap_bare_latex_tokens(text: str) -> str:
    """Wrap bare LaTeX command / caret tokens in \\( \\) outside existing
    math spans so KaTeX renders them instead of students seeing markup."""
    if not text or ("\\" not in text and "^" not in text):
        return text
    parts: List[str] = []
    last = 0
    for m in _MATH_SPAN_RE.finditer(text):
        parts.append(_wrap_outside_segment(text[last : m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_wrap_outside_segment(text[last:]))
    return "".join(parts)


# ── Caption quality (figure residue) ─────────────────────────────────────
#
# OCR/vision captioning of geometry figures sometimes returns nothing but
# the diagram's own labels ("A", "ΔB", "∠ABC") — rendering that into a
# figure slot paints giant label glyphs (s3b Q23). A caption is only
# useful if it contains at least one complete word of prose.

_WORD_RE = re.compile(r"[A-Za-z]{4,}")
_LABEL_TOKEN_RE = re.compile(
    r"^(?:[A-Za-z]|Δ[A-Za-z]{0,3}|∠[A-Za-z]{0,3}|[A-Z]{2,3}|"
    r"[α-ωΑ-Ω]|[0-9]+(?:\.[0-9]+)?|[°′″%]|[+\-×÷=:.,;()\[\]{}|/\\^_'\"]+)$"
)


def is_label_only_caption(text: str) -> bool:
    """True when a caption is too short or is just diagram-label residue
    (single letters, ΔB/∠ABC tokens, numbers) with no complete word."""
    stripped = (text or "").strip()
    if len(stripped) < 10:
        return True
    if not _WORD_RE.search(stripped):
        return True
    tokens = stripped.split()
    return all(_LABEL_TOKEN_RE.match(tok) for tok in tokens)


# ── Composition ──────────────────────────────────────────────────────────

def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")


def clean_question_text(
    text: str, *, or_labels: Sequence[str] = DEFAULT_OR_LABELS
) -> str:
    """Full scrub for LLM-emitted question/or-choice content.

    Order matters: leakage and VI blocks are removed first (they can leave
    dangling OR lines behind), then orphan ORs, then bare-LaTeX rescue.
    """
    if not text:
        return text
    text = strip_blueprint_leakage(text)
    text = strip_vi_blocks(text)
    text = remove_orphan_or_tokens(text, or_labels)
    return wrap_bare_latex_tokens(text)
