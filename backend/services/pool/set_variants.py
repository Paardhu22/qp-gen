"""Derive additional paper Sets (B, C) from an assembled master paper.

Multiple-set generation reuses ONE pool and ONE Model 1 run. Set A is the
master, assembled normally by Model 2. Sets B and C are produced here — never
by generating new questions, only by substituting alternatives that already
exist in the pool.

The rules (from the feature spec) are deliberately mechanical, so this is a
pure, deterministic, Django-free module that a solver can own end to end:

  • MCQs are never replaced — the same MCQs appear in every set.
  • ~30% of the remaining questions are replaced, in mark-priority order
    (5-mark first, then 3-mark, then 2-mark, then whatever is left), because
    higher-mark questions carry more of a paper's uniqueness.
  • A replacement must match the question it displaces on subject, chapter,
    topic, type, marks, difficulty and Bloom level. A near-parallel question,
    in other words — same slot, different wording.
  • If no matching alternative exists in the pool, the original is kept rather
    than the blueprint broken.
  • Shared (and replaced) questions are then shuffled WITHIN their sections so
    the set does not read in the same order as the master. Sections are never
    mixed.

Invariants the caller can rely on: identical total marks, identical section
structure, and no duplicate question id within a single set.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from services.pool.model2 import SlotAssignment
from services.pool.schema import PoolQuestion

#: Question types that must be identical across every set. MCQs anchor a CBSE
#: paper's objective section; the spec fixes them so all sets share them.
DEFAULT_FIXED_TYPES = frozenset({"MCQ"})

#: Share of the replaceable (non-fixed) questions to swap in each variant.
DEFAULT_REPLACE_FRACTION = 0.30


@dataclass
class PaperVariant:
    """One derived set, e.g. Set B.

    `assignments` are in DISPLAY order — already shuffled within each section —
    so the caller renders them in list order rather than re-sorting by slot
    index (which would undo the shuffle).
    """

    label: str
    #: Assignments in display order (sections contiguous and in master order,
    #: questions shuffled within each section).
    assignments: List[SlotAssignment] = field(default_factory=list)
    replaced_count: int = 0
    fixed_count: int = 0
    retained_count: int = 0


def _matches(
    candidate: PoolQuestion, original: PoolQuestion, *, require_topic: bool = True
) -> bool:
    """Is `candidate` a valid parallel replacement for `original`?

    Marks and type decide whether the question can fill the same slot at all;
    subject/chapter/difficulty/bloom keep the replacement pedagogically
    equivalent rather than merely structurally valid. `topic` is included
    when `require_topic` is set, but it is Model 1's free-text label for
    "the specific concept within the chapter" — two genuinely parallel
    questions on the same chapter rarely land on the exact same wording for
    it, so callers try a topic-strict pass first and fall back to
    chapter-level matching (see `_find_replacement`) rather than treating a
    topic mismatch as disqualifying on its own.
    """
    # Provenance first: a Reading asset and a Literature question can look
    # structurally identical (same type, same marks) and still be completely
    # wrong for each other's slot.
    if candidate.generator != original.generator:
        return False
    if int(candidate.marks) != int(original.marks):
        return False
    if candidate.type != original.type:
        return False
    if candidate.blooms != original.blooms:
        return False
    if candidate.difficulty != original.difficulty:
        return False

    def _norm(value: str) -> str:
        return str(value or "").strip().lower()

    if _norm(candidate.subject) != _norm(original.subject):
        return False
    if _norm(candidate.chapter) != _norm(original.chapter):
        return False
    if require_topic and _norm(candidate.topic) != _norm(original.topic):
        return False
    return True


def _find_replacement(
    original: PoolQuestion,
    pool: Sequence[PoolQuestion],
    used_ids: set,
    rng: random.Random,
) -> Optional[PoolQuestion]:
    """Pick an unused pool question that parallels `original`, or None."""

    def _candidates(*, require_topic: bool) -> List[PoolQuestion]:
        return [
            q
            for q in pool
            if q.id not in used_ids
            and q.id != original.id
            and str(q.question or "").strip()
            and _matches(q, original, require_topic=require_topic)
        ]

    candidates = _candidates(require_topic=True)
    if not candidates:
        # No exact-topic parallel — fall back to same subject/chapter/type/
        # marks/difficulty/bloom without requiring Model 1's free-text topic
        # label to match verbatim. Without this fallback almost every slot
        # has zero candidates in practice (topics are LLM-phrased per
        # question), so "swap ~30%" silently degrades to "swap ~0%" and every
        # derived set reads as an exact copy of the master.
        candidates = _candidates(require_topic=False)
    if not candidates:
        return None
    # Sort for determinism, then let the seeded rng pick — so Set B and Set C,
    # seeded differently, tend to land on different alternates for the same
    # slot instead of always the first one.
    candidates.sort(key=lambda q: q.id)
    return rng.choice(candidates)


def _replacement_order(assignments: Sequence[SlotAssignment], fixed_types) -> List[int]:
    """Positions eligible for replacement, in mark-priority order.

    Higher marks first (5 → 3 → 2 → …); the rng-driven caller breaks ties, so a
    fixed secondary key here only guarantees a stable starting order. Fixed
    types (MCQs) are excluded entirely.
    """
    eligible = [
        i
        for i, a in enumerate(assignments)
        if a.question.type not in fixed_types
    ]
    # Negative marks → descending. Slot index as a stable secondary key.
    eligible.sort(
        key=lambda i: (
            -int(assignments[i].question.marks),
            int(getattr(assignments[i].slot, "index", 0) or 0),
        )
    )
    return eligible


def _shuffle_within_sections(
    assignments: Sequence[SlotAssignment], rng: random.Random
) -> List[SlotAssignment]:
    """Reorder questions within each section; keep sections contiguous.

    Section order follows first appearance (which mirrors the master), so the
    blueprint's section sequence is preserved. Only the order of questions
    inside a section changes. A section that shuffles back into its original
    order is rotated by one so the set visibly differs from the master.
    """
    by_section: Dict[str, List[SlotAssignment]] = {}
    order: List[str] = []
    for a in assignments:
        title = str(getattr(a.slot, "section_title", "") or "Questions")
        if title not in by_section:
            by_section[title] = []
            order.append(title)
        by_section[title].append(a)

    result: List[SlotAssignment] = []
    for title in order:
        group = list(by_section[title])
        if len(group) > 1:
            original = list(group)
            rng.shuffle(group)
            if group == original:
                group = group[1:] + group[:1]
        result.extend(group)
    return result


def _clone_assignment(source: SlotAssignment) -> SlotAssignment:
    """A shallow copy that shares the slot but can hold a different question."""
    return SlotAssignment(
        slot=source.slot,
        question=source.question,
        alternates=[],
        or_choice=source.or_choice,
        swapped_by_review=False,
    )


def derive_variant(
    master: Sequence[SlotAssignment],
    pool: Sequence[PoolQuestion],
    *,
    label: str,
    seed: int,
    replace_fraction: float = DEFAULT_REPLACE_FRACTION,
    fixed_types=DEFAULT_FIXED_TYPES,
) -> PaperVariant:
    """Build one variant set from the master's assignments and the pool."""
    rng = random.Random(seed)

    assignments = [_clone_assignment(a) for a in master]

    # Every question already on the paper is reserved, so a replacement can
    # never duplicate one — including the OR-choice halves, which stay fixed.
    used_ids: set = set()
    for a in assignments:
        used_ids.add(a.question.id)
        if a.or_choice is not None:
            used_ids.add(a.or_choice.id)

    total = len(assignments)
    fixed_count = sum(1 for a in assignments if a.question.type in fixed_types)
    replaceable_positions = _replacement_order(assignments, fixed_types)

    # ~30% of the WHOLE paper, matching the spec's "70% remain / 30% replaced".
    target = round(replace_fraction * total)
    target = max(0, min(target, len(replaceable_positions)))

    replaced = 0
    retained = 0
    for position in replaceable_positions:
        if replaced >= target:
            break
        original = assignments[position].question
        alternative = _find_replacement(original, pool, used_ids, rng)
        if alternative is None:
            # No parallel question in the pool — keep the original rather than
            # violate the blueprint.
            retained += 1
            continue
        used_ids.discard(original.id)
        used_ids.add(alternative.id)
        assignments[position].question = alternative
        replaced += 1

    display_order = _shuffle_within_sections(assignments, rng)

    return PaperVariant(
        label=label,
        assignments=display_order,
        replaced_count=replaced,
        fixed_count=fixed_count,
        retained_count=retained,
    )


#: Labels for the second and third sets. Set A is the master and is never
#: produced here.
_VARIANT_LABELS = ["B", "C", "D", "E"]


def derive_variants(
    master: Sequence[SlotAssignment],
    pool: Sequence[PoolQuestion],
    *,
    num_variants: int,
    base_seed: int = 0xB05,
    replace_fraction: float = DEFAULT_REPLACE_FRACTION,
    fixed_types=DEFAULT_FIXED_TYPES,
) -> List[PaperVariant]:
    """Derive `num_variants` sets (B, C, …) from a single master paper."""
    variants: List[PaperVariant] = []
    for i in range(max(0, num_variants)):
        label = _VARIANT_LABELS[i] if i < len(_VARIANT_LABELS) else chr(ord("B") + i)
        variants.append(
            derive_variant(
                master,
                pool,
                label=label,
                # A distinct seed per set so B and C diverge from each other,
                # not just from A.
                seed=base_seed + (i + 1) * 7919,
                replace_fraction=replace_fraction,
                fixed_types=fixed_types,
            )
        )
    return variants
