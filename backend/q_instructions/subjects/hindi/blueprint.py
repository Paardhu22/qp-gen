"""
AOS Hindi Course B — Exam Blueprint Registry
==============================================
CBSE Class 10 Hindi Course B (Code 085) — 80 marks, 16 questions, 3 hours.
All labels stored in ASCII for safety; actual content is Devanagari Unicode in generation.
"""

from typing import Dict, Tuple

from q_instructions.core.enums import (
    AcademicClass, ExamType, QuestionTypeCode, BloomsLevel, StreamType
)
from q_instructions.core.datatypes import SectionBlueprint, ExamBlueprint


class HindiBlueprintRegistry:
    """CBSE Class 10 Hindi Course B SQP 2025-26 blueprint."""

    def __init__(self) -> None:
        self._blueprints: Dict[Tuple[ExamType, AcademicClass], ExamBlueprint] = {}
        self._initialize()

    def _initialize(self) -> None:
        # Khand Ka - Apathit Bodh (14m): Q1 7m + Q2 7m
        # Khand Kha - Vyakaran (16m): Q3-Q6 4m each
        # Khand Ga - Pathyapustak (28m): Q7 5m + Q8 6m + Q9 5m + Q10 6m + Q11 6m
        # Khand Gha - Rachnatmak (22m): Q12 5m + Q13 5m + Q14 4m + Q15 3m + Q16 5m
        # Total: 16 questions, 80 marks
        sections = [
            SectionBlueprint("KA", QuestionTypeCode.CASE_STUDY, 2, 7, 0),      # Apathit 14m
            SectionBlueprint("KHA", QuestionTypeCode.SHORT_ANSWER, 4, 4, 0),   # Grammar 16m
            SectionBlueprint("GA", QuestionTypeCode.SHORT_ANSWER, 5, 5, 0),    # Pathyapustak ~28m
            SectionBlueprint("GHA", QuestionTypeCode.LONG_ANSWER, 5, 4, 3),    # Rachnatmak 22m
        ]

        self._blueprints[(ExamType.FINAL, AcademicClass.CLASS_10)] = ExamBlueprint(
            exam_type=ExamType.FINAL,
            academic_class=AcademicClass.CLASS_10,
            duration_minutes=180,
            total_marks=80,
            sections=sections,
            bloom_distribution_target={
                BloomsLevel.REMEMBER: 0.20,
                BloomsLevel.UNDERSTAND: 0.30,
                BloomsLevel.APPLY: 0.25,
                BloomsLevel.ANALYZE: 0.15,
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
            raise KeyError(f"No Hindi blueprint for {exam_type.name} / {academic_class.value}.")
        return self._blueprints[key]
