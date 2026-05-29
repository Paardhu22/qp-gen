"""
AOS Mathematics Standard — Subject Plugin
==========================================
Concrete implementation of ISubjectPlugin for CBSE Class 10 Mathematics Standard (Code 041).
Eligible: CBSE Class 10 only.
"""

from typing import List

from q_instructions.core.enums import AcademicClass, StreamType, QuestionTypeCode, BloomsLevel
from q_instructions.core.interfaces import ISubjectPlugin
from q_instructions.core.datatypes import StreamProfile, QuestionTypeProfile, BloomsTaxonomyProfile

from q_instructions.subjects.mathematics.streams import MathematicsStreamEngine
from q_instructions.subjects.mathematics.blooms_engine import MathematicsBloomsTaxonomyEngine


class MathematicsPlugin(ISubjectPlugin):
    """
    Mathematics Standard subject plugin (CBSE Code 041, Class X only).
    Integrates a numerical-dominant stream profile and math-calibrated Bloom's engine.
    """

    def __init__(self) -> None:
        self._streams = MathematicsStreamEngine()
        self._blooms = MathematicsBloomsTaxonomyEngine()
        self._qtype_profiles = {
            QuestionTypeCode.MCQ: QuestionTypeProfile(
                QuestionTypeCode.MCQ, (1, 1), False,
                [BloomsLevel.REMEMBER, BloomsLevel.UNDERSTAND, BloomsLevel.APPLY],
                [], [StreamType.INTEGRATED], 1.0,
                "1-mark MCQ; distractors represent common computational errors.",
            ),
            QuestionTypeCode.ASSERTION_REASON: QuestionTypeProfile(
                QuestionTypeCode.ASSERTION_REASON, (1, 1), False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 1.5,
                "CBSE standard Assertion-Reason with 4-option direction block.",
            ),
            QuestionTypeCode.SHORT_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.SHORT_ANSWER, (2, 3), False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 3.0,
                "2m VSA or 3m SA — algebraic/proof-based short questions.",
            ),
            QuestionTypeCode.LONG_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.LONG_ANSWER, (5, 5), False,
                [BloomsLevel.ANALYZE, BloomsLevel.EVALUATE],
                [], [StreamType.INTEGRATED], 5.0,
                "5-mark multi-step theorem/proof/word problem.",
            ),
            QuestionTypeCode.CASE_STUDY: QuestionTypeProfile(
                QuestionTypeCode.CASE_STUDY, (4, 4), False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 4.0,
                "4-mark case study; 3 sub-parts (i)1m+(ii)1m+(iii)2m; sub-part (iii) has OR choice.",
            ),
            QuestionTypeCode.NUMERICAL: QuestionTypeProfile(
                QuestionTypeCode.NUMERICAL, (2, 5), False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 4.0,
                "Numerical calculation question.",
            ),
        }

    def get_subject_name(self) -> str:
        return "Mathematics"

    def get_supported_classes(self) -> List[AcademicClass]:
        return [AcademicClass.CLASS_10]

    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        return self._streams.get_profile(stream)

    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        if qtype not in self._qtype_profiles:
            raise KeyError(f"Question type {qtype.name} not cataloged for Mathematics.")
        return self._qtype_profiles[qtype]

    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        return self._blooms.get_profile(level)
