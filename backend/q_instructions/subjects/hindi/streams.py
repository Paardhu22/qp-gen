"""
AOS Hindi Course B — Stream Foundation Engine
===============================================
Hindi has no sub-stream split; uses INTEGRATED with language-literacy profile.
"""

from q_instructions.core.enums import StreamType, CognitiveStyle
from q_instructions.core.datatypes import StreamProfile, TheoryPracticalRatio


class HindiStreamEngine:
    """Returns the single INTEGRATED stream profile for Hindi Course B."""

    def __init__(self) -> None:
        self._profile = StreamProfile(
            stream_type=StreamType.INTEGRATED,
            cognitive_style=CognitiveStyle.PHENOMENOLOGICAL,
            preferred_question_types=["SHORT_ANSWER", "LONG_ANSWER", "CASE_STUDY", "MCQ"],
            diagram_frequency_coefficient=0.00,
            numerical_weightage_coefficient=0.00,
            theory_practical_ratio=TheoryPracticalRatio(55.0, 45.0),
            core_focus_description=(
                "CBSE Class 10 Hindi Course B (Code 085) covers Apathit Bodh (unseen passages), "
                "Vyavaharik Vyakaran (applied grammar: padband, vakya, samas, muhavare), "
                "Sparsh Gadya/Kavya, Sanchayan prose, and Rachnatmak Lekhan "
                "(anuched, patr, soochna, vigyapan, laghu-katha/email). "
                "All output strictly in Devanagari Unicode."
            ),
        )

    def get_profile(self, stream_type: StreamType) -> StreamProfile:
        return self._profile
