"""
AOS Telugu Telangana — Stream Foundation Engine
=================================================
Telugu has no sub-stream split; uses INTEGRATED with Telugu-language-literacy profile.
All content MUST be in Telugu Unicode script (U+0C00–U+0C7F).
"""

from q_instructions.core.enums import StreamType, CognitiveStyle
from q_instructions.core.datatypes import StreamProfile, TheoryPracticalRatio


class TeluguStreamEngine:
    """Returns the single INTEGRATED stream profile for Telugu Telangana."""

    def __init__(self) -> None:
        self._profile = StreamProfile(
            stream_type=StreamType.INTEGRATED,
            cognitive_style=CognitiveStyle.PHENOMENOLOGICAL,
            preferred_question_types=["MCQ", "SHORT_ANSWER", "LONG_ANSWER", "CASE_STUDY"],
            diagram_frequency_coefficient=0.00,
            numerical_weightage_coefficient=0.00,
            theory_practical_ratio=TheoryPracticalRatio(50.0, 50.0),
            core_focus_description=(
                "CBSE Class 10 Telugu Telangana (Code 089) covers reading comprehension about "
                "Telugu/Telangana scholars, creative writing (lekha-rachana, prakriya), "
                "grammar (sandhi, chhandassu, samasam, alankaaralu, paryaya padaalu, "
                "jaatiyaalu, samethalu, pathyamsha prakriya), and literature "
                "(gadyam, padyam, upavachakam Ramayanam). "
                "EVERY word MUST be in Telugu Unicode script — no Roman transliteration."
            ),
        )

    def get_profile(self, stream_type: StreamType) -> StreamProfile:
        return self._profile
