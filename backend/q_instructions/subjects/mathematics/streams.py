"""
AOS Mathematics Standard — Stream Foundation Engine
=====================================================
Mathematics has no sub-stream split; uses INTEGRATED with numerical-heavy profile.
"""

from typing import Dict

from q_instructions.core.enums import StreamType, CognitiveStyle
from q_instructions.core.datatypes import StreamProfile, TheoryPracticalRatio


class MathematicsStreamEngine:
    """Returns the single INTEGRATED stream profile for Mathematics."""

    def __init__(self) -> None:
        self._profile = StreamProfile(
            stream_type=StreamType.INTEGRATED,
            cognitive_style=CognitiveStyle.MATHEMATICAL_MODELING,
            preferred_question_types=["NUMERICAL", "MCQ", "SHORT_ANSWER", "CASE_STUDY", "LONG_ANSWER"],
            diagram_frequency_coefficient=0.20,
            numerical_weightage_coefficient=0.85,
            theory_practical_ratio=TheoryPracticalRatio(70.0, 30.0),
            core_focus_description=(
                "CBSE Class 10 Mathematics Standard covers Real Numbers, Polynomials, "
                "Linear Equations, Quadratic Equations, APs, Coordinate Geometry, Triangles, "
                "Circles, Trigonometry, Mensuration, Statistics, and Probability. "
                "Demands algebraic manipulation, proof-writing, and multi-step problem solving."
            ),
        )

    def get_profile(self, stream_type: StreamType) -> StreamProfile:
        return self._profile
