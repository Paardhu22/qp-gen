"""The question type catalogue — the single source of truth for question types.

    services.question_types.CATALOG["MCQ_ODD_ONE_OUT"]      # the entry
    services.question_types.resolve("ODD_ONE_OUT")          # old code → entry
    services.question_types.shape_of("MCQ_ODD_ONE_OUT")     # → "MCQ"

A catalogue code is a type's identity; its `shape` is the runtime question
shape the pipeline has always understood. See `registry.py` for how every
historical vocabulary resolves, and `docs/question-type-catalogue-plan.md` for
the design.

Django-free: safe to import from the pool, the blueprint engine, migrations'
export command and tests alike.
"""

from services.question_types.families import FAMILIES, FAMILIES_BY_CODE
from services.question_types.registry import (
    CATALOG,
    Resolution,
    SlotType,
    aliases_for,
    all_types,
    available_types,
    default_type_for_shape,
    effective_shape,
    get,
    is_composite,
    is_option_bearing,
    legacy_bucket,
    normalize_type_code,
    resolve,
    resolve_slot_type,
    shape_of,
    type_for_route,
)
from services.question_types.shapes import (
    BUCKET_ACCEPTS,
    COMPOSITE_SHAPES,
    OPTION_BEARING_SHAPES,
    SHAPE_CODES,
    SHAPE_SYNONYMS,
    SHAPES,
    SHAPES_BY_CODE,
    bucket_for_shape,
)
from services.question_types.spec import OptionRule, Route, TypeSpec

__all__ = [
    "BUCKET_ACCEPTS",
    "CATALOG",
    "COMPOSITE_SHAPES",
    "FAMILIES",
    "FAMILIES_BY_CODE",
    "OPTION_BEARING_SHAPES",
    "OptionRule",
    "Resolution",
    "Route",
    "SHAPES",
    "SHAPES_BY_CODE",
    "SHAPE_CODES",
    "SHAPE_SYNONYMS",
    "SlotType",
    "TypeSpec",
    "aliases_for",
    "all_types",
    "available_types",
    "bucket_for_shape",
    "default_type_for_shape",
    "effective_shape",
    "get",
    "is_composite",
    "is_option_bearing",
    "legacy_bucket",
    "normalize_type_code",
    "resolve",
    "resolve_slot_type",
    "shape_of",
    "type_for_route",
]
