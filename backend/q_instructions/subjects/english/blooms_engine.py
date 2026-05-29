"""
AOS English Language & Literature — Bloom's Taxonomy Engine
=============================================================
Cognitive demands and action verbs for CBSE Class 10 English.
"""

from typing import Dict, Set

from q_instructions.core.enums import BloomsLevel, StreamType
from q_instructions.core.datatypes import BloomsVerb, BloomsTaxonomyProfile

_ALL = {StreamType.INTEGRATED}


class EnglishBloomsTaxonomyEngine:
    """Bloom's taxonomy profiles with English-specific verb bindings."""

    def __init__(self) -> None:
        self._profiles: Dict[BloomsLevel, BloomsTaxonomyProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._profiles[BloomsLevel.REMEMBER] = BloomsTaxonomyProfile(
            level=BloomsLevel.REMEMBER,
            cognitive_weight_index=1.0,
            action_verbs=[
                BloomsVerb("Identify", _ALL, "Identify the poetic device used in the given line."),
                BloomsVerb("List", _ALL, "List the characters mentioned in the extract."),
                BloomsVerb("Recall", _ALL, "Recall the setting of the story."),
            ],
            difficulty_coefficient_range=(0.1, 0.35),
            description="Testing recall of textbook facts and vocabulary.",
        )

        self._profiles[BloomsLevel.UNDERSTAND] = BloomsTaxonomyProfile(
            level=BloomsLevel.UNDERSTAND,
            cognitive_weight_index=2.0,
            action_verbs=[
                BloomsVerb("Explain", _ALL, "Explain the central idea of the poem."),
                BloomsVerb("Interpret", _ALL, "Interpret the tone of the given passage."),
                BloomsVerb("Summarise", _ALL, "Summarise the key message of the chapter."),
            ],
            difficulty_coefficient_range=(0.3, 0.55),
            description="Testing comprehension of meaning, tone, and message.",
        )

        self._profiles[BloomsLevel.APPLY] = BloomsTaxonomyProfile(
            level=BloomsLevel.APPLY,
            cognitive_weight_index=3.5,
            action_verbs=[
                BloomsVerb("Write", _ALL, "Write a formal letter requesting the facility."),
                BloomsVerb("Transform", _ALL, "Transform the given sentence into reported speech."),
                BloomsVerb("Use", _ALL, "Use the given word in a meaningful sentence."),
            ],
            difficulty_coefficient_range=(0.5, 0.72),
            description="Applying grammar rules or writing skills to new situations.",
        )

        self._profiles[BloomsLevel.ANALYZE] = BloomsTaxonomyProfile(
            level=BloomsLevel.ANALYZE,
            cognitive_weight_index=4.8,
            action_verbs=[
                BloomsVerb("Analyse", _ALL, "Analyse how the author builds suspense."),
                BloomsVerb("Compare", _ALL, "Compare the themes of two given poems."),
                BloomsVerb("Examine", _ALL, "Examine the significance of the title."),
            ],
            difficulty_coefficient_range=(0.6, 0.83),
            description="Breaking text into components; examining cause-effect and theme.",
        )

        self._profiles[BloomsLevel.EVALUATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.EVALUATE,
            cognitive_weight_index=5.5,
            action_verbs=[
                BloomsVerb("Justify", _ALL, "Justify whether the character's decision was right."),
                BloomsVerb("Critique", _ALL, "Critique the narrative technique used in the story."),
                BloomsVerb("Assess", _ALL, "Assess the social message of the chapter."),
            ],
            difficulty_coefficient_range=(0.7, 0.92),
            description="Judging literary merit, character decisions, and thematic arguments.",
        )

        self._profiles[BloomsLevel.CREATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.CREATE,
            cognitive_weight_index=6.0,
            action_verbs=[
                BloomsVerb("Compose", _ALL, "Compose an analytical paragraph comparing the two profiles."),
                BloomsVerb("Draft", _ALL, "Draft a letter to the editor on the given issue."),
                BloomsVerb("Design", _ALL, "Design a dialogue extending the scene in the chapter."),
            ],
            difficulty_coefficient_range=(0.8, 1.0),
            description="Producing original writing: letters, analytical paragraphs, creative extensions.",
        )

    def get_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        if level not in self._profiles:
            raise KeyError(f"Bloom's level {level.name} not registered for English.")
        return self._profiles[level]
