"""
AOS English Language & Literature — Subject Plugin
===================================================
Concrete implementation of ISubjectPlugin for CBSE Class 10 English (Code 184).
Eligible: CBSE Class 10 only.
"""

from typing import List

from q_instructions.core.enums import AcademicClass, StreamType, QuestionTypeCode, BloomsLevel
from q_instructions.core.interfaces import ISubjectPlugin
from q_instructions.core.datatypes import StreamProfile, QuestionTypeProfile, BloomsTaxonomyProfile

from q_instructions.subjects.english.streams import EnglishStreamEngine
from q_instructions.subjects.english.blooms_engine import EnglishBloomsTaxonomyEngine


class EnglishPlugin(ISubjectPlugin):
    """
    English Language & Literature subject plugin (CBSE Code 184, Class X only).
    Integrates a literacy-dominant stream profile and English-calibrated Bloom's engine.
    """

    def __init__(self) -> None:
        self._streams = EnglishStreamEngine()
        self._blooms = EnglishBloomsTaxonomyEngine()
        self._qtype_profiles = {
            QuestionTypeCode.MCQ: QuestionTypeProfile(
                QuestionTypeCode.MCQ, (1, 1), False,
                [BloomsLevel.REMEMBER, BloomsLevel.UNDERSTAND],
                [], [StreamType.INTEGRATED], 1.0,
                "1-mark MCQ in grammar or vocabulary tasks.",
            ),
            QuestionTypeCode.CASE_STUDY: QuestionTypeProfile(
                QuestionTypeCode.CASE_STUDY, (10, 10), False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 3.5,
                "Reading comprehension passage with 8-9 sub-questions.",
            ),
            QuestionTypeCode.SHORT_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.SHORT_ANSWER, (3, 12), False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE, BloomsLevel.EVALUATE],
                [], [StreamType.INTEGRATED], 3.0,
                "Grammar tasks, extract sub-questions, or literature short answers.",
            ),
            QuestionTypeCode.LONG_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.LONG_ANSWER, (5, 6), False,
                [BloomsLevel.EVALUATE, BloomsLevel.CREATE],
                [], [StreamType.INTEGRATED], 5.0,
                "Formal letter, analytical paragraph, or long literature response.",
            ),
        }

    def get_subject_name(self) -> str:
        return "English"

    def get_supported_classes(self) -> List[AcademicClass]:
        return [AcademicClass.CLASS_10]

    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        return self._streams.get_profile(stream)

    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        if qtype not in self._qtype_profiles:
            raise KeyError(f"Question type {qtype.name} not cataloged for English.")
        return self._qtype_profiles[qtype]

    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        return self._blooms.get_profile(level)
