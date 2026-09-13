"""The catalogue data, one module per family, in A→J order."""

from __future__ import annotations

from typing import List

from services.question_types.catalog import (
    choice,
    descriptive,
    language,
    maths,
    practical,
    primary,
    source,
    structural,
    supply,
    visual,
    writing,
)
from services.question_types.spec import TypeSpec

ALL_ENTRIES: List[TypeSpec] = [
    *choice.ENTRIES,
    *supply.ENTRIES,
    *descriptive.ENTRIES,
    *source.ENTRIES,
    *visual.ENTRIES,
    *language.ENTRIES,
    *writing.ENTRIES,
    *maths.ENTRIES,
    *practical.ENTRIES,
    *primary.ENTRIES,
    *structural.ENTRIES,
]
