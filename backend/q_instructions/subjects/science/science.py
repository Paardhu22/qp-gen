"""
AOS Science — Science Subject Plugin
=======================================
Concrete implementation of ISubjectPlugin contract.
Registers Science-specific streams, Blooms calibration, and question archetypes.
"""

from typing import List

from q_instructions.core.enums import AcademicClass, StreamType, QuestionTypeCode, BloomsLevel
from q_instructions.core.interfaces import ISubjectPlugin
from q_instructions.core.datatypes import StreamProfile, QuestionTypeProfile, BloomsTaxonomyProfile

from q_instructions.subjects.science.streams import StreamFoundationEngine
from q_instructions.subjects.science.blooms_engine import BloomsTaxonomyEngine


class SciencePlugin(ISubjectPlugin):
    """
    Official Science subject plugin.
    Integrates streams, Blooms calibration, and question archetype engines.
    """

    def __init__(self) -> None:
        self._streams = StreamFoundationEngine()
        self._blooms = BloomsTaxonomyEngine()
        # Archetype rules
        self._qtype_profiles = {
            QuestionTypeCode.MCQ: QuestionTypeProfile(
                QuestionTypeCode.MCQ, (1, 1), False,
                [BloomsLevel.REMEMBER, BloomsLevel.UNDERSTAND], [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY, StreamType.INTEGRATED],
                1.0, "Standard 1-mark Multiple Choice Question."
            ),
            QuestionTypeCode.ASSERTION_REASON: QuestionTypeProfile(
                QuestionTypeCode.ASSERTION_REASON, (1, 1), False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.ANALYZE], [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY],
                1.5, "CBSE Assertion-Reason paired logic check."
            ),
            QuestionTypeCode.SHORT_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.SHORT_ANSWER, (2, 3), False,
                [BloomsLevel.UNDERSTAND, BloomsLevel.APPLY], [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY, StreamType.INTEGRATED],
                2.5, "Short answers requiring descriptive explanations."
            ),
            QuestionTypeCode.LONG_ANSWER: QuestionTypeProfile(
                QuestionTypeCode.LONG_ANSWER, (5, 5), True,
                [BloomsLevel.EVALUATE, BloomsLevel.CREATE], [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY],
                5.0, "Multi-part comprehensive question."
            ),
            QuestionTypeCode.NUMERICAL: QuestionTypeProfile(
                QuestionTypeCode.NUMERICAL, (2, 5), False,
                [BloomsLevel.APPLY, BloomsLevel.ANALYZE], [],
                [StreamType.PHYSICS, StreamType.CHEMISTRY],
                4.0, "Quantitative application/calculations."
            ),
            QuestionTypeCode.DIAGRAM: QuestionTypeProfile(
                QuestionTypeCode.DIAGRAM, (3, 5), True,
                [BloomsLevel.UNDERSTAND, BloomsLevel.APPLY], [],
                [StreamType.PHYSICS, StreamType.BIOLOGY],
                3.5, "Scientific ray optics/anatomy mapping tasks."
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
            AcademicClass.CLASS_10
        ]

    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        return self._streams.get_profile(stream)

    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        if qtype not in self._qtype_profiles:
            raise KeyError(f"Question type archetype {qtype.name} not cataloged for Science.")
        return self._qtype_profiles[qtype]

    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        return self._blooms.get_profile(level)
