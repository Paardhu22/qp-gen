"""Paper difficulty as a slider, not a switch.

A teacher picks a level from 0 (gentle) to 100 (demanding). That level is not a
label stuck on every question: it fixes the *mix* of the paper — what share of
its questions are basic, moderate and challenging — and the mix is then dealt to
the individual slots, so each question is written, and later selected, against
its own target.

Why this is its own module. Difficulty used to be one word (``easy`` /
``medium`` / ``hard``) applied to the whole paper. Model 1 was told to
"calibrate overall difficulty", which is not something a model can act on, and
Model 2 treated it as a faint nudge beside much louder scoring terms. The
result was an easy paper and a hard paper that read alike. Here:

* ``shares_for``      the level → mix curve (per class band)
* ``assign_tiers``    the mix → a tier for every slot (monotone in the level)
* ``apply_profile``   stamp those tiers on a plan's slots
* ``rule_text``       what the three tiers *mean*, for the question writer

Three properties are tested and meant to be kept:

* a higher level never moves a slot to an easier tier (the paper shifts
  progressively, it does not reshuffle);
* every part of the paper carries the mix, tilted a little toward harder
  questions where the marks are higher, rather than all the hard questions
  landing in one section;
* even the top of the scale is a *board-appropriate* paper: at most ~45% of it
  challenging, never fewer than ~12% basic, and the writer is told to stay in
  the class's syllabus.

Pure Python; no Django.
"""

from __future__ import annotations

import dataclasses
import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

TIERS: Tuple[str, str, str] = ("easy", "medium", "hard")
DEFAULT_LEVEL = 50

#: What the old three-way switch means on the slider. Requests, saved templates
#: and chat answers from before the slider carry only a label.
LABEL_LEVELS: Dict[str, int] = {"easy": 15, "medium": 50, "hard": 85}

#: The level at which a paper starts to read as medium / hard, for the label
#: that older consumers (and the stored per-question tag) still use.
_MEDIUM_FROM = 34
_HARD_FROM = 67

# ── The curve ───────────────────────────────────────────────────────────

#: (easy, medium, hard) shares at the bottom, middle and top of the slider, by
#: class band. Between anchors the shares are interpolated linearly, so a small
#: move of the slider is a small move of the mix.
#:
#: The top of the scale is deliberately not extreme: challenging questions top
#: out at 45% for the board years (and far less for younger classes), and basic
#: ones never vanish. The bottom is "mostly straightforward" but not all basic.
#: A younger class's "hard" paper leans easier than a board year's.
#:
#: Mirrored in `frontend/features/generation/difficulty-profile.ts` for the
#: slider's preview; `test_difficulty` fails if they drift apart.
ANCHORS: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "1-2": {"low": (0.78, 0.22, 0.00), "mid": (0.55, 0.40, 0.05), "high": (0.40, 0.48, 0.12)},
    "3-5": {"low": (0.68, 0.28, 0.04), "mid": (0.40, 0.45, 0.15), "high": (0.22, 0.46, 0.32)},
    "6-8": {"low": (0.62, 0.31, 0.07), "mid": (0.35, 0.48, 0.17), "high": (0.15, 0.45, 0.40)},
    "9-10": {"low": (0.58, 0.34, 0.08), "mid": (0.30, 0.50, 0.20), "high": (0.12, 0.43, 0.45)},
}


def class_band(class_num: Optional[int]) -> str:
    """The band a class falls in. No class means the board-year band."""
    if class_num is None:
        return "9-10"
    if class_num <= 2:
        return "1-2"
    if class_num <= 5:
        return "3-5"
    if class_num <= 8:
        return "6-8"
    return "9-10"


def normalize_level(value: Any, default: int = DEFAULT_LEVEL) -> int:
    """Any way a client may state a difficulty, as a level from 0 to 100.

    A number (or numeric string) is the slider itself, clamped. The words
    ``easy`` / ``medium`` / ``hard`` map to their anchors. Anything else is the
    default: an unreadable difficulty must not fail a generation.
    """
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return max(0, min(100, int(round(value))))
    text = str(value).strip().lower()
    if not text:
        return default
    if text in LABEL_LEVELS:
        return LABEL_LEVELS[text]
    try:
        return max(0, min(100, int(round(float(text)))))
    except ValueError:
        return default


def resolve_level(payload: Optional[Dict[str, Any]], difficulty: Any = None) -> int:
    """The level a request asks for: the slider if it sent one, else its label."""
    payload = payload or {}
    for key in ("difficultyLevel", "difficulty_level"):
        if payload.get(key) not in (None, ""):
            return normalize_level(payload[key])
    return normalize_level(difficulty if difficulty not in (None, "") else payload.get("difficulty"))


def label_for_level(level: int) -> str:
    """``easy`` / ``medium`` / ``hard`` for a level: the tag older code reads."""
    level = normalize_level(level)
    if level < _MEDIUM_FROM:
        return "easy"
    if level < _HARD_FROM:
        return "medium"
    return "hard"


def shares_for(level: int, class_num: Optional[int] = None) -> Dict[str, float]:
    """The mix at a level: the share of basic, moderate and challenging questions."""
    level = normalize_level(level)
    anchors = ANCHORS[class_band(class_num)]
    if level <= 50:
        a, b, t = anchors["low"], anchors["mid"], level / 50.0
    else:
        a, b, t = anchors["mid"], anchors["high"], (level - 50) / 50.0
    mix = [x + (y - x) * t for x, y in zip(a, b)]
    return {tier: round(share, 6) for tier, share in zip(TIERS, mix)}


def tier_counts(total: int, shares: Dict[str, float]) -> Tuple[int, int, int]:
    """How many of ``total`` slots go to each tier, as (easy, medium, hard).

    The two ends are rounded independently and the middle takes the rest, which
    keeps each count monotone as the level moves: more hard slots, fewer easy
    ones, never the reverse.
    """
    total = max(0, int(total))
    easy = int(math.floor(total * shares["easy"] + 0.5))
    hard = int(math.floor(total * shares["hard"] + 0.5))
    while easy + hard > total:
        if easy >= hard:
            easy -= 1
        else:
            hard -= 1
    return easy, total - easy - hard, hard


# ── Dealing the mix to slots ────────────────────────────────────────────

_GOLDEN = 0.6180339887498949

#: How much a slot's own character tilts it toward a harder tier. Small enough
#: that the mix shows in every section; large enough that a 5-mark analysis
#: question is likelier to be challenging than a 1-mark recall one.
_TILT = 0.30

_MARKS_AFFINITY = {1: 0.15, 2: 0.30, 3: 0.45, 4: 0.60}
_RECALL_SHAPES = ("TRUE", "FILL", "ONE_WORD", "MATCH", "DEFINE")
_DEMANDING_SHAPES = ("ASSERTION", "CASE", "NUMERIC", "LONG", "PROOF")


def slot_affinity(slot: Any) -> float:
    """How well a slot suits a harder question, from 0 to 1.

    More marks, higher-order thinking and case/assertion/numerical shapes pull
    up; recall shapes (true/false, fill-in, one word) pull down.
    """
    try:
        marks = int(getattr(slot, "marks", 0) or 0)
    except (TypeError, ValueError):
        marks = 0
    score = _MARKS_AFFINITY.get(marks, 0.75 if marks >= 5 else 0.30)
    if getattr(slot, "hots", False):
        score += 0.20
    if getattr(slot, "competency", False):
        score += 0.05
    shape = str(getattr(slot, "question_type", "") or "").upper()
    if any(word in shape for word in _DEMANDING_SHAPES):
        score += 0.10
    if any(word in shape for word in _RECALL_SHAPES):
        score -= 0.10
    return max(0.0, min(1.0, score))


def assign_tiers(slots: Sequence[Any], level: int, class_num: Optional[int] = None) -> List[str]:
    """A tier for every slot, in slot order.

    Slots are ranked by ``tilt * affinity + spread``, where ``spread`` walks the
    unit interval by the golden ratio so that any stretch of the paper — a
    section, a run of one-markers — is spread evenly across the range. The
    hardest ``H`` slots are challenging and the lowest ``E`` are basic.

    Because the ranking does not depend on the level, a higher level only ever
    *grows* the challenging set and *shrinks* the basic set: no slot gets
    easier as the slider goes up.
    """
    n = len(slots)
    if n == 0:
        return []
    easy, _, hard = tier_counts(n, shares_for(level, class_num))

    keys = [
        _TILT * slot_affinity(slot) + math.fmod((index + 1) * _GOLDEN, 1.0)
        for index, slot in enumerate(slots)
    ]
    # Ties broken by position so the result is a pure function of the plan.
    order = sorted(range(n), key=lambda i: (keys[i], i))

    tiers = ["medium"] * n
    for i in order[:easy]:
        tiers[i] = "easy"
    for i in order[n - hard:] if hard else []:
        tiers[i] = "hard"
    return tiers


def apply_profile(plan: Sequence[Any], level: int, class_num: Optional[int] = None) -> List[Any]:
    """The plan with a target tier stamped on every slot.

    ``tier`` is the marker that a profile was applied (it stays empty on a plan
    that only carries an overall label); ``difficulty`` is set to the same
    value, because that is the field the rest of the pipeline already reads
    off a slot. A slot that is not a dataclass with those fields is left as it
    is: a profile must never fail a generation.
    """
    slots = list(plan or [])
    tiers = assign_tiers(slots, level, class_num)
    stamped: List[Any] = []
    for slot, tier in zip(slots, tiers):
        try:
            stamped.append(dataclasses.replace(slot, tier=tier, difficulty=tier))
        except (TypeError, ValueError):
            stamped.append(slot)
    return stamped


def mix_of(plan: Sequence[Any]) -> Dict[str, int]:
    """How many slots of a plan sit in each tier (slots without one are not counted)."""
    counts = {tier: 0 for tier in TIERS}
    for slot in plan or []:
        tier = str(getattr(slot, "tier", "") or "")
        if tier in counts:
            counts[tier] += 1
    return counts


def profile_summary(plan: Sequence[Any], level: int, class_num: Optional[int] = None) -> Dict[str, Any]:
    """What was asked for and what the plan holds, for the client and the logs."""
    return {
        "level": normalize_level(level),
        "label": label_for_level(level),
        "band": class_band(class_num),
        "shares": shares_for(level, class_num),
        "counts": mix_of(plan),
    }


# ── What the tiers mean (for the question writer) ───────────────────────

_SUBJECT_HARD = {
    "maths": (
        "combines two or more concepts (a coordinate-geometry condition with algebra, "
        "trigonometry inside a mensuration problem) or is a multi-step problem with an "
        "involved but board-level calculation"
    ),
    "science": (
        "applies a concept to an unfamiliar situation, combines two ideas, or asks the "
        "student to analyse given data, an experiment or a scenario"
    ),
    "social": (
        "asks the student to analyse causes and consequences, compare, or evaluate, "
        "drawing several facts together"
    ),
    "language": (
        "asks for inference, tone or interpretation beyond the literal meaning, or "
        "careful control of structure and expression"
    ),
}


def subject_family(subject: str) -> str:
    """The broad family a subject belongs to, for the wording of the tiers."""
    name = (subject or "").strip().lower()
    if "math" in name or "statistic" in name or "ict" in name or "comput" in name:
        return "maths"
    if any(word in name for word in ("social", "history", "geograph", "civics", "econom", "political")):
        return "social"
    if any(word in name for word in ("english", "hindi", "telugu", "sanskrit", "language", "literature")):
        return "language"
    return "science"


def describe_mix(level: int, class_num: Optional[int] = None) -> str:
    """The mix at a level, in words: ``about 30% basic, 50% moderate and 20% challenging``."""
    shares = shares_for(level, class_num)
    parts = [
        f"{round(shares['easy'] * 100)}% basic",
        f"{round(shares['medium'] * 100)}% moderate",
        f"{round(shares['hard'] * 100)}% challenging",
    ]
    return f"about {parts[0]}, {parts[1]} and {parts[2]}"


def rule_text(level: int, class_num: Optional[int], subject: str) -> str:
    """The difficulty rule for a question writer's system prompt.

    Says what each tier *is*, because a bare "hard" is the thing models do not
    act on: tiers differ in the thinking they demand (steps, concepts combined,
    working involved), never only in numbers or wording, and the top tier stays
    inside the class's syllabus.
    """
    grade = f"Class {class_num}" if class_num else "this class"
    hard_detail = _SUBJECT_HARD[subject_family(subject)]
    return (
        "Difficulty is set question by question: each group in the batch "
        "instruction states how many questions to write at each level, and you set "
        "every question's `difficulty` to its level. The levels:\n"
        "      • easy (basic): tests a fundamental idea or one direct application — "
        "a single concept and a single step, straight from the chapter. It is still a "
        "real question that needs understanding; never a bare lookup of a name, term or "
        "number that needs none.\n"
        "      • medium (moderate): needs some reasoning — two or three steps, choosing the "
        "right method, applying a concept to a new but routine situation, or connecting "
        "two ideas.\n"
        f"      • hard (challenging): {hard_detail}.\n"
        "      Levels differ in the THINKING a question demands — more steps, more "
        "concepts combined, more involved working — not in its numbers or wording, so "
        "never write a harder question by changing the numbers of an easier one. Stay "
        f"strictly inside the {grade} syllabus at every level: no off-syllabus topics, "
        "trick wording or competition-style problems. Challenging means demanding for "
        f"a good {grade} student, not impossible. "
        f"Across the paper the aim is {describe_mix(level, class_num)}."
    )


def mix_instruction(tiers: Tuple[int, int, int]) -> str:
    """The batch-instruction line for a quota's tier counts (empty when it has none)."""
    easy, medium, hard = tiers
    if easy + medium + hard <= 0:
        return ""
    parts = []
    if easy:
        parts.append(f"{easy} basic (`easy`)")
    if medium:
        parts.append(f"{medium} moderate (`medium`)")
    if hard:
        parts.append(f"{hard} challenging (`hard`)")
    return (
        "Difficulty mix for these: " + ", ".join(parts) + ". Write each at its level "
        "(see rule 8) and set its `difficulty` to match."
    )


def paper_brief(level: int, class_num: Optional[int] = None) -> str:
    """One line for the generators that write a few whole items at a time
    (reading passages, grammar sets) and so cannot be handed a count per tier."""
    return (
        f"Overall difficulty: {label_for_level(level)} (level {normalize_level(level)}/100). "
        f"Across the paper the aim is {describe_mix(level, class_num)}; pitch these items "
        "so they carry that mix, at the thinking each level demands, and stay inside the "
        "class's syllabus."
    )
