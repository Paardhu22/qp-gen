"""Resolve any question-type string to a `QuestionType` code seeded in the DB.

`Question.type` is a ForeignKey to `QuestionType`, keyed by the catalogue code
("MCQ_SINGLE", "SA", "MCQ_ODD_ONE_OUT", …). Writers still arrive speaking older
vocabularies:

  * pool auto-save (`services.pool.schema.PoolQuestion.to_model_kwargs`) sends
    runtime shapes such as "MCQ" and "SHORT_ANSWER";
  * manual "Save Questions" (`apps.projects.serializers.QuestionSerializer`)
    sends whatever the editor attribute holds — "SHORT", "MCQ", a catalogue code.

What every string MEANS is answered by `services.question_types`, the single
source of truth. This module adds the one thing the catalogue cannot know:
which codes the database has actually been seeded with.
"""

from __future__ import annotations

from typing import Iterable, Optional, Set

from services.question_types import default_type_for_shape, resolve, shape_of

#: Ultimate fallback when a code can't be mapped. "SA" (Short Answer) is the
#: most neutral descriptive type and is always seeded. Chosen over dropping the
#: question — a mis-typed question is still a usable question in the bank.
_DEFAULT_CODE = "SA"


def _normalize(raw) -> str:
    return str(raw or "").strip().upper().replace(" ", "_").replace("-", "_")


def valid_type_codes() -> Set[str]:
    """All canonical `QuestionType.code` values currently in the DB.

    Queried fresh (single indexed scan of a small table) so it stays correct
    across test-DB resets and future seed changes. Callers persisting many rows
    should fetch this once and pass it in via `valid`.
    """
    from apps.projects.models import QuestionType

    return set(QuestionType.objects.values_list("code", flat=True))


def to_pool_type(code) -> str:
    """The runtime shape for a stored code, for reading bank rows back into a
    PoolQuestion ("Create Paper from Saved Questions").

    Returns the input unchanged when it names nothing the catalogue knows, so
    the caller's own normalisation and default still apply.
    """
    value = _normalize(code)
    if not value:
        return ""
    return shape_of(value) or value


def resolve_type_code(
    raw,
    *,
    valid: Optional[Iterable[str]] = None,
    default: str = _DEFAULT_CODE,
) -> Optional[str]:
    """Map any legacy/alias/catalogue type string to a seeded `QuestionType.code`.

    Returns `None` only when there are no question types seeded at all (so the
    caller can leave the nullable FK empty rather than fail). Otherwise always
    returns a code that exists in the DB.
    """
    valid_set = set(valid) if valid is not None else valid_type_codes()
    if not valid_set:
        return None

    value = _normalize(raw)

    # Already a seeded code.
    if value in valid_set:
        return value

    resolution = resolve(value)
    if resolution is not None:
        if resolution.code in valid_set:
            return resolution.code
        # A catalogue type this database has not been seeded with yet keeps the
        # nearest meaning it can: the default type of its shape, which always is.
        fallback = default_type_for_shape(resolution.spec.shape)
        if fallback in valid_set:
            return fallback

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
