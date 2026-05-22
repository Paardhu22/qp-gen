"""
Science instruction set bundle.
"""

from typing import List

from ...enums import AcademicClass, BloomsLevel, QuestionTypeCode, StreamType
from ...interfaces import ISubjectPlugin
from ...datatypes import BloomsTaxonomyProfile, QuestionTypeProfile, StreamProfile

from .blooms import BloomsTaxonomyEngine
from .streams import StreamFoundationEngine


class SciencePlugin(ISubjectPlugin):
    def __init__(self) -> None:
        self._streams = StreamFoundationEngine()
        self._blooms = BloomsTaxonomyEngine()
        self._qtype_profiles = {
            QuestionTypeCode.MCQ: QuestionTypeProfile(
                QuestionTypeCode.MCQ,
                (1, 1),
                False,
                [BloomsLevel.REMEMBER, BloomsLevel.UNDERSTAND],
                [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY, StreamType.INTEGRATED],
                1.0,
                "Standard 1-mark Multiple Choice Question.",
            ),
            QuestionTypeCode.ASSERTION_REASON: QuestionTypeProfile(
                QuestionTypeCode.ASSERTION_REASON,
                (1, 1),
                False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.ANALYZE],
                [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY],
                1.5,
                "CBSE Assertion-Reason paired logic check.",
            ),
            QuestionTypeCode.SHORT_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.SHORT_ANSWER,
                (2, 3),
                False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.APPLY],
                [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY, StreamType.INTEGRATED],
                2.5,
                "Short answers requiring descriptive explanations.",
            ),
            QuestionTypeCode.LONG_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.LONG_ANSWER,
                (5, 5),
                True,
                [BloomsLevel.EVALUATE, BloomsLevel.CREATE],
                [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY],
                5.0,
                "Multi-part comprehensive question.",
            ),
            QuestionTypeCode.NUMERICAL: QuestionTypeProfile(
                QuestionTypeCode.NUMERICAL,
                (2, 5),
                False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE],
                [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY],
                4.0,
                "Quantitative application/calculations.",
            ),
            QuestionTypeCode.DIAGRAM: QuestionTypeProfile(
                QuestionTypeCode.DIAGRAM,
                (3, 5),
                True,
                [BloomsLevel.UNDERSTAND, BloomsLevel.APPLY],
                [],
                [StreamType.PHYSICS, StreamType.BIOLOGY],
                3.5,
                "Scientific ray optics/anatomy mapping tasks.",
            ),
        }

    def get_subject_name(self) -> str:
        return "Science"

    def get_supported_classes(self) -> List[AcademicClass]:
        return [
            AcademicClass.CLASS_6,
            AcademicClass.CLASS_7,
            AcademicClass.CLASS_8,
            AcademicClass.CLASS_9,
            AcademicClass.CLASS_10,
        ]

    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        return self._streams.get_profile(stream)

    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        if qtype not in self._qtype_profiles:
            raise KeyError(f"Question type archetype {qtype.name} not cataloged for Science.")
        return self._qtype_profiles[qtype]

    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        return self._blooms.get_profile(level)


class ScienceInstructionSet:
    def __init__(self) -> None:
        self._plugin = SciencePlugin()

    def subject_name(self) -> str:
        return "Science"

    def plugin(self) -> ISubjectPlugin:
        return self._plugin

    def bundle(self):
        from ..base import SubjectBundle

        return SubjectBundle(name=self.subject_name(), plugin=self._plugin)
