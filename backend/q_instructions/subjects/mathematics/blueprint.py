"""
AOS Mathematics Standard — Exam Blueprint Registry
=====================================================
CBSE Class 10 Mathematics Standard (Code 041) — 80 marks, 38 questions, 3 hours.
"""

from typing import Dict, Tuple

from q_instructions.core.enums import (
    AcademicClass, ExamType, QuestionTypeCode, BloomsLevel, StreamType
)
from q_instructions.core.datatypes import SectionBlueprint, ExamBlueprint


class MathematicsBlueprintRegistry:
    """CBSE Class 10 Mathematics Standard SQP 2025-26 blueprint."""

    def __init__(self) -> None:
        self._blueprints: Dict[Tuple[ExamType, AcademicClass], ExamBlueprint] = {}
        self._initialize()

    def _initialize(self) -> None:
        # Section A: Q1–Q18 MCQ (1m) + Q19–Q20 ASSERTION_REASON (1m) = 20m
        # Section B: Q21–Q25 VSA SHORT_ANSWER (2m each) = 10m
        # Section C: Q26–Q31 SA SHORT_ANSWER (3m each) = 18m
        # Section D: Q32–Q35 LA LONG_ANSWER (5m each) = 20m
        # Section E: Q36–Q38 CASE_STUDY (4m each) = 12m
        # Total: 38 questions, 80 marks
        sections = [
            SectionBlueprint("A", QuestionTypeCode.MCQ, 20, 1, 0),
            SectionBlueprint("B", QuestionTypeCode.SHORT_ANSWER, 5, 2, 2),
            SectionBlueprint("C", QuestionTypeCode.SHORT_ANSWER, 6, 3, 2),
            SectionBlueprint("D", QuestionTypeCode.LONG_ANSWER, 4, 5, 2),
            SectionBlueprint("E", QuestionTypeCode.CASE_STUDY, 3, 4, 3),
        ]

        total = sum(s.get_total_marks() for s in sections)
        assert total == 80, f"Mathematics blueprint marks error: {total} != 80"

        self._blueprints[(ExamType.FINAL, AcademicClass.CLASS_10)] = ExamBlueprint(
            exam_type=ExamType.FINAL,
            academic_class=AcademicClass.CLASS_10,
            duration_minutes=180,
            total_marks=80,
            sections=sections,
            bloom_distribution_target={
                BloomsLevel.REMEMBER: 0.15,
                BloomsLevel.UNDERSTAND: 0.15,
                BloomsLevel.APPLY: 0.35,
                BloomsLevel.ANALYZE: 0.25,
                BloomsLevel.EVALUATE: 0.07,
                BloomsLevel.CREATE: 0.03,
            },
            stream_distribution_target={
                StreamType.INTEGRATED: 1.0,
            },
            difficulty_target={
                "easy": 0.30,
                "medium": 0.45,
                "hard": 0.25,
            },
        )

    def get_blueprint(self, exam_type: ExamType, academic_class: AcademicClass) -> ExamBlueprint:
        key = (exam_type, academic_class)
        if key not in self._blueprints:
            raise KeyError(f"No Mathematics blueprint for {exam_type.name} / {academic_class.value}.")
        return self._blueprints[key]
