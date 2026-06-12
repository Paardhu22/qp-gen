"""Single source of truth for CBSE Class 10 off-syllabus exclusions and
per-subject cognitive-band (Bloom) targets.

This module is intentionally dependency-light (stdlib only) so both the
prose blueprint builders in ``services.generation_router`` and the
retrieval filter in ``services.retrieval_service`` can import it without
pulling in Django, q_instructions, or boto3.

Two distinct exclusion kinds:

* **Whole-chapter exclusions** carry ``source_match_substrings`` and are
  enforced BOTH in the prose sent to the LLM AND at retrieval time (the
  whole chapter is off the year-end paper, so dropping its chunks is
  correct). Example: "The Age of Industrialisation".
* **Sub-topic exclusions** have an EMPTY ``source_match_substrings`` and
  are enforced via PROSE ONLY. Their chapter is still partly in scope
  (e.g. "Evolution" lives inside "Heredity and Evolution", whose Heredity
  half stays examinable), so a chapter-level retrieval filter would
  over-exclude. We tell the model not to use the sub-topic instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ExcludedTopic:
    """One off-syllabus topic for a subject/class."""

    label: str
    note: str
    # Lowercase substrings matched against a chunk's source identifiers
    # (S3 key / chapter / sourcePdf). EMPTY ⇒ prose-only sub-topic that must
    # NOT trigger a retrieval-time chapter drop.
    source_match_substrings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeLimit:
    """A chapter that stays partly in scope — only listed sub-topics allowed."""

    chapter: str
    allowed_only: Tuple[str, ...]


# ---------------------------------------------------------------------------
# Class 10 exclusion registry (subject_norm → topics). subject_norm matches
# services.generation_router.normalize_subject output.
# ---------------------------------------------------------------------------

_CLASS10_EXCLUSIONS: Dict[str, List[ExcludedTopic]] = {
    "science": [
        ExcludedTopic(
            label="Periodic Classification of Elements",
            note="assessed only in periodic/formative tests, not the year-end theory paper",
            source_match_substrings=("periodic classification",),
        ),
        ExcludedTopic(
            label="Evolution (the Evolution portion of 'Heredity and Evolution')",
            note="Heredity itself remains in scope; exclude only the Evolution sub-topic",
            source_match_substrings=(),  # prose-only: chapter is partly in scope
        ),
        ExcludedTopic(
            label="Electric Motor, Electromagnetic Induction, and Electric Generator",
            note="within 'Magnetic Effects of Electric Current'; the rest of the chapter stays in scope",
            source_match_substrings=(),  # prose-only: chapter is partly in scope
        ),
    ],
    "social science": [
        ExcludedTopic(
            label="'The Age of Industrialisation' (History)",
            note="periodic assessment only, not in the year-end theory paper",
            source_match_substrings=("age of industrialisation", "age of industrialization"),
        ),
        ExcludedTopic(
            label="'Consumer Rights' (Economics)",
            note="project work only, not the theory paper",
            source_match_substrings=("consumer rights",),
        ),
    ],
}

# Chapters that remain in scope but only for specific sub-topics (prose-only).
_CLASS10_SCOPE_LIMITS: Dict[str, List[ScopeLimit]] = {
    "social science": [
        ScopeLimit(
            chapter="Globalisation (Economics)",
            allowed_only=("What is Globalisation?", "Factors enabling Globalisation"),
        ),
    ],
}


# ---------------------------------------------------------------------------
# Cognitive-band (Bloom) targets. Numbers are official CBSE competency
# weightages, expressed as whole-paper, mark-weighted targets.
# ---------------------------------------------------------------------------

# Social Science: 30 / 13.75 / 50 (+6.25 map). Most HOTS-heavy subject.
SOCIAL_SCIENCE_BANDS = (30, 14, 50)  # Band1, Band2, Band3 (percent, rounded)

# Mathematics Standard (041) vs Basic (241): same A–E skeleton, different mix.
MATHS_STANDARD_BANDS = (54, 24, 22)
MATHS_BASIC_BANDS = (75, 15, 10)


def _applies(subject_norm: str, class_num: int) -> bool:
    return class_num == 10


# ---------------------------------------------------------------------------
# Exclusion accessors
# ---------------------------------------------------------------------------

def excluded_topics_for(subject_norm: str, class_num: int) -> List[ExcludedTopic]:
    if not _applies(subject_norm, class_num):
        return []
    return list(_CLASS10_EXCLUSIONS.get(subject_norm, []))


def scope_limits_for(subject_norm: str, class_num: int) -> List[ScopeLimit]:
    if not _applies(subject_norm, class_num):
        return []
    return list(_CLASS10_SCOPE_LIMITS.get(subject_norm, []))


def excluded_source_substrings(subject_norm: str, class_num: int) -> List[str]:
    """Whole-chapter substrings for the retrieval-time filter only.

    Sub-topic (prose-only) exclusions are deliberately omitted — their
    chapters are partly in scope.
    """
    subs: List[str] = []
    for topic in excluded_topics_for(subject_norm, class_num):
        subs.extend(topic.source_match_substrings)
    return subs


def excluded_topics_prose_block(subject_norm: str, class_num: int) -> List[str]:
    """Multi-line prose block for the paper-level blueprint builders."""
    topics = excluded_topics_for(subject_norm, class_num)
    limits = scope_limits_for(subject_norm, class_num)
    if not topics and not limits:
        return []
    lines = [
        "DO NOT generate questions on the following off-syllabus topics, even if "
        "they appear in the provided source material (excluded from the CBSE Class 10 "
        "year-end theory paper):",
    ]
    for topic in topics:
        lines.append(f"- {topic.label} — {topic.note}.")
    for limit in limits:
        allowed = "; ".join(limit.allowed_only)
        lines.append(
            f"- SCOPE LIMIT — {limit.chapter}: restrict to ONLY \"{allowed}\". "
            "Do NOT generate questions on any other sub-topic of that chapter."
        )
    return lines


def excluded_topics_compact_line(subject_norm: str, class_num: int) -> Optional[str]:
    """One compact line for the per-slot prompt (kept short to protect TTFT)."""
    topics = excluded_topics_for(subject_norm, class_num)
    if not topics:
        return None
    labels = ", ".join(t.label for t in topics)
    return f"- Off-syllabus — DO NOT generate questions on: {labels}."


def chunk_source_is_excluded(metadata: dict, substrings: List[str]) -> bool:
    """True if a retrieved chunk's source identifiers match any excluded substring."""
    if not substrings or not metadata:
        return False
    haystacks = [
        str(metadata.get(key, "")).lower()
        for key in (
            "s3_key",
            "hsat_chapter",
            "hsat_book",
            "sourcePdf",
            "source_pdf",
            "chapter",
            "semanticSection",
            "inferredChapter",
        )
    ]
    blob = " | ".join(haystacks)
    return any(sub in blob for sub in substrings)


# ---------------------------------------------------------------------------
# Cognitive-band prose
# ---------------------------------------------------------------------------

def social_science_bloom_bias_block(class_num: int) -> List[str]:
    if class_num != 10:
        return []
    b1, b2, b3 = SOCIAL_SCIENCE_BANDS
    return [
        "COGNITIVE DEMAND (CBSE Social Science competency mix — target the whole "
        "paper, mark-weighted):",
        f"- ~{b1}% Band 1 (Remembering + Understanding): recall, describe, explain.",
        f"- ~{b2}% Band 2 (Applying).",
        f"- ~{b3}% Band 3 (Analysing/Evaluating/Creating): Social Science is the "
        "HOTS-heavy subject — bias HARD toward higher-order thinking.",
        "- ~6% map skill (separate competency).",
        "- Frame the 4-mark Case-Based Questions and 5-mark Long Answers as "
        "\"analyse the following source/statement\", \"compare\", \"justify\", or "
        "\"evaluate the impact of\" — NOT pure recall.",
    ]


def social_science_bloom_bias_line(class_num: int) -> Optional[str]:
    if class_num != 10:
        return None
    return (
        "- Cognitive bias: Social Science is ~50% HOTS — frame as analyse/compare/"
        "justify/evaluate (source-based), not recall."
    )


def maths_cognitive_band_block(is_basic: bool) -> List[str]:
    if is_basic:
        b1, b2, b3 = MATHS_BASIC_BANDS
        return [
            f"COGNITIVE DEMAND (Mathematics Basic, Code 241 — mark-weighted paper target):",
            f"- Band 1 (Remember + Understand): ~{b1}% — heavily front-load recall/understanding.",
            f"- Band 2 (Apply): ~{b2}%.",
            f"- Band 3 (Analyse/Evaluate/Create, HOTS): ~{b3}% — keep HOTS minimal.",
            "- Same 38-question A–E skeleton, same Q19/Q20 Assertion-Reason rule, same "
            "Section E case structure — only the cognitive mix changes.",
        ]
    b1, b2, b3 = MATHS_STANDARD_BANDS
    return [
        f"COGNITIVE DEMAND (Mathematics Standard, Code 041 — mark-weighted paper target):",
        f"- Band 1 (Remember + Understand): ~{b1}%.",
        f"- Band 2 (Apply): ~{b2}%.",
        f"- Band 3 (Analyse/Evaluate/Create, HOTS): ~{b3}%.",
    ]


def maths_cognitive_band_line(is_basic: bool) -> str:
    if is_basic:
        b1, _, b3 = MATHS_BASIC_BANDS
        return (
            f"- Cognitive tier: Mathematics Basic (241) — favour Band 1 recall/"
            f"understanding (~{b1}%); keep HOTS minimal (~{b3}%)."
        )
    b1, _, b3 = MATHS_STANDARD_BANDS
    return (
        f"- Cognitive tier: Mathematics Standard (041) — balanced "
        f"(~{b1}% recall/understand, ~{b3}% HOTS)."
    )
