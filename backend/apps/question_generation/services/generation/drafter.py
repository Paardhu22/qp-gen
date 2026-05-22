from typing import List

from ...domain.board_systems.cbse.templates import QuestionTemplateLibrary
from ...domain.datatypes import CompiledPaperBlueprint, InstitutionPolicy, QuestionInstance
from ...domain.enums import QuestionTypeCode
from ...domain.generation.parameter_synthesizer import ParameterSynthesizer
from ...domain.generation.template_selector import IntelligentTemplateSelector
from ...domain.instructions.science.curriculum import CurriculumGraphFactory


class TemplateDraftingService:
    def __init__(self) -> None:
        self._templates = QuestionTemplateLibrary()
        self._graph = CurriculumGraphFactory.construct_comprehensive_graph()
        self._selector = IntelligentTemplateSelector(self._templates)
        self._synthesizer = ParameterSynthesizer()

    def draft_questions(
        self, blueprint: CompiledPaperBlueprint, policy: InstitutionPolicy, context_map: dict
    ) -> List[QuestionInstance]:
        questions: List[QuestionInstance] = []

        for cid in blueprint.retrieval_targets:
            node = self._graph.nodes.get(cid)
            if not node:
                continue

            qtype = self._resolve_qtype(node)
            template = self._selector.select(qtype, None)

            q_text = template.template_text
            q_text = q_text.replace("[Chemical compound]", node.concept_name)
            q_text = q_text.replace("[Product]", "gaseous oxides")
            q_text = q_text.replace("[Reaction type]", "Thermal Decomposition")

            context_text = context_map.get(cid)
            if context_text:
                q_text = q_text.replace("[Technical passage detailing resistivity]", f"Textbook: {context_text}")

            q_text = self._synthesizer.synthesize(q_text)
            if not self._synthesizer.validate_no_placeholders(q_text):
                continue

            marks = {
                QuestionTypeCode.MCQ: 1,
                QuestionTypeCode.SHORT_ANSWER: 3,
                QuestionTypeCode.CASE_STUDY: 4,
                QuestionTypeCode.LONG_ANSWER: 5,
                QuestionTypeCode.NUMERICAL: 3,
                QuestionTypeCode.DIAGRAM: 3,
            }.get(qtype, 2)

            questions.append(
                QuestionInstance(
                    question_id=f"Q_{cid}",
                    academic_class=blueprint.academic_class,
                    stream=node.stream,
                    question_type=qtype,
                    blooms_level=template.target_bloom,
                    assigned_marks=marks,
                    content_text=q_text,
                    expected_word_count=50 if qtype == QuestionTypeCode.MCQ else 150,
                    metadata={"concept_id": cid},
                )
            )

        return questions

    @staticmethod
    def _resolve_qtype(node) -> QuestionTypeCode:
        if node.base_numerical_depth > 0.70:
            return QuestionTypeCode.NUMERICAL
        if "circ" in node.concept_id.lower() or "nut" in node.concept_id.lower():
            return QuestionTypeCode.DIAGRAM
        if node.base_reasoning_steps >= 4:
            return QuestionTypeCode.CASE_STUDY
        return QuestionTypeCode.SHORT_ANSWER
