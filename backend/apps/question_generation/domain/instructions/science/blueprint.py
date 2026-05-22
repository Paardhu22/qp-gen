"""
Science exam blueprint registry.
"""

from typing import Dict, Tuple

from ...datatypes import ExamBlueprint, SectionBlueprint
from ...enums import AcademicClass, BloomsLevel, ExamType, QuestionTypeCode, StreamType


class ExamBlueprintRegistry:
    def __init__(self) -> None:
        self._blueprints: Dict[Tuple[ExamType, AcademicClass], ExamBlueprint] = {}
        self._initialize()

    def _initialize(self) -> None:
        sections_c10 = [
            SectionBlueprint("A", QuestionTypeCode.MCQ, 16, 1, 0),
            SectionBlueprint("B", QuestionTypeCode.ASSERTION_REASON, 4, 1, 0),
            SectionBlueprint("C", QuestionTypeCode.SHORT_ANSWER, 6, 2, 2),
            SectionBlueprint("D", QuestionTypeCode.SHORT_ANSWER, 7, 3, 2),
            SectionBlueprint("E", QuestionTypeCode.CASE_STUDY, 3, 4, 1),
            SectionBlueprint("F", QuestionTypeCode.LONG_ANSWER, 2, 5, 2),
        ]

        self._blueprints[(ExamType.FINAL, AcademicClass.CLASS_10)] = ExamBlueprint(
            exam_type=ExamType.FINAL,
            academic_class=AcademicClass.CLASS_10,
            duration_minutes=180,
            total_marks=80,
            sections=sections_c10,
            bloom_distribution_target={
                BloomsLevel.REMEMBER: 0.20,
                BloomsLevel.UNDERSTAND: 0.25,
                BloomsLevel.APPLY: 0.30,
                BloomsLevel.ANALYZE: 0.15,
                BloomsLevel.EVALUATE: 0.07,
                BloomsLevel.CREATE: 0.03,
            },
            stream_distribution_target={
                StreamType.PHYSICS: 0.35,
                StreamType.CHEMISTRY: 0.30,
                StreamType.BIOLOGY: 0.35,
            },
            difficulty_target={"easy": 0.30, "medium": 0.45, "hard": 0.25},
        )

        sections_unit = [
            SectionBlueprint("A", QuestionTypeCode.MCQ, 5, 1, 0),
            SectionBlueprint("B", QuestionTypeCode.SHORT_ANSWER, 5, 2, 1),
            SectionBlueprint("C", QuestionTypeCode.SHORT_ANSWER, 3, 3, 1),
            SectionBlueprint("D", QuestionTypeCode.LONG_ANSWER, 1, 5, 1),
        ]

        self._blueprints[(ExamType.UNIT_TEST, AcademicClass.CLASS_10)] = ExamBlueprint(
            exam_type=ExamType.UNIT_TEST,
            academic_class=AcademicClass.CLASS_10,
            duration_minutes=45,
            total_marks=25,
            sections=sections_unit,
            bloom_distribution_target={
                BloomsLevel.REMEMBER: 0.30,
                BloomsLevel.UNDERSTAND: 0.30,
                BloomsLevel.APPLY: 0.25,
                BloomsLevel.ANALYZE: 0.15,
            },
            stream_distribution_target={},
            difficulty_target={"easy": 0.40, "medium": 0.40, "hard": 0.20},
        )

    def get_blueprint(self, exam_type: ExamType, academic_class: AcademicClass) -> ExamBlueprint:
        key = (exam_type, academic_class)
        if key not in self._blueprints:
            raise KeyError(f"No blueprint for {exam_type.name} / {academic_class.value}.")
        return self._blueprints[key]
