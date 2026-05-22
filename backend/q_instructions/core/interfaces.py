"""
AOS Core — Abstract Contracts & Interfaces
=============================================
Defines the ABC interfaces that all plugins, validators, engines,
and board systems must implement. Enables dependency inversion —
upper layers depend on these contracts, not on concrete implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from q_instructions.core.enums import (
    AcademicClass, StreamType, QuestionTypeCode, BloomsLevel,
    ExamType, EducationBoard
)
from q_instructions.core.datatypes import (
    ExamBlueprint, ValidationError, ValidationReport,
    QuestionInstance, CompiledPaperBlueprint, StreamProfile,
    QuestionTypeProfile, BloomsTaxonomyProfile, MarksDepthProfile,
    ConceptNode, ConceptWeightProfile, ChapterMetadata,
    ParsedQuestionNode, QuestionTemplate, DistractorOption,
    StudentProfile, PaperAnalyticsDashboard, AnswerKeyRubric,
    SemanticTextbookChunk, PromptPackage, InstitutionPolicy
)


# ---------------------------------------------------------------------------
# Subject Plugin Contract
# ---------------------------------------------------------------------------

class ISubjectPlugin(ABC):
    """
    Contract for subject-specific engines.
    Science, Math, Social, English — each implements this.
    """

    @abstractmethod
    def get_subject_name(self) -> str:
        """Returns the canonical subject name."""
        ...

    @abstractmethod
    def get_supported_classes(self) -> List[AcademicClass]:
        """Returns classes this subject covers."""
        ...

    @abstractmethod
    def get_stream_profile(self, stream: StreamType) -> StreamProfile:
        """Returns the stream constraints profile."""
        ...

    @abstractmethod
    def get_question_type_profile(self, qtype: QuestionTypeCode) -> QuestionTypeProfile:
        """Returns constraints for a question archetype."""
        ...

    @abstractmethod
    def get_blooms_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        """Returns cognitive taxonomy profile for a Bloom's level."""
        ...


# ---------------------------------------------------------------------------
# Validation Rule Contract
# ---------------------------------------------------------------------------

class IValidationRule(ABC):
    """Interface for modular validation policy rules."""

    @abstractmethod
    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        """Runs validation checks, returning errors found."""
        ...


# ---------------------------------------------------------------------------
# Board System Contract
# ---------------------------------------------------------------------------

class IBoardSystem(ABC):
    """Contract for board-specific style, parsing, and policy engines."""

    @abstractmethod
    def get_board_code(self) -> EducationBoard:
        """Returns the board identifier."""
        ...

    @abstractmethod
    def parse_sample_paper(self, raw_text: str) -> List[ParsedQuestionNode]:
        """Parses an official sample paper into structured nodes."""
        ...

    @abstractmethod
    def get_templates(self, qtype: QuestionTypeCode) -> List[QuestionTemplate]:
        """Returns question generation templates for a type."""
        ...

    @abstractmethod
    def generate_distractors(self, correct_value: float, **kwargs) -> List[DistractorOption]:
        """Generates misconception-based MCQ distractors."""
        ...


# ---------------------------------------------------------------------------
# Blueprint Compiler Contract
# ---------------------------------------------------------------------------

class IBlueprintCompiler(ABC):
    """
    Contract for the deterministic blueprint compiler.
    Takes exam specifications and produces a fully resolved
    CompiledPaperBlueprint BEFORE any generation occurs.
    """

    @abstractmethod
    def compile(
        self,
        board: EducationBoard,
        academic_class: AcademicClass,
        exam_type: ExamType,
        total_marks: int,
        chapters: List[str],
        difficulty: str,
        institution_policy: Optional[InstitutionPolicy] = None
    ) -> CompiledPaperBlueprint:
        """Compiles a deterministic blueprint from specifications."""
        ...


# ---------------------------------------------------------------------------
# Retrieval Contract
# ---------------------------------------------------------------------------

class IRetrievalEngine(ABC):
    """Contract for semantic context retrieval."""

    @abstractmethod
    def retrieve(self, concept_id: str, query_embedding: List[float], max_chunks: int) -> List[SemanticTextbookChunk]:
        """Retrieves semantically relevant textbook context."""
        ...


# ---------------------------------------------------------------------------
# Prompt Builder Contract
# ---------------------------------------------------------------------------

class IPromptBuilder(ABC):
    """Contract for modular prompt assembly."""

    @abstractmethod
    def build(
        self,
        concept: ConceptNode,
        template: QuestionTemplate,
        context: List[SemanticTextbookChunk],
        policy: InstitutionPolicy,
        board: EducationBoard
    ) -> PromptPackage:
        """Assembles a structured prompt package."""
        ...


# ---------------------------------------------------------------------------
# Safety Engine Contract
# ---------------------------------------------------------------------------

class ISafetyEngine(ABC):
    """Contract for generation safety validation."""

    @abstractmethod
    def audit_question(self, q: QuestionInstance) -> List[str]:
        """Audits a single generated question, returning error messages."""
        ...

    @abstractmethod
    def audit_paper(self, questions: List[QuestionInstance], concept_ids: List[str]) -> List[str]:
        """Audits a complete assembled paper."""
        ...


# ---------------------------------------------------------------------------
# Section Choreographer Contract
# ---------------------------------------------------------------------------

class ISectionChoreographer(ABC):
    """Contract for section-level question arrangement."""

    @abstractmethod
    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        """Arranges questions within a section according to pedagogical rules."""
        ...


# ---------------------------------------------------------------------------
# Choice Equivalence Contract
# ---------------------------------------------------------------------------

class IChoiceEquivalenceRule(ABC):
    """Contract for internal choice equivalence validation."""

    @abstractmethod
    def is_equivalent(self, q1: QuestionInstance, q2: QuestionInstance) -> bool:
        """Checks if two questions are fair internal choice alternatives."""
        ...


# ---------------------------------------------------------------------------
# Analytics Contract
# ---------------------------------------------------------------------------

class IAnalyticsEngine(ABC):
    """Contract for exam analytics computation."""

    @abstractmethod
    def compute(self, questions: List[QuestionInstance], concept_ids: List[str]) -> PaperAnalyticsDashboard:
        """Computes analytics for a generated paper."""
        ...
