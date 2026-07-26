"""Independent asset generators — the non-textbook half of a language paper.

See README.md for the architecture. The short version: a blueprint slot names
the generator that owns it, and only slots naming `question_pool` are allowed
to see uploaded textbook content.
"""

from services.assets.base import (
    AssetBatchResult,
    AssetGenerator,
    AssetRequest,
)
from services.assets.registry import (
    DEFAULT_GENERATOR,
    generator_for_slot,
    get_generator,
    is_asset_generator,
    partition_plan,
    registered_generators,
)
from services.assets.runner import generate_assets_for_plan

__all__ = [
    "AssetBatchResult",
    "AssetGenerator",
    "AssetRequest",
    "DEFAULT_GENERATOR",
    "generate_assets_for_plan",
    "generator_for_slot",
    "get_generator",
    "is_asset_generator",
    "partition_plan",
    "registered_generators",
]
