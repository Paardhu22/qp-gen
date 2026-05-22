"""
Question Generation Domain - Shared Datatypes
"""

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .enums import (
    AbstractionLevel,
    AcademicClass,
    BloomsLevel,
    CognitiveStyle,
    ConceptualMaturityLevel,
    EducationBoard,
    ExamType,
    GradingDimension,
    MisconceptionType,
    NumericalComplexityLevel,
    QuestionTypeCode,
    RelationshipType,
    ReasoningExpectation,
    StreamMode,
    StreamType,
    StudentArchetype,
    TokenKind,
    ValidationSeverity,
)


@dataclass(frozen=True)
class BoardPolicy:
    board: EducationBoard
    marking_scheme_type: str
    grading_scale: List[str]
    allow_halves: bool
    competency_ratio_target: float
    practical_internal_marks: int


@dataclass(frozen=True)
class InstitutionPolicy:
    institution_id: str
    name: str
    comp_questions_minimum_ratio: float
    mcq_ratio_allowance: float
    long_answer_max_ratio: float
    require_visual_alternate: bool
    allowed_streams: Set[StreamType]
    custom_instruction_footer: str


@dataclass(frozen=True)
class SubjectProfile:
    subject_name: str
    supported_classes: Set[AcademicClass]
    stream_mode_mapping: Dict[AcademicClass, StreamMode]
    board_policies: Dict[EducationBoard, BoardPolicy]


@dataclass(frozen=True)
class TheoryPracticalRatio:
    theory_percentage: float
    practical_percentage: float

    def __post_init__(self) -> None:
        if not math.isclose(self.theory_percentage + self.practical_percentage, 100.0, rel_tol=1e-5):
            raise ValueError("Theory and Practical percentages must sum to 100.")


@dataclass(frozen=True)
class StreamProfile:
    stream_type: StreamType
    cognitive_style: CognitiveStyle
    preferred_question_types: List[str]
    diagram_frequency_coefficient: float
    numerical_weightage_coefficient: float
    theory_practical_ratio: TheoryPracticalRatio
    core_focus_description: str


@dataclass(frozen=True)
class ExpectedAnswerDepth:
    minimum_sentences: int
    target_word_count: int
    requires_diagram: bool
    requires_equation: bool
    multi_step_reasoning_allowed: bool


@dataclass(frozen=True)
class ClassProgressionProfile:
    academic_class: AcademicClass
    maturity_level: ConceptualMaturityLevel
    reasoning_expectation: ReasoningExpectation
    numerical_complexity: NumericalComplexityLevel
    max_blooms_permitted: BloomsLevel
    answer_depth: ExpectedAnswerDepth


@dataclass(frozen=True)
class RubricComponent:
    component_name: str
    marks_allocated: int
    validation_rule_description: str


@dataclass(frozen=True)
class QuestionTypeProfile:
    question_type: QuestionTypeCode
    valid_marks_range: Tuple[int, int]
    requires_diagram: bool
    typical_bloom_levels: List[BloomsLevel]
    expected_rubric_components: List[RubricComponent]
    target_streams: List[StreamType]
    cognitive_load_coefficient: float
    description: str


@dataclass(frozen=True)
class BloomsVerb:
    verb: str
    target_stream_contexts: Set[StreamType]
    sample_phrase_template: str


@dataclass(frozen=True)
class BloomsTaxonomyProfile:
    level: BloomsLevel
    cognitive_weight_index: float
    action_verbs: List[BloomsVerb]
    difficulty_coefficient_range: Tuple[float, float]
    description: str


@dataclass(frozen=True)
class MarksDepthProfile:
    marks_value: int
    expected_reasoning_steps: int
    expected_diagrams: int
    target_word_range: Tuple[int, int]
    typical_time_seconds: int
    applicable_types: List[QuestionTypeCode]


@dataclass(frozen=True)
class SectionBlueprint:
    section_id: str
    question_type: QuestionTypeCode
    question_count: int
    marks_per_question: int
    internal_choice_count: int

    def get_total_marks(self) -> int:
        return self.question_count * self.marks_per_question


@dataclass(frozen=True)
class ExamBlueprint:
    exam_type: ExamType
    academic_class: AcademicClass
    duration_minutes: int
    total_marks: int
    sections: List[SectionBlueprint]
    bloom_distribution_target: Dict[BloomsLevel, float]
    stream_distribution_target: Dict[StreamType, float]
    difficulty_target: Dict[str, float]


@dataclass(frozen=True)
class ChapterMetadata:
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
    concept_id: str
    concept_name: str
    academic_class: AcademicClass
    stream: StreamType
    abstraction_level: AbstractionLevel
    base_numerical_depth: float
    base_reasoning_steps: int


@dataclass(frozen=True)
class ConceptEdge:
    source_id: str
    target_id: str
    relationship: RelationshipType
    strength: float


@dataclass(frozen=True)
class ConceptWeightProfile:
    concept_id: str
    board_weightage: float
    frequency_score: float
    is_board_favorite: bool
    target_nep_competency_code: str


@dataclass
class QuestionInstance:
    question_id: str
    academic_class: AcademicClass
    stream: StreamType
    question_type: QuestionTypeCode
    blooms_level: BloomsLevel
    assigned_marks: int
    content_text: str
    expected_word_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperToken:
    kind: TokenKind
    text: str
    line_number: int


@dataclass
class ParsedQuestionNode:
    question_num: int
    raw_text: str
    assigned_marks: int
    is_internal_choice: bool = False
    section_id: str = "A"
    detected_type: QuestionTypeCode = QuestionTypeCode.MCQ
    extracted_keywords: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class QuestionTemplate:
    template_id: str
    target_type: QuestionTypeCode
    target_bloom: BloomsLevel
    template_text: str
    required_placeholders: List[str]


@dataclass(frozen=True)
class DistractorOption:
    option_label: str
    option_value: str
    is_correct: bool
    misconception_type: Optional[MisconceptionType] = None


@dataclass(frozen=True)
class ValidationError:
    rule_name: str
    severity: ValidationSeverity
    affected_element: str
    error_message: str
    suggested_remediation: str


@dataclass
class ValidationReport:
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
                    "remediation": e.suggested_remediation,
                }
                for e in self.errors
            ],
        }, indent=4)


@dataclass(frozen=True)
class RubricTier:
    tier_name: str
    marks_multiplier: float
    criteria_description: str


@dataclass(frozen=True)
class RubricCriteria:
    criteria_id: str
    target_answer_step: str
    marks_weight: float
    competency_mapped: str


@dataclass(frozen=True)
class AnswerKeyRubric:
    question_id: str
    expected_answer: str
    rubrics: List[RubricCriteria]
    evaluator_tip: str


@dataclass(frozen=True)
class StudentProfile:
    archetype: StudentArchetype
    baseline_proficiency: float
    anxiety_baseline: float
    fatigue_resistance: float
    recovery_multiplier: float
    time_pressure_sensitivity: float


@dataclass
class StudentPsychologicalState:
    current_fatigue: float = 0.0
    current_anxiety: float = 0.0
    questions_attempted: int = 0
    marks_attempted: int = 0
    time_elapsed_minutes: float = 0.0
    cognitive_load_cumulative: float = 0.0


@dataclass(frozen=True)
class PsychometricStimulus:
    fatigue_delta: float
    anxiety_delta: float
    estimated_minutes: float
    is_relief_question: bool
    bloom_cognitive_load: float


@dataclass(frozen=True)
class PaperAnalyticsDashboard:
    total_marks: int
    total_questions: int
    average_difficulty: float
    difficulty_skewness: str
    blooms_distribution: Dict[BloomsLevel, int]
    stream_distribution: Dict[StreamType, float]
    nep_competency_coverage: List[str]


@dataclass(frozen=True)
class RealismMetricsReport:
    target_paper_id: str
    section_layout_similarity: float
    marks_weight_similarity: float
    keywords_phrasing_similarity: float
    chronological_sequence_similarity: float
    overall_realism_index: float


@dataclass(frozen=True)
class SemanticTextbookChunk:
    chunk_id: str
    chapter_id: str
    concept_id: str
    text_content: str
    vector_embedding: List[float]
    competency_tags: List[str]


@dataclass(frozen=True)
class AcademicContextPacket:
    concept_id: str
    primary_chunk: SemanticTextbookChunk
    supporting_chunks: List[SemanticTextbookChunk]
    extracted_keywords: List[str]
    complexity_score: float


@dataclass
class PromptPackage:
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


@dataclass(frozen=True)
class InternalChoiceOption:
    option_a: QuestionInstance
    option_b: QuestionInstance
    section_id: str


@dataclass(frozen=True)
class CompiledPaperBlueprint:
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
    retrieval_targets: List[str]
    institution_policy: Optional[InstitutionPolicy] = None


@dataclass(frozen=True)
class AssembledPaperBooklet:
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
