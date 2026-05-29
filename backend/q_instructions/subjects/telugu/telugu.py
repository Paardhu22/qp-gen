"""
AOS Telugu Telangana — Subject Plugin
=======================================
Concrete implementation of ISubjectPlugin for CBSE Class 10 Telugu Telangana (Code 089).
Eligible: CBSE Class 10 only.
EVERY question, option, instruction, and section header MUST be in Telugu Unicode script.
"""

from typing import List

from q_instructions.core.enums import AcademicClass, StreamType, QuestionTypeCode, BloomsLevel
from q_instructions.core.interfaces import ISubjectPlugin
from q_instructions.core.datatypes import StreamProfile, QuestionTypeProfile, BloomsTaxonomyProfile

from q_instructions.subjects.telugu.streams import TeluguStreamEngine
from q_instructions.subjects.telugu.blooms_engine import TeluguBloomsTaxonomyEngine


class TeluguPlugin(ISubjectPlugin):
    """
    Telugu Telangana subject plugin (CBSE Code 089, Class X only).
    Post-generation guard: verify question_text contains Telugu Unicode;
    if Roman script appears the LLM ignored the language rule — regenerate.
    """

    def __init__(self) -> None:
        self._streams = TeluguStreamEngine()
        self._blooms = TeluguBloomsTaxonomyEngine()
        self._qtype_profiles = {
            QuestionTypeCode.MCQ: QuestionTypeProfile(
                QuestionTypeCode.MCQ, (2, 5), False,
                [BloomsLevel.REMEMBER, BloomsLevel.UNDERSTAND],
                [], [StreamType.INTEGRATED], 1.0,
                "MCQ cluster in Telugu Unicode — sandhi/chhandassu/samasam/alankaaralu.",
            ),
            QuestionTypeCode.CASE_STUDY: QuestionTypeProfile(
                QuestionTypeCode.CASE_STUDY, (10, 10), False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 3.5,
                "Reading comprehension passage (Q1) with 5 MCQs ×2m in Telugu Unicode.",
            ),
            QuestionTypeCode.SHORT_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.SHORT_ANSWER, (4, 4), False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 3.0,
                "Sangraha javabulu — 4 questions do any 2 (~50-60 words) in Telugu Unicode.",
            ),
            QuestionTypeCode.LONG_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.LONG_ANSWER, (4, 8), False,
                [BloomsLevel.ANALYZE, BloomsLevel.EVALUATE],
                [], [StreamType.INTEGRATED], 5.0,
                "Vipulamga / padya anvaya / upavachakam in Telugu Unicode.",
            ),
        }

    def get_subject_name(self) -> str:
        return "Telugu"

    def get_supported_classes(self) -> List[AcademicClass]:
        return [AcademicClass.CLASS_10]

    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        return self._streams.get_profile(stream)

    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        if qtype not in self._qtype_profiles:
            raise KeyError(f"Question type {qtype.name} not cataloged for Telugu.")
        return self._qtype_profiles[qtype]

    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        return self._blooms.get_profile(level)
