"""
AOS Core — Canonical Data Types
=================================
ALL shared frozen dataclasses live here.
These are the structural contracts that flow between modules.
Depends ONLY on core.enums.
"""

import math
import json
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional, Any

from q_instructions.core.enums import (
    EducationBoard, AcademicClass, StreamType, StreamMode,
    QuestionTypeCode, BloomsLevel, ExamType, ValidationSeverity,
    GradingDimension, CognitiveStyle, AbstractionLevel,
    RelationshipType, TokenKind, StudentArchetype,
    ConceptualMaturityLevel, ReasoningExpectation, NumericalComplexityLevel,
    MisconceptionType
)


# ---------------------------------------------------------------------------
# Board & Institution Policies
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoardPolicy:
    """Constraints governed by a target education board."""
    board: EducationBoard
    marking_scheme_type: str
    grading_scale: List[str]
    allow_halves: bool
    competency_ratio_target: float
    practical_internal_marks: int


@dataclass(frozen=True)
class InstitutionPolicy:
    """Policy overrides governable by individual schools."""
    institution_id: str
    name: str
    comp_questions_minimum_ratio: float
    mcq_ratio_allowance: float
    long_answer_max_ratio: float
    require_visual_alternate: bool
    allowed_streams: Set[StreamType]
    custom_instruction_footer: str


# ---------------------------------------------------------------------------
# Subject & Stream Profiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubjectProfile:
    """Comprehensive academic profile for a subject."""
    subject_name: str
    supported_classes: Set[AcademicClass]
    stream_mode_mapping: Dict[AcademicClass, StreamMode]
    board_policies: Dict[EducationBoard, BoardPolicy]


@dataclass(frozen=True)
class TheoryPracticalRatio:
    """Balance ratio of theoretical to practical content."""
    theory_percentage: float
    practical_percentage: float

    def __post_init__(self) -> None:
        if not math.isclose(self.theory_percentage + self.practical_percentage, 100.0, rel_tol=1e-5):
            raise ValueError("Theory and Practical percentages must sum to 100.")


@dataclass(frozen=True)
class StreamProfile:
    """Core characteristics defining a scientific stream."""
    stream_type: StreamType
    cognitive_style: CognitiveStyle
    preferred_question_types: List[str]
    diagram_frequency_coefficient: float
    numerical_weightage_coefficient: float
    theory_practical_ratio: TheoryPracticalRatio
    core_focus_description: str


# ---------------------------------------------------------------------------
# Class Progression
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExpectedAnswerDepth:
    """Expected structural sophistication of student responses."""
    minimum_sentences: int
    target_word_count: int
    requires_diagram: bool
    requires_equation: bool
    multi_step_reasoning_allowed: bool


@dataclass(frozen=True)
class ClassProgressionProfile:
    """Maps expected developmental constraints per class level."""
    academic_class: AcademicClass
    maturity_level: ConceptualMaturityLevel
    reasoning_expectation: ReasoningExpectation
    numerical_complexity: NumericalComplexityLevel
    max_blooms_permitted: BloomsLevel
    answer_depth: ExpectedAnswerDepth


# ---------------------------------------------------------------------------
# Question Type Profiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RubricComponent:
    """Marks allocation structure for a rubric element."""
    component_name: str
    marks_allocated: int
    validation_rule_description: str


@dataclass(frozen=True)
class QuestionTypeProfile:
    """Constraints governing a specific question archetype."""
    question_type: QuestionTypeCode
    valid_marks_range: Tuple[int, int]
    requires_diagram: bool
    typical_bloom_levels: List[BloomsLevel]
    expected_rubric_components: List[RubricComponent]
    target_streams: List[StreamType]
    cognitive_load_coefficient: float
    description: str


# ---------------------------------------------------------------------------
# Bloom's Taxonomy Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BloomsVerb:
    """Cognitive verb aligned to CBSE assessments."""
    verb: str
    target_stream_contexts: Set[StreamType]
    sample_phrase_template: str


@dataclass(frozen=True)
class BloomsTaxonomyProfile:
    """Taxonomy constraints for a Bloom's tier."""
    level: BloomsLevel
    cognitive_weight_index: float
    action_verbs: List[BloomsVerb]
    difficulty_coefficient_range: Tuple[float, float]
    description: str


# ---------------------------------------------------------------------------
# Marks Depth
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarksDepthProfile:
    """Depth of expected response for a specific marks slot."""
    marks_value: int
    expected_reasoning_steps: int
    expected_diagrams: int
    target_word_range: Tuple[int, int]
    typical_time_seconds: int
    applicable_types: List[QuestionTypeCode]


# ---------------------------------------------------------------------------
# Exam Blueprint Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SectionBlueprint:
    """Blueprint constraints governing individual paper sections."""
    section_id: str
    question_type: QuestionTypeCode
    question_count: int
    marks_per_question: int
    internal_choice_count: int

    def get_total_marks(self) -> int:
        return self.question_count * self.marks_per_question


@dataclass(frozen=True)
class ExamBlueprint:
    """Master layout specification defining exam structure."""
    exam_type: ExamType
    academic_class: AcademicClass
    duration_minutes: int
    total_marks: int
    sections: List[SectionBlueprint]
    bloom_distribution_target: Dict[BloomsLevel, float]
    stream_distribution_target: Dict[StreamType, float]
    difficulty_target: Dict[str, float]


# ---------------------------------------------------------------------------
# Curriculum & Concept Graph Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChapterMetadata:
    """Academic chapter profile."""
    chapter_id: str
    chapter_name: str
    academic_class: AcademicClass
    primary_stream: StreamType
    ncert_chapter_number: int
    complexity_coefficient: float
    practical_weightage: float
    theoretical_density: float


@dataclass(frozen=True)
class ConceptNode:
    """A single concept vertex in the curriculum graph."""
    concept_id: str
    concept_name: str
    academic_class: AcademicClass
    stream: StreamType
    abstraction_level: AbstractionLevel
    base_numerical_depth: float
    base_reasoning_steps: int


@dataclass(frozen=True)
class ConceptEdge:
    """A directed edge in the concept dependency graph."""
    source_id: str
    target_id: str
    relationship: RelationshipType
    strength: float


@dataclass(frozen=True)
class ConceptWeightProfile:
    """Weightage and competency mapping for a concept."""
    concept_id: str
    board_weightage: float
    frequency_score: float
    is_board_favorite: bool
    target_nep_competency_code: str


# ---------------------------------------------------------------------------
# Question Instance (mutable — runtime state)
# ---------------------------------------------------------------------------

@dataclass
class QuestionInstance:
    """A structured academic question conforming to AOS rules."""
    question_id: str
    academic_class: AcademicClass
    stream: StreamType
    question_type: QuestionTypeCode
    blooms_level: BloomsLevel
    assigned_marks: int
    content_text: str
    expected_word_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Board Learning Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaperToken:
    """A single parsed structural token from an official exam paper."""
    kind: TokenKind
    text: str
    line_number: int


@dataclass
class ParsedQuestionNode:
    """Intermediate parsed question extracted from official papers."""
    question_num: int
    raw_text: str
    assigned_marks: int
    is_internal_choice: bool = False
    section_id: str = "A"
    detected_type: QuestionTypeCode = QuestionTypeCode.MCQ
    extracted_keywords: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class QuestionTemplate:
    """Parametric template for structured question generation."""
    template_id: str
    target_type: QuestionTypeCode
    target_bloom: BloomsLevel
    template_text: str
    required_placeholders: List[str]


@dataclass(frozen=True)
class DistractorOption:
    """A single MCQ option with misconception metadata."""
    option_label: str
    option_value: str
    is_correct: bool
    misconception_type: Optional[MisconceptionType] = None


# ---------------------------------------------------------------------------
# Validation Framework Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationError:
    """Explicit mapping of a validation issue."""
    rule_name: str
    severity: ValidationSeverity
    affected_element: str
    error_message: str
    suggested_remediation: str


@dataclass
class ValidationReport:
    """Report packaging all errors, logs, and statuses."""
    is_valid: bool
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    errors: List[ValidationError] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "is_valid": self.is_valid,
            "diagnostics": self.diagnostics,
            "errors": [
                {
                    "rule": e.rule_name,
                    "severity": e.severity.name,
                    "element": e.affected_element,
                    "message": e.error_message,
                    "remediation": e.suggested_remediation
                }
                for e in self.errors
            ]
        }, indent=4)


# ---------------------------------------------------------------------------
# Rubric Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RubricTier:
    """Marks allocation for a performance tier."""
    tier_name: str
    marks_multiplier: float
    criteria_description: str


@dataclass(frozen=True)
class RubricCriteria:
    """Marking step within a rubric."""
    criteria_id: str
    target_answer_step: str
    marks_weight: float
    competency_mapped: str


@dataclass(frozen=True)
class AnswerKeyRubric:
    """Expected response and marking rubric for a question."""
    question_id: str
    expected_answer: str
    rubrics: List[RubricCriteria]
    evaluator_tip: str


# ---------------------------------------------------------------------------
# Psychometric Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StudentProfile:
    """Core psychometric parameters for student simulation."""
    archetype: StudentArchetype
    baseline_proficiency: float
    anxiety_baseline: float
    fatigue_resistance: float
    recovery_multiplier: float
    time_pressure_sensitivity: float


@dataclass
class StudentPsychologicalState:
    """Mutable real-time state tracking a simulated student."""
    current_fatigue: float = 0.0
    current_anxiety: float = 0.0
    questions_attempted: int = 0
    marks_attempted: int = 0
    time_elapsed_minutes: float = 0.0
    cognitive_load_cumulative: float = 0.0


@dataclass(frozen=True)
class PsychometricStimulus:
    """Describes the psychometric impact of a single question on student state."""
    fatigue_delta: float
    anxiety_delta: float
    estimated_minutes: float
    is_relief_question: bool
    bloom_cognitive_load: float


# ---------------------------------------------------------------------------
# Analytics Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaperAnalyticsDashboard:
    """Summary statistics of a generated paper."""
    total_marks: int
    total_questions: int
    average_difficulty: float
    difficulty_skewness: str
    blooms_distribution: Dict[BloomsLevel, int]
    stream_distribution: Dict[StreamType, float]
    nep_competency_coverage: List[str]


@dataclass(frozen=True)
class RealismMetricsReport:
    """Comparative realism statistics between generated and official papers."""
    target_paper_id: str
    section_layout_similarity: float
    marks_weight_similarity: float
    keywords_phrasing_similarity: float
    chronological_sequence_similarity: float
    overall_realism_index: float


# ---------------------------------------------------------------------------
# Retrieval Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticTextbookChunk:
    """A context-bearing text chunk from textbooks with vector embedding."""
    chunk_id: str
    chapter_id: str
    concept_id: str
    text_content: str
    vector_embedding: List[float]
    competency_tags: List[str]


@dataclass(frozen=True)
class AcademicContextPacket:
    """Assembled context payload for question generation drafting."""
    concept_id: str
    primary_chunk: SemanticTextbookChunk
    supporting_chunks: List[SemanticTextbookChunk]
    extracted_keywords: List[str]
    complexity_score: float


# ---------------------------------------------------------------------------
# Generation Types
# ---------------------------------------------------------------------------

@dataclass
class PromptPackage:
    """Assembled modular instructions for AI generation models."""
    target_model: str
    system_instructions: str
    context_chunks_text: str
    wording_guidelines: str
    cognitive_bloom_modifiers: str
    output_schema_directives: str

    def compile(self) -> str:
        sep = "=" * 50
        return (
            f"{self.system_instructions}\n\n"
            f"{sep}\nRETRIEVED TEXTBOOK CONTEXT:\n{sep}\n"
            f"{self.context_chunks_text}\n\n"
            f"{sep}\nCOGNITIVE TAXONOMY & WORDING DIRECTIVES:\n{sep}\n"
            f"{self.cognitive_bloom_modifiers}\n"
            f"{self.wording_guidelines}\n\n"
            f"{sep}\nOUTPUT SCHEMA FORMAT:\n{sep}\n"
            f"{self.output_schema_directives}"
        )


# ---------------------------------------------------------------------------
# Internal Choice Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InternalChoiceOption:
    """Paired internal choice questions (OR option in CBSE papers)."""
    option_a: QuestionInstance
    option_b: QuestionInstance
    section_id: str


# ---------------------------------------------------------------------------
# Compiled Blueprint (THE HEART)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompiledPaperBlueprint:
    """
    Deterministic, fully resolved exam blueprint.
    This is the SINGLE SOURCE OF TRUTH before generation begins.
    """
    paper_id: str
    board: EducationBoard
    academic_class: AcademicClass
    exam_type: ExamType
    total_marks: int
    duration_minutes: int
    sections: List[SectionBlueprint]
    stream_distribution: Dict[StreamType, float]
    competency_distribution: Dict[str, float]
    blooms_distribution: Dict[BloomsLevel, float]
    chapter_distribution: Dict[str, float]
    difficulty_curve: List[float]
    question_type_distribution: Dict[QuestionTypeCode, int]
    retrieval_targets: List[str]  # Concept IDs to retrieve context for
    institution_policy: Optional[InstitutionPolicy] = None


# ---------------------------------------------------------------------------
# Final Output Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AssembledPaperBooklet:
    """The final compiled product delivered to schools and candidates."""
    paper_id: str
    school_name: str
    board: EducationBoard
    general_instructions: List[str]
    question_sequence: List[QuestionInstance]
    vi_accessible_sequence: List[QuestionInstance]
    answer_keys: List[AnswerKeyRubric]
    analytics: PaperAnalyticsDashboard
    generation_duration_ms: float
    memory_allocation_kb: float
