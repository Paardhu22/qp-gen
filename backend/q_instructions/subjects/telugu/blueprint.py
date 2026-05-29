"""
AOS Telugu Telangana — Exam Blueprint Registry
===============================================
CBSE Class 10 Telugu Telangana (Code 089) — 80 marks, 18 questions, 3 hours.
All question content MUST be generated in Telugu Unicode script (U+0C00–U+0C7F).
"""

from typing import Dict, Tuple

from q_instructions.core.enums import (
    AcademicClass, ExamType, QuestionTypeCode, BloomsLevel, StreamType
)
from q_instructions.core.datatypes import SectionBlueprint, ExamBlueprint


class TeluguBlueprintRegistry:
    """CBSE Class 10 Telugu Telangana SQP 2025-26 blueprint."""

    def __init__(self) -> None:
        self._blueprints: Dict[Tuple[ExamType, AcademicClass], ExamBlueprint] = {}
        self._initialize()

    def _initialize(self) -> None:
        # Vibhagam A (10m): Q1 READING_COMP 10m
        # Vibhagam B (11m): Q2 LETTER 6m + Q3 LA 5m
        # Vibhagam C (29m): Q4-Q12 MCQ clusters (4+4+4+4+2+2+2+2+5)
        # Vibhagam D (30m): Q13-Q18 (4+4+4+4+6+8)
        # Total: 18 questions, 80 marks
        sections = [
            SectionBlueprint("VA", QuestionTypeCode.CASE_STUDY, 1, 10, 0),       # Vibhagam A 10m
            SectionBlueprint("VB", QuestionTypeCode.LONG_ANSWER, 2, 5, 1),        # Vibhagam B ~11m
            SectionBlueprint("VC_MCQ", QuestionTypeCode.MCQ, 9, 3, 0),            # Vibhagam C MCQs ~29m
            SectionBlueprint("VD", QuestionTypeCode.SHORT_ANSWER, 6, 5, 4),       # Vibhagam D ~30m
        ]

        self._blueprints[(ExamType.FINAL, AcademicClass.CLASS_10)] = ExamBlueprint(
            exam_type=ExamType.FINAL,
            academic_class=AcademicClass.CLASS_10,
            duration_minutes=180,
            total_marks=80,
            sections=sections,
            bloom_distribution_target={
                BloomsLevel.REMEMBER: 0.25,
                BloomsLevel.UNDERSTAND: 0.30,
                BloomsLevel.APPLY: 0.25,
                BloomsLevel.ANALYZE: 0.12,
                BloomsLevel.EVALUATE: 0.05,
                BloomsLevel.CREATE: 0.03,
            },
            stream_distribution_target={
                StreamType.INTEGRATED: 1.0,
            },
            difficulty_target={
                "easy": 0.30,
                "medium": 0.50,
                "hard": 0.20,
            },
        )

    def get_blueprint(self, exam_type: ExamType, academic_class: AcademicClass) -> ExamBlueprint:
        key = (exam_type, academic_class)
        if key not in self._blueprints:
            raise KeyError(f"No Telugu blueprint for {exam_type.name} / {academic_class.value}.")
        return self._blueprints[key]
