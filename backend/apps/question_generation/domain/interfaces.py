"""
Question Generation Domain - Interfaces
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .datatypes import (
    AnswerKeyRubric,
    CompiledPaperBlueprint,
    ConceptNode,
    ConceptWeightProfile,
    ExamBlueprint,
    MarksDepthProfile,
    ParsedQuestionNode,
    PaperAnalyticsDashboard,
    PromptPackage,
    QuestionInstance,
    QuestionTemplate,
    SemanticTextbookChunk,
    StreamProfile,
    QuestionTypeProfile,
    BloomsTaxonomyProfile,
    InstitutionPolicy,
    ValidationError,
)
from .enums import AcademicClass, BloomsLevel, EducationBoard, ExamType, QuestionTypeCode, StreamType


class ISubjectPlugin(ABC):
    @abstractmethod
    def get_subject_name(self) -> str:
        ...

    @abstractmethod
    def get_supported_classes(self) -> List[AcademicClass]:
        ...

    @abstractmethod
    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        ...

    @abstractmethod
    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        ...

    @abstractmethod
    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        ...


class IValidationRule(ABC):
    @abstractmethod
    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        ...


class IBoardSystem(ABC):
    @abstractmethod
    def get_board_code(self) -> EducationBoard:
        ...

    @abstractmethod
    def parse_sample_paper(self, raw_text: str) -> List[ParsedQuestionNode]:
        ...

    @abstractmethod
    def get_templates(self, qtype: QuestionTypeCode) -> List[QuestionTemplate]:
        ...

    @abstractmethod
    def generate_distractors(self, correct_value: float, **kwargs) -> List[Any]:
        ...


class IBlueprintCompiler(ABC):
    @abstractmethod
    def compile(
        self,
        board: EducationBoard,
        academic_class: AcademicClass,
        exam_type: ExamType,
        total_marks: int,
        chapters: List[str],
        difficulty: str,
        count: Optional[int] = None,
        institution_policy: Optional[InstitutionPolicy] = None,
    ) -> CompiledPaperBlueprint:
        ...


class IRetrievalEngine(ABC):
    @abstractmethod
    def retrieve(self, concept_id: str, query_embedding: List[float], max_chunks: int) -> List[SemanticTextbookChunk]:
        ...


class IPromptBuilder(ABC):
    @abstractmethod
    def build(
        self,
        concept: ConceptNode,
        template: QuestionTemplate,
        context: List[SemanticTextbookChunk],
        policy: InstitutionPolicy,
        board: EducationBoard,
    ) -> PromptPackage:
        ...


class ISafetyEngine(ABC):
    @abstractmethod
    def audit_question(self, q: QuestionInstance) -> List[str]:
        ...

    @abstractmethod
    def audit_paper(self, questions: List[QuestionInstance], concept_ids: List[str]) -> List[str]:
        ...


class ISectionChoreographer(ABC):
    @abstractmethod
    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        ...


class IChoiceEquivalenceRule(ABC):
    @abstractmethod
    def is_equivalent(self, q1: QuestionInstance, q2: QuestionInstance) -> bool:
        ...


class IAnalyticsEngine(ABC):
    @abstractmethod
    def compute(self, questions: List[QuestionInstance], concept_ids: List[str]) -> PaperAnalyticsDashboard:
        ...
