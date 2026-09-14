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

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Sequence, Tuple

from services.question_types import SHAPES


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
    #: The catalogue type and slot attributes for this shape, stamped onto the
    #: questions the same way. Empty for a shape's default type.
    type_code: str = ""
    hots: bool = False
    competency: bool = False


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


#: Completion tokens one question of each shape needs, explanation included.
#: Defined on the shape itself in `services.question_types.shapes`.
_TOKENS_PER_QUESTION: Dict[str, int] = {shape.code: shape.tokens for shape in SHAPES}


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
                TypeQuota("SHORT_ANSWER", 3, 4, (HOTS_HINT,), hots=True),
            ],
        ),
        Batch(
            "case_study",
            [
                TypeQuota("CASE_STUDY", 4, 6),
                TypeQuota(
                    "SHORT_ANSWER",
                    4,
                    2,
                    (COMPETENCY_HINT,),
                    type_code="APPLICATION_SCENARIO",
                    competency=True,
                ),
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
                TypeQuota("SHORT_ANSWER", 3, 4, (HOTS_HINT,), hots=True),
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
                q.type,
                q.marks,
                max(1, round(q.count * scale)),
                q.hints,
                q.asset_type,
                q.type_code,
                q.hots,
                q.competency,
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
    from services.question_types import default_type_for_shape, resolve_slot_type

    Key = Tuple[str, int, str, str, bool, bool]
    counts: Dict[Key, int] = {}
    hints: Dict[Key, List[str]] = {}
    order: List[Key] = []
    for slot in plan or []:
        raw_type = getattr(slot, "question_type", "") or ""
        raw_code = getattr(slot, "type_code", "") or ""
        if not (normalize_type(raw_type) or raw_code):
            continue
        slot_type = resolve_slot_type(
            raw_code,
            raw_type,
            hots=bool(getattr(slot, "hots", False)),
            competency=bool(getattr(slot, "competency", False)),
        )
        qtype = slot_type.shape
        try:
            marks = int(getattr(slot, "marks", 0) or 0)
        except (TypeError, ValueError):
            continue
        if marks <= 0:
            continue
        asset_type = str(getattr(slot, "asset_type", "") or "")
        # A shape's default type is what these prompts always asked for, so
        # it stays out of the key: those batches read exactly as before.
        type_code = (
            "" if slot_type.code == default_type_for_shape(qtype) else slot_type.code
        )
        key = (qtype, marks, asset_type, type_code, slot_type.hots, slot_type.competency)
        if key not in counts:
            order.append(key)
            hints[key] = attribute_hints(slot_type.hots, slot_type.competency)
        counts[key] = counts.get(key, 0) + 1
        hint = str(getattr(slot, "instruction_hint", "") or "").strip()
        if hint and hint not in hints[key]:
            hints[key].append(hint)

    if not order:
        return []

    batches = [
        Batch(
            "_".join(
                part
                for part in (
                    f"{qtype.lower()}_{marks}m",
                    asset_type,
                    type_code.lower(),
                    "hots" if hots else "",
                    "competency" if competency else "",
                )
                if part
            ),
            [
                TypeQuota(
                    qtype,
                    marks,
                    counts[key],
                    tuple(hints[key]),
                    asset_type,
                    type_code,
                    hots,
                    competency,
                )
            ],
        )
        for key in order
        for (qtype, marks, asset_type, type_code, hots, competency) in [key]
    ]
    # A type the teacher picked by name has no stand-in of its own shape, so
    # one answer the writer gets wrong leaves its slot empty. Its batch always
    # carries a spare: a few more output tokens on a call made either way. A
    # shape's default type keeps exactly the counts it always had.
    spared: List[Batch] = []
    for batch, key in zip(_scale_batches(batches, target_total), order):
        quota = batch.quotas[0]
        if quota.type_code and quota.count <= counts[key]:
            batch = Batch(batch.name, [replace(quota, count=counts[key] + 1)])
        spared.append(batch)
    return spared


#: What each slot attribute adds to Model 1's instruction for its quota.
HOTS_HINT = (
    "Higher-order thinking: every question must require analysis, evaluation "
    "or creation (Bloom ANALYZE, EVALUATE or CREATE), never recall."
)
COMPETENCY_HINT = (
    "Competency based: frame every question in a realistic, unfamiliar "
    "real-world situation the student must apply the concept to."
)


def attribute_hints(hots: bool, competency: bool) -> List[str]:
    hints: List[str] = []
    if hots:
        hints.append(HOTS_HINT)
    if competency:
        hints.append(COMPETENCY_HINT)
    return hints


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
