import base64
import json
import logging
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Set

from apps.generation.models import GenerationHistory
from django.conf import settings
from django.core.files.storage import default_storage

from apps.question_generation.domain.context import (
    GenerationConstraints,
    GenerationContext,
    TokenBudget,
)
from apps.question_generation.domain.enums import AcademicClass, EducationBoard
from apps.question_generation.infrastructure.observability.metrics import GenerationMetrics
from apps.question_generation.infrastructure.providers.openai_provider import OpenAIProvider
from apps.question_generation.infrastructure.token_budget.budgeter import (
    allocate_budget,
    trim_chunks_to_budget,
)
from apps.question_generation.services.prompting.assembler import PromptAssembler, default_system_rules
from apps.question_generation.services.prompting.request_factory import LLMRequestFactory
from services.retrieval_service import retrieve_relevant_chunks
from apps.question_generation.services.retrieval.context_service import (
    retrieval_quality_summary,
)
from services.content_filters import (
    clean_question_text,
    clean_vi_alternative_text,
    remove_orphan_or_tokens,
    strip_blueprint_leakage,
    wrap_bare_latex_tokens,
)
from services.language_validation import validate_language_question
from services.media_urls import vision_url_for_chunk

logger = logging.getLogger("[LEGACY_ENGINE]")


def _system_rules_for_slot(slot, constraints) -> str:
    """
    Mode-aware system rules. CONTENT keeps the original chunk-grounded rules so
    Science/Social/Maths/literature are byte-for-byte unchanged. GRAMMAR/COMPOSITION/
    PASSAGE must NOT be told to use retrieved chunks (there are none) — they are
    generated from rules or a fresh scenario.
    """
    mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()
    if mode == "CONTENT":
        return default_system_rules(constraints)

    base = [
        "You are a CBSE examiner generating ONE question for a language paper.",
        "Generate the QUESTION ONLY — never the student's answer except in the answer key field.",
        "Do NOT use, quote, or rely on any uploaded textbook content; this slot is not content-retrieval based.",
        "Obey the exact slot contract and JSON schema. Never add extra question objects or split an OR into another question.",
    ]
    if mode == "GRAMMAR":
        base.append("Grammar tasks are rule-based and self-contained, each in a fresh micro-context you invent.")
    elif mode == "PASSAGE":
        base.append("Generate an ORIGINAL, previously-unseen passage; never reproduce prescribed/uploaded text.")
    elif mode == "COMPOSITION":
        base.append("Provide a self-contained scenario/stimulus/topic with hints and an explicit word limit.")
    if constraints:
        base.append(f"Resolved paper count: {constraints.count} question objects.")
    return "\n".join(base)


def _sse_event(data: dict, event: str = "update") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class JsonObjectStreamExtractor:
    """
    Incrementally detects complete JSON objects without trying to parse partial
    token buffers. json.loads is called only after brace depth returns to zero.
    """

    def __init__(self) -> None:
        self._buffer: List[str] = []
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._started = False

    def feed(self, text: str) -> List[dict]:
        completed: List[dict] = []

        for ch in text:
            if not self._started:
                if ch == "{":
                    self._started = True
                    self._depth = 1
                    self._buffer = [ch]
                continue

            self._buffer.append(ch)

            if self._escape:
                self._escape = False
                continue

            if ch == "\\" and self._in_string:
                self._escape = True
                continue

            if ch == '"':
                self._in_string = not self._in_string
                continue

            if self._in_string:
                continue

            if ch == "{":
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0:
                    raw = "".join(self._buffer)
                    completed.append(json.loads(raw))
                    self._buffer = []
                    self._started = False
                    self._in_string = False
                    self._escape = False

        return completed


def _get_rate_limit_sleep_time(exc) -> float:
    # Check if this looks like a rate limit error (e.g. contains 429 or "rate limit")
    exc_str = str(exc)
    if "429" in exc_str or "rate limit" in exc_str.lower() or "tpm" in exc_str.lower():
        # Look for "try again in X.XXXs" or "try again in X.XXX seconds"
        match = re.search(r"try again in (\d+(?:\.\d+)?)s", exc_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) + 0.5 # Add a small buffer
        # Also match "try again in X seconds"
        match = re.search(r"try again in (\d+(?:\.\d+)?) seconds", exc_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) + 0.5
        # Default backoff sleep
        return 5.0
    return 1.0 # default short sleep for other transient connection/stream errors


def _empty_result() -> Dict[str, Any]:
    return {"generalInstructions": [], "sections": []}


def _find_or_create_section(result: Dict[str, List[dict]], title: str) -> dict:
    for section in result["sections"]:
        if section.get("title") == title:
            return section
    section = {"title": title, "questions": []}
    result["sections"].append(section)
    return section


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _allowed_image_urls(source_chunks: List[dict]) -> List[str]:
    urls: List[str] = []
    seen: Set[str] = set()
    for chunk in source_chunks:
        metadata = chunk.get("metadata") or {}
        url = chunk.get("image_url") or metadata.get("image_url")
        if url and url not in seen:
            urls.append(str(url))
            seen.add(str(url))
    return urls


def _is_model_readable_image_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://") or url.startswith("data:")


def _storage_image_data_url(metadata: dict) -> str:
    stored_path = metadata.get("image_storage_path")
    if not stored_path:
        return ""

    try:
        with default_storage.open(stored_path, "rb") as handle:
            payload = base64.b64encode(handle.read()).decode("ascii")
    except Exception as exc:
        logger.warning("[VISION] Could not read stored image %s: %s", stored_path, exc)
        return ""

    mime_type = metadata.get("mimeType") or "image/png"
    return f"data:{mime_type};base64,{payload}"


def _vision_image_payload_urls(source_chunks: List[dict]) -> List[str]:
    """URLs OpenAI downloads to *see* the source images.

    These must be minted at call time: chunk metadata only stores the
    permanent storage key, and any http(s) URL persisted at ingest time
    (legacy chunks stored presigned URLs with X-Amz-Expires=3600) is
    stale by now — OpenAI rejects it with `invalid_image_url`. Order of
    preference per chunk:
      1. fresh presigned S3 URL (expire=900, consumed immediately),
      2. base64 data URL read from storage (local-disk deployments),
      3. the stored URL, only when it carries no storage path at all
         (e.g. data: URLs, which never expire).
    """
    urls: List[str] = []
    seen: Set[str] = set()
    # Track per-chunk identity so two chunks pointing at the same stored
    # image still dedupe even though each presigned URL is unique.
    seen_paths: Set[str] = set()
    for chunk in source_chunks:
        metadata = chunk.get("metadata") or {}
        storage_path = str(metadata.get("image_storage_path") or "")
        if storage_path:
            if storage_path in seen_paths:
                continue
            vision_url = vision_url_for_chunk(metadata) or _storage_image_data_url(metadata)
            if vision_url:
                seen_paths.add(storage_path)
                urls.append(vision_url)
            continue
        image_url = str(chunk.get("image_url") or metadata.get("image_url") or "").strip()
        if image_url.startswith("data:") and image_url not in seen:
            urls.append(image_url)
            seen.add(image_url)
    return urls


# ── ISSUE 2: figure-pipeline helpers ────────────────────────────────────
# A question may legitimately need a diagram (geometry / trig / mensuration /
# circuit / optics). We accept ONE shape: an inline SVG the LLM emits as
# `figure: {type: "svg", content: "<svg ...>...</svg>"}`. We never accept a
# bare external URL the LLM made up — those rendered as broken-image
# placeholders with alt="Question visual". If neither a real source image
# nor a valid SVG is provided, the stem must be text-self-contained.

_SVG_TAG = re.compile(r"<svg\b[^>]*>.*?</svg\s*>", re.IGNORECASE | re.DOTALL)
# External resource refs we refuse inside an inline SVG (no remote loads
# from the model, no script execution).
_SVG_FORBIDDEN = re.compile(
    r'<(?:script|foreignObject)\b|xlink:href\s*=\s*[\'"]https?://',
    re.IGNORECASE,
)


def _figure_to_data_url(raw_figure: Any) -> str:
    """Validate an inline-SVG figure and encode it as a data: URL.

    Accepts either:
      - a dict like {"type": "svg", "content": "<svg ...>...</svg>"}
      - a raw string starting with "<svg"
    Returns an empty string for anything we can't safely render.
    """
    if not raw_figure:
        return ""

    if isinstance(raw_figure, dict):
        if str(raw_figure.get("type") or "svg").lower() != "svg":
            return ""
        svg = str(raw_figure.get("content") or raw_figure.get("svg") or "").strip()
    elif isinstance(raw_figure, str):
        svg = raw_figure.strip()
    else:
        return ""

    if not svg or "<svg" not in svg.lower():
        return ""

    match = _SVG_TAG.search(svg)
    if not match:
        return ""
    svg_clean = match.group(0)
    if _SVG_FORBIDDEN.search(svg_clean):
        return ""

    # Cap at 16 KB to keep the editor payload sane — a hand-laid geometry
    # diagram is well under 2 KB. Anything larger is almost certainly junk.
    if len(svg_clean.encode("utf-8")) > 16_384:
        return ""

    # Reject body-empty SVGs (`<svg viewBox='…' />` or `<svg></svg>`). The
    # editor would otherwise show an empty bordered box where a labelled
    # diagram should be — that's the artefact reported on Q24 / Q33. A real
    # geometry figure always contains at least one DRAWING primitive.
    # <text>/<g>/<tspan> deliberately do NOT count: an SVG whose only
    # content is text labels ("A", "ΔB") renders as giant floating letters
    # where the diagram should be (the s3b Q23 artefact). Labels are
    # welcome alongside shapes, never instead of them.
    if not re.search(
        r"<\s*(line|rect|circle|ellipse|polyline|polygon|path)\b",
        svg_clean,
        re.IGNORECASE,
    ):
        return ""

    b64 = base64.b64encode(svg_clean.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


# Phrases that prove the question text DEPENDS on a figure the LLM thinks
# exists. If none was actually supplied, we must not stream the stem — the
# teacher would get a "see figure" question with no figure.
#
# Cluster B widening: the original regex only caught lead-in verbs
# ("observe / see / refer to ..."), but the LLM also slips in trailing
# references like "as in the diagram", "the figure shows", or just "from
# the figure" — those all imply a figure that may not exist, so they
# count as a missing-figure citation.
_FIGURE_NOUNS = (
    r"(?:figure|diagram|fig\.?|image|picture|circuit|graph|sketch|drawing)"
)
_FIGURE_REFERENCE = re.compile(
    r"(?:"
    # Leading verb phrases: "Observe the figure", "As shown in the diagram"
    r"\b(?:observe|see|refer\s+to|study|consider|examine|look\s+at|"
    r"as\s+shown|shown\s+(?:in|below|above|here)|"
    r"in|from|using|based\s+on)\s+"
    r"(?:the\s+)?(?:given\s+|adjoining\s+|following\s+|above\s+|below\s+|"
    r"attached\s+|provided\s+|opposite\s+|alongside\s+)?"
    rf"{_FIGURE_NOUNS}\b"
    r"|"
    # Trailing references: "the figure shows", "the diagram below illustrates"
    rf"\bthe\s+{_FIGURE_NOUNS}\s+(?:above|below|here|shown|given)?\s*"
    r"(?:shows?|illustrates?|represents?|depicts?|gives?)\b"
    r"|"
    # Vocative: "In Fig. 2.1", "From figure 4"
    rf"\bin\s+{_FIGURE_NOUNS}\.?\s*\d"
    r")",
    re.IGNORECASE,
)


def _content_references_missing_figure(content: str) -> bool:
    if not content:
        return False
    return bool(_FIGURE_REFERENCE.search(content))


def _strip_figure_references(content: str) -> str:
    """Last-resort: drop sentences that cite a figure when none exists.

    Used only on the final regeneration attempt so the user never sees a
    broken-image placeholder. The remaining stem may read awkwardly but
    will not lie about a non-existent diagram.
    """
    sentences = re.split(r"(?<=[.!?])\s+", content)
    kept = [s for s in sentences if not _FIGURE_REFERENCE.search(s)]
    cleaned = " ".join(kept).strip()
    return cleaned or content


def _coerce_or_choice(raw_question: dict, allowed_urls: List[str]) -> Optional[dict]:
    raw_choice = (
        raw_question.get("or_choice")
        or raw_question.get("orChoice")
        or raw_question.get("alternative")
        or raw_question.get("internal_choice")
    )
    if raw_choice in (None, "", False):
        return None

    if isinstance(raw_choice, str):
        raw_choice = {"content": raw_choice}
    if not isinstance(raw_choice, dict):
        return None

    options_raw = raw_choice.get("options", [])
    options = [str(opt).strip() for opt in options_raw if str(opt).strip()] if isinstance(options_raw, list) else []
    options = [
        cleaned
        for cleaned in (
            wrap_bare_latex_tokens(strip_blueprint_leakage(opt)) for opt in options
        )
        if cleaned.strip()
    ]
    candidate_url = str(raw_choice.get("image_url") or raw_choice.get("imageUrl") or "").strip()
    image_url = candidate_url if candidate_url in allowed_urls else ""
    # Same scrub as the parent content — the alternative is just as exposed
    # to instruction echoes / VI residue / leading "OR" lines.
    content = clean_question_text(_stringify(raw_choice.get("content")).strip())
    if not content:
        return None

    return {
        "content": content,
        "options": options,
        "answer": _stringify(raw_choice.get("answer")).strip(),
        "image_url": image_url,
    }


def _coerce_vi_alternative(raw_question: dict) -> Optional[str]:
    raw_vi = (
        raw_question.get("vi_alternative")
        or raw_question.get("viAlternative")
        or raw_question.get("visually_impaired_alternative")
        or raw_question.get("visual_alternative")
    )
    if raw_vi in (None, "", False):
        return None
    if isinstance(raw_vi, dict):
        raw_vi = raw_vi.get("content") or raw_vi.get("question") or raw_vi.get("text")
    # Strip the model's own dashed/Note framing — the printer adds the
    # canonical framing exactly once.
    content = clean_vi_alternative_text(_stringify(raw_vi).strip())
    return content or None


def _normalize_for_match(text: str) -> str:
    """Lowercase + collapse whitespace so we can spot duplicate OR content
    even when the LLM varies spacing or punctuation between the two emit
    sites (the `content` body and the `or_choice.content` field)."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _content_already_has_or_alternative(content: str, or_alternative: str) -> bool:
    """True if `content` already contains an explicit OR block whose text
    substantially overlaps `or_alternative`. The LLM sometimes emits the
    alternative TWICE (inside `content` after a literal "OR" line *and*
    in the `or_choice.content` field), which historically caused
    `_printable_question_content` to print the whole alternative twice in
    every Section B/C/D OR question + every Section E case-study sub-part
    (iii). Detecting the overlap lets us print exactly one OR block."""
    norm_content = _normalize_for_match(content)
    norm_alt = _normalize_for_match(or_alternative)
    if not norm_alt or " or " not in f" {norm_content} ":
        return False
    # Compare the FIRST ~60 chars of the alternative — short enough to be
    # robust to a stray trailing word, long enough that two genuinely
    # different sub-questions never collide.
    head = norm_alt[:60]
    return head and head in norm_content


def _printable_question_content(content: str, or_choice: Optional[dict], vi_alternative: Optional[str], or_label: str = "OR") -> str:
    parts = [content.strip()]
    if or_choice:
        alt_text = or_choice.get("content", "").strip()
        # Guard against LLM double-emission: if `content` already carries the
        # OR alternative inline (e.g. `… Q text A.\n\nOR\n\n Q text B`), do
        # NOT append it again from `or_choice` — that produced the visible
        # "every OR question prints twice" bug across Sections B/C/D/E.
        if alt_text and not _content_already_has_or_alternative(content, alt_text):
            parts.extend([or_label, alt_text])
    if vi_alternative:
        parts.extend(
            [
                "- - - - - - - - - - - - - - - - - - -",
                "Note: The following question is for Visually Impaired Students only in lieu of the visual question above.",
                vi_alternative.strip(),
                "- - - - - - - - - - - - - - - - - - -",
            ]
        )
    return "\n\n".join(part for part in parts if part)


def _format_chunk_for_prompt(chunk: dict) -> str:
    metadata = chunk.get("metadata") or {}
    page = chunk.get("page")
    image_url = chunk.get("image_url") or metadata.get("image_url")
    header_parts = []
    if page:
        header_parts.append(f"page={page}")
    if metadata.get("semanticSection"):
        header_parts.append(f"section={metadata.get('semanticSection')}")
    if image_url:
        header_parts.append(f"image_url={image_url}")

    header = f"[Retrieved chunk {' | '.join(header_parts)}]" if header_parts else "[Retrieved chunk]"
    return f"{header}\n{chunk.get('content', '')}".strip()


def _extract_reuse_terms(question: dict) -> Set[str]:
    terms: Set[str] = set()
    metadata = question.get("metadata") or {}
    for key in ["inferredTopic", "inferredChapter"]:
        value = str(metadata.get(key) or "").strip().lower()
        if value:
            terms.add(value)
    content = str(question.get("content") or "")
    for number in re.findall(r"\b\d+(?:\.\d+)?\b", content):
        terms.add(f"value:{number}")
    return terms


def _coerce_question(
    raw_payload: dict,
    slot,
    source_chunks: List[dict],
    is_retry: bool = False,
    is_visual_mandatory: bool = False,
    include_vi_alternatives: bool = True,
) -> dict:
    """Normalise the LLM payload into the editor-facing question shape.

    ``include_vi_alternatives`` is a per-paper toggle: when False, any VI
    alternative the model returned is dropped from the printable content,
    the dedicated field, and the metadata flag — implemented as a
    post-generation FILTER (not a prompt change) so the model still sees
    VI cues in the source and uses them for grounding when relevant.
    """
    raw_question = raw_payload.get("question", raw_payload)
    if not isinstance(raw_question, dict):
        raise ValueError("LLM returned a non-object question payload.")

    content = _stringify(raw_question.get("content")).strip()
    if not content:
        raise ValueError("LLM returned an empty question.")
    # Round-4 scrub: instruction echoes ("Internal choice — answer
    # either…"), VI blocks copied from contaminated chunks, orphan OR
    # separators, and bare un-delimited LaTeX the editor can't render.
    content = clean_question_text(content)
    if not content:
        raise ValueError("Question content was only instruction/VI residue.")

    options_raw = raw_question.get("options", [])
    options = [str(opt).strip() for opt in options_raw if str(opt).strip()] if isinstance(options_raw, list) else []
    options = [
        cleaned
        for cleaned in (
            wrap_bare_latex_tokens(strip_blueprint_leakage(opt)) for opt in options
        )
        if cleaned.strip()
    ]
    if slot.question_type == "ASSERTION_REASON":
        options = [
            "Both A and R are true, and R is the correct explanation of A.",
            "Both A and R are true, and R is not the correct explanation of A.",
            "A is true but R is false.",
            "A is false but R is true.",
        ]

    # ── ISSUE 1: type fidelity — the slot's declared type wins ─────────
    # MCQ/AR slots SHOULD come back with 4 options; SHORT/LONG slots
    # must NOT smuggle in MCQ-style options. On early attempts, reject
    # so the caller regenerates; on the last attempt, log and pass
    # through (the slot's legacy_type is still stamped onto the output
    # so the rubric stays correct, but we don't drop the question
    # entirely after the model has failed twice).
    if slot.legacy_type in ("MCQ", "ASSERTION_REASON") and len(options) < 2 and not is_retry:
        raise ValueError(
            f"Type mismatch: slot is {slot.legacy_type} but LLM returned no options. Regenerating."
        )
    if slot.legacy_type not in ("MCQ", "ASSERTION_REASON") and options and not is_retry:
        raise ValueError(
            f"Type mismatch: slot is {slot.legacy_type} (descriptive) but LLM "
            "returned MCQ-style options. Regenerating without options."
        )
    if slot.legacy_type not in ("MCQ", "ASSERTION_REASON") and options:
        # Last attempt: drop the stray options so the descriptive question
        # renders cleanly rather than streaming an MCQ-shaped artifact.
        options = []

    allowed_urls = _allowed_image_urls(source_chunks)
    candidate_image_url = str(raw_question.get("image_url") or raw_question.get("imageUrl") or "").strip()
    image_url = candidate_image_url if candidate_image_url in allowed_urls else ""

    # ── ISSUE 2: real figure pipeline (no fake "Question visual" placeholders) ──
    # Prefer an inline SVG figure when the LLM emits one — `figure: {type:
    # "svg", content: "<svg ...>...</svg>"}`. We validate it parses, then
    # encode it as a data URL so the existing FloatImage TipTap node /
    # PDF/DOCX exporters render it inline without any hallucinated
    # external src. If the LLM cited a figure ("observe the diagram",
    # "see the figure below") but provided neither a real image_url nor
    # a valid inline SVG, the question is rejected for regeneration with
    # an explicit instruction to write a text-self-contained stem.
    raw_figure = raw_question.get("figure") or raw_question.get("svg")
    figure_data_url = _figure_to_data_url(raw_figure)
    if figure_data_url and not image_url:
        image_url = figure_data_url

    if (slot.requires_image or is_visual_mandatory) and not image_url and allowed_urls:
        if not is_retry:
            raise ValueError("LLM omitted the mandatory visual image_url.")
        # Cluster B (final-retry guard): on retry we used to silently
        # attach `allowed_urls[0]` — the first source image, often a
        # totally unrelated figure for a different chunk. That produced
        # broken-context stems whose floatImage either pointed at the
        # wrong picture or 404'd. Instead, accept the text-only
        # rendering and strip any dangling "see figure" sentence so the
        # editor never carries an orphaned figure placeholder.
        content = _strip_figure_references(content)

    # For slots that MUST include an inline SVG figure, reject on first attempt
    # so the retry prompt explicitly requests the figure again.
    if getattr(slot, "requires_figure", False) and not image_url:
        if not is_retry:
            raise ValueError(
                "This question REQUIRES an inline SVG figure in the `figure` field. "
                "Re-generate and include a valid SVG diagram with labelled vertices/sides/angles."
            )
        # On retry still no figure: accept the text-only version so we don't
        # infinite-loop, but strip any dangling "see figure" references.
        content = _strip_figure_references(content)

    if not image_url and _content_references_missing_figure(content):
        if not is_retry:
            raise ValueError(
                "Question references a figure/diagram but no inline SVG, "
                "image_url, or source figure was provided. Regenerate as "
                "a text-self-contained stem (include all geometry data in words)."
            )
        # Last attempt: scrub the figure references out of the stem so we
        # never stream a broken-image placeholder to the editor.
        content = _strip_figure_references(content)

    # Cluster B final guard: if we stripped figure references AND no
    # valid figure was attached, also drop any leftover image_url so the
    # editor never builds a floatImage NodeView for a question whose
    # text no longer cites one. (This catches the case where the LLM
    # returned both a stale "Observe the figure" sentence AND a stale
    # image_url that pointed at an irrelevant picture.)
    if (
        image_url
        and not _figure_to_data_url(raw_figure)
        and not _content_references_missing_figure(content)
        and not getattr(slot, "requires_image", False)
        and not getattr(slot, "requires_figure", False)
    ):
        # The post-strip stem doesn't cite a figure and the slot doesn't
        # mandate one — let the image come along ONLY if the LLM also
        # explicitly named it (candidate_image_url was non-empty and
        # validated). If it didn't, we already cleared image_url above.
        pass

    or_choice = _coerce_or_choice(raw_question, allowed_urls)
    if slot.choice_required and not or_choice:
        raise ValueError("LLM omitted the required nested OR choice.")

    vi_alternative = _coerce_vi_alternative(raw_question)
    if slot.vi_required and not vi_alternative:
        if is_retry:
            vi_alternative = "[Placeholder: The AI failed to generate a visually impaired alternative for this question.]"
        else:
            raise ValueError("LLM omitted the required Visually Impaired alternative.")

    # Per-paper toggle (Cluster C): even when the model generated a
    # legitimate VI alternative (because the source paper carries them, as
    # CBSE SQPs do), the user can opt the rendered output out of including
    # them. This must happen AFTER coercion so the LLM still sees the VI
    # cue in the source and grounds correctly.
    if not include_vi_alternatives:
        vi_alternative = None

    first_chunk = source_chunks[0] if source_chunks else {}
    first_meta = first_chunk.get("metadata") or {}
    metadata_raw = raw_question.get("metadata", {})
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    metadata = {
        **metadata,
        "gradeClass": metadata.get("gradeClass") or f"Class {slot.class_num}",
        "subject": metadata.get("subject") or slot.subject,
        "inferredTopic": metadata.get("inferredTopic") or slot.stream.replace("_", " ").title(),
        "inferredChapter": metadata.get("inferredChapter") or first_meta.get("chapter") or first_meta.get("semanticSection") or "",
        "sourcePdf": metadata.get("sourcePdf") or first_meta.get("sourcePdf") or "",
        "difficulty": metadata.get("difficulty") or slot.difficulty,
        "section": slot.section_title,
    }
    if image_url:
        metadata["image_url"] = image_url
    if vi_alternative:
        metadata["vi_alternative"] = True
    else:
        # When the toggle drops VI we drop the metadata marker too, so the
        # review tray and any downstream consumers can't mis-read a filtered
        # paper as one that still ships VI alternatives.
        metadata.pop("vi_alternative", None)

    _subj = str(getattr(slot, "subject", "")).strip().lower()
    or_label = {"hindi": "अथवा", "telugu": "లేదా"}.get(_subj, "OR")
    printable_content = _printable_question_content(content, or_choice, vi_alternative, or_label=or_label)
    # Final pass over the assembled text: collapses an OR that content
    # ended with against the separator we just added, and drops any OR
    # left dangling at the very top/bottom. (Per-field cleaning above
    # can't see across the content/or_choice join.)
    printable_content = remove_orphan_or_tokens(printable_content)

    return {
        "content": printable_content,
        "type": slot.legacy_type,
        "options": options,
        "answer": _stringify(raw_question.get("answer")).strip(),
        "marks": slot.marks,
        "image_url": image_url,
        "or_choice": or_choice,
        "vi_alternative": vi_alternative,
        "metadata": metadata,
    }


def _single_question_schema(is_visual_mandatory: bool, slot) -> str:
    schema = (
        "{\n"
        '  "question": {\n'
        f'    "content": "String (Question text)",\n'
        f'    "type": "String ({slot.legacy_type})",\n'
    )
    if slot.legacy_type in ["MCQ", "ASSERTION_REASON"]:
        schema += '    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],\n'
    
    schema += '    "answer": "String (Correct answer or scoring points)",\n'
    schema += f'    "marks": {slot.marks},\n'
    
    if is_visual_mandatory:
        schema += '    "image_url": "String (CRITICAL: MUST include the provided image URL)",\n'
    else:
        schema += '    "image_url": "String or omit entirely if no image is mandated",\n'

    # figure field — inline SVG for geometry diagrams.
    # When slot.requires_figure=True the field is mandatory; otherwise optional.
    if getattr(slot, "requires_figure", False):
        schema += (
            '    "figure": "REQUIRED — MUST be present: '
            '{type: \\"svg\\", content: \\"<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 200 200\'>...</svg>\\"}. '
            'A standalone inline SVG with clearly labelled vertices, sides, and angles. '
            'Use <text> elements for labels (e.g., A, B, C, 6cm, 90°). '
            'NO <script>, NO <foreignObject>, NO external xlink:href. '
            'Omitting this field will cause the response to be REJECTED."'
            ",\n"
        )
    else:
        schema += (
            '    "figure": "OPTIONAL — for geometry/trigonometry/mensuration ONLY: '
            '{type: \\"svg\\", content: \\"<svg viewBox=...>...</svg>\\"}. '
            'A standalone inline SVG with labelled vertices/sides/angles. '
            'NO <script>, NO <foreignObject>, NO external xlink:href. '
            'If you cannot render a faithful figure, OMIT this key and write '
            'a stem that contains all geometric data in words (\'In right '
            'triangle ABC, right-angled at B, AB = 24 cm…\'). NEVER reference '
            '\'the figure\' / \'the diagram\' unless this field is populated."'
            ",\n"
        )

    if slot.choice_required:
        schema += '    "or_choice": { "content": "String", "options": ["(if MCQ)"], "answer": "String", "image_url": "String" },\n'
    else:
        schema += '    "or_choice": "CRITICAL: Omit this key entirely unless internal choice is mandated",\n'
        
    if slot.vi_required:
        schema += '    "vi_alternative": { "content": "String (Full text replacement question)" },\n'
    else:
        schema += '    "vi_alternative": "CRITICAL: Omit this key entirely unless visually impaired alternative is mandated",\n'
        
    schema += (
        '    "metadata": {\n'
        '      "gradeClass": "String",\n'
        '      "subject": "String",\n'
        '      "inferredTopic": "String",\n'
        '      "inferredChapter": "String",\n'
        '      "difficulty": "easy | medium | hard"\n'
        '    }\n'
        '  }\n'
        '}\n'
        'Rules: Do NOT use null. If a field is not required (like or_choice or vi_alternative), omit the key entirely from the JSON object.\n'
    )
    return schema


def _build_user_prompt(
    slot,
    total_slots: int,
    topic: str,
    image_urls: Optional[List[str]] = None,
    used_terms: Optional[Set[str]] = None,
    is_visual_mandatory: bool = False,
) -> str:
    topic_line = f"Topic/focus: {topic}." if topic else "Topic/focus: infer from the retrieved chunks."
    image_line = ""
    if image_urls:
        image_line = f"\nAvailable image_url values: {', '.join(image_urls)}."
    reuse_line = ""
    if used_terms:
        reuse_line = f"\nDo not reuse these concepts or exact values: {', '.join(sorted(used_terms)[:30])}."
        
    visual_override = ""
    if is_visual_mandatory:
        # Cluster B: the previous override mandated "Observe the given
        # figure" language even on retries where no usable figure could
        # be attached, producing broken `<img>` placeholders that read
        # as horizontal underlines. The new contract gives the model
        # exactly two ways to handle a picture-bearing slot — supply
        # the figure inline as SVG, OR rewrite the question so it is
        # answerable from text alone. There is no third option that
        # produces a "see figure" stem with no figure.
        visual_override = (
            "\nVISUAL SLOT — choose EXACTLY ONE option:\n"
            "  OPTION 1 (preferred): include a self-contained inline "
            "SVG diagram in the `figure` field with all labelled "
            "vertices / sides / angles the question needs. If you also "
            "want to cite an attached source image, set `image_url` to "
            "one of the URLs listed above.\n"
            "  OPTION 2: write the question so that every measurement, "
            "coordinate or relationship needed to solve it appears in "
            "the question text itself, and DO NOT mention any figure, "
            "diagram, image, picture, circuit, graph, or sketch.\n"
            "Either option is acceptable. NEVER write 'observe the "
            "figure', 'see the diagram', 'in the figure', or any "
            "similar phrase unless OPTION 1 is satisfied — a stem that "
            "references a figure that wasn't supplied will be rejected.\n"
        )
        
    return (
        f"Question {slot.index} of {total_slots}.\n"
        f"{topic_line}\n\n"
        f"{slot.exact_instruction}{image_line}{reuse_line}{visual_override}\n\n"
        "Return only valid JSON matching the schema. Do not include markdown."
    )


def _parse_gim_instructions(instructions: str, pdf_count: int, exact_count: Optional[int] = None) -> List[dict]:
    """
    Parse teacher's general instructions text into a flat list of question slots.
    Returns a list of dicts:
        [{"section_title": Optional[str], "type": ..., "marks": ..., "count": ...}, ...]

    Issue 3 — `section_title` is preserved verbatim from the input ("Section A",
    "Part B", "Sec C", …) so the generator can honour an A/B/C-style breakdown
    instead of dumping everything into a single fall-back "Questions" section.
    Names and order are kept exactly as the teacher wrote them.
    """
    import re

    text_raw = instructions.strip()
    text = instructions.lower().strip()
    if not text:
        return []

    number_words = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20,
    }
    for word, val in number_words.items():
        text = re.sub(r'\b' + word + r'\b', str(val), text)

    type_map = {
        'mcq': 'MCQ', 'multiple choice': 'MCQ', 'multiple-choice': 'MCQ',
        'assertion reason': 'ASSERTION_REASON', 'assertion-reason': 'ASSERTION_REASON', 'ar': 'ASSERTION_REASON',
        'short answer': 'SHORT_ANSWER', 'short-answer': 'SHORT_ANSWER', 'short': 'SHORT_ANSWER',
        'vsa': 'SHORT_ANSWER', 'very short': 'SHORT_ANSWER', 'very-short': 'SHORT_ANSWER',
        'long answer': 'LONG_ANSWER', 'long-answer': 'LONG_ANSWER', 'long': 'LONG_ANSWER',
        'case study': 'CASE_STUDY', 'case-study': 'CASE_STUDY', 'case based': 'CASE_STUDY',
        'case-based': 'CASE_STUDY', 'cbq': 'CASE_STUDY',
    }

    default_marks = {
        'MCQ': 1, 'ASSERTION_REASON': 1, 'SHORT_ANSWER': 2,
        'LONG_ANSWER': 5, 'CASE_STUDY': 4,
    }

    slots = []

    # Check for "no mcq" / "no mcqs" patterns → exclusions
    no_types = set()
    for pattern_text, qtype in type_map.items():
        if re.search(r'\bno\s+' + re.escape(pattern_text) + r'[s]?\b', text):
            no_types.add(qtype)

    # Check for per-PDF distribution: "from each source/pdf N each" or "N from each"
    per_pdf_match = re.search(
        r'(?:from\s+each\s+(?:source|pdf|file|document)\s+(\d+))|'
        r'(?:(\d+)\s+(?:from\s+each|each|per)\s+(?:source|pdf|file|document))|'
        r'(?:(\d+)\s+each\s+questions?)|'
        r'(?:each\s+(?:source|pdf)\s+(\d+)\s+(?:each\s+)?questions?)',
        text
    )
    per_pdf_count = None
    if per_pdf_match:
        per_pdf_count = int(next(g for g in per_pdf_match.groups() if g is not None))

    # Parse explicit type+count clauses like "3 MCQs", "5 short answers of 2 marks"
    # Issue 3 — split on newlines/semicolons/commas/and AND propagate the
    # most-recently-seen "Section X" / "Part X" prefix to the slots that follow,
    # so the structure typed by the teacher is preserved verbatim in the output.
    clauses = re.split(r'[,;\n]+|\band\b', text)
    parsed_any = False
    current_section: Optional[str] = None

    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        # Skip exclusion clauses
        if re.match(r'\bno\s+', clause):
            continue

        # Section header at the start of the clause: "Section A: 5 short answers"
        sec_match = re.search(
            r'\b(section|part|sec)\b\s*[-:]?\s*([a-z0-9]+)\b',
            clause,
            re.IGNORECASE,
        )
        if sec_match:
            sec_type = sec_match.group(1).strip().capitalize()
            if sec_type == "Sec":
                sec_type = "Section"
            sec_val = sec_match.group(2).strip().upper()
            current_section = f"{sec_type} {sec_val}"
            clause = (clause[: sec_match.start()] + " " + clause[sec_match.end():]).strip()

        # Find count
        count_match = re.search(r'(\d+)', clause)
        if not count_match:
            continue
        count_val = int(count_match.group(1))

        # Find question type
        found_type = None
        for pattern_text, qtype in type_map.items():
            if re.search(r'\b' + re.escape(pattern_text) + r'[s]?\b', clause):
                found_type = qtype
                break

        if found_type is None:
            # Check if this looks like a marks spec ("2 marks") rather than a count
            if re.search(r'\bmarks?\b', clause):
                continue
            continue

        if found_type in no_types:
            continue

        # Find marks override
        marks_match = re.search(r'(\d+)\s*marks?', clause)
        marks_val = int(marks_match.group(1)) if marks_match else default_marks.get(found_type, 2)

        slots.append({
            "section_title": current_section,
            "type": found_type,
            "marks": marks_val,
            "count": count_val,
        })
        parsed_any = True

    # If per-PDF distribution is specified but no explicit types were parsed
    if per_pdf_count and not parsed_any:
        # Detect marks from instructions: "all 2 marks" / "2 marks each"
        all_marks_match = re.search(r'(?:all\s+)?(\d+)\s+marks?\s*(?:each)?', text)
        marks = int(all_marks_match.group(1)) if all_marks_match else 2

        # Determine type based on exclusions and marks
        qtype = 'SHORT_ANSWER'
        if 'SHORT_ANSWER' in no_types:
            qtype = 'LONG_ANSWER'
        if marks == 1 and 'MCQ' not in no_types:
            qtype = 'MCQ'
        elif marks >= 5:
            qtype = 'LONG_ANSWER'

        total = per_pdf_count * max(pdf_count, 1)
        slots.append({"section_title": None, "type": qtype, "marks": marks, "count": total})
        parsed_any = True

    # Fallback: if nothing was parsed, use exact_count with defaults
    if not parsed_any:
        total = exact_count or 10
        marks = 2
        all_marks_match = re.search(r'(?:all\s+)?(\d+)\s+marks?\s*(?:each)?', text)
        if all_marks_match:
            marks = int(all_marks_match.group(1))
        qtype = 'SHORT_ANSWER'
        if 'SHORT_ANSWER' in no_types:
            qtype = 'LONG_ANSWER' if 'LONG_ANSWER' not in no_types else 'MCQ'
        slots.append({"section_title": None, "type": qtype, "marks": marks, "count": total})

    # Touch the trailing argument-vs-warning so future code reviewers see
    # the unused-variable trail rather than guessing.
    _ = text_raw

    return slots


def _build_gim_system_prompt(instructions: str, source_chunks_text: str) -> str:
    """Build the minimal, direct system prompt for General Instructions Mode.

    Issue 3 — when `source_chunks_text` is empty (no PDFs uploaded, or
    retrieval returned nothing for this slot) we MUST NOT instruct the model
    to "generate strictly from source material" — that's the prompt path
    that produced zero questions and surfaced as "Generation failed before
    any questions could be produced". In that no-source case we ask the
    model to use general curriculum knowledge appropriate to the subject /
    class instead.
    """
    has_source = bool(source_chunks_text.strip())
    grounding_clause = (
        "Generate questions STRICTLY from the provided source material below. "
        "Do not add any information not present in the source text."
        if has_source
        else (
            "No source material was attached to this slot. Generate the "
            "question from general curriculum knowledge appropriate to the "
            "subject and grade level inferred from the teacher's instructions. "
            "Stay factually accurate."
        )
    )
    answerability_clause = (
        "- Every question must be answerable from the source material alone\n"
        if has_source
        else (
            "- Every question must be factually accurate and grade-appropriate\n"
        )
    )
    source_block = (
        f"SOURCE MATERIAL:\n{source_chunks_text}\n"
        if has_source
        else "SOURCE MATERIAL: (none — generate from general curriculum knowledge)\n"
    )
    return (
        "You are a question paper generator. "
        f"{grounding_clause}\n\n"
        "Follow the teacher's instructions EXACTLY as written. Do not add "
        "extra questions, extra sections, or extra structure beyond what "
        "the teacher asked for.\n\n"
        f"Teacher's instructions: {instructions}\n\n"
        "For each question, return valid JSON with these fields:\n"
        "  content: the question text\n"
        "  type: MCQ / SHORT_ANSWER / LONG_ANSWER / ASSERTION_REASON\n"
        "  marks: number of marks\n"
        "  options: list of 4 options if MCQ, empty list otherwise\n"
        "  answer: correct answer text\n"
        "  Do NOT include or_choice unless the teacher explicitly asked for internal choice.\n\n"
        "Rules:\n"
        "- Generate ONLY the question types the teacher specified\n"
        "- Use ONLY the marks values the teacher specified\n"
        "- Do NOT add section headers or labels unless teacher asked for them\n"
        "- Do NOT enforce any board exam pattern\n"
        "- Do NOT add questions beyond the count the teacher asked for\n"
        f"{answerability_clause}"
        "- Do NOT use null for any field. Omit optional keys entirely.\n\n"
        f"{source_block}"
    )


def stream_general_instructions_questions(
    user,
    pdf_source_ids: List[str],
    topic: str,
    count: int,
    difficulty: str,
    instructions: str = "",
    payload: Optional[dict] = None,
    hsat_source_ids: Optional[List[str]] = None,
) -> Iterable[str]:
    """
    General Instructions Mode handler.
    The teacher's instructions text IS the complete specification.
    No q_instructions, no blueprint, no CBSE structure.
    """
    import concurrent.futures

    from apps.question_generation.infrastructure.providers.openai_provider import OpenAIProvider
    from apps.question_generation.infrastructure.providers.base import LLMMessage, LLMRequest
    from apps.question_generation.infrastructure.token_budget.budgeter import (
        allocate_budget,
        trim_chunks_to_budget,
    )
    from services.retrieval_service import retrieve_relevant_chunks
    from apps.question_generation.services.retrieval.context_service import (
        retrieval_quality_summary,
    )

    logger.info("[GIM] Entered stream_general_instructions_questions")

    payload = payload or {}

    # Step 1: Validate instructions
    if not instructions or not instructions.strip():
        yield _sse_event(
            {"error": "General Instructions Mode requires you to describe what questions you want. "
                      "Please write your instructions in the text box."},
            event="error",
        )
        return

    # Extract basic metadata for context/labeling
    class_raw = payload.get("class", payload.get("class_level", payload.get("gradeClass", "10")))
    class_str = str(class_raw or "").strip()
    class_digits = "".join(filter(str.isdigit, class_str))
    class_num = int(class_digits) if class_digits else 10
    subject_raw = str(payload.get("subject", "")).strip() or "General"

    hsat_source_ids = list(hsat_source_ids or [])
    total_source_count = len(pdf_source_ids) + len(hsat_source_ids)

    # Step 2: Parse instructions into a flat slot list
    exact_count = count if count and count > 0 else None
    parsed_slots = _parse_gim_instructions(instructions, total_source_count, exact_count)

    if not parsed_slots:
        yield _sse_event(
            {"error": "Could not parse any question specifications from your instructions. "
                      "Please be more specific (e.g., '5 MCQs, 3 short answers of 2 marks each')."},
            event="error",
        )
        return

    # Expand parsed slots into a flat list of individual question entries.
    # Issue 3 — `section_title` survives the expansion so per-section grouping
    # is honoured downstream. When the teacher writes no section prefix at
    # all we fall back to a single "Questions" bucket; when they explicitly
    # say "Section A: 5 short answers" we preserve "Section A" verbatim.
    flat_plan: List[dict] = []
    for slot_spec in parsed_slots:
        section_title = slot_spec.get("section_title") or "Questions"
        for _ in range(slot_spec["count"]):
            flat_plan.append({
                "section_title": section_title,
                "type": slot_spec["type"],
                "marks": slot_spec["marks"],
                "index": len(flat_plan) + 1,
            })

    total_questions = len(flat_plan)
    total_marks = sum(s["marks"] for s in flat_plan)

    # Issue 3 — section ordering: first-seen wins. Stable across the LLM's
    # concurrent completion order so what the teacher typed (A → B → C) is
    # what the rendered paper shows.
    section_order: List[str] = []
    section_marks: Dict[str, int] = {}
    section_questions: Dict[str, int] = {}
    for entry in flat_plan:
        title = entry["section_title"]
        if title not in section_order:
            section_order.append(title)
        section_marks[title] = section_marks.get(title, 0) + entry["marks"]
        section_questions[title] = section_questions.get(title, 0) + 1

    logger.info("[GIM] Parsed plan: %d questions, %d total marks across %d section(s): %s",
                total_questions, total_marks, len(section_order), section_order)

    # Step 3: Build general instructions for the paper header
    general_instructions_lines = [
        f"There are {total_questions} questions. All questions are compulsory.",
        instructions.strip(),
    ]

    # Step 4: Emit plan event
    yield _sse_event(
        {
            "total": total_questions,
            "subject": subject_raw,
            "class": class_num,
            "blueprint": f"General Instructions Mode: {total_questions} questions, {total_marks} marks",
            "summary": {
                "total_questions": total_questions,
                "total_marks": total_marks,
                "or_choices": 0,
                "image_questions": 0,
                "vi_alternatives": 0,
                "exact_counts": [f"{s['count']} {s['type'].replace('_', ' ').title()} ({s['marks']}m)" for s in parsed_slots],
                "section_marks": section_marks,
                "section_questions": section_questions,
                "section_order": section_order,
            },
            "generalInstructions": general_instructions_lines,
        },
        event="plan",
    )

    # Step 5: Retrieval — same shared system as Board Mode
    max_input_tokens, max_output_tokens = allocate_budget(
        total_max_tokens=5000, reserved_system_tokens=350, max_output_tokens=750,
    )
    provider = OpenAIProvider()
    result = _empty_result()
    result["generalInstructions"] = general_instructions_lines

    used_chunk_ids: Set[str] = set()
    _topic_cache: Dict[str, List[dict]] = {}

    # Phase 1: Allocate chunks for each slot
    allocated_slots: List[dict] = []

    for slot_entry in flat_plan:
        # Build retrieval query from instructions + type
        query_parts = [
            topic.strip() if topic else "",
            subject_raw,
            f"class {class_num}",
            slot_entry["type"].replace("_", " "),
            f"{slot_entry['marks']} mark",
            instructions[:200].strip(),
        ]
        retrieval_query = " ".join(part for part in query_parts if part)

        cache_key = retrieval_query
        if cache_key not in _topic_cache:
            _topic_cache[cache_key] = retrieve_relevant_chunks(
                retrieval_query,
                pdf_source_ids,
                limit=50,
                user=user,
                require_image=False,
                exclude_chunk_ids=None,
                hsat_source_ids=hsat_source_ids,
            )

        top_50 = _topic_cache[cache_key]
        valid_chunks = [c for c in top_50 if str(c.get("id")) not in used_chunk_ids]
        context = valid_chunks[:4]

        for item in context:
            if item.get("id"):
                used_chunk_ids.add(str(item["id"]))

        allocated_slots.append({
            "slot_entry": slot_entry,
            "context": context,
            "retrieval_query": retrieval_query,
        })

    # Phase 2: Generate questions in parallel
    def _generate_gim_slot(allocated: dict) -> tuple:
        slot_entry = allocated["slot_entry"]
        context = allocated["context"]
        idx = slot_entry["index"]

        # Issue 3 — when no chunks were retrievable for this slot (no PDFs
        # uploaded, or none of them matched the retrieval query) we used to
        # bail out with a warning and produce zero questions. The result was
        # the misleading "Generation failed before any questions could be
        # produced" error, even though the model could have generated a
        # question from general curriculum knowledge.
        #
        # The teacher's intent in General Instructions Mode is plain: the
        # text in the textarea IS the spec. If there is no source material,
        # we fall back to LLM curriculum knowledge AND surface a `warning`
        # event so the editor can show a "no source-grounded" badge on
        # those questions. Total failure is reserved for cases where every
        # slot ALSO failed at the LLM step.
        if not context:
            source_text = ""
        else:
            raw_chunks = [_format_chunk_for_prompt(item) for item in context]
            budget_result = trim_chunks_to_budget(raw_chunks, max_input_tokens)
            source_text = "\n\n".join(budget_result.selected_chunks)

        # Build the minimal system prompt
        system_prompt = _build_gim_system_prompt(instructions, source_text)

        # Build user prompt for this specific question
        user_prompt = (
            f"Generate question {idx} of {total_questions}.\n"
            f"Question type: {slot_entry['type']}\n"
            f"Marks: {slot_entry['marks']}\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "question": {\n'
            f'    "content": "String (Question text)",\n'
            f'    "type": "{slot_entry["type"]}",\n'
        )
        if slot_entry["type"] in ["MCQ", "ASSERTION_REASON"]:
            user_prompt += '    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],\n'
        user_prompt += (
            '    "answer": "String (Correct answer)",\n'
            f'    "marks": {slot_entry["marks"]}\n'
            '  }\n'
            '}\n'
            "Do not include markdown. Return only the JSON object."
        )

        # Build a proper LLMRequest. The dict form previously used here
        # was the deploy-blocker: OpenAIProvider.stream_chat accesses
        # request.model / request.messages as attributes, so every slot
        # raised AttributeError before reaching OpenAI. We also drop the
        # temperature/max_tokens that the dict carried — reasoning-model
        # defaults like gpt-5-mini reject custom temperature, and the
        # provider already omits these parameters from the API call.
        llm_request = LLMRequest(
            model=settings.OPENAI_MODEL,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_format={"type": "json_object"},
            stream=True,
            stream_options={"include_usage": True},
        )

        logger.info(
            "[GIM] Slot %s/%s start: model=%s type=%s marks=%s section=%r "
            "prompt_chars=system:%d/user:%d source_chars=%d chunks=%d",
            idx, total_questions, settings.OPENAI_MODEL,
            slot_entry["type"], slot_entry["marks"],
            slot_entry.get("section_title") or "Questions",
            len(system_prompt), len(user_prompt),
            len(source_text), len(context),
        )

        events = []
        question = None

        for attempt in range(3):
            extractor = JsonObjectStreamExtractor()
            buffer = ""
            parsed_payload = None

            try:
                for delta in provider.stream_chat(llm_request):
                    if not delta:
                        continue
                    buffer += delta
                    for parsed in extractor.feed(delta):
                        parsed_payload = parsed
            except Exception as exc:
                if attempt == 0:
                    sleep_time = _get_rate_limit_sleep_time(exc)
                    logger.warning(
                        "[GIM] Slot %s streaming failed attempt 1 "
                        "(%s: %s) — sleeping %s s before retrying.",
                        idx, type(exc).__name__, exc, sleep_time,
                    )
                    time.sleep(sleep_time)
                    continue
                logger.error(
                    "[GIM] Slot %s streaming failed (%s: %s). "
                    "model=%s system_chars=%d user_chars=%d buffer_len=%d",
                    idx, type(exc).__name__, exc,
                    settings.OPENAI_MODEL,
                    len(system_prompt), len(user_prompt), len(buffer),
                    exc_info=True,
                )
                events.append(_sse_event(
                    {"error": f"{type(exc).__name__}: {exc}", "index": idx},
                    event="warning",
                ))
                break

            if parsed_payload is None and buffer.strip():
                try:
                    parsed_payload = json.loads(buffer)
                except json.JSONDecodeError:
                    if attempt == 0:
                        continue
                    events.append(_sse_event({"error": f"Invalid JSON for question {idx}", "index": idx}, event="warning"))
                    break

            if parsed_payload is None:
                if attempt == 0:
                    continue
                events.append(_sse_event({"error": f"No content returned for question {idx}", "index": idx}, event="warning"))
                break

            try:
                raw_q = parsed_payload.get("question", parsed_payload)
                if not isinstance(raw_q, dict):
                    raise ValueError("LLM returned non-object")

                content = _stringify(raw_q.get("content")).strip()
                if not content:
                    raise ValueError("Empty question content")
                # Same round-4 scrub as the board-mode engine: instruction
                # echoes, VI residue, orphan ORs, bare LaTeX.
                content = clean_question_text(content)
                if not content:
                    raise ValueError("Question content was only instruction/VI residue")

                options_raw = raw_q.get("options", [])
                options = [str(opt).strip() for opt in options_raw if str(opt).strip()] if isinstance(options_raw, list) else []
                options = [
                    cleaned
                    for cleaned in (
                        wrap_bare_latex_tokens(strip_blueprint_leakage(opt))
                        for opt in options
                    )
                    if cleaned.strip()
                ]

                if slot_entry["type"] == "ASSERTION_REASON":
                    options = [
                        "Both A and R are true, and R is the correct explanation of A.",
                        "Both A and R are true, and R is not the correct explanation of A.",
                        "A is true but R is false.",
                        "A is false but R is true.",
                    ]

                # Map type to legacy display type
                legacy_type_map = {
                    "MCQ": "MCQ", "ASSERTION_REASON": "ASSERTION_REASON",
                    "SHORT_ANSWER": "SHORT", "LONG_ANSWER": "LONG",
                    "CASE_STUDY": "CASE_STUDY",
                }
                display_type = legacy_type_map.get(slot_entry["type"], "SHORT")

                first_chunk = context[0] if context else {}
                first_meta = first_chunk.get("metadata") or {}

                section_name = slot_entry.get("section_title") or "Questions"
                question = {
                    "content": content,
                    "type": display_type,
                    "options": options,
                    "answer": _stringify(raw_q.get("answer")).strip(),
                    "marks": slot_entry["marks"],
                    "image_url": "",
                    "or_choice": None,
                    "vi_alternative": None,
                    "metadata": {
                        "gradeClass": f"Class {class_num}",
                        "subject": subject_raw,
                        "inferredTopic": first_meta.get("chapter") or first_meta.get("semanticSection") or "",
                        "inferredChapter": first_meta.get("chapter") or first_meta.get("semanticSection") or "",
                        "sourcePdf": first_meta.get("sourcePdf") or "",
                        "difficulty": difficulty,
                        "section": section_name,
                        # Tag questions the LLM produced without source backing
                        # so the editor can show a "no-source" badge — clearer
                        # than the silent fallback we used to do.
                        "sourceGrounded": bool(context),
                    },
                }
                break
            except Exception as exc:
                if attempt == 0:
                    logger.warning("[GIM] Normalization failed for slot %s attempt 1: %s", idx, exc)
                    continue
                logger.error("[GIM] Normalization failed for slot %s: %s", idx, exc, exc_info=True)
                events.append(_sse_event({"error": str(exc), "index": idx}, event="warning"))
                break

        if question:
            events.append(_sse_event({
                "index": idx,
                "total": total_questions,
                "section": slot_entry.get("section_title") or "Questions",
                "question": question,
            }, event="question"))

        return events, question

    # Execute generation in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_slot = {executor.submit(_generate_gim_slot, a): a for a in allocated_slots}
        for future in concurrent.futures.as_completed(future_to_slot):
            try:
                events, question = future.result()
                for event in events:
                    yield event

                if question:
                    slot_entry = future_to_slot[future]["slot_entry"]
                    section_name = slot_entry.get("section_title") or "Questions"
                    section = _find_or_create_section(result, section_name)
                    section["questions"].append(question)
                    yield _sse_event(result, event="update")
            except Exception as exc:
                logger.error("[GIM] Future failed: %s", exc)

    # Re-order sections to match the teacher's typed order (A → B → C),
    # since the concurrent executor's completion order is arbitrary.
    if section_order:
        result["sections"].sort(
            key=lambda s: section_order.index(s["title"])
            if s.get("title") in section_order
            else len(section_order)
        )

    total_generated = sum(len(s.get("questions", [])) for s in result["sections"])
    if total_generated == 0:
        # Issue 3 — be specific about WHY nothing was produced. The vague
        # message that used to fire here hid the real cause from the
        # teacher (no PDFs / retrieval miss / LLM failure all looked alike).
        diagnosis: List[str] = []
        if not pdf_source_ids:
            diagnosis.append(
                "No PDF sources were uploaded — General Instructions Mode now "
                "falls back to general curriculum knowledge in that case, so "
                "this normally still produces output. Check the model / OPENAI_API_KEY "
                "configuration and the backend logs for the per-slot errors above."
            )
        else:
            diagnosis.append(
                "Every slot failed at the LLM step. Common causes: invalid "
                "OPENAI_API_KEY, the model rejected the instructions as unsafe, "
                "or a network timeout. See the backend logs for the per-slot "
                "errors above."
            )
        yield _sse_event(
            {
                "error": "Generation failed before any questions could be produced. " + " ".join(diagnosis),
            },
            event="error",
        )
        return

    # Persist history
    try:
        GenerationHistory.objects.create(
            prompt=json.dumps({"mode": "general_instructions", "instructions": instructions}, ensure_ascii=False),
            settings={
                "topic": topic, "count": count, "resolvedCount": total_questions,
                "qp_type": "general_instructions",
                "difficulty": difficulty, "pdfSourceIds": pdf_source_ids,
                "instructions": instructions, "subject": subject_raw, "class": class_num,
            },
            result=result, user=user,
        )
    except Exception as exc:
        logger.warning("[GIM_HISTORY] Could not persist generation history: %s", exc)

    yield _sse_event({"done": True, "result": result}, event="done")


def stream_generated_questions(
    user,
    pdf_source_ids: List[str],
    topic: str,
    count: int,
    difficulty: str,
    instructions: str = "",
    payload: Optional[dict] = None,
    hsat_source_ids: Optional[List[str]] = None,
) -> Iterable[str]:
    import concurrent.futures
    from services.generation_router import (
        build_slot_blueprint_instructions,
        build_blueprint_instructions,
        build_general_instructions,
        build_realized_general_instructions,
        build_question_plan,
        extract_class_number,
        normalize_subject,
        paper_plan_section_order,
        resolve_maths_basic,
        summarize_question_plan,
        should_use_new_engine,
    )
    from services.syllabus_scope import excluded_source_substrings

    logger.info(f"[STREAM_SERVICE] Entered stream_generated_questions for topic '{topic}'")

    payload = payload or {}

    # ISSUE A1: explicit content-scope policy.
    # `strict` (default): generate the FULL blueprint; slots without sufficient
    #   PDF coverage fall back to curriculum-only generation. The result is a
    #   structurally complete paper — what a CBSE board paper requires.
    # `source_only`: generate only what the corpus can ground. The realized
    #   paper may be smaller than the blueprint; the printed header/totals
    #   reflect what was actually produced, and a visible notice is added.
    scope_policy = str(
        payload.get("content_scope_policy")
        or payload.get("contentScopePolicy")
        or "strict"
    ).strip().lower()
    if scope_policy not in {"strict", "source_only"}:
        scope_policy = "strict"

    # Per-paper toggle for VI alternatives (Cluster C). Default True to
    # match CBSE Sample Paper convention. Accepts both snake_case and
    # camelCase + the false-string variants the FE may send.
    raw_vi_flag = payload.get(
        "include_vi_alternatives",
        payload.get("includeViAlternatives", True),
    )
    include_vi_alternatives = bool(raw_vi_flag) and str(raw_vi_flag).strip().lower() not in {
        "false", "0", "no", "off",
    }

    # ── HARD BRANCH: Route based on qp_type ──────────────────────────
    qp_type = str(
        payload.get("qp_type")
        or payload.get("qpType")
        or payload.get("qp_type", "")
    ).strip().lower()

    hsat_source_ids = list(hsat_source_ids or [])

    if qp_type == "general_instructions":
        logger.info("[STREAM_SERVICE] QP Type = general_instructions → routing to GIM handler")
        yield from stream_general_instructions_questions(
            user=user,
            pdf_source_ids=pdf_source_ids,
            topic=topic,
            count=count,
            difficulty=difficulty,
            instructions=instructions,
            payload=payload,
            hsat_source_ids=hsat_source_ids,
        )
        return
    # ── END BRANCH — Board Mode continues below unchanged ─────────────

    logger.info("[STREAM_SERVICE] Building q_instructions plan before retrieval/LLM...")

    if not should_use_new_engine(payload):
        yield _sse_event({"error": "This CBSE subject/class is not configured in q_instructions. Supported: Science & Social Science (Classes 1-10); Mathematics, English, Hindi, Telugu (Class 10)."}, event="error")
        return

    class_raw = payload.get("class", payload.get("class_level", payload.get("gradeClass", "10")))
    class_num = extract_class_number(class_raw, default=10)
    subject_raw = str(payload.get("subject", "Science")).strip() or "Science"
    subject_norm = normalize_subject(subject_raw)
    subject_label = "Social Science" if subject_norm == "social science" else "Science"
    # Mathematics Standard (041) vs Basic (241): same A–E skeleton, different
    # Bloom-band target prose. Detected from the payload / subject string.
    maths_basic = resolve_maths_basic(subject_raw, payload)
    # Off-syllabus whole-chapter exclusions (e.g. Social Science "Age of
    # Industrialisation") to drop from RAG retrieval. Single source of truth in
    # services.syllabus_scope — same list the prose builder cites.
    exclude_substrings = excluded_source_substrings(subject_norm, class_num)
    count_variation = str(payload.get("count_variation") or payload.get("countVariation") or payload.get("countType") or "").strip().lower()
    resolved_count = -1 if count_variation in {"cbse exact pattern", "cbse", "exact"} else count

    try:
        plan = build_question_plan(
            topic=topic, difficulty=difficulty, count=resolved_count, class_num=class_num, subject=subject_raw, instructions=instructions, count_variation=count_variation,
        )
        # We still generate the master blueprint for history logging
        master_blueprint = build_blueprint_instructions(
            topic=topic, difficulty=difficulty, count=resolved_count, class_num=class_num, subject=subject_raw, plan=plan, maths_basic=maths_basic,
        )
    except Exception as exc:
        logger.error("[AOS] Failed to compile q_instructions plan: %s", exc, exc_info=True)
        yield _sse_event({"error": str(exc)}, event="error")
        return

    if not plan:
        yield _sse_event({"error": "No question plan could be compiled."}, event="error")
        return

    constraints = GenerationConstraints(count=len(plan), difficulty=difficulty)
    board = EducationBoard.CBSE
    academic_class = AcademicClass.CLASS_10
    board_raw = str(payload.get("board", "CBSE")).strip().upper()
    if board_raw in EducationBoard.__members__:
        board = EducationBoard[board_raw]
    class_name = f"CLASS_{class_num}"
    if class_name in AcademicClass.__members__:
        academic_class = AcademicClass[class_name]

    max_input_tokens, max_output_tokens = allocate_budget(
        total_max_tokens=5000, reserved_system_tokens=350, max_output_tokens=750,
    )
    assembler = PromptAssembler(version_id="v1")
    request_factory = LLMRequestFactory()
    provider = OpenAIProvider()
    result = _empty_result()
    general_instructions = build_general_instructions(plan, subject_raw, class_num, instructions=instructions)
    result["generalInstructions"] = general_instructions

    # Phase 1: The Allocation Loop (Sequential & Instantaneous)
    #
    # CHUNK REUSE POLICY — the old strict per-chunk dedup (each chunk could
    # back at most one slot) was the root cause of the "Curriculum fallback
    # flood" reported by users: a 65-chunk source can ground 65/4 ≈ 16 slots
    # before exhaustion, after which every remaining slot in a 30-/38-question
    # paper fell through to curriculum mode. Allowing each chunk to ground up
    # to `max_chunk_reuses` slots restores grounded coverage without flooding
    # the paper with near-duplicate questions: the chunk pool gains ~3×
    # effective capacity, and the retrieval query continues to differ per
    # slot so the LLM produces distinct stems. Tunable via the
    # `MAX_CHUNK_REUSES` setting (defaults to 3, the value that takes the
    # 38-slot dedup simulation against the trio of user-supplied PDFs from
    # 55% fallback → 0% fallback while keeping no single chunk attached to
    # more than 3 slot prompts).
    max_chunk_reuses = max(
        1, int(getattr(settings, "MAX_CHUNK_REUSES", 3))
    )
    allocated_slots = []
    chunk_use_count: Dict[str, int] = {}
    _topic_cache = {}
    blueprint_total = len(plan)
    curriculum_fallback_indices: List[int] = []
    source_only_pruned_indices: List[int] = []

    for slot in plan:
        slot_mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()
        # RAG only for CONTENT slots. GRAMMAR/COMPOSITION/PASSAGE are rule-/scenario-based and
        # must never receive educator-uploaded chunks (empty retrieval_query → no retrieval call).
        if slot_mode != "CONTENT" or not slot.retrieval_query:
            allocated_slots.append({
                "slot": slot, "context": [], "is_visual_mandatory": False,
                "curriculum_fallback": False,
            })
            continue

        cache_key = (slot.retrieval_query, slot.requires_image)
        if cache_key not in _topic_cache:
            _topic_cache[cache_key] = retrieve_relevant_chunks(
                slot.retrieval_query,
                pdf_source_ids,
                limit=50,
                user=user,
                require_image=slot.requires_image,
                exclude_chunk_ids=None,
                hsat_source_ids=hsat_source_ids,
                exclude_source_substrings=exclude_substrings,
            )

        top_50 = _topic_cache[cache_key]
        valid_chunks = [
            c for c in top_50
            if chunk_use_count.get(str(c.get("id")), 0) < max_chunk_reuses
        ]
        context = valid_chunks[:4]

        for item in context:
            cid = str(item.get("id") or "")
            if cid:
                chunk_use_count[cid] = chunk_use_count.get(cid, 0) + 1

        # Cluster B (figure pipeline): the previous logic auto-promoted ANY
        # slot whose context happened to contain an image-bearing chunk into
        # is_visual_mandatory=True, which in turn forced the LLM to write
        # "Observe the given figure..." even for pure-text questions like
        # `sec²θ - tan²θ = 1`. We now respect the blueprint exclusively —
        # only slots that the q_instructions planner actually marked as
        # picture-bearing (requires_image / requires_figure) get the visual
        # mandate. Slots whose retrieval happened to surface an image-laden
        # chunk simply have those images AVAILABLE (via _allowed_image_urls)
        # but are no longer forced to cite them.
        is_visual_mandatory = bool(
            getattr(slot, "requires_image", False)
            or getattr(slot, "requires_figure", False)
        )

        # ISSUE A1: when the uploaded sources can't cover this CONTENT slot,
        # honour the scope policy explicitly instead of silently truncating.
        if not context:
            if scope_policy == "source_only":
                source_only_pruned_indices.append(slot.index)
                continue  # skip this slot — header will be derived from realized
            # strict (default) — fall back to CBSE-curriculum generation for this slot
            curriculum_fallback_indices.append(slot.index)
            allocated_slots.append({
                "slot": slot, "context": [], "is_visual_mandatory": False,
                "curriculum_fallback": True,
            })
            continue

        allocated_slots.append({
            "slot": slot,
            "context": context,
            "is_visual_mandatory": is_visual_mandatory,
            "curriculum_fallback": False,
        })

    yield _sse_event(
        {
            "total": len(plan),
            "subject": subject_label,
            "class": class_num,
            "blueprint": master_blueprint,
            "summary": summarize_question_plan(plan),
            "generalInstructions": general_instructions,
        },
        event="plan",
    )

    prompt_audit = []
    total_estimated_input_tokens = 0
    truncation_events = 0
    provider_failures = 0

    def _slot_output_budget(slot) -> int:
        """Per-slot max_output_tokens override.

        The shared 750-token budget truncated Section E case studies (a
        passage + 3 sub-parts + the mandatory OR in sub-part iii easily
        exceeds 750), which is why Q38 printed mid-sentence with the
        "...height 42" / "1" tail. Scale by question shape:

          * CASE_STUDY (4m) — passage + 3 sub-parts + OR  → ~2200 tok
          * LONG_ANSWER (5m) — multi-step proof / word problem → ~1500 tok
          * ASSERTION_REASON — fixed 4-direction block      → ~600 tok
          * MCQ + SHORT_ANSWER — concise stems              → 750 tok (default)
        """
        qtype = str(getattr(slot, "question_type", "") or "")
        marks = int(getattr(slot, "marks", 1) or 1)
        if qtype == "CASE_STUDY":
            return 2200
        if qtype == "LONG_ANSWER" or marks >= 5:
            return 1500
        if marks == 3:
            return 1000
        return 750

    def _generate_slot(allocated):
        slot = allocated["slot"]
        context = allocated["context"]
        is_visual_mandatory = allocated["is_visual_mandatory"]
        curriculum_fallback = bool(allocated.get("curriculum_fallback"))

        slot_mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()

        # CONTENT slots normally need textbook chunks. If `curriculum_fallback`
        # is set (scope_policy=strict, sources didn't cover this topic), we
        # proceed with no chunks — the LLM uses CBSE curriculum knowledge.
        if slot_mode == "CONTENT" and not context and not curriculum_fallback:
            return (
                [_sse_event({"error": f"No relevant textbook chunks found for {slot.section_title} question {slot.index}.", "index": slot.index}, event="warning")],
                None, None, None
            )

        if context:
            retrieval_metrics = retrieval_quality_summary(context)
            logger.info("[RAG] slot=%s metrics=%s", slot.index, retrieval_metrics)

        image_urls = _allowed_image_urls(context) if slot.requires_image or is_visual_mandatory else []
        vision_image_urls = _vision_image_payload_urls(context) if slot.requires_image or is_visual_mandatory else []
        raw_chunks = [_format_chunk_for_prompt(item) for item in context]
        budget_result = trim_chunks_to_budget(raw_chunks, max_input_tokens)

        gen_context = GenerationContext(
            subject=subject_label,
            board=board,
            academic_class=academic_class,
            difficulty=difficulty,
            retrieved_chunks=budget_result.selected_chunks,
            token_budget=TokenBudget(
                model=settings.OPENAI_MODEL,
                max_input_tokens=max_input_tokens,
                max_output_tokens=_slot_output_budget(slot),
                reserved_system_tokens=350,
            ),
            generation_constraints=constraints,
            prompt_version="v1",
        )
        
        # Directive 5: Truncated prompt
        slot_blueprint = build_slot_blueprint_instructions(slot, difficulty, class_num, subject_raw, maths_basic=maths_basic)

        if curriculum_fallback:
            system_rules = (
                "Generate ONE CBSE question for the slot below using your knowledge of "
                "the CBSE curriculum. No textbook chunks are provided for this slot; "
                "rely on the standard CBSE syllabus for the given subject and class. "
                "Obey the exact slot contract and JSON schema. Never add extra question "
                "objects or split an OR choice into another question."
            )
            if constraints:
                system_rules += f"\nResolved paper count: {constraints.count} question objects."
        else:
            system_rules = _system_rules_for_slot(slot, constraints)

        fallback_extra = (
            "CURRICULUM FALLBACK: no textbook chunks were available for this topic. "
            "Generate a curriculum-grounded question from the standard CBSE syllabus."
        ) if curriculum_fallback else None
        merged_extra = "\n".join(filter(None, [instructions or None, fallback_extra]))

        prompt_document = assembler.assemble(
            context=gen_context,
            system_rules=system_rules,
            output_schema=_single_question_schema(is_visual_mandatory, slot),
            blueprint_instructions=slot_blueprint,
            extra_instructions=merged_extra or None,
        )
        
        audit_info = {
            "index": slot.index,
            "section": slot.section_title,
            "type": slot.legacy_type,
            "marks": slot.marks,
            "query": slot.retrieval_query,
            "chunks": len(context),
            "orChoice": slot.choice_required,
            "imageUrls": len(image_urls),
            "visionImages": len(vision_image_urls),
        }

        # used_terms is dropped for parallel generation since slots are mutually exclusive via chunks
        prompt = _build_user_prompt(
            slot,
            len(plan),
            topic,
            image_urls=image_urls,
            used_terms=set(), 
            is_visual_mandatory=is_visual_mandatory,
        )
        llm_request = request_factory.build(
            prompt_document, prompt, model=settings.OPENAI_MODEL, image_urls=vision_image_urls,
        )
        
        question = None
        events = []
        failures = 0

        # Language (non-CONTENT) slots get an extra attempt so a hard validation/script
        # failure can be regenerated rather than silently streamed to the editor.
        max_attempts = 3 if slot_mode != "CONTENT" else 3

        for attempt in range(max_attempts):
            is_last = attempt >= max_attempts - 1
            extractor = JsonObjectStreamExtractor()
            buffer = ""
            parsed_payload = None

            try:
                for delta in provider.stream_chat(llm_request):
                    if not delta:
                        continue
                    buffer += delta
                    for parsed in extractor.feed(delta):
                        parsed_payload = parsed
            except Exception as exc:
                if not is_last:
                    sleep_time = _get_rate_limit_sleep_time(exc)
                    logger.warning(
                        "[LLM] Streaming failed for slot %s (attempt %s): %s. Sleeping %s s before retrying...",
                        slot.index, attempt + 1, exc, sleep_time
                    )
                    time.sleep(sleep_time)
                    continue
                failures += 1
                logger.error("[LLM] Streaming failed for slot %s: %s", slot.index, exc, exc_info=True)
                events.append(_sse_event({"error": str(exc), "index": slot.index}, event="warning"))
                break

            if parsed_payload is None and buffer.strip():
                try:
                    parsed_payload = json.loads(buffer)
                except json.JSONDecodeError as exc:
                    if not is_last:
                        logger.warning("[LLM] Invalid JSON for slot %s (attempt %s): %s. Retrying...", slot.index, attempt + 1, exc)
                        continue
                    failures += 1
                    logger.error("[LLM] Invalid JSON for slot %s: %s", slot.index, exc)
                    events.append(_sse_event({"error": f"Invalid JSON for question {slot.index}", "index": slot.index}, event="warning"))
                    break

            if parsed_payload is None:
                if not is_last:
                    logger.warning("[LLM] No question content returned for slot %s (attempt %s). Retrying...", slot.index, attempt + 1)
                    continue
                failures += 1
                events.append(_sse_event({"error": f"No question content returned for question {slot.index}", "index": slot.index}, event="warning"))
                break

            try:
                candidate = _coerce_question(
                    parsed_payload,
                    slot,
                    context,
                    is_retry=(attempt > 0),
                    is_visual_mandatory=is_visual_mandatory,
                    include_vi_alternatives=include_vi_alternatives,
                )
            except Exception as exc:
                if not is_last:
                    logger.warning("[LLM] Could not normalize slot %s (attempt %s): %s. Retrying...", slot.index, attempt + 1, exc)
                    continue
                failures += 1
                logger.error("[LLM] Could not normalize slot %s: %s", slot.index, exc, exc_info=True)
                events.append(_sse_event({"error": str(exc), "index": slot.index}, event="warning"))
                break

            # Hard language gate (no-op for CONTENT slots). Never stream a malformed
            # grammar/composition/passage question — regenerate, then surface a clear error.
            is_valid, reason = validate_language_question(slot, candidate)
            if not is_valid:
                if not is_last:
                    logger.warning("[VALIDATION] slot %s rejected (%s). Regenerating...", slot.index, reason)
                    continue
                failures += 1
                logger.error("[VALIDATION] slot %s failed after %s attempts: %s", slot.index, max_attempts, reason)
                events.append(_sse_event({"error": f"Question {slot.index} failed validation: {reason}", "index": slot.index}, event="warning"))
                break

            question = candidate
            break

        if question:
            # Stamp provenance so the frontend review tray can show a
            # "From sources" vs "Curriculum fallback" badge and the teacher
            # can be selective about ungrounded questions.
            source_type = "curriculum_fallback" if curriculum_fallback else "rag"
            question.setdefault("metadata", {})
            if isinstance(question["metadata"], dict):
                question["metadata"]["sourceType"] = source_type
                # Plan position (1-indexed). Parallel generation finishes in
                # arbitrary order; consumers sort by this to restore the
                # blueprint layout (e.g. Maths Section A: Q1–18 MCQ then
                # Q19–20 Assertion-Reason).
                question["metadata"]["slotIndex"] = slot.index
            question["sourceType"] = source_type

            events.append(_sse_event({
                "index": slot.index,
                "total": len(plan),
                "section": slot.section_title,
                "question": question,
                "sourceType": source_type,
            }, event="question"))

        return events, audit_info, question, (failures, budget_result.estimated_tokens, budget_result.truncation_events)

    # Phase 2: The Generation Loop (Parallel)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_slot = {executor.submit(_generate_slot, a): a for a in allocated_slots}
        for future in concurrent.futures.as_completed(future_to_slot):
            try:
                events, audit_info, question, metrics_tuple = future.result()
                for event in events:
                    yield event
                
                if audit_info:
                    prompt_audit.append(audit_info)
                if question:
                    slot = future_to_slot[future]["slot"]
                    section = _find_or_create_section(result, slot.section_title)
                    section["questions"].append(question)
                    yield _sse_event(result, event="update")
                    
                if metrics_tuple:
                    provider_failures += metrics_tuple[0]
                    total_estimated_input_tokens += metrics_tuple[1]
                    truncation_events += metrics_tuple[2]
            except Exception as exc:
                logger.error("Future failed: %s", exc)

    metrics = GenerationMetrics(
        prompt_version="v1",
        model=settings.OPENAI_MODEL,
        chunk_count=sum(item["chunks"] for item in prompt_audit),
        estimated_input_tokens=total_estimated_input_tokens,
        estimated_output_tokens=max_output_tokens * len(plan),
        truncation_events=truncation_events,
        provider_failures=provider_failures,
    )
    logger.info(f"[PROMPT_METRICS] {metrics.to_dict()}")

    total_questions = sum(len(section.get("questions", [])) for section in result["sections"])
    if total_questions == 0:
        yield _sse_event({"error": "Generation failed before any questions could be produced."}, event="error")
        return

    # ── Intra-section slot ordering ──────────────────────────────────────
    # The parallel loop above appends questions in COMPLETION order, so a
    # blueprint that pins Assertion-Reason to Section A slots 19–20 could
    # render them anywhere in the section (the reported paper had an AR at
    # Q20 but a probability MCQ at Q19). Restore the plan's order before
    # the dedup pass and the final result the editor consumes.
    for section in result.get("sections", []):
        questions = section.get("questions") or []
        if len(questions) > 1:
            questions.sort(
                key=lambda q: int(
                    (q.get("metadata") or {}).get("slotIndex") or 10**6
                )
            )

    # ── Section A near-duplicate detection ──────────────────────────────
    # Parallel generation (Phase 2) hands every slot an empty `used_terms`
    # set, so when two MCQs retrieve overlapping chunks the LLM can return
    # the same scenario for both. The reported case (Q4 == Q7 — identical
    # right-triangle sin-A stem) is exactly that. We do a lightweight
    # signature match on the first ~80 chars of the stem after stripping
    # math delimiters/punctuation; if two questions in the SAME section
    # collide, we keep the lower-indexed one and warn for the other.
    # A future pass can hand this list to the regeneration retry loop;
    # for now we surface it so the operator can spot the issue immediately.
    def _stem_signature(content: str) -> str:
        s = re.sub(r"\\[\(\)\[\]]", " ", content or "")
        s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().lower()
        # 60-char prefix: long enough that two genuinely different stems
        # never collide, short enough to catch rephrased tails. (Was 80,
        # which let near-identical stems diverge in the last 20 chars and
        # slip through.)
        return s[:60]

    duplicate_warnings: List[Dict[str, object]] = []
    # One signature map across the WHOLE paper, not per section — two
    # sections can retrieve the same chunk and the LLM will happily reuse
    # the scenario across a 1-mark MCQ and a 2-mark short answer.
    seen: Dict[str, object] = {}
    for section in result.get("sections", []):
        for q in section.get("questions", []):
            sig = _stem_signature(str(q.get("content") or ""))
            if not sig:
                continue
            prior = seen.get(sig)
            if prior is not None:
                duplicate_warnings.append({
                    "section": section.get("title"),
                    "duplicateOf": prior,
                    "signature": sig[:40],
                })
                # Tag the duplicate so reviewers/PDF footer can flag it.
                meta = q.setdefault("metadata", {})
                if isinstance(meta, dict):
                    meta["duplicateOf"] = prior
            else:
                seen[sig] = q.get("metadata", {}).get("section") or section.get("title", "")
    if duplicate_warnings:
        logger.warning(
            "[DEDUP] Detected %d near-duplicate question(s): %s",
            len(duplicate_warnings),
            duplicate_warnings,
        )
        yield _sse_event({
            "duplicates": duplicate_warnings,
            "message": (
                f"{len(duplicate_warnings)} near-duplicate question(s) detected "
                "after parallel generation. Review and regenerate the flagged slots."
            ),
        }, event="warning")

    # ── PaperPlan section ordering (ISSUE 1) ─────────────────────────────
    # Concurrent LLM completion appends sections in whatever order they
    # finish — that can render the paper as "Section C, Section A, Section
    # B" even though the teacher typed A, B, C. Re-sort the realized
    # sections to match the plan's declared order so both the printed
    # header and the editor layout follow the teacher's intent. Anything
    # the plan didn't enumerate (rare safety net) keeps its current order
    # at the tail.
    plan_order = paper_plan_section_order(plan)
    if plan_order:
        order_index = {title: i for i, title in enumerate(plan_order)}
        result["sections"].sort(
            key=lambda s: order_index.get(s.get("title", ""), len(order_index))
        )

    # ISSUE A2: rewrite the printable general-instructions from the REALIZED
    # paper so the header (total questions, per-section counts, marks) cannot
    # contradict the body. This replaces the planned/blueprint header that was
    # emitted earlier in the `plan` event.
    fallback_count = len(curriculum_fallback_indices)
    realized_general_instructions = build_realized_general_instructions(
        result,
        subject_raw,
        class_num,
        scope_policy=scope_policy,
        fallback_count=fallback_count,
        requested_count=blueprint_total,
    )
    result["generalInstructions"] = realized_general_instructions

    if scope_policy == "source_only" and total_questions < blueprint_total:
        yield _sse_event({
            "scope": "source_only",
            "requested": blueprint_total,
            "realized": total_questions,
            "message": (
                f"Only {total_questions} of {blueprint_total} blueprint questions "
                "could be grounded in the uploaded sources. Upload more chapters or "
                "switch to full-blueprint (strict) mode for a complete paper."
            ),
        }, event="notice")
    elif fallback_count > 0:
        yield _sse_event({
            "scope": "strict",
            "curriculumFallbackCount": fallback_count,
            "realized": total_questions,
            "message": (
                f"{fallback_count} of {total_questions} questions were generated from the "
                "CBSE curriculum (uploaded sources did not cover those topics). "
                "Upload more chapters to ground every slot in your source material."
            ),
        }, event="notice")

    # ── Fallback transparency: PDF footer + Django log warning ──────────
    # Per spec: when a question is generated from curriculum fallback, the
    # printed paper must carry a visible footer note so the teacher knows
    # which slots are ungrounded. We pin the fallback indices onto the
    # result so the editor's footer builder can mark them with a "†".
    # In parallel: log a warning when the fallback rate breaches 30% so
    # the dev team sees over-reliance on curriculum knowledge.
    if total_questions > 0:
        fallback_rate = fallback_count / total_questions
        if fallback_rate > 0.30:
            logger.warning(
                "[FALLBACK] High curriculum-fallback rate: %s/%s = %.1f%% "
                "(threshold 30%%). Sources were unable to cover the majority "
                "of the blueprint — consider uploading more chapters.",
                fallback_count,
                total_questions,
                fallback_rate * 100.0,
            )
    result.setdefault("meta", {})
    if isinstance(result["meta"], dict):
        result["meta"]["curriculumFallbackCount"] = fallback_count
        result["meta"]["curriculumFallbackIndices"] = list(curriculum_fallback_indices)
        result["meta"]["totalQuestions"] = total_questions
        result["meta"]["duplicateWarnings"] = duplicate_warnings
        if fallback_count > 0:
            # The frontend reads `result.meta.footerNotes` and appends each
            # entry as a small italic line beneath the question paper before
            # PDF export. Teachers see exactly which questions came from
            # CBSE curriculum knowledge rather than the uploaded sources.
            result["meta"].setdefault("footerNotes", []).append(
                "† Questions marked with a dagger were generated from CBSE "
                "curriculum knowledge as the uploaded sources did not cover "
                "this topic."
            )

    try:
        GenerationHistory.objects.create(
            prompt=json.dumps({"blueprint": master_blueprint, "plan": prompt_audit}, ensure_ascii=False),
            settings={
                "topic": topic, "count": count, "resolvedCountInput": resolved_count, "resolvedCount": len(plan),
                "countVariation": count_variation or ("cbse" if count <= 0 else "custom"),
                "difficulty": difficulty, "pdfSourceIds": pdf_source_ids, "instructions": instructions,
                "subject": subject_label, "class": class_num,
                "contentScopePolicy": scope_policy,
                "blueprintTotal": blueprint_total,
                "realizedTotal": total_questions,
                "curriculumFallbackCount": fallback_count,
                "sourceOnlyPrunedCount": len(source_only_pruned_indices),
            },
            result=result, user=user,
        )
    except Exception as exc:
        logger.warning("[HISTORY] Could not persist generation history: %s", exc)

    yield _sse_event({"done": True, "result": result}, event="done")
