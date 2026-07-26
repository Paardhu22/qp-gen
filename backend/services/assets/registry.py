"""Generator Factory + blueprint routing.

`partition_plan` is the routing engine's one public act: it turns a flat list
of blueprint slots into "these slots belong to Reading, these to Grammar,
these to Writing, these to the textbook pool". Everything downstream — which
generator runs, whether chapters are read at all, what Model 1's recipe covers,
which pool questions may fill which slot — follows from that partition.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from services.assets.base import AssetGenerator

#: The reserved routing key for "the existing chapter → Model 1 → pool
#: pipeline". Deliberately NOT an AssetGenerator: that path is owned by the
#: streaming pipeline (chapter detection, per-chapter concurrency, the image
#: stage), and wrapping it in this interface would invert a lot of machinery
#: for no benefit. Any slot that does not name a generator gets this one, which
#: is what makes the refactor a no-op for every non-English subject.
#:
#: Defined in `services.pool.schema` so the pool can gate on provenance without
#: importing the asset package (which is built on top of the pool).
from services.pool.schema import DEFAULT_GENERATOR  # noqa: E402  (re-export)

logger = logging.getLogger("[ASSETS]")

_REGISTRY: Dict[str, AssetGenerator] = {}


def register(generator: AssetGenerator) -> AssetGenerator:
    """Add a generator to the registry. Idempotent for the same name."""
    name = str(getattr(generator, "name", "") or "").strip()
    if not name:
        raise ValueError("An AssetGenerator must declare a non-empty `name`.")
    if name == DEFAULT_GENERATOR:
        raise ValueError(
            f"{DEFAULT_GENERATOR!r} is reserved for the textbook pipeline and "
            "cannot be registered as an asset generator."
        )
    _REGISTRY[name] = generator
    return generator


def get_generator(name: str) -> Optional[AssetGenerator]:
    return _REGISTRY.get(str(name or "").strip())


def is_asset_generator(name: str) -> bool:
    """True when `name` routes to an independent generator (not the textbook)."""
    return str(name or "").strip() in _REGISTRY


def registered_generators() -> List[AssetGenerator]:
    return list(_REGISTRY.values())


def generator_for_slot(slot: Any) -> str:
    """Which generator owns this slot.

    A slot with no `generator` (every non-English blueprint, every General
    Instructions slot, every bank-derived slot) routes to the textbook pool —
    the pre-refactor behaviour.
    """
    name = str(getattr(slot, "generator", "") or "").strip()
    if not name:
        return DEFAULT_GENERATOR
    if name != DEFAULT_GENERATOR and name not in _REGISTRY:
        # A blueprint naming a generator nobody registered would silently lose
        # its section. Fall back to the textbook pool and say so loudly.
        logger.warning(
            "Slot %s names unknown generator %r; falling back to %r.",
            getattr(slot, "index", "?"), name, DEFAULT_GENERATOR,
        )
        return DEFAULT_GENERATOR
    return name


def partition_plan(plan: Sequence[Any]) -> Dict[str, List[Any]]:
    """Group blueprint slots by the generator that owns them.

    Ordering is preserved inside each group, and `DEFAULT_GENERATOR` is always
    present (possibly empty) so callers can read it without a guard.
    """
    groups: Dict[str, List[Any]] = {DEFAULT_GENERATOR: []}
    for slot in plan or []:
        groups.setdefault(generator_for_slot(slot), []).append(slot)
    return groups


def routing_summary(plan: Sequence[Any]) -> List[Dict[str, Any]]:
    """Per-generator marks/counts, for the SSE `plan` event and logging.

    Makes the routing decision visible to the teacher and to a log reader:
    an English paper should show 20 marks of Reading, 20 of Grammar+Writing
    and 40 of textbook Literature.
    """
    groups = partition_plan(plan)
    summary: List[Dict[str, Any]] = []
    for name, slots in groups.items():
        if not slots:
            continue
        generator = get_generator(name)
        summary.append(
            {
                "generator": name,
                "label": (
                    generator.label
                    if generator is not None
                    else "Textbook question pool"
                ),
                "usesUploadedContent": name == DEFAULT_GENERATOR,
                "questions": len(slots),
                "marks": sum(int(getattr(s, "marks", 0) or 0) for s in slots),
                "sections": sorted(
                    {
                        str(getattr(s, "section_title", "") or "")
                        for s in slots
                        if getattr(s, "section_title", "")
                    }
                ),
                "assetTypes": sorted(
                    {
                        str(getattr(s, "asset_type", "") or "")
                        for s in slots
                        if getattr(s, "asset_type", "")
                    }
                ),
            }
        )
    return summary


def requires_uploaded_content(plan: Sequence[Any]) -> bool:
    """True when at least one slot still needs the uploaded textbook.

    The gate that lets an all-asset paper generate with no upload at all, and
    keeps the hard "no readable content" error for papers that genuinely
    cannot be built without one.
    """
    return bool(partition_plan(plan).get(DEFAULT_GENERATOR))


def _autoload() -> None:
    """Import the built-in generators so importing the package registers them."""
    from services.assets import grammar, reading, writing  # noqa: F401


_autoload()
