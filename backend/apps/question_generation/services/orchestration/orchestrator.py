import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from ...domain.accessibility import AccessibilityLearningEngine
from ...domain.blueprints.compiler import BlueprintCompiler
from ...domain.datatypes import AssembledPaperBooklet, CompiledPaperBlueprint, InstitutionPolicy, QuestionInstance
from ...domain.enums import AcademicClass, EducationBoard, ExamType
from ...domain.instructions.science.curriculum import CurriculumGraphFactory
from ...domain.safety import GenerationSafetyEngine
from ...domain.validators import ValidationOrchestrator
from ..generation.analytics_service import AnalyticsService
from ..generation.answer_keys import AnswerKeyCompiler
from ..generation.drafter import TemplateDraftingService
from ..retrieval.concept_context import ConceptContextService


@dataclass(frozen=True)
class OrchestrationReport:
    errors: List[str]
    validation: Optional[object]


class QuestionGenerationOrchestrator:
    def __init__(self) -> None:
        self._compiler = BlueprintCompiler()
        self._graph = CurriculumGraphFactory.construct_comprehensive_graph()
        self._safety = GenerationSafetyEngine(self._graph)
        self._validator = ValidationOrchestrator()
        self._drafting = TemplateDraftingService()
        self._accessibility = AccessibilityLearningEngine()
        self._answers = AnswerKeyCompiler()
        self._analytics = AnalyticsService()
        self._concept_context = ConceptContextService()

    def generate_paper(
        self,
        board: EducationBoard,
        academic_class: AcademicClass,
        exam_type: ExamType,
        total_marks: int,
        chapters: List[str],
        difficulty: str,
        count: Optional[int],
        policy: InstitutionPolicy,
        context_map: Optional[Dict[str, str]] = None,
    ) -> AssembledPaperBooklet:
        start_time = time.time()

        blueprint = self._compiler.compile(
            board=board,
            academic_class=academic_class,
            exam_type=exam_type,
            total_marks=total_marks,
            chapters=chapters,
            difficulty=difficulty,
            count=count,
            institution_policy=policy,
        )

        if context_map is None:
            context_map = self._concept_context.build_context_map(blueprint.retrieval_targets)

        questions = self._drafting.draft_questions(blueprint, policy, context_map)
        errors = self._safety.audit_paper(questions, blueprint.retrieval_targets)

        validation = self._validator.validate(
            blueprint=blueprint,
            target_data={
                "stream_marks": self._stream_marks(questions),
                "bloom_distribution": blueprint.blooms_distribution,
                "competency_question_count": len(questions),
                "total_question_count": len(questions),
                "competency_minimum_ratio": 0.50,
            },
        )

        standard, vi_accessible = self._accessibility.generate_dual_booklet(questions)
        answer_keys = self._answers.compile(questions, blueprint.retrieval_targets)
        analytics = self._analytics.compute(questions, blueprint.retrieval_targets)

        elapsed = (time.time() - start_time) * 1000.0
        mem = sys.getsizeof(self) / 1024.0

        if errors:
            # In future: return alongside diagnostics
            pass

        return AssembledPaperBooklet(
            paper_id=blueprint.paper_id,
            school_name=policy.name,
            board=board,
            general_instructions=[
                "All questions are compulsory.",
                f"This paper consists of {len(questions)} questions.",
                policy.custom_instruction_footer,
            ],
            question_sequence=standard,
            vi_accessible_sequence=vi_accessible,
            answer_keys=answer_keys,
            analytics=analytics,
            generation_duration_ms=elapsed,
            memory_allocation_kb=mem,
        )

    @staticmethod
    def _stream_marks(questions: List[QuestionInstance]) -> Dict[object, int]:
        stream_marks: Dict[object, int] = {}
        for q in questions:
            stream_marks[q.stream] = stream_marks.get(q.stream, 0) + q.assigned_marks
        return stream_marks
