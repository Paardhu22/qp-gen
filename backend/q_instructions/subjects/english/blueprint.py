"""
AOS English Language & Literature — Exam Blueprint Registry
=============================================================
CBSE Class 10 English Language & Literature (Code 184) — 80 marks, 11 questions, 3 hours.
"""

from typing import Dict, Tuple

from q_instructions.core.enums import (
    AcademicClass, ExamType, QuestionTypeCode, BloomsLevel, StreamType
)
from q_instructions.core.datatypes import SectionBlueprint, ExamBlueprint


class EnglishBlueprintRegistry:
    """CBSE Class 10 English Language & Literature SQP 2025-26 blueprint."""

    def __init__(self) -> None:
        self._blueprints: Dict[Tuple[ExamType, AcademicClass], ExamBlueprint] = {}
        self._initialize()

    def _initialize(self) -> None:
        # Section A Reading (20m): Q1 CASE_STUDY 10m + Q2 CASE_STUDY 10m
        # Section B Grammar & Writing (20m): Q3 SHORT_ANSWER 10m + Q4 LONG_ANSWER 5m + Q5 SHORT_ANSWER 5m
        # Section C Literature (40m): Q6 SHORT_ANSWER 5m + Q7 SHORT_ANSWER 5m +
        #                              Q8 SHORT_ANSWER 12m + Q9 SHORT_ANSWER 6m +
        #                              Q10 LONG_ANSWER 6m + Q11 LONG_ANSWER 6m
        # Total: 11 questions, 80 marks
        sections = [
            SectionBlueprint("A", QuestionTypeCode.CASE_STUDY, 2, 10, 0),   # 20m
            SectionBlueprint("B_GA", QuestionTypeCode.SHORT_ANSWER, 1, 10, 0),  # Grammar 10m
            SectionBlueprint("B_W1", QuestionTypeCode.LONG_ANSWER, 1, 5, 1),    # Letter 5m (choice)
            SectionBlueprint("B_W2", QuestionTypeCode.SHORT_ANSWER, 1, 5, 1),   # Analytical para 5m
            SectionBlueprint("C_EX", QuestionTypeCode.SHORT_ANSWER, 2, 5, 2),   # Extracts 5+5m
            SectionBlueprint("C_SA", QuestionTypeCode.SHORT_ANSWER, 2, 9, 0),   # SA 12+6m (approx)
            SectionBlueprint("C_LA", QuestionTypeCode.LONG_ANSWER, 2, 6, 2),    # LA 6+6m
        ]

        self._blueprints[(ExamType.FINAL, AcademicClass.CLASS_10)] = ExamBlueprint(
            exam_type=ExamType.FINAL,
            academic_class=AcademicClass.CLASS_10,
            duration_minutes=180,
            total_marks=80,
            sections=sections,
            bloom_distribution_target={
                BloomsLevel.REMEMBER: 0.10,
                BloomsLevel.UNDERSTAND: 0.25,
                BloomsLevel.APPLY: 0.30,
                BloomsLevel.ANALYZE: 0.20,
                BloomsLevel.EVALUATE: 0.10,
                BloomsLevel.CREATE: 0.05,
            },
            stream_distribution_target={
                StreamType.INTEGRATED: 1.0,
            },
            difficulty_target={
                "easy": 0.25,
                "medium": 0.50,
                "hard": 0.25,
            },
        )

    def get_blueprint(self, exam_type: ExamType, academic_class: AcademicClass) -> ExamBlueprint:
        key = (exam_type, academic_class)
        if key not in self._blueprints:
            raise KeyError(f"No English blueprint for {exam_type.name} / {academic_class.value}.")
        return self._blueprints[key]
