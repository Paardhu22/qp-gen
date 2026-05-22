"""
Question Generation Domain - Safety Engine
"""

from typing import List

from .constants import FORBIDDEN_HALLUCINATION_TERMS
from .datatypes import QuestionInstance
from .enums import QuestionTypeCode
from .instructions.science.curriculum import ConceptGraph, CurriculumDuplicatePreventionEngine


class GenerationSafetyEngine:
    def __init__(self, concept_graph: ConceptGraph) -> None:
        self._graph = concept_graph
        self._dup_engine = CurriculumDuplicatePreventionEngine(concept_graph)

    def audit_question(self, q: QuestionInstance) -> List[str]:
        errors: List[str] = []
        lower = q.content_text.lower()

        for term in FORBIDDEN_HALLUCINATION_TERMS:
            if term in lower:
                errors.append(f"Hallucinated term '{term}' in question {q.question_id}.")

        if q.question_type == QuestionTypeCode.MCQ and q.assigned_marks != 1:
            errors.append(f"MCQ {q.question_id}: marks={q.assigned_marks}, expected 1.")
        if q.question_type == QuestionTypeCode.LONG_ANSWER and q.assigned_marks < 5:
            errors.append(f"Long answer {q.question_id}: marks={q.assigned_marks}, expected >=5.")

        if q.question_type == QuestionTypeCode.DIAGRAM:
            if not any(w in lower for w in ["draw", "sketch", "diagram", "label"]):
                errors.append(f"Diagram {q.question_id}: missing drawing directives.")

        return errors

    def audit_paper(self, questions: List[QuestionInstance], concept_ids: List[str]) -> List[str]:
        errors: List[str] = []
        for q in questions:
            errors.extend(self.audit_question(q))

        _, dup_errors = self._dup_engine.audit_duplication_safety(concept_ids)
        errors.extend(dup_errors)
        return errors
