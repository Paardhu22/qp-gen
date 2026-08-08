"""The Question Pool contract.

Every stage of the pool architecture speaks this shape:

    Model 1 ─┐
             ├─→ PoolQuestion[] ─→ store ─→ Model 2 ─→ Paper
    Image ───┘

The canonical type vocabulary is deliberately `QuestionTypeCode` from
`q_instructions.core.enums`, NOT a fresh set. Model 2 has to map pool
questions onto blueprint slots produced by `build_question_plan`, and those
slots carry `question_type` (a QuestionTypeCode name) plus a coarser
`legacy_type`. Inventing a parallel vocabulary here would mean a lossy
translation table sitting between the pool and the blueprint — and every
mismatch in it shows up as an unfillable slot at assembly time.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from utils.ids import generate_id

# ── Canonical vocabularies ──────────────────────────────────────────────

#: The routing key for "written from uploaded textbook content by Model 1".
#: Lives here, at the bottom of the dependency graph, because both the pool and
#: `services.assets` need it and the pool cannot import the asset package
#: (the asset package is built on this module). `services.assets.registry`
#: re-exports it as the public name.
DEFAULT_GENERATOR = "question_pool"

#: Question types the pool can hold. Superset of QuestionTypeCode: the extra
#: members are the language-subject types the router emits (READING_COMP,
#: LETTER, GRAMMAR, …) plus VERY_SHORT_ANSWER, which CBSE uses as a distinct
#: 1-mark descriptive type but QuestionTypeCode folds into SHORT_ANSWER.
QUESTION_TYPES = {
    "MCQ",
    "ASSERTION_REASON",
    "CASE_STUDY",
    "NUMERICAL",
    "DIAGRAM",
    "EXPERIMENTAL",
    "HOTS",
    "COMPETENCY",
    "VERY_SHORT_ANSWER",
    "SHORT_ANSWER",
    "LONG_ANSWER",
    # Language subjects
    "READING_COMP",
    "EXTRACT_PROSE",
    "EXTRACT_POETRY",
    "ANALYTICAL_PARAGRAPH",
    "GRAMMAR",
    "LETTER",
    "COMPOSITION",
    # Objective short forms
    "FILL_IN_THE_BLANK",
    "TRUE_FALSE",
    "MATCH_THE_FOLLOWING",
    "ONE_WORD",
}

BLOOMS_LEVELS = {
    "REMEMBER", "UNDERSTAND", "APPLY", "ANALYZE", "EVALUATE", "CREATE",
}

DIFFICULTIES = {"easy", "medium", "hard"}

#: Types whose answer is chosen from a fixed option list. Model 2 rejects any
#: of these that arrive without options, and the normaliser refuses to coerce
#: one into existence — a 4-option MCQ with 2 options is a broken question,
#: not a fixable one.
OPTION_BEARING_TYPES = {"MCQ", "ASSERTION_REASON", "TRUE_FALSE", "MATCH_THE_FOLLOWING"}

#: Assertion-Reason always uses the same four CBSE directions, so the pool
#: stores them verbatim rather than trusting the model to restate them.
ASSERTION_REASON_OPTIONS = [
    "Both Assertion (A) and Reason (R) are true and Reason (R) is the correct explanation of Assertion (A).",
    "Both Assertion (A) and Reason (R) are true but Reason (R) is not the correct explanation of Assertion (A).",
    "Assertion (A) is true but Reason (R) is false.",
    "Assertion (A) is false but Reason (R) is true.",
]

#: Maps the coarse `legacy_type` on a blueprint slot to every pool type that
#: can legitimately fill it. Model 2 uses this when a slot only specifies the
#: legacy type. SHORT deliberately accepts several descriptive types — a
#: 2-mark "SHORT" slot is happy with a NUMERICAL or EXPERIMENTAL question.
LEGACY_TYPE_ACCEPTS: Dict[str, set[str]] = {
    "MCQ": {"MCQ"},
    "ASSERTION_REASON": {"ASSERTION_REASON"},
    "CASE_STUDY": {"CASE_STUDY", "READING_COMP"},
    "DIAGRAM": {"DIAGRAM"},
    "SHORT": {
        "SHORT_ANSWER", "VERY_SHORT_ANSWER", "NUMERICAL", "EXPERIMENTAL",
        "COMPETENCY", "HOTS", "GRAMMAR", "EXTRACT_PROSE", "EXTRACT_POETRY",
        "ANALYTICAL_PARAGRAPH", "FILL_IN_THE_BLANK", "TRUE_FALSE",
        "MATCH_THE_FOLLOWING", "ONE_WORD",
    },
    "LONG": {"LONG_ANSWER", "CASE_STUDY", "LETTER", "COMPOSITION", "HOTS"},
}

#: Type synonyms the LLM reliably emits despite an explicit enum instruction.
_TYPE_ALIASES = {
    "MULTIPLE_CHOICE": "MCQ",
    "MULTIPLE CHOICE": "MCQ",
    "MCQS": "MCQ",
    "OBJECTIVE": "MCQ",
    "ASSERTION": "ASSERTION_REASON",
    "ASSERTION_AND_REASON": "ASSERTION_REASON",
    "ASSERTION-REASON": "ASSERTION_REASON",
    "AR": "ASSERTION_REASON",
    "CASE": "CASE_STUDY",
    "CASE_BASED": "CASE_STUDY",
    "CBQ": "CASE_STUDY",
    "SOURCE_BASED": "CASE_STUDY",
    "VSA": "VERY_SHORT_ANSWER",
    "VERY_SHORT": "VERY_SHORT_ANSWER",
    "SA": "SHORT_ANSWER",
    "SHORT": "SHORT_ANSWER",
    "LA": "LONG_ANSWER",
    "LONG": "LONG_ANSWER",
    "ESSAY": "LONG_ANSWER",
    "NUMERIC": "NUMERICAL",
    "CALCULATION": "NUMERICAL",
    "FILL_IN_THE_BLANKS": "FILL_IN_THE_BLANK",
    "FILL_IN_BLANK": "FILL_IN_THE_BLANK",
    "TRUE_OR_FALSE": "TRUE_FALSE",
    "MATCH": "MATCH_THE_FOLLOWING",
    "MATCHING": "MATCH_THE_FOLLOWING",
    "DIAGRAM_BASED": "DIAGRAM",
    "IMAGE": "DIAGRAM",
    "IMAGE_BASED": "DIAGRAM",
    "PICTURE_BASED": "DIAGRAM",
    "GRAPH": "DIAGRAM",
}

_BLOOMS_ALIASES = {
    "REMEMBERING": "REMEMBER",
    "KNOWLEDGE": "REMEMBER",
    "RECALL": "REMEMBER",
    "UNDERSTANDING": "UNDERSTAND",
    "COMPREHENSION": "UNDERSTAND",
    "APPLYING": "APPLY",
    "APPLICATION": "APPLY",
    "ANALYSING": "ANALYZE",
    "ANALYZING": "ANALYZE",
    "ANALYSE": "ANALYZE",
    "ANALYSIS": "ANALYZE",
    "EVALUATING": "EVALUATE",
    "EVALUATION": "EVALUATE",
    "CREATING": "CREATE",
    "SYNTHESIS": "CREATE",
}

_DIFFICULTY_ALIASES = {
    "e": "easy", "simple": "easy", "basic": "easy", "low": "easy",
    "m": "medium", "moderate": "medium", "average": "medium", "mid": "medium",
    "h": "hard", "difficult": "hard", "challenging": "hard", "high": "hard",
    "hots": "hard",
}


class PoolValidationError(ValueError):
    """A raw question could not be coerced into the pool contract."""


@dataclass
class PoolQuestion:
    """One question in the pool. Mirrors the persisted `Question` row.

    `question` (not `content`) is the field name here because that is the
    contract the architecture spec defines and what Model 1 is told to emit.
    `to_model_kwargs()` translates to the Django column names.
    """

    id: str
    subject: str
    chapter: str
    topic: str
    type: str
    blooms: str
    difficulty: str
    marks: int
    question: str
    options: List[str] = field(default_factory=list)
    answer: str = ""
    explanation: str = ""
    image: Optional[str] = None

    #: Provenance. `generator` names the pipeline that wrote this question and
    #: is the first thing `slot_accepts` checks — a Reading asset must never be
    #: eligible for a Literature slot, and vice versa, no matter how well the
    #: type and marks line up. Defaults to the textbook pool so every question
    #: written before this field existed keeps its old meaning.
    generator: str = "question_pool"
    #: The shape within that generator ("discursive_passage", "grammar_task",
    #: "formal_letter"). Advisory: used for reuse keying and diagnostics, not
    #: for eligibility.
    asset_type: str = ""

    #: Non-spec fields the pipeline needs. Excluded from the wire payload sent
    #: to Model 2 so its prompt stays small.
    source_type: str = "pool"
    content_hash: str = ""
    pool_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def uses_uploaded_content(self) -> bool:
        """True when this question was written from an uploaded chapter."""
        return self.generator == DEFAULT_GENERATOR

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_wire(self) -> Dict[str, Any]:
        """The shape Model 2 sees: metadata only, stem truncated.

        Model 2 judges quality and concept overlap; it does not need full
        explanations or option text to do that. Sending the whole pool
        verbatim would be ~40k tokens for an 80-question pool — this keeps a
        110-candidate review call around 6k.
        """
        stem = re.sub(r"\s+", " ", self.question).strip()
        return {
            "id": self.id,
            "type": self.type,
            "marks": self.marks,
            "topic": self.topic,
            "blooms": self.blooms,
            "difficulty": self.difficulty,
            "has_image": bool(self.image),
            "stem": stem[:160] + ("…" if len(stem) > 160 else ""),
        }

    def to_model_kwargs(
        self,
        *,
        user,
        project,
        paper=None,
        grade_class: Optional[str] = None,
        valid_type_codes=None,
    ) -> Dict[str, Any]:
        """Kwargs for constructing a `projects.Question` row.

        `grade_class` must be supplied by the caller — the pool contract has no
        class field, but `load_bank` filters on it, so omitting it makes a
        saved question invisible to "Create Paper from Saved Questions".

        `Question.type` is a FK to `QuestionType` keyed by a canonical code that
        differs from the pool's vocabulary (pool "MCQ" → DB "MCQ_SINGLE"). We
        emit `type_id` (the resolved code string) rather than `type` so
        `bulk_create` never has to fetch the related row. Callers persisting a
        whole pool should pass `valid_type_codes` once to avoid re-querying it
        per question.
        """
        from apps.projects.question_types import resolve_type_code

        type_code = resolve_type_code(self.type, valid=valid_type_codes)
        source_pdf = (self.metadata or {}).get("sourcePdf") or (
            self.metadata or {}
        ).get("sourceDocument")
        if isinstance(source_pdf, list):
            source_pdf = ", ".join(str(x) for x in source_pdf if str(x).strip())
        source_pdf = str(source_pdf or "").strip()[:255] or None

        return {
            "type_id": type_code,
            "content": self.question,
            "answer": self.answer or None,
            "options": self.options or [],
            "marks": self.marks,
            "grade_class": grade_class,
            "bloom_taxonomy": self.blooms or None,
            "explanation": self.explanation or None,
            "image_url": self.image or None,
            "subject": self.subject or None,
            "inferred_chapter": self.chapter or None,
            "inferred_topic": self.topic or None,
            "source_pdf": source_pdf,
            "difficulty": self.difficulty or None,
            "content_hash": self.content_hash or None,
            "pool_id": self.pool_id or None,
            "source_type": self.source_type or None,
            # Provenance rides in metadata rather than its own column:
            # `generator`/`assetType` are read back by `from_model` only, which
            # does not justify a migration on the live table, and keeping it
            # here means an older row simply reads back as `question_pool` —
            # the pre-refactor meaning.
            "metadata": {
                **(self.metadata or {}),
                "generator": self.generator or DEFAULT_GENERATOR,
                **({"assetType": self.asset_type} if self.asset_type else {}),
            },
            "user": user,
            "project": project,
            "paper": paper,
        }

    @classmethod
    def from_model(cls, row) -> "PoolQuestion":
        """Rebuild a PoolQuestion from a persisted row.

        This is the path "Create Paper from Saved Questions" takes — the bank
        is the source of truth, so Model 2 must be able to run against rows it
        did not just generate.
        """
        from apps.projects.question_types import to_pool_type

        row_metadata = getattr(row, "metadata", {}) or {}

        # `row.type` is now a FK; read the id (the canonical code, e.g.
        # "MCQ_SINGLE") and translate it back to the pool vocabulary ("MCQ").
        return cls(
            id=row.id,
            subject=row.subject or "",
            chapter=row.inferred_chapter or "",
            topic=row.inferred_topic or "",
            type=normalize_type(to_pool_type(getattr(row, "type_id", None)))
            or "SHORT_ANSWER",
            blooms=normalize_blooms(row.bloom_taxonomy) or "UNDERSTAND",
            difficulty=normalize_difficulty(row.difficulty) or "medium",
            marks=int(row.marks or 1),
            question=row.content or "",
            options=list(row.options or []),
            answer=row.answer or "",
            explanation=getattr(row, "explanation", "") or "",
            image=getattr(row, "image_url", None),
            # Rows banked before provenance existed have no `generator` and
            # correctly read back as textbook-pool questions.
            generator=str(row_metadata.get("generator") or DEFAULT_GENERATOR),
            asset_type=str(row_metadata.get("assetType") or ""),
            source_type=getattr(row, "source_type", "pool") or "pool",
            content_hash=getattr(row, "content_hash", "") or "",
            pool_id=getattr(row, "pool_id", "") or "",
            metadata=row_metadata,
        )


# ── Normalisation ───────────────────────────────────────────────────────


def normalize_type(raw: Any) -> str:
    value = str(raw or "").strip().upper().replace(" ", "_").replace("-", "_")
    if not value:
        return ""
    if value in QUESTION_TYPES:
        return value
    return _TYPE_ALIASES.get(value, "")


def normalize_blooms(raw: Any) -> str:
    value = str(raw or "").strip().upper()
    if value in BLOOMS_LEVELS:
        return value
    return _BLOOMS_ALIASES.get(value, "")


def normalize_difficulty(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in DIFFICULTIES:
        return value
    return _DIFFICULTY_ALIASES.get(value, "")


def compute_content_hash(subject: str, chapter: str, question: str) -> str:
    """Stable dedup key for (subject, chapter, question text).

    Normalises whitespace, case, and punctuation first so that a regenerated
    chapter producing "What is Ohm's law?" and "What is Ohm's Law ?" collapses
    to one row. Deliberately NOT scoped to difficulty or marks: the same stem
    asked at 1 mark and 3 marks is the same question, and keeping both would
    let a paper print near-identical items in two sections.
    """
    normalised = re.sub(r"[^a-z0-9]+", " ", str(question or "").lower()).strip()
    payload = f"{str(subject or '').lower().strip()}|{str(chapter or '').lower().strip()}|{normalised}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_pool_question(
    raw: Dict[str, Any],
    *,
    subject: str,
    chapter: str,
    pool_id: str = "",
    default_difficulty: str = "medium",
    source_type: str = "pool",
    generator: str = DEFAULT_GENERATOR,
    asset_type: str = "",
) -> PoolQuestion:
    """Coerce one raw LLM object into the pool contract.

    Raises PoolValidationError for anything unsalvageable. The caller drops
    that question and keeps the rest of the batch — one malformed object in an
    80-question response must not fail the whole generation.
    """
    if not isinstance(raw, dict):
        raise PoolValidationError(f"Expected an object, got {type(raw).__name__}")

    # The spec field is `question`; accept `content`/`stem` too since the model
    # drifts toward them when the surrounding prompt mentions "content".
    text = str(
        raw.get("question") or raw.get("content") or raw.get("stem") or ""
    ).strip()
    if not text:
        raise PoolValidationError("Question text is empty")

    qtype = normalize_type(raw.get("type"))
    if not qtype:
        raise PoolValidationError(f"Unrecognised question type: {raw.get('type')!r}")

    options_raw = raw.get("options")
    options: List[str] = []
    if isinstance(options_raw, list):
        options = [str(o).strip() for o in options_raw if str(o or "").strip()]
    elif isinstance(options_raw, dict):
        # Some responses come back as {"A": "...", "B": "..."} despite the schema.
        options = [str(v).strip() for _, v in sorted(options_raw.items()) if str(v or "").strip()]

    if qtype == "ASSERTION_REASON":
        # Always the canonical four directions — never the model's paraphrase.
        options = list(ASSERTION_REASON_OPTIONS)
    elif qtype in OPTION_BEARING_TYPES:
        if len(options) < 2:
            raise PoolValidationError(
                f"{qtype} needs at least 2 options, got {len(options)}"
            )
        if qtype == "MCQ" and len(options) != 4:
            # CBSE MCQs are 4-option. 3 or 5 means the model lost the plot on
            # this item; cheaper to drop it than to pad or trim a distractor.
            raise PoolValidationError(
                f"MCQ must have exactly 4 options, got {len(options)}"
            )
    else:
        # A descriptive question with options is a mislabelled MCQ. Drop the
        # options rather than the question — the stem is usually fine.
        options = []

    try:
        marks = int(raw.get("marks") or 1)
    except (TypeError, ValueError):
        marks = 1
    if marks < 1 or marks > 10:
        marks = max(1, min(10, marks))

    # Deliberately NOT read from the model's response. Image generation was
    # removed from the pipeline, so there is no such thing as a legitimate
    # image URL coming back from an LLM — a model that emits one has invented
    # it, and an invented URL renders as a broken image on a printed paper.
    #
    # Rule 7 of Model 1's system prompt already forbids figure-dependent
    # questions; this makes it structural rather than a matter of the model
    # complying. Banked questions keep their images: they are rebuilt by
    # `PoolQuestion.from_model`, which does not come through here.
    image = None

    return PoolQuestion(
        id=str(raw.get("id") or "").strip() or generate_id(),
        subject=subject,
        chapter=chapter,
        topic=str(raw.get("topic") or "").strip() or chapter,
        type=qtype,
        blooms=normalize_blooms(raw.get("blooms") or raw.get("bloom")) or "UNDERSTAND",
        difficulty=normalize_difficulty(raw.get("difficulty")) or default_difficulty,
        marks=marks,
        question=text,
        options=options,
        answer=str(raw.get("answer") or "").strip(),
        explanation=str(raw.get("explanation") or "").strip(),
        image=image,
        generator=generator or DEFAULT_GENERATOR,
        asset_type=asset_type,
        source_type=source_type,
        content_hash=compute_content_hash(subject, chapter, text),
        pool_id=pool_id,
        metadata={},
    )


def slot_generator(slot) -> str:
    """Which generator the blueprint says owns this slot.

    Mirrors `services.assets.registry.generator_for_slot` without importing it,
    so the pool stays free of any dependency on the asset package. Slots with
    no declared generator — every non-English blueprint, General Instructions
    mode, anything reconstructed from the bank — mean the textbook pool.
    """
    return str(getattr(slot, "generator", "") or "").strip() or DEFAULT_GENERATOR


def slot_accepts(pool_question: PoolQuestion, slot) -> bool:
    """Can this pool question fill this blueprint slot?

    Provenance first, then type and marks.

    Provenance is the gate the architecture turns on: a slot the blueprint
    routed to the Reading generator may only be filled by a Reading asset, and
    a Literature slot may only be filled from the textbook pool. Without it, a
    10-mark textbook question is a perfectly legal fill for a 10-mark Reading
    slot — which is precisely how an English paper ended up asking students to
    "explain Hari Singh" under a Reading Skills heading.

    Marks must then be exact: a 3-mark slot filled with a 5-mark question
    breaks the paper's total, the one thing a board paper cannot get wrong.
    """
    if pool_question.generator != slot_generator(slot):
        return False

    if int(pool_question.marks) != int(getattr(slot, "marks", 0) or 0):
        return False

    slot_type = normalize_type(getattr(slot, "question_type", ""))
    if slot_type and pool_question.type == slot_type:
        return True

    legacy = str(getattr(slot, "legacy_type", "") or "").strip().upper()
    accepted = LEGACY_TYPE_ACCEPTS.get(legacy)
    if accepted:
        return pool_question.type in accepted

    return False


def pool_summary(questions: List[PoolQuestion]) -> Dict[str, Any]:
    """Coverage counts, used for diagnostics and the SSE `pool` event."""
    by_type: Dict[str, int] = {}
    by_marks: Dict[int, int] = {}
    by_difficulty: Dict[str, int] = {}
    by_blooms: Dict[str, int] = {}
    by_generator: Dict[str, int] = {}

    for question in questions:
        by_type[question.type] = by_type.get(question.type, 0) + 1
        by_marks[question.marks] = by_marks.get(question.marks, 0) + 1
        by_difficulty[question.difficulty] = by_difficulty.get(question.difficulty, 0) + 1
        by_blooms[question.blooms] = by_blooms.get(question.blooms, 0) + 1
        by_generator[question.generator] = by_generator.get(question.generator, 0) + 1

    return {
        "total": len(questions),
        "byType": by_type,
        "byMarks": {str(k): v for k, v in sorted(by_marks.items())},
        "byDifficulty": by_difficulty,
        "byBlooms": by_blooms,
        "byGenerator": by_generator,
        "withImage": sum(1 for q in questions if q.image),
    }
