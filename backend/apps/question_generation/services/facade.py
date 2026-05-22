import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..domain.datatypes import AssembledPaperBooklet, InstitutionPolicy
from ..domain.enums import AcademicClass, EducationBoard, ExamType
from ..domain.instructions.science.curriculum import CurriculumWeightageRegistry
from ..infrastructure.observability.metrics import GenerationMetrics
from ..services.orchestration.orchestrator import QuestionGenerationOrchestrator


@dataclass(frozen=True)
class GeneratePaperRequest:
    board: str
    academic_class: str
    exam_type: str
    chapters: List[str]
    difficulty: str = "medium"
    count: Optional[int] = None
    institution_id: str = "CBSE_OFFICIAL"
    seed: int = 42


@dataclass(frozen=True)
class QuestionDTO:
    question_id: str
    academic_class: str
    stream: str
    question_type: str
    blooms_level: str
    assigned_marks: int
    content_text: str
    expected_word_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyticsDTO:
    total_marks: int
    total_questions: int
    average_difficulty: float
    difficulty_skewness: str
    blooms_distribution: Dict[str, int]
    stream_distribution: Dict[str, float]
    competencies_covered: List[str]


@dataclass(frozen=True)
class GeneratedPaperResponse:
    paper_id: str
    school_name: str
    board: str
    general_instructions: List[str]
    questions: List[QuestionDTO]
    vi_accessible_questions: List[QuestionDTO]
    answer_keys: List[Dict[str, Any]]
    analytics: AnalyticsDTO
    observability_metrics: Dict[str, Any]


class AcademicGenerationFacade:
    def __init__(self, institution_policy: Optional[InstitutionPolicy] = None) -> None:
        self._orchestrator = QuestionGenerationOrchestrator()
        self._policy = institution_policy or InstitutionPolicy(
            institution_id="CBSE_OFFICIAL",
            name="CBSE Official",
            comp_questions_minimum_ratio=0.50,
            mcq_ratio_allowance=0.20,
            long_answer_max_ratio=0.20,
            require_visual_alternate=True,
            allowed_streams=set(),
            custom_instruction_footer="",
        )
        self._weights = CurriculumWeightageRegistry()

    def generate_paper(
        self,
        request: GeneratePaperRequest,
        context_map: Optional[Dict[str, str]] = None,
    ) -> GeneratedPaperResponse:
        start_time = time.time()

        board = EducationBoard[request.board]
        academic_class = AcademicClass[request.academic_class]
        exam_type = ExamType[request.exam_type]

        booklet = self._orchestrator.generate_paper(
            board=board,
            academic_class=academic_class,
            exam_type=exam_type,
            total_marks=80,
            chapters=request.chapters,
            difficulty=request.difficulty,
            count=request.count,
            policy=self._policy,
            context_map=context_map,
        )

        questions = [
            QuestionDTO(
                question_id=q.question_id,
                academic_class=q.academic_class.name,
                stream=q.stream.name,
                question_type=q.question_type.name,
                blooms_level=q.blooms_level.name,
                assigned_marks=q.assigned_marks,
                content_text=q.content_text,
                expected_word_count=q.expected_word_count,
                metadata=q.metadata,
            )
            for q in booklet.question_sequence
        ]

        vi_questions = [
            QuestionDTO(
                question_id=q.question_id,
                academic_class=q.academic_class.name,
                stream=q.stream.name,
                question_type=q.question_type.name,
                blooms_level=q.blooms_level.name,
                assigned_marks=q.assigned_marks,
                content_text=q.content_text,
                expected_word_count=q.expected_word_count,
                metadata=q.metadata,
            )
            for q in booklet.vi_accessible_sequence
        ]

        analytics_dto = AnalyticsDTO(
            total_marks=booklet.analytics.total_marks,
            total_questions=booklet.analytics.total_questions,
            average_difficulty=round(booklet.analytics.average_difficulty, 3),
            difficulty_skewness=booklet.analytics.difficulty_skewness,
            blooms_distribution={k.name: v for k, v in booklet.analytics.blooms_distribution.items()},
            stream_distribution={k.name: v for k, v in booklet.analytics.stream_distribution.items()},
            competencies_covered=booklet.analytics.nep_competency_coverage,
        )

        safe_context_map = context_map or {}
        metrics = GenerationMetrics(
            prompt_version="v1",
            model="template",
            chunk_count=len(safe_context_map),
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            truncation_events=0,
            provider_failures=0,
            latency_ms=(time.time() - start_time) * 1000.0,
        )

        return GeneratedPaperResponse(
            paper_id=booklet.paper_id,
            school_name=booklet.school_name,
            board=booklet.board.name,
            general_instructions=booklet.general_instructions,
            questions=questions,
            vi_accessible_questions=vi_questions,
            answer_keys=[
                {
                    "question_id": ak.question_id,
                    "expected_answer": ak.expected_answer,
                    "rubrics": [
                        {
                            "criteria_id": r.criteria_id,
                            "target_answer_step": r.target_answer_step,
                            "marks_weight": r.marks_weight,
                            "competency_mapped": r.competency_mapped,
                        }
                        for r in ak.rubrics
                    ],
                    "evaluator_tip": ak.evaluator_tip,
                }
                for ak in booklet.answer_keys
            ],
            analytics=analytics_dto,
            observability_metrics=metrics.to_dict(),
        )
