"""
Question Generation Domain - Accessibility Engine
"""

from typing import List, Tuple

from .datatypes import QuestionInstance
from .enums import QuestionTypeCode


class AccessibilityLearningEngine:
    _VI_DRAWING_REPLACEMENTS = {
        "heart": (
            "Instead of sketching double heart pathways, write a step-by-step "
            "schematic passage showing blood flow paths. Contrast pulmonary "
            "and systemic oxygen exchanges."
        ),
        "mirror": (
            "Instead of drawing mirror ray paths, mathematically calculate "
            "position, size and magnification variables. Describe the image "
            "nature in three sentences."
        ),
        "circuit": (
            "Instead of drawing the circuit, list all components in sequence "
            "and calculate total resistance and current mathematically."
        ),
        "lens": (
            "Instead of drawing ray paths through the lens, describe the "
            "refraction process step-by-step and calculate image position."
        ),
    }

    def translate_for_vi(self, question: QuestionInstance) -> QuestionInstance:
        if question.question_type != QuestionTypeCode.DIAGRAM:
            return question

        lower = question.content_text.lower()
        for keyword, replacement_text in self._VI_DRAWING_REPLACEMENTS.items():
            if keyword in lower:
                vi_text = (
                    "Descriptive Alternate (For Visually Impaired Candidates):\n"
                    f"{replacement_text}"
                )
                return QuestionInstance(
                    question_id=question.question_id,
                    academic_class=question.academic_class,
                    stream=question.stream,
                    question_type=question.question_type,
                    blooms_level=question.blooms_level,
                    assigned_marks=question.assigned_marks,
                    content_text=vi_text,
                    expected_word_count=question.expected_word_count,
                    metadata={**question.metadata, "vi_accessible": True},
                )

        vi_text = (
            "Descriptive Alternate (For Visually Impaired Candidates):\n"
            "Describe conceptually the components and structural features "
            f"involved in the following: {question.content_text}"
        )
        return QuestionInstance(
            question_id=question.question_id,
            academic_class=question.academic_class,
            stream=question.stream,
            question_type=question.question_type,
            blooms_level=question.blooms_level,
            assigned_marks=question.assigned_marks,
            content_text=vi_text,
            expected_word_count=question.expected_word_count,
            metadata={**question.metadata, "vi_accessible": True},
        )

    def generate_dual_booklet(
        self, questions: List[QuestionInstance]
    ) -> Tuple[List[QuestionInstance], List[QuestionInstance]]:
        standard = list(questions)
        vi_accessible = [self.translate_for_vi(q) for q in questions]
        return standard, vi_accessible
