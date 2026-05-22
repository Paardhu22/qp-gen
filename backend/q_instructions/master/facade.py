"""
AOS Integration — Academic Generation Facade & Contracts
=========================================================
Serves as the strict boundary between the QP Application Layer and the
Science Academic Domain Layer. All interactions must flow through this facade.
Provides stable DTO contracts, canonical execution pipeline flow,
and robust observability instrumentation (structured logs, tracing).
"""

import time
import logging
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from q_instructions.core.enums import (
    EducationBoard, AcademicClass, ExamType, QuestionTypeCode, BloomsLevel, StreamType
)
from q_instructions.core.datatypes import (
    CompiledPaperBlueprint, AssembledPaperBooklet, QuestionInstance,
    InstitutionPolicy, AnswerKeyRubric, SemanticTextbookChunk,
    AcademicContextPacket
)
from q_instructions.core.exceptions import BlueprintCompilationError, ConceptNotFoundError
from q_instructions.master.orchestrator import MasterAcademicOrchestrator


# ---------------------------------------------------------------------------
# Integration DTOs (Data Transfer Objects)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeneratePaperRequest:
    """Stable request contract from Next.js/Frontend Layer."""
    board: str  # e.g. "CBSE"
    academic_class: str  # e.g. "CLASS_10"
    exam_type: str  # e.g. "FINAL"
    chapters: List[str]
    difficulty: str = "medium"
    count: Optional[int] = None
    institution_id: str = "CBSE_OFFICIAL"
    seed: int = 42


@dataclass(frozen=True)
class GenerateQuestionsRequest:
    """Stable request contract to generate isolated questions for a bank."""
    academic_class: str
    stream: str
    question_type: str
    blooms_level: str
    count: int
    concept_ids: List[str]


@dataclass(frozen=True)
class QuestionDTO:
    """Stable integration DTO representing a generated question."""
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
class PaperBlueprintDTO:
    """Integration DTO for pre-generation blueprint inspection."""
    paper_id: str
    board: str
    academic_class: str
    exam_type: str
    total_marks: int
    duration_minutes: int
    sections: List[Dict[str, Any]]
    retrieval_targets: List[str]


@dataclass(frozen=True)
class ValidationResultDTO:
    """Consolidated UI-safe validation status payload."""
    is_valid: bool
    errors: List[Dict[str, str]]
    warnings: List[Dict[str, str]]
    diagnostics: Dict[str, Any]


@dataclass(frozen=True)
class AnalyticsDTO:
    """Structured paper diagnostic metrics DTO."""
    total_marks: int
    total_questions: int
    average_difficulty: float
    difficulty_skewness: str
    blooms_distribution: Dict[str, int]
    stream_distribution: Dict[str, float]
    competencies_covered: List[str]


@dataclass(frozen=True)
class AcademicContextPacketDTO:
    """Textbook context metadata packet DTO."""
    concept_id: str
    primary_text: str
    supporting_texts: List[str]
    keywords: List[str]


@dataclass(frozen=True)
class GeneratedPaperResponse:
    """Clean production-grade payload delivered back to Next.js/Editor."""
    paper_id: str
    school_name: str
    board: str
    general_instructions: List[str]
    questions: List[QuestionDTO]
    vi_accessible_questions: List[QuestionDTO]
    answer_keys: List[Dict[str, Any]]
    analytics: AnalyticsDTO
    observability_metrics: Dict[str, Any]


# ---------------------------------------------------------------------------
# Structured Observability Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("AOS.AcademicGenerationFacade")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    '{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": %(message)s}'
))
if not logger.handlers:
    logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Facade Gateway
# ---------------------------------------------------------------------------

class AcademicGenerationFacade:
    """
    Unified public API gatekeeper for the Science Academic Engine.
    Encapsulates all domain complexity from Layer 0 to 4.
    """

    def __init__(self) -> None:
        # Re-uses the coordinate-only master orchestrator
        self._orchestrator = MasterAcademicOrchestrator()

    def generate_paper(self, request: GeneratePaperRequest) -> GeneratedPaperResponse:
        """
        Executes the canonical, end-to-end integration-safe generation flow:
          UI Request → Blueprint → Context Retrieval → Drafting → Validation → VI alternate → Analytics.
        """
        start_time = time.time()
        logger.info(f'{{"action": "generate_paper_start", "institution_id": "{request.institution_id}"}}')

        # Map string parameters to core Enums
        try:
            ac_class = AcademicClass[request.academic_class]
            ex_type = ExamType[request.exam_type]
            board = EducationBoard[request.board]
        except KeyError as e:
            logger.error(f'{{"action": "generate_paper_error", "reason": "invalid_enum_value", "details": "{str(e)}"}}')
            raise ValueError(f"Invalid integration parameters: {e}")

        # Update coordinator's institution_id
        self._orchestrator.institution_id = request.institution_id

        # 1. Pipeline Execution with Tracing
        bp_start = time.time()
        policy = self._orchestrator._institutions.get_policy(request.institution_id)
        blueprint = self._orchestrator._compiler.compile(
            board=board,
            academic_class=ac_class,
            exam_type=ex_type,
            total_marks=80,
            chapters=request.chapters,
            difficulty=request.difficulty,
            count=request.count,
            institution_policy=policy
        )
        bp_duration = (time.time() - bp_start) * 1000.0

        # 2. Draft & Retrieve Context
        draft_start = time.time()
        questions = self._orchestrator._draft_questions(blueprint, policy)
        draft_duration = (time.time() - draft_start) * 1000.0

        # 3. Safety Audit & Validation
        val_start = time.time()
        errors = self._orchestrator._safety.audit_paper(questions, blueprint.retrieval_targets)
        val_duration = (time.time() - val_start) * 1000.0

        # 4. VI Alternate Booklet
        vi_start = time.time()
        standard, vi_accessible = self._orchestrator._accessibility.generate_dual_booklet(questions)
        vi_duration = (time.time() - vi_start) * 1000.0

        # 5. Answer keys & rubrics
        answer_keys = self._orchestrator._compile_answer_keys(questions, blueprint.retrieval_targets)

        # 6. Analytics dashboard conversion
        raw_analytics = self._orchestrator._compute_analytics(questions, blueprint.retrieval_targets)
        
        analytics_dto = AnalyticsDTO(
            total_marks=raw_analytics.total_marks,
            total_questions=raw_analytics.total_questions,
            average_difficulty=round(raw_analytics.average_difficulty, 3),
            difficulty_skewness=raw_analytics.difficulty_skewness,
            blooms_distribution={k.name: v for k, v in raw_analytics.blooms_distribution.items()},
            stream_distribution={k.name: v for k, v in raw_analytics.stream_distribution.items()},
            competencies_covered=raw_analytics.nep_competency_coverage
        )

        total_duration = (time.time() - start_time) * 1000.0
        
        # Build observability payload
        metrics = {
            "blueprint_compile_time_ms": bp_duration,
            "question_drafting_time_ms": draft_duration,
            "validation_audit_time_ms": val_duration,
            "accessibility_split_time_ms": vi_duration,
            "total_execution_time_ms": total_duration,
            "hallucination_violations_count": len([e for e in errors if "hallucinated" in e.lower()]),
            "safety_violations_count": len(errors),
            "safety_errors_list": errors
        }

        logger.info(
            f'{{"action": "generate_paper_success", '
            f'"paper_id": "{blueprint.paper_id}", '
            f'"total_duration_ms": {total_duration:.2f}, '
            f'"violations": {len(errors)}}}'
        )

        # Convert core dataclasses to integration-safe DTOs
        return GeneratedPaperResponse(
            paper_id=blueprint.paper_id,
            school_name=policy.name,
            board=board.name,
            general_instructions=[
                "All questions are compulsory.",
                f"This paper consists of {len(questions)} questions.",
                policy.custom_instruction_footer
            ],
            questions=[self._to_dto(q) for q in standard],
            vi_accessible_questions=[self._to_dto(q) for q in vi_accessible],
            answer_keys=[self._to_rubric_dict(r) for r in answer_keys],
            analytics=analytics_dto,
            observability_metrics=metrics
        )

    def generate_questions(self, request: GenerateQuestionsRequest) -> List[QuestionDTO]:
        """Generates isolated template-based questions for the central question bank."""
        logger.info(f'{{"action": "generate_questions_start", "count": {request.count}}}')
        dtos = []
        try:
            qtype = QuestionTypeCode[request.question_type]
            stream = StreamType[request.stream]
            bloom = BloomsLevel[request.blooms_level]
        except KeyError as e:
            logger.error(f'{{"action": "generate_questions_error", "reason": "invalid_enum", "details": "{str(e)}"}}')
            raise ValueError(f"Invalid parameters: {e}")

        templates = self._orchestrator._templates.get_templates_by_type(qtype)
        template = templates[0] if templates else self._orchestrator._templates.get_all_templates()[0]

        for i, cid in enumerate(request.concept_ids[:request.count]):
            node = self._orchestrator._graph.nodes.get(cid)
            concept_name = node.concept_name if node else "Integrated Concept"

            q_text = template.template_text.replace("[Chemical compound]", concept_name)
            q_text = q_text.replace("[Product]", "gaseous elements")
            
            dtos.append(QuestionDTO(
                question_id=f"Q_BANK_{cid}_{i}",
                academic_class=request.academic_class,
                stream=stream.name,
                question_type=qtype.name,
                blooms_level=bloom.name,
                assigned_marks=3,
                content_text=q_text,
                expected_word_count=120
            ))

        return dtos

    def validate_blueprint(self, blueprint_dto: PaperBlueprintDTO) -> ValidationResultDTO:
        """Validates a pre-configured UI blueprint configuration without drafting content."""
        logger.info(f'{{"action": "validate_blueprint_start", "paper_id": "{blueprint_dto.paper_id}"}}')
        
        try:
            ac_class = AcademicClass[blueprint_dto.academic_class]
            ex_type = ExamType[blueprint_dto.exam_type]
            board = EducationBoard[blueprint_dto.board]
        except KeyError as e:
            return ValidationResultDTO(
                is_valid=False,
                errors=[{"rule": "ValidationOrchestrator", "message": f"Invalid enum parameter: {e}"}],
                warnings=[],
                diagnostics={}
            )

        policy = self._orchestrator._institutions.get_policy("CBSE_OFFICIAL")
        
        # Run Blueprint Compiler
        compiled = self._orchestrator._compiler.compile(
            board=board,
            academic_class=ac_class,
            exam_type=ex_type,
            total_marks=blueprint_dto.total_marks,
            chapters=blueprint_dto.retrieval_targets,
            difficulty="medium",
            institution_policy=policy
        )

        # Mock standard metrics for validation
        mock_data = {
            "total_question_count": len(compiled.retrieval_targets),
            "competency_question_count": int(len(compiled.retrieval_targets) * 0.55),
            "competency_minimum_ratio": 0.50,
            "stream_marks": {
                StreamType.PHYSICS: 30,
                StreamType.CHEMISTRY: 25,
                StreamType.BIOLOGY: 25
            },
            "bloom_distribution": {
                BloomsLevel.REMEMBER: 0.20,
                BloomsLevel.UNDERSTAND: 0.30,
                BloomsLevel.APPLY: 0.50
            }
        }

        from q_instructions.core.validators import ValidationOrchestrator
        validator = ValidationOrchestrator()
        report = validator.validate(compiled, mock_data)
        
        errors = []
        warnings = []
        for e in report.errors:
            err_dict = {"rule": e.rule_name, "message": e.error_message, "remediation": e.suggested_remediation}
            if e.severity.name == "ERROR":
                errors.append(err_dict)
            else:
                warnings.append(err_dict)

        return ValidationResultDTO(
            is_valid=report.is_valid,
            errors=errors,
            warnings=warnings,
            diagnostics=report.diagnostics
        )

    def _to_dto(self, q: QuestionInstance) -> QuestionDTO:
        return QuestionDTO(
            question_id=q.question_id,
            academic_class=q.academic_class.name,
            stream=q.stream.name,
            question_type=q.question_type.name,
            blooms_level=q.blooms_level.name,
            assigned_marks=q.assigned_marks,
            content_text=q.content_text,
            expected_word_count=q.expected_word_count,
            metadata=q.metadata
        )

    def _to_rubric_dict(self, r: AnswerKeyRubric) -> Dict[str, Any]:
        return {
            "question_id": r.question_id,
            "expected_answer": r.expected_answer,
            "rubrics": [
                {
                    "criteria_id": c.criteria_id,
                    "target_answer_step": c.target_answer_step,
                    "marks_weight": c.marks_weight,
                    "competency_mapped": c.competency_mapped
                }
                for c in r.rubrics
            ],
            "evaluator_tip": r.evaluator_tip
        }
