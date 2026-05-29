"""
AOS Hindi Course B — Subject Plugin
======================================
Concrete implementation of ISubjectPlugin for CBSE Class 10 Hindi Course B (Code 085).
Eligible: CBSE Class 10 only.
All generated content must be in Devanagari Unicode.
"""

from typing import List

from q_instructions.core.enums import AcademicClass, StreamType, QuestionTypeCode, BloomsLevel
from q_instructions.core.interfaces import ISubjectPlugin
from q_instructions.core.datatypes import StreamProfile, QuestionTypeProfile, BloomsTaxonomyProfile

from q_instructions.subjects.hindi.streams import HindiStreamEngine
from q_instructions.subjects.hindi.blooms_engine import HindiBloomsTaxonomyEngine


class HindiPlugin(ISubjectPlugin):
    """
    Hindi Course B subject plugin (CBSE Code 085, Class X only).
    All content must be generated in Devanagari Unicode (U+0900–U+097F).
    """

    def __init__(self) -> None:
        self._streams = HindiStreamEngine()
        self._blooms = HindiBloomsTaxonomyEngine()
        self._qtype_profiles = {
            QuestionTypeCode.MCQ: QuestionTypeProfile(
                QuestionTypeCode.MCQ, (1, 5), False,
                [BloomsLevel.REMEMBER, BloomsLevel.UNDERSTAND],
                [], [StreamType.INTEGRATED], 1.0,
                "MCQ cluster for pathit gadyansh or kavyansh (5×1m).",
            ),
            QuestionTypeCode.CASE_STUDY: QuestionTypeProfile(
                QuestionTypeCode.CASE_STUDY, (7, 7), False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 3.5,
                "Apathit bodh passage + 7 sub-parts (MCQ + short answers) in Devanagari.",
            ),
            QuestionTypeCode.SHORT_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.SHORT_ANSWER, (2, 6), False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE],
                [], [StreamType.INTEGRATED], 2.5,
                "Grammar tasks (padband/samas/muhavare) or literature short answers in Devanagari.",
            ),
            QuestionTypeCode.LONG_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.LONG_ANSWER, (3, 5), False,
                [BloomsLevel.EVALUATE, BloomsLevel.CREATE],
                [], [StreamType.INTEGRATED], 5.0,
                "Rachnatmak lekhan: anuched, soochna, vigyapan, laghu-katha/email in Devanagari.",
            ),
        }

    def get_subject_name(self) -> str:
        return "Hindi"

    def get_supported_classes(self) -> List[AcademicClass]:
        return [AcademicClass.CLASS_10]

    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        return self._streams.get_profile(stream)

    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        if qtype not in self._qtype_profiles:
            raise KeyError(f"Question type {qtype.name} not cataloged for Hindi.")
        return self._qtype_profiles[qtype]

    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        return self._blooms.get_profile(level)
