"""
AOS Social Science — Exam Blueprint Registry
========================================
Defines standard CBSE exam structures for Social Science (sections, marks, times).
"""

from typing import Dict, Tuple

from q_instructions.core.enums import (
    AcademicClass, ExamType, QuestionTypeCode, BloomsLevel, StreamType
)
from q_instructions.core.datatypes import SectionBlueprint, ExamBlueprint


class SocialScienceBlueprintRegistry:
    """Factory containing master structures conforming to CBSE Social Science layouts."""

    def __init__(self) -> None:
        self._blueprints: Dict[Tuple[ExamType, AcademicClass], ExamBlueprint] = {}
        self._initialize()

    def _initialize(self) -> None:
        # Class 10 CBSE Social Science Board Exam (80 marks, 3 hours)
        # Four Tracks (20 marks each)
        sections_c10 = [
            SectionBlueprint("A", QuestionTypeCode.MCQ, 20, 1, 0), # 20 MCQs (5 per track)
            SectionBlueprint("B", QuestionTypeCode.SHORT_ANSWER, 4, 2, 0), # VSAs
            SectionBlueprint("C", QuestionTypeCode.SHORT_ANSWER, 5, 3, 0), # SAs
            SectionBlueprint("D", QuestionTypeCode.LONG_ANSWER, 4, 5, 4), # 4 LAs (1 per track, all with OR)
            SectionBlueprint("E", QuestionTypeCode.CASE_STUDY, 3, 4, 0), # 3 CBQs
            SectionBlueprint("F", QuestionTypeCode.DIAGRAM, 1, 5, 0), # Map Section
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
                BloomsLevel.EVALUATE: 0.05,
                BloomsLevel.CREATE: 0.05,
            },
            stream_distribution_target={
                StreamType.HISTORY: 0.25,
                StreamType.GEOGRAPHY: 0.25,
                StreamType.CIVICS: 0.25,
                StreamType.ECONOMICS: 0.25,
            },
            difficulty_target={
                "easy": 0.30,
                "medium": 0.50,
                "hard": 0.20,
            }
        )

    def get_blueprint(self, exam_type: ExamType, academic_class: AcademicClass) -> ExamBlueprint:
        key = (exam_type, academic_class)
        if key not in self._blueprints:
            raise KeyError(f"No Social Science blueprint for {exam_type.name} / {academic_class.value}.")
        return self._blueprints[key]
