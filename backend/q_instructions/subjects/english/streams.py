"""
AOS English Language & Literature — Stream Foundation Engine
=============================================================
English has no sub-stream split; uses INTEGRATED with literacy-heavy profile.
"""

from q_instructions.core.enums import StreamType, CognitiveStyle
from q_instructions.core.datatypes import StreamProfile, TheoryPracticalRatio


class EnglishStreamEngine:
    """Returns the single INTEGRATED stream profile for English."""

    def __init__(self) -> None:
        self._profile = StreamProfile(
            stream_type=StreamType.INTEGRATED,
            cognitive_style=CognitiveStyle.PHENOMENOLOGICAL,
            preferred_question_types=["SHORT_ANSWER", "LONG_ANSWER", "CASE_STUDY", "MCQ"],
            diagram_frequency_coefficient=0.05,
            numerical_weightage_coefficient=0.00,
            theory_practical_ratio=TheoryPracticalRatio(60.0, 40.0),
            core_focus_description=(
                "CBSE Class 10 English Language & Literature covers Reading Comprehension, "
                "Grammar (tenses, reported speech, error correction), Formal Writing "
                "(letters, paragraphs), and Literature (First Flight Prose/Poetry, Footprints). "
                "Demands inference, critical analysis, and creative writing skills."
            ),
        )

    def get_profile(self, stream_type: StreamType) -> StreamProfile:
        return self._profile
