"""How many of each question type Model 1 should produce, per subject.

A pool exists to be *selected from*, so it has to over-provision every shape
the blueprint might ask for. The CBSE Class 10 Science/Social Science board
pattern needs 20×1m, 6×2m, 7×3m, 3×5m and 3×4m case studies — a pool that
holds exactly that many can only be assembled one way, and Model 2's review
step would have nothing to choose between. Each recipe therefore carries
roughly 2× the board requirement.

Recipes are also the unit of parallelism: each batch is one LLM call, sized so
its output lands well inside the completion limit. Splitting by question shape
rather than by chapter section means every batch still sees the whole chapter,
which is what stops a batch from over-indexing on one section.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class TypeQuota:
    """`count` questions of `type`, each worth `marks`.

    `hints` carry the blueprint's per-slot `instruction_hint` for this shape.
    The pool pipeline reads only `question_type` and `marks` off a slot, so
    without this the structural detail the blueprint already knows — "five
    questions, the student answers any four", "two extract options from
    different chapters" — never reached Model 1, and a 12-mark composite slot
    came back as one 12-mark essay. Empty for the fixed per-subject recipes, so
    Science / Social Science / Mathematics prompts are byte-identical.
    """

    type: str
    marks: int
    count: int
    hints: Tuple[str, ...] = ()
    #: The blueprint's `asset_type` for this shape ("extract_prose",
    #: "long_answer"). Stamped onto the questions Model 1 produces so the
    #: assembler can tell a prose extract from a poetry extract — both are
    #: 5-mark descriptive questions and are otherwise indistinguishable, which
    #: is how a poetry extract ended up in the prose slot. Empty for the fixed
    #: per-subject recipes.
    asset_type: str = ""


@dataclass(frozen=True)
class Batch:
    """One Model 1 call."""

    name: str
    quotas: Sequence[TypeQuota]

    @property
    def total(self) -> int:
        return sum(q.count for q in self.quotas)

    @property
    def max_output_tokens(self) -> int:
        """Budget from the batch's heaviest shape.

        A 5-mark long answer with an explanation runs ~350 tokens; a 4-mark
        case study with three sub-parts runs ~600. Under-budgeting here is the
        classic truncation bug — the last question of the batch arrives half
        written and gets dropped by the normaliser.
        """
        per_question = max(
            (_TOKENS_PER_QUESTION.get(q.type, 200) for q in self.quotas),
            default=200,
        )
        # +15% headroom, floor of 2000 so a small batch still has room.
        return max(2000, int(self.total * per_question * 1.15))


_TOKENS_PER_QUESTION: Dict[str, int] = {
    "MCQ": 130,
    "ASSERTION_REASON": 170,
    "TRUE_FALSE": 90,
    "FILL_IN_THE_BLANK": 90,
    "ONE_WORD": 80,
    "MATCH_THE_FOLLOWING": 200,
    "VERY_SHORT_ANSWER": 130,
    "SHORT_ANSWER": 220,
    "NUMERICAL": 260,
    "EXPERIMENTAL": 260,
    "LONG_ANSWER": 400,
    "HOTS": 300,
    "COMPETENCY": 320,
    "CASE_STUDY": 650,
    "READING_COMP": 650,
    "DIAGRAM": 220,
    "GRAMMAR": 120,
    "EXTRACT_PROSE": 300,
    "EXTRACT_POETRY": 300,
    "ANALYTICAL_PARAGRAPH": 320,
    "LETTER": 400,
    "COMPOSITION": 400,
}


def _content_subject_batches() -> List[Batch]:
    """Science / Social Science / Mathematics — the CBSE A–E skeleton.

    Totals 84 questions against a 38-question board paper.
    """
    return [
        Batch(
            "objective",
            [
                TypeQuota("MCQ", 1, 30),
                TypeQuota("ASSERTION_REASON", 1, 10),
            ],
        ),
        Batch(
            "short",
            [
                TypeQuota("VERY_SHORT_ANSWER", 1, 6),
                TypeQuota("SHORT_ANSWER", 2, 14),
                TypeQuota("SHORT_ANSWER", 3, 14),
            ],
        ),
        Batch(
            "long",
            [
                TypeQuota("LONG_ANSWER", 5, 8),
                TypeQuota("HOTS", 3, 4),
            ],
        ),
        Batch(
            "case_study",
            [
                TypeQuota("CASE_STUDY", 4, 6),
                TypeQuota("COMPETENCY", 4, 2),
            ],
        ),
    ]


def _mathematics_batches() -> List[Batch]:
    """Maths leans numerical and needs far fewer prose questions."""
    return [
        Batch(
            "objective",
            [
                TypeQuota("MCQ", 1, 30),
                TypeQuota("ASSERTION_REASON", 1, 10),
            ],
        ),
        Batch(
            "short",
            [
                TypeQuota("VERY_SHORT_ANSWER", 1, 4),
                TypeQuota("NUMERICAL", 2, 14),
                TypeQuota("NUMERICAL", 3, 14),
            ],
        ),
        Batch(
            "long",
            [
                TypeQuota("LONG_ANSWER", 5, 8),
                TypeQuota("HOTS", 3, 4),
            ],
        ),
        Batch(
            "case_study",
            [TypeQuota("CASE_STUDY", 4, 8)],
        ),
    ]


def _language_batches() -> List[Batch]:
    """English / Hindi / Telugu.

    Grammar and composition slots are rule- or scenario-based rather than
    chapter-grounded, but they still belong in the pool so a language paper can
    be assembled from saved questions without a second engine.
    """
    return [
        Batch(
            "objective",
            [
                TypeQuota("MCQ", 1, 20),
                TypeQuota("GRAMMAR", 1, 16),
            ],
        ),
        Batch(
            "extracts",
            [
                TypeQuota("EXTRACT_PROSE", 3, 8),
                TypeQuota("EXTRACT_POETRY", 3, 8),
                TypeQuota("SHORT_ANSWER", 2, 10),
            ],
        ),
        Batch(
            "long",
            [
                TypeQuota("LONG_ANSWER", 5, 6),
                TypeQuota("ANALYTICAL_PARAGRAPH", 5, 4),
            ],
        ),
        Batch(
            "comprehension",
            [
                TypeQuota("READING_COMP", 5, 3),
                TypeQuota("LETTER", 5, 3),
                TypeQuota("COMPOSITION", 5, 3),
            ],
        ),
    ]


_LANGUAGE_SUBJECTS = {"english", "hindi", "telugu", "sanskrit"}


def _scale_batches(batches: Sequence[Batch], target_total: int) -> List[Batch]:
    """Rescale a recipe to `target_total`, preserving its type/mark mix.

    Quotas scale proportionally and never drop below 1, so every shape in the
    recipe survives at any size — a small (unit-test) pool keeps one of each.
    """
    batches = list(batches)
    if not target_total or target_total <= 0:
        return batches

    current = sum(b.total for b in batches)
    if current == 0 or target_total == current:
        return batches

    scale = target_total / current
    scaled: List[Batch] = []
    for batch in batches:
        quotas = [
            TypeQuota(
                q.type, q.marks, max(1, round(q.count * scale)), q.hints, q.asset_type
            )
            for q in batch.quotas
        ]
        scaled.append(Batch(batch.name, quotas))
    return scaled


def batches_from_plan(plan: Sequence[Any], *, target_total: int = 0) -> List[Batch]:
    """Derive a Model 1 recipe from the actual blueprint plan.

    The fixed per-subject recipes below are tuned to the Science/Social Science
    skeleton (atomic 1–5 mark questions). Composite-question subjects — the CBSE
    language papers especially — ask for shapes those recipes never produce (a
    10-mark reading-comprehension slot, a 12-mark "answer any 4 of 5" bundle, a
    6-mark long answer). `slot_accepts` matches on EXACT marks, so a pool that
    lacks a slot's mark value can never fill it, and the slot renders empty.

    Building the recipe straight from the plan guarantees the pool holds every
    (type, marks) shape the blueprint will ask for. One batch per distinct shape
    keeps each Model 1 call small and independently retryable, and lets the
    token budget track that shape. Over-provisioning is handled by the caller's
    `target_total` (the pipeline sizes it well above the blueprint), which the
    proportional scaling then spreads across shapes.

    Each shape also carries the `instruction_hint`s of the slots that produced
    it, so the structural detail the blueprint knows reaches Model 1 instead of
    being dropped on the floor (see `TypeQuota.hints`).

    Shapes are keyed on `(type, marks, asset_type)`. Including the asset type
    is what keeps a prose-extract batch separate from a poetry-extract batch —
    they are both 5-mark descriptive questions, so without it they collapse
    into one batch and the assembler has no way to tell the two slots' answers
    apart. Blueprints that declare no asset types (every non-English subject)
    key on `(type, marks)` exactly as before.
    """
    from services.pool.schema import normalize_type

    Key = Tuple[str, int, str]
    counts: Dict[Key, int] = {}
    hints: Dict[Key, List[str]] = {}
    order: List[Key] = []
    for slot in plan or []:
        raw_type = getattr(slot, "question_type", "") or ""
        qtype = normalize_type(raw_type)
        if not qtype:
            continue
        try:
            marks = int(getattr(slot, "marks", 0) or 0)
        except (TypeError, ValueError):
            continue
        if marks <= 0:
            continue
        asset_type = str(getattr(slot, "asset_type", "") or "")
        key = (qtype, marks, asset_type)
        if key not in counts:
            order.append(key)
            hints[key] = []
        counts[key] = counts.get(key, 0) + 1
        hint = str(getattr(slot, "instruction_hint", "") or "").strip()
        if hint and hint not in hints[key]:
            hints[key].append(hint)

    if not order:
        return []

    batches = [
        Batch(
            f"{qtype.lower()}_{marks}m" + (f"_{asset_type}" if asset_type else ""),
            [
                TypeQuota(
                    qtype,
                    marks,
                    counts[key],
                    tuple(hints[key]),
                    asset_type,
                )
            ],
        )
        for key in order
        for (qtype, marks, asset_type) in [key]
    ]
    return _scale_batches(batches, target_total)


def batches_for_subject(subject_norm: str, *, target_total: int = 0) -> List[Batch]:
    """Pick the recipe for a subject, optionally rescaled to a target size.

    `target_total` lets a caller ask for a smaller pool (a unit test paper does
    not need 84 questions). Quotas scale proportionally, never below 1, so the
    type mix is preserved at any size.
    """
    subject = (subject_norm or "").strip().lower()

    if subject in _LANGUAGE_SUBJECTS:
        batches = _language_batches()
    elif subject in {"mathematics", "maths", "math"}:
        batches = _mathematics_batches()
    else:
        batches = _content_subject_batches()

    return _scale_batches(batches, target_total)


def default_pool_size(subject_norm: str) -> int:
    return sum(b.total for b in batches_for_subject(subject_norm))
