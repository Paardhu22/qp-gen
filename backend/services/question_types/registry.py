"""One answer to "what type is this?" for any string the product has ever used.

Inputs arrive in four vocabularies, and all of them must keep working forever:

* catalogue codes — `MCQ_ODD_ONE_OUT`, `SA` (the identity going forward);
* runtime shapes — `MCQ`, `SHORT_ANSWER`, `HOTS` (saved templates, editor
  documents, slotMeta, every blueprint the engine emits);
* old DB codes — `STATEMENT_EVAL`, `ODD_ONE_OUT` (bank rows before 0016);
* what people and models actually write — "odd one out", `MULTIPLE_CHOICE`.

## Two lookups, two precedence orders

`shape_of` answers with the RUNTIME SHAPE and checks shapes and the model
synonyms first, exactly as `schema.normalize_type` always has. That order is
load-bearing: a model that writes "ESSAY" has always meant a long answer, and
must keep meaning one, even though "essay" is also a teacher's word for the
writing type.

`resolve` answers with the CATALOGUE TYPE and checks catalogue codes first,
then shapes (so `HOTS` still carries its `hots` attribute), then aliases, then
the model synonyms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

from services.question_types.catalog import ALL_ENTRIES
from services.question_types.families import FAMILIES_BY_CODE
from services.question_types.shapes import (
    COMPOSITE_SHAPES,
    OPTION_BEARING_SHAPES,
    SHAPE_CODES,
    SHAPE_SYNONYMS,
    SHAPES,
    SHAPES_BY_CODE,
    bucket_for_shape,
)
from services.question_types.spec import TypeSpec, validate_spec


@dataclass(frozen=True)
class Resolution:
    """A catalogue type plus the slot attributes the input implied."""

    spec: TypeSpec
    attributes: FrozenSet[str] = frozenset()

    @property
    def code(self) -> str:
        return self.spec.code


_SEPARATORS = re.compile(r"[\s\-/]+")


def _shape_key(raw) -> str:
    """The normalisation `schema.normalize_type` has always applied."""
    return str(raw or "").strip().upper().replace(" ", "_").replace("-", "_")


def _alias_key(raw) -> str:
    """Looser folding for catalogue lookups: slashes and runs of separators too."""
    text = _SEPARATORS.sub("_", str(raw or "").strip().upper())
    return re.sub(r"_+", "_", text).strip("_")


# ── Build and check the catalogue ───────────────────────────────────────


def _build_catalog(entries: Iterable[TypeSpec]) -> Dict[str, TypeSpec]:
    catalog: Dict[str, TypeSpec] = {}
    for spec in entries:
        if spec.code in catalog:
            raise ValueError(f"Duplicate catalogue code {spec.code!r}")
        validate_spec(spec, FAMILIES_BY_CODE)
        if spec.shape not in SHAPE_CODES:
            raise ValueError(f"{spec.code}: unknown shape {spec.shape!r}")
        if SHAPES_BY_CODE[spec.shape].retired:
            raise ValueError(f"{spec.code}: shape {spec.shape!r} is retired")
        catalog[spec.code] = spec
    for shape in SHAPES:
        if shape.default_type not in catalog:
            raise ValueError(
                f"Shape {shape.code} defaults to {shape.default_type!r}, which is not catalogued"
            )
    return catalog


CATALOG: Dict[str, TypeSpec] = _build_catalog(ALL_ENTRIES)


def _build_index() -> Dict[str, Tuple[str, FrozenSet[str]]]:
    index: Dict[str, Tuple[str, FrozenSet[str]]] = {}

    def claim(key: str, code: str, attributes: FrozenSet[str], source: str, *, strict: bool) -> None:
        if not key:
            return
        existing = index.get(key)
        if existing is None:
            index[key] = (code, attributes)
        elif strict and existing[0] != code:
            raise ValueError(
                f"Alias {key!r} ({source}) points at {code}, but already means {existing[0]}"
            )

    # 1. Catalogue codes.
    for code in CATALOG:
        claim(_alias_key(code), code, frozenset(), "code", strict=True)
    # 2. Runtime shapes, carrying what a retired shape implied.
    for shape in SHAPES:
        claim(_alias_key(shape.code), shape.default_type, frozenset(shape.implies), "shape", strict=False)
    # 3. Aliases declared on entries. Strict: two types claiming one phrase is
    #    a data bug, and the first to import would silently win.
    for spec in CATALOG.values():
        for alias in spec.aliases:
            key = _alias_key(alias)
            if key in index and index[key][0] == spec.code:
                continue
            if key in {_alias_key(s.code) for s in SHAPES}:
                # A shape name listed as an alias must agree with the shape.
                if index[key][0] != spec.code:
                    raise ValueError(f"Alias {alias!r} on {spec.code} contradicts shape {key}")
                continue
            claim(key, spec.code, frozenset(), f"alias on {spec.code}", strict=True)
    # 4. Model synonyms, through the shape they name. Never overrides.
    for synonym, shape_code in SHAPE_SYNONYMS.items():
        shape = SHAPES_BY_CODE[shape_code]
        claim(_alias_key(synonym), shape.default_type, frozenset(shape.implies), "synonym", strict=False)
    return index


_INDEX: Dict[str, Tuple[str, FrozenSet[str]]] = _build_index()


# ── Lookups ─────────────────────────────────────────────────────────────


def get(code) -> Optional[TypeSpec]:
    """The entry for an exact catalogue code, or None."""
    return CATALOG.get(str(code or "").strip().upper())


def resolve(raw) -> Optional[Resolution]:
    """The catalogue type any input means, or None when nothing matches."""
    hit = _INDEX.get(_alias_key(raw))
    if hit is None:
        return None
    code, attributes = hit
    return Resolution(CATALOG[code], attributes)


def normalize_type_code(raw) -> str:
    """The catalogue code for any input, or "" when it is not recognised."""
    resolution = resolve(raw)
    return resolution.code if resolution else ""


def shape_of(raw) -> str:
    """The runtime shape for any input, or "" when it is not recognised.

    Shapes and model synonyms win over catalogue aliases — see the module
    docstring for why.
    """
    key = _shape_key(raw)
    if not key:
        return ""
    if key in SHAPE_CODES:
        return key
    if key in SHAPE_SYNONYMS:
        return SHAPE_SYNONYMS[key]
    resolution = resolve(raw)
    return resolution.spec.shape if resolution else ""


def default_type_for_shape(shape_code) -> str:
    shape = SHAPES_BY_CODE.get(_shape_key(shape_code))
    return shape.default_type if shape else ""


def legacy_bucket(raw) -> str:
    """The coarse blueprint bucket (`legacy_type`) for any input."""
    return bucket_for_shape(shape_of(raw))


def is_option_bearing(raw) -> bool:
    return shape_of(raw) in OPTION_BEARING_SHAPES


def is_composite(raw) -> bool:
    """True when the editor lays the question out as a composite run."""
    resolution = resolve(raw)
    if resolution and resolution.spec.is_container:
        return True
    return shape_of(raw) in COMPOSITE_SHAPES


def all_types() -> List[TypeSpec]:
    return list(CATALOG.values())


def available_types() -> List[TypeSpec]:
    return [spec for spec in CATALOG.values() if spec.is_available]


def aliases_for(code: str) -> List[str]:
    """Every lookup key that resolves to `code` — for search in the picker."""
    return sorted(key for key, (target, _) in _INDEX.items() if target == code)


@dataclass(frozen=True)
class SlotType:
    """What a blueprint slot is, once its type fields are reconciled."""

    code: str
    shape: str
    hots: bool = False
    competency: bool = False


def effective_shape(raw) -> str:
    """`shape_of`, with a retired shape read as the shape it became.

    "HOTS" is no longer a shape anything is written as: it is a short answer
    carrying the `hots` attribute.
    """
    shape_code = shape_of(raw)
    shape = SHAPES_BY_CODE.get(shape_code)
    if shape is not None and shape.retired:
        return CATALOG[shape.default_type].shape
    return shape_code


def resolve_slot_type(
    type_code="",
    question_type="",
    *,
    hots: bool = False,
    competency: bool = False,
    default: str = "SA",
) -> SlotType:
    """Reconcile a slot's catalogue code with its runtime shape.

    A slot can carry both: `typeCode` from the catalogue picker and
    `questionType` from anything that only knows shapes — an older client, a
    saved template, the swap menu. The code is the more precise, so it wins,
    unless it disagrees with the shape: that means the type was changed later
    by something that could not update the code, and the newer choice must not
    be quietly reverted by a stale one.
    """
    hint = effective_shape(question_type) if question_type else ""

    chosen = resolve(type_code) if type_code else None
    if chosen is not None and hint and chosen.spec.shape != hint:
        chosen = None
    if chosen is None and question_type:
        chosen = resolve(question_type)
        if chosen is not None and hint and chosen.spec.shape != hint:
            # "ESSAY" is a long answer as a shape and the writing type as a
            # phrase. For a slot, the shape reading is the one it always had.
            chosen = resolve(default_type_for_shape(hint))
    if chosen is None:
        chosen = resolve(default)

    attributes = set(chosen.attributes)
    if hots:
        attributes.add("hots")
    if competency:
        attributes.add("competency")
    return SlotType(
        code=chosen.code,
        shape=chosen.spec.shape,
        hots="hots" in attributes,
        competency="competency" in attributes,
    )


def type_for_route(generator: str, asset_type: str) -> str:
    """The catalogue type a generator's format produces, or "" when none does."""
    for spec in CATALOG.values():
        route = spec.route
        if route and route.generator == generator and asset_type in (route.asset_type, *route.also):
            return spec.code
    return ""
