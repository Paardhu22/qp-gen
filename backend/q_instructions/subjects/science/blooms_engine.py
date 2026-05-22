"""
AOS Science — Bloom's Taxonomy Engine
========================================
Manages cognitive demands, action verb bindings, and difficulty calibrations.
"""

from typing import Dict, Set

from q_instructions.core.enums import BloomsLevel, StreamType
from q_instructions.core.datatypes import BloomsVerb, BloomsTaxonomyProfile


class BloomsTaxonomyEngine:
    """Manages Bloom's taxonomy profiles with verb-to-level bindings."""

    def __init__(self) -> None:
        self._profiles: Dict[BloomsLevel, BloomsTaxonomyProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._profiles[BloomsLevel.REMEMBER] = BloomsTaxonomyProfile(
            level=BloomsLevel.REMEMBER,
            cognitive_weight_index=1.0,
            action_verbs=[
                BloomsVerb("State", {StreamType.PHYSICS, StreamType.CHEMISTRY}, "State Ohm's law."),
                BloomsVerb("Define", {StreamType.BIOLOGY, StreamType.INTEGRATED}, "Define photosynthesis."),
                BloomsVerb("Label", {StreamType.BIOLOGY}, "Label the parts of the human heart."),
            ],
            difficulty_coefficient_range=(0.1, 0.4),
            description="Testing memory retrieval. Simplest cognitive layer."
        )

        self._profiles[BloomsLevel.UNDERSTAND] = BloomsTaxonomyProfile(
            level=BloomsLevel.UNDERSTAND,
            cognitive_weight_index=2.0,
            action_verbs=[
                BloomsVerb("Explain", {StreamType.PHYSICS, StreamType.BIOLOGY}, "Explain transport of water in plants."),
                BloomsVerb("Differentiate", {StreamType.CHEMISTRY, StreamType.BIOLOGY}, "Differentiate between metals and non-metals."),
                BloomsVerb("Illustrate", {StreamType.PHYSICS}, "Illustrate real image formation by a concave mirror."),
            ],
            difficulty_coefficient_range=(0.3, 0.6),
            description="Testing comprehension. Expects re-phrasing without memorization."
        )

        self._profiles[BloomsLevel.APPLY] = BloomsTaxonomyProfile(
            level=BloomsLevel.APPLY,
            cognitive_weight_index=3.5,
            action_verbs=[
                BloomsVerb("Calculate", {StreamType.PHYSICS, StreamType.CHEMISTRY}, "Calculate the refractive index of glass."),
                BloomsVerb("Balance", {StreamType.CHEMISTRY}, "Balance: Fe + H2O -> Fe3O4 + H2."),
                BloomsVerb("Predict", {StreamType.BIOLOGY, StreamType.PHYSICS}, "Predict F2 phenotype in a monohybrid cross."),
            ],
            difficulty_coefficient_range=(0.5, 0.8),
            description="Testing operational capacity. Requires selecting correct formulas."
        )

        self._profiles[BloomsLevel.ANALYZE] = BloomsTaxonomyProfile(
            level=BloomsLevel.ANALYZE,
            cognitive_weight_index=4.8,
            action_verbs=[
                BloomsVerb("Isolate", {StreamType.PHYSICS}, "Isolate variables causing resistance changes."),
                BloomsVerb("Deduce", {StreamType.CHEMISTRY, StreamType.BIOLOGY}, "Deduce nature of compound X from its reaction."),
                BloomsVerb("Compare", {StreamType.INTEGRATED}, "Compare water retention efficiency of different soils."),
            ],
            difficulty_coefficient_range=(0.6, 0.9),
            description="Deconstructing components. Determining how pieces form a system."
        )

        self._profiles[BloomsLevel.EVALUATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.EVALUATE,
            cognitive_weight_index=5.5,
            action_verbs=[
                BloomsVerb("Justify", {StreamType.BIOLOGY, StreamType.PHYSICS}, "Justify why parallel circuits are preferred."),
                BloomsVerb("Critique", {StreamType.CHEMISTRY}, "Critique Mendeleev's vs Modern periodic classification."),
                BloomsVerb("Assess", {StreamType.INTEGRATED}, "Assess environmental impacts of plastic accumulation."),
            ],
            difficulty_coefficient_range=(0.7, 0.95),
            description="Judging validity. Assessing systems using criteria or safety protocols."
        )

        self._profiles[BloomsLevel.CREATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.CREATE,
            cognitive_weight_index=6.0,
            action_verbs=[
                BloomsVerb("Design", {StreamType.PHYSICS, StreamType.CHEMISTRY}, "Design a protocol to isolate pure oxygen."),
                BloomsVerb("Formulate", {StreamType.BIOLOGY}, "Formulate a biological defense using selective breeding."),
                BloomsVerb("Synthesize", {StreamType.CHEMISTRY}, "Synthesize a framework mapping carbon chains to properties."),
            ],
            difficulty_coefficient_range=(0.8, 1.0),
            description="Synthesizing new schema. Proposing research designs."
        )

    def get_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        if level not in self._profiles:
            raise KeyError(f"Bloom's level {level.name} not registered.")
        return self._profiles[level]

    def verify_action_verb(self, level: BloomsLevel, verb: str) -> bool:
        """Checks if a verb is bound to the target Bloom's cognitive layer."""
        profile = self.get_profile(level)
        return any(v.verb.lower() == verb.lower() for v in profile.action_verbs)
