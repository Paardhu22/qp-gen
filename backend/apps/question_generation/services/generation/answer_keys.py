from typing import List

from ...domain.datatypes import AnswerKeyRubric, QuestionInstance, RubricCriteria
from ...domain.enums import QuestionTypeCode
from ...domain.instructions.science.curriculum import CurriculumWeightageRegistry


class AnswerKeyCompiler:
    def __init__(self) -> None:
        self._weights = CurriculumWeightageRegistry()

    def compile(self, questions: List[QuestionInstance], concept_ids: List[str]) -> List[AnswerKeyRubric]:
        keys: List[AnswerKeyRubric] = []
        for idx, q in enumerate(questions):
            cid = concept_ids[idx] if idx < len(concept_ids) else ""
            profile = self._weights.get_weight_profile(cid)
            comp = profile.target_nep_competency_code

            if q.question_type == QuestionTypeCode.NUMERICAL:
                keys.append(
                    AnswerKeyRubric(
                        question_id=q.question_id,
                        expected_answer="Step-by-step: Given -> Formula -> Substitution -> Answer with units.",
                        rubrics=[
                            RubricCriteria("R1", "Given values with signs", 0.5, comp),
                            RubricCriteria("R2", "Formula statement", 0.5, comp),
                            RubricCriteria("R3", "Algebraic steps", 1.0, comp),
                            RubricCriteria("R4", "Final answer with units", 1.0, comp),
                        ],
                        evaluator_tip="Award partial credit for correct formula even with algebraic slips.",
                    )
                )
            else:
                keys.append(
                    AnswerKeyRubric(
                        question_id=q.question_id,
                        expected_answer="Explanatory points with scientific reasoning.",
                        rubrics=[
                            RubricCriteria("R1", "Core scientific points", 1.0, comp),
                            RubricCriteria("R2", "Supporting explanations", 1.0, comp),
                            RubricCriteria("R3", "Equations/diagrams if applicable", 1.0, comp),
                        ],
                        evaluator_tip="Look for keywords matching Bloom's action verbs.",
                    )
                )
        return keys
