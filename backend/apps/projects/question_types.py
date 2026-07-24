"""Resolve legacy / pool question-type codes to canonical `QuestionType` codes.

`Question.type` used to be a free-text column ("MCQ", "SHORT_ANSWER", …). It is
now a ForeignKey to `QuestionType`, whose primary key is a *new* granular code
vocabulary ("MCQ_SINGLE", "SA", "LA", …) seeded in migration 0012.

Two write paths still emit the old vocabulary and would otherwise blow up when
Django tries to coerce a bare string into a `QuestionType` instance:

  * pool auto-save (`services.pool.schema.PoolQuestion.to_model_kwargs`)
  * manual "Save Questions" (`apps.projects.serializers.QuestionSerializer`)

Both funnel through `resolve_type_code` so the mapping lives in exactly one
place. Anything already canonical is returned unchanged, so this stays correct
if a caller starts emitting the new codes directly.
"""

from __future__ import annotations

from typing import Iterable, Optional, Set

#: Old pool/legacy code → canonical `QuestionType.code`. Extends the data
#: migration in 0012 to cover the full pool vocabulary (see
#: `services.pool.schema.QUESTION_TYPES`) plus a few aliases the generator emits.
LEGACY_TYPE_CODE_MAP = {
    # Objective
    "MCQ": "MCQ_SINGLE",
    "MULTIPLE_CHOICE": "MCQ_SINGLE",
    "ASSERTION_REASON": "ASSERTION_REASON",
    "TRUE_FALSE": "TRUE_FALSE",
    "FILL_IN_THE_BLANK": "FILL_BLANK",
    "FILL_IN_THE_BLANKS": "FILL_BLANK",
    "MATCH_THE_FOLLOWING": "MATCH_FOLLOWING",
    "ONE_WORD": "ONE_WORD",
    # Descriptive
    "VERY_SHORT_ANSWER": "VSA",
    "SHORT_ANSWER": "SA",
    "LONG_ANSWER": "LA",
    "HOTS": "SA",
    "COMPETENCY": "SA",
    "NUMERICAL": "NUMERICAL",
    # Source based
    "CASE_STUDY": "CASE_STUDY",
    "SOURCE_BASED": "SOURCE_BASED",
    "READING_COMP": "PASSAGE_UNSEEN",
    "EXTRACT_PROSE": "EXTRACT_SEEN",
    "EXTRACT_POETRY": "POETRY_APPRECIATION",
    # Visual / practical
    "DIAGRAM": "DIAGRAM_DRAW",
    "EXPERIMENTAL": "EXPERIMENT_BASED",
    # Language
    "GRAMMAR": "GRAMMAR_ITEM",
    "LETTER": "LETTER_WRITING",
    "COMPOSITION": "ESSAY_WRITING",
    "ANALYTICAL_PARAGRAPH": "ANALYTICAL_PARAGRAPH",
}

#: Canonical `QuestionType.code` → pool vocabulary, for reading bank rows back
#: into a `PoolQuestion` ("Create Paper from Saved Questions"). The forward map
#: is many-to-one (HOTS, COMPETENCY, SHORT_ANSWER all → SA), so this picks the
#: single most representative pool type per canonical code. Codes with no pool
#: equivalent are absent; `to_pool_type` falls back to normalisation there.
CANONICAL_TO_POOL_TYPE = {
    "MCQ_SINGLE": "MCQ",
    "MCQ_MULTI": "MCQ",
    "ASSERTION_REASON": "ASSERTION_REASON",
    "TRUE_FALSE": "TRUE_FALSE",
    "FILL_BLANK": "FILL_IN_THE_BLANK",
    "MATCH_FOLLOWING": "MATCH_THE_FOLLOWING",
    "ONE_WORD": "ONE_WORD",
    "VSA": "VERY_SHORT_ANSWER",
    "SA": "SHORT_ANSWER",
    "LA": "LONG_ANSWER",
    "VLA": "LONG_ANSWER",
    "NUMERICAL": "NUMERICAL",
    "CASE_STUDY": "CASE_STUDY",
    "SOURCE_BASED": "CASE_STUDY",
    "PASSAGE_UNSEEN": "READING_COMP",
    "EXTRACT_SEEN": "EXTRACT_PROSE",
    "POETRY_APPRECIATION": "EXTRACT_POETRY",
    "DIAGRAM_DRAW": "DIAGRAM",
    "DIAGRAM_LABEL": "DIAGRAM",
    "EXPERIMENT_BASED": "EXPERIMENTAL",
    "GRAMMAR_ITEM": "GRAMMAR",
    "LETTER_WRITING": "LETTER",
    "EMAIL_WRITING": "LETTER",
    "ESSAY_WRITING": "COMPOSITION",
    "ANALYTICAL_PARAGRAPH": "ANALYTICAL_PARAGRAPH",
}

#: Ultimate fallback when a code can't be mapped. "SA" (Short Answer) is the
#: most neutral descriptive type and is always seeded. Chosen over dropping the
#: question — a mis-typed question is still a usable question in the bank.
_DEFAULT_CODE = "SA"


def _normalize(raw) -> str:
    return str(raw or "").strip().upper().replace(" ", "_").replace("-", "_")


def valid_type_codes() -> Set[str]:
    """All canonical `QuestionType.code` values currently in the DB.

    Queried fresh (single indexed scan of a ~70-row table) so it stays correct
    across test-DB resets and future seed changes. Callers persisting many rows
    should fetch this once and pass it in via `valid`.
    """
    from apps.projects.models import QuestionType

    return set(QuestionType.objects.values_list("code", flat=True))


def to_pool_type(code) -> str:
    """Reverse of `resolve_type_code` for reading bank rows into a PoolQuestion.

    Returns a pool-vocabulary type string, or "" when the code has no pool
    equivalent (the caller then applies its own default, typically
    SHORT_ANSWER).
    """
    value = _normalize(code)
    if not value:
        return ""
    return CANONICAL_TO_POOL_TYPE.get(value, value)


def resolve_type_code(
    raw,
    *,
    valid: Optional[Iterable[str]] = None,
    default: str = _DEFAULT_CODE,
) -> Optional[str]:
    """Map any legacy/alias/canonical type string to a valid `QuestionType.code`.

    Returns `None` only when there are no question types seeded at all (so the
    caller can leave the nullable FK empty rather than fail). Otherwise always
    returns a code that exists in the DB.
    """
    valid_set = set(valid) if valid is not None else valid_type_codes()
    if not valid_set:
        return None

    value = _normalize(raw)

    # Already canonical.
    if value in valid_set:
        return value

    # Known legacy/pool code.
    mapped = LEGACY_TYPE_CODE_MAP.get(value)
    if mapped in valid_set:
        return mapped

    # Explicit alias rows, if any were seeded.
    from apps.projects.models import QuestionTypeAlias

    alias_code = (
        QuestionTypeAlias.objects.filter(alias__iexact=value)
        .values_list("type_id", flat=True)
        .first()
    )
    if alias_code in valid_set:
        return alias_code

    return default if default in valid_set else next(iter(valid_set))
