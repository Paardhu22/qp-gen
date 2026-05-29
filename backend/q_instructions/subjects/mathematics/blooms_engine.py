"""
AOS Mathematics Standard — Bloom's Taxonomy Engine
=====================================================
Cognitive demands, action verbs, and difficulty calibrations for CBSE Class 10 Math.
"""

from typing import Dict, Set

from q_instructions.core.enums import BloomsLevel, StreamType
from q_instructions.core.datatypes import BloomsVerb, BloomsTaxonomyProfile

_ALL = {StreamType.INTEGRATED}


class MathematicsBloomsTaxonomyEngine:
    """Bloom's taxonomy profiles with math-specific verb bindings."""

    def __init__(self) -> None:
        self._profiles: Dict[BloomsLevel, BloomsTaxonomyProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._profiles[BloomsLevel.REMEMBER] = BloomsTaxonomyProfile(
            level=BloomsLevel.REMEMBER,
            cognitive_weight_index=1.0,
            action_verbs=[
                BloomsVerb("State", _ALL, "State the Fundamental Theorem of Arithmetic."),
                BloomsVerb("Define", _ALL, "Define a quadratic polynomial."),
                BloomsVerb("Recall", _ALL, "Recall the distance formula."),
            ],
            difficulty_coefficient_range=(0.1, 0.35),
            description="Testing recall of formulas, theorems, and definitions.",
        )

        self._profiles[BloomsLevel.UNDERSTAND] = BloomsTaxonomyProfile(
            level=BloomsLevel.UNDERSTAND,
            cognitive_weight_index=2.0,
            action_verbs=[
                BloomsVerb("Explain", _ALL, "Explain why 5^n cannot end in 0."),
                BloomsVerb("Classify", _ALL, "Classify the given equation as quadratic or not."),
                BloomsVerb("Interpret", _ALL, "Interpret the meaning of a zero of a polynomial."),
            ],
            difficulty_coefficient_range=(0.3, 0.55),
            description="Testing comprehension of mathematical concepts and relationships.",
        )

        self._profiles[BloomsLevel.APPLY] = BloomsTaxonomyProfile(
            level=BloomsLevel.APPLY,
            cognitive_weight_index=3.5,
            action_verbs=[
                BloomsVerb("Calculate", _ALL, "Calculate the HCF of 96 and 72 using prime factorisation."),
                BloomsVerb("Solve", _ALL, "Solve the quadratic equation x² - 5x + 6 = 0."),
                BloomsVerb("Find", _ALL, "Find the nth term of the given AP."),
            ],
            difficulty_coefficient_range=(0.5, 0.75),
            description="Testing operational capacity — selecting correct formulas and executing.",
        )

        self._profiles[BloomsLevel.ANALYZE] = BloomsTaxonomyProfile(
            level=BloomsLevel.ANALYZE,
            cognitive_weight_index=4.8,
            action_verbs=[
                BloomsVerb("Prove", _ALL, "Prove that √2 is irrational."),
                BloomsVerb("Deduce", _ALL, "Deduce the condition for two lines to be parallel."),
                BloomsVerb("Compare", _ALL, "Compare the mean, median, and mode of the given data."),
            ],
            difficulty_coefficient_range=(0.6, 0.85),
            description="Breaking a problem into components; applying BPT, similarity, etc.",
        )

        self._profiles[BloomsLevel.EVALUATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.EVALUATE,
            cognitive_weight_index=5.5,
            action_verbs=[
                BloomsVerb("Verify", _ALL, "Verify the relationship between zeroes and coefficients."),
                BloomsVerb("Justify", _ALL, "Justify whether the given triangles are similar."),
                BloomsVerb("Critique", _ALL, "Critique the statement about probability."),
            ],
            difficulty_coefficient_range=(0.7, 0.92),
            description="Judging validity of proofs, solutions, or statistical interpretations.",
        )

        self._profiles[BloomsLevel.CREATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.CREATE,
            cognitive_weight_index=6.0,
            action_verbs=[
                BloomsVerb("Construct", _ALL, "Construct a word problem modelled by a quadratic equation."),
                BloomsVerb("Formulate", _ALL, "Formulate linear equations from the given scenario."),
                BloomsVerb("Design", _ALL, "Design a grouped frequency table from raw data."),
            ],
            difficulty_coefficient_range=(0.8, 1.0),
            description="Synthesising new problem structures or mathematical models.",
        )

    def get_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        if level not in self._profiles:
            raise KeyError(f"Bloom's level {level.name} not registered for Mathematics.")
        return self._profiles[level]
