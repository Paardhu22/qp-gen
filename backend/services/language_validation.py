"""
Hard validation gates for CBSE language-paper generation (English / Hindi / Telugu).

These run AFTER the LLM produces a question object and BEFORE it is streamed to the
editor. The model emits FREE TEXT (this codebase has no structured sub-parts), so the
checks are deliberately CONSERVATIVE: they reject only clear, high-confidence
violations to avoid false-reject retry storms, while still catching the catastrophic
failures a teacher must never see on a printed exam:

  - Roman-script output in a Devanagari / Telugu slot
  - a composition slot missing its word limit
  - a Hindi अनुच्छेद topic with fewer than 3 संकेत-बिन्दु
  - an English analytical-paragraph stimulus with fewer than 2 comparable options
  - a Telugu Chandas answer whose gaṇa sequence contradicts the named metre

`validate_language_question` is the single entry point used by the generator. For
CONTENT slots (Science / Social / Maths / literature) it is a no-op — those flows are
left exactly as they were.
"""

import re
from typing import Tuple

from services.generation_router import normalize_subject, TELUGU_METRE_GANA

DEVANAGARI_LO, DEVANAGARI_HI = 0x0900, 0x097F
TELUGU_LO, TELUGU_HI = 0x0C00, 0x0C7F

# ~120 words / 120-150 words / ~120 शब्द / 100 పదాలు ...
_WORD_LIMIT_RE = re.compile(
    r"\d+\s*(?:[-–]\s*\d+\s*)?(?:words?|word\s*limit|शब्द|शब्द-?\s*सीमा|पदाल|పదాల|మాటల)",
    re.IGNORECASE,
)
_OPTION_MARKER_RE = re.compile(
    r"\([A-Ca-c]\)|\bOption\s*[A-C]\b|\bProfile\s*[0-9A-C]\b|\bCandidate\s*[0-9A-C]\b"
    r"|\bExcerpt\s*[0-9A-C]\b|\bSpeaker\s*[0-9A-C]\b",
    re.IGNORECASE,
)


def _qtext(question: dict) -> str:
    """Concatenate the printable surfaces of a coerced question for inspection."""
    parts = [
        str(question.get("content") or ""),
        str(question.get("answer") or ""),
    ]
    oc = question.get("or_choice")
    if isinstance(oc, dict):
        parts.append(str(oc.get("content") or ""))
        parts.append(str(oc.get("answer") or ""))
    return "\n".join(parts)


def _script_ratio(text: str, lo: int, hi: int) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters)


def validate_script(text: str, subject_norm: str) -> Tuple[bool, str]:
    """Hard script guard. Roman-dominant output in a Hindi/Telugu slot is a failure."""
    if subject_norm == "hindi":
        if _script_ratio(text, DEVANAGARI_LO, DEVANAGARI_HI) < 0.5:
            return False, "Hindi output is not predominantly Devanagari (Roman-script leakage)."
    elif subject_norm == "telugu":
        if _script_ratio(text, TELUGU_LO, TELUGU_HI) < 0.5:
            return False, "Telugu output is not predominantly Telugu Unicode (Roman-script leakage)."
    return True, ""


def _has_word_limit(text: str) -> bool:
    return bool(_WORD_LIMIT_RE.search(text))


def count_anuched_hint_points(segment: str) -> int:
    """Count संकेत-बिन्दु in one topic segment: short Devanagari fragments, no digits."""
    frags = re.split(r"[•·\-–—/,;\n]", segment)
    out = 0
    for f in frags:
        f = f.strip()
        if not f or re.search(r"\d", f):
            continue  # skip word-limit / numbering noise
        if re.search(r"[ऀ-ॿ]", f) and len(f.split()) <= 6:
            out += 1
    return out


def _validate_hindi_anuched(text: str) -> Tuple[bool, str]:
    # Each topic ships one "संकेत-बिन्दु" group; split on the label.
    segments = re.split(r"संकेत[-\s]?बि(?:न्|ं)दु", text)
    topics = segments[1:]
    if len(topics) < 3:
        return False, f"अनुच्छेद must provide 3 topics each labelled संकेत-बिन्दु (found {len(topics)})."
    for i, seg in enumerate(topics, 1):
        # Bound a topic's hint group at the next numbered topic marker, if any.
        head = re.split(r"(?m)^\s*\(?[0-9१२३४५६७८९०]+[.)]", seg)[0]
        n = count_anuched_hint_points(head)
        if n < 3:
            return False, f"अनुच्छेद topic {i} has {n} संकेत-बिन्दु (need exactly 3)."
    return True, ""


def _validate_english_analytical(text: str) -> Tuple[bool, str]:
    markers = set(m.group(0).lower().replace(" ", "") for m in _OPTION_MARKER_RE.finditer(text))
    if len(markers) < 2:
        return False, "Analytical-paragraph stimulus needs >= 2 comparable options."
    return True, ""


def validate_telugu_chandas(text: str) -> Tuple[bool, str]:
    """Post-hoc gaṇa↔metre consistency check (only fires on a clear, parseable mismatch)."""
    named = [m for m in TELUGU_METRE_GANA if m in text]
    if not named:
        return True, ""
    for m in named:
        correct = TELUGU_METRE_GANA[m]
        for other, gana in TELUGU_METRE_GANA.items():
            if other != m and gana in text and correct not in text:
                return False, (
                    f"Chandas gaṇa mismatch: text names {m} but lists {other}'s gaṇa ({gana})."
                )
    return True, ""


def validate_composition(slot, question: dict) -> Tuple[bool, str]:
    """Hard composition gate (Hindi अनुच्छेद / English analytical / scenario writing)."""
    subject_norm = normalize_subject(getattr(slot, "subject", ""))
    text = _qtext(question)
    hint = getattr(slot, "instruction_hint", "") or ""

    ok, reason = validate_script(text, subject_norm)
    if not ok:
        return ok, reason

    if not _has_word_limit(text):
        return False, "Composition is missing an explicit word limit in the question stem."

    if subject_norm == "hindi" and "अनुच्छेद" in hint:
        return _validate_hindi_anuched(text)
    if subject_norm == "english" and "Analytical" in hint:
        return _validate_english_analytical(text)
    return True, ""


def validate_grammar(slot, question: dict) -> Tuple[bool, str]:
    subject_norm = normalize_subject(getattr(slot, "subject", ""))
    text = _qtext(question)
    ok, reason = validate_script(text, subject_norm)
    if not ok:
        return ok, reason
    if subject_norm == "telugu" and "ఛందస" in (getattr(slot, "instruction_hint", "") or ""):
        return validate_telugu_chandas(text)
    return True, ""


def validate_passage(slot, question: dict) -> Tuple[bool, str]:
    subject_norm = normalize_subject(getattr(slot, "subject", ""))
    return validate_script(_qtext(question), subject_norm)


def validate_language_question(slot, question: dict) -> Tuple[bool, str]:
    """Single dispatcher. No-op for CONTENT slots (Science/Social/Maths/literature)."""
    mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()
    if mode == "GRAMMAR":
        return validate_grammar(slot, question)
    if mode == "COMPOSITION":
        return validate_composition(slot, question)
    if mode == "PASSAGE":
        return validate_passage(slot, question)
    return True, ""
