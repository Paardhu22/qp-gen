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
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class TypeQuota:
    """`count` questions of `type`, each worth `marks`."""

    type: str
    marks: int
    count: int


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

    if not target_total or target_total <= 0:
        return batches

    current = sum(b.total for b in batches)
    if current == 0 or target_total == current:
        return batches

    scale = target_total / current
    scaled: List[Batch] = []
    for batch in batches:
        quotas = [
            TypeQuota(q.type, q.marks, max(1, round(q.count * scale)))
            for q in batch.quotas
        ]
        scaled.append(Batch(batch.name, quotas))
    return scaled


def default_pool_size(subject_norm: str) -> int:
    return sum(b.total for b in batches_for_subject(subject_norm))
