"""
Academic Operating System (AOS) - Core Subject Infrastructure
================================================================================
Module: configs.cbse.science.science
Phase: 1 - Foundational Academic Engine
Description: A production-grade, highly typed, modular academic architecture
             for CBSE Science (Classes 6-10). This module establishes the
             base intelligence layer, governing conceptual progression, stream
             policies, marks depths, cognitive load taxonomies, exam structures,
             curriculum directories, multi-dimensional rubrics, and validation
             rules for high-fidelity question paper generation.
================================================================================
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Set, Tuple, Optional, Any, Union
import json
import math


# ==============================================================================
# 1. SUBJECT METADATA ENGINE
# ==============================================================================

class EducationBoard(Enum):
    """Supported national and state education boards."""
    CBSE = "Central Board of Secondary Education"
    ICSE = "Indian Certificate of Secondary Education"
    IB = "International Baccalaureate"
    STATE_BOARD = "State Secondary Education Board"


class SubjectCode(Enum):
    """Official academic subject codes."""
    SCIENCE_GENERAL = "086"  # CBSE Class 9 & 10 Science code
    SCIENCE_INTEGRATED = "SCI-INT"  # Class 6-8 Integrated Science


class AcademicClass(Enum):
    """Target classes supported by the curriculum foundation."""
    CLASS_6 = "Class 6"
    CLASS_7 = "Class 7"
    CLASS_8 = "Class 8"
    CLASS_9 = "Class 9"
    CLASS_10 = "Class 10"


class StreamMode(Enum):
    """Curriculum streaming configuration based on academic level."""
    INTEGRATED = "Integrated General Science (No formal stream boundaries)"
    HYBRID = "Hybrid General Science (Emergent stream grouping)"
    SPLIT = "Fully Split Science (Strict Physics, Chemistry, Biology boundaries)"


class CurriculumTier(Enum):
    """Pedagogical targeting levels for question calibration."""
    FOUNDATION = "Remedial and Core Literacy"
    STANDARD = "Core CBSE Board Curriculum Alignment"
    ADVANCED = "HOTS, Exemplar, and Analytical Enrichment"
    OLYMPIAD = "Competitive and High-Cognitive Reasoning"


@dataclass(frozen=True)
class BoardPolicy:
    """Defines strict constraints and rules governed by the target education board."""
    board: EducationBoard
    marking_scheme_type: str  # e.g., "Step-wise with keyword credit"
    grading_scale: List[str]
    allow_halves: bool  # Whether 0.5 marks are allowed
    competency_ratio_target: float  # Recommended percentage of competency questions (e.g., 0.50 for CBSE 2024+)
    practical_internal_marks: int


@dataclass(frozen=True)
class SubjectProfile:
    """Comprehensive academic profile for the subject."""
    subject_name: str
    subject_code: SubjectCode
    supported_classes: Set[AcademicClass]
    stream_mode_mapping: Dict[AcademicClass, StreamMode]
    board_policies: Dict[EducationBoard, BoardPolicy]


class SubjectMetadataEngine:
    """Orchestrates metadata definitions, resolving stream configurations and policies."""

    def __init__(self) -> None:
        # Standard CBSE Board Policy for Science (aligned with National Education Policy - NEP 2020)
        cbse_policy = BoardPolicy(
            board=EducationBoard.CBSE,
            marking_scheme_type="Rubric-based step-wise marking with descriptive keywords",
            grading_scale=["A1", "A2", "B1", "B2", "C1", "C2", "D", "E"],
            allow_halves=False,  # CBSE usually avoids fractional marks in individual questions
            competency_ratio_target=0.50,  # 50% competency-based questions mandated for Class 9/10
            practical_internal_marks=20
        )

        self._profile = SubjectProfile(
            subject_name="Science",
            subject_code=SubjectCode.SCIENCE_GENERAL,
            supported_classes={
                AcademicClass.CLASS_6,
                AcademicClass.CLASS_7,
                AcademicClass.CLASS_8,
                AcademicClass.CLASS_9,
                AcademicClass.CLASS_10
            },
            stream_mode_mapping={
                AcademicClass.CLASS_6: StreamMode.INTEGRATED,
                AcademicClass.CLASS_7: StreamMode.INTEGRATED,
                AcademicClass.CLASS_8: StreamMode.HYBRID,
                AcademicClass.CLASS_9: StreamMode.SPLIT,
                AcademicClass.CLASS_10: StreamMode.SPLIT
            },
            board_policies={
                EducationBoard.CBSE: cbse_policy
            }
        )

    def get_profile(self) -> SubjectProfile:
        """Retrieves the global subject profile."""
        return self._profile

    def get_stream_mode(self, academic_class: AcademicClass) -> StreamMode:
        """Returns the streaming policy mode for a specific class."""
        return self._profile.stream_mode_mapping.get(
            academic_class, StreamMode.INTEGRATED
        )

    def get_board_policy(self, board: EducationBoard) -> BoardPolicy:
        """Fetches board-specific structural policy constraints."""
        if board not in self._profile.board_policies:
            raise KeyError(f"Board policy for {board.name} is not initialized in this engine.")
        return self._profile.board_policies[board]

    def is_class_supported(self, academic_class: AcademicClass) -> bool:
        """Validates if the class exists in this subject infrastructure."""
        return academic_class in self._profile.supported_classes


# ==============================================================================
# 2. CLASS PROGRESSION ENGINE
# ==============================================================================

class ConceptualMaturityLevel(Enum):
    """Levels of cognitive schema maturation expected of students."""
    CONCRETE_OBSERVATIONAL = auto()   # Direct physical observation, sensory classification
    TRANSITIONAL_EMPIRICAL = auto()   # Identifying patterns, simple relational links, semi-guided inferences
    SYSTEMIC_ANALYTICAL = auto()      # Formulating laws, tracking dynamic variables, structural parsing
    ABSTRACT_QUALITATIVE = auto()     # Micro-macro modeling, non-observable frameworks (atoms, fields)
    RATIONAL_FORMAL = auto()          # Mathematical modeling, thermodynamic/quantum-mechanics proxies, absolute formal proofs


class ReasoningExpectation(Enum):
    """Expectation profiles for deductive, inductive, and structural thinking."""
    DIRECT_IDENTIFICATION = auto()    # Recall, pointing out, listing obvious components
    SINGLE_VARIABLE_CORRELATION = auto()  # "If A increases, B increases" (Direct proportionality)
    MULTI_FACTOR_CAUSAL_LINKS = auto()  # Isolating variables, tracing chain effects: A -> B -> C
    HYPOTHESIS_DEDUCTION = auto()     # Setting up hypothesis, predicting outcomes based on laws
    SYSTEMIC_SYNTHESIS = auto()       # Resolving conflicting variables, cross-disciplinary optimization


class NumericalComplexityLevel(Enum):
    """Numerical capability frameworks by class tier."""
    ARITHMETIC_BASIC = auto()         # Addition, subtraction, simple direct division (e.g., speed = distance/time)
    RATIO_CONVERSION = auto()         # Metric conversions, simple direct proportions, fractional weights
    ALGEBRAIC_SINGLE_STEP = auto()    # Isolating a single variable in linear formulas (e.g., F = ma, solve for a)
    ALGEBRAIC_MULTI_STEP = auto()     # Multi-step formulas, quadratic solutions, simultaneous equations
    GRAPHICAL_COMPUTATION = auto()    # Extracting numerical data from slopes, areas under curve, trig functions


@dataclass(frozen=True)
class ExpectedAnswerDepth:
    """Visual and text depth configurations for student responses."""
    min_word_count: int
    max_word_count: int
    bullet_points_preferred: bool
    requires_diagram_support: bool
    intermediate_steps_expected: int


@dataclass(frozen=True)
class ClassProgressionProfile:
    """Core progression criteria detailing class-specific academic maturity."""
    academic_class: AcademicClass
    maturity_level: ConceptualMaturityLevel
    reasoning_expectation: ReasoningExpectation
    numerical_complexity: NumericalComplexityLevel
    answer_depth_by_marks: Dict[int, ExpectedAnswerDepth]
    description: str


class ClassProgressionEngine:
    """Governs the evolution of cognitive, numerical, and reasoning demands across classes."""

    def __init__(self) -> None:
        self._progression_map: Dict[AcademicClass, ClassProgressionProfile] = {}
        self._initialize_profiles()

    def _initialize_profiles(self) -> None:
        # Configuration mapping marks to expected answer depths for Class 6
        depth_class_6 = {
            1: ExpectedAnswerDepth(5, 15, True, False, 0),
            2: ExpectedAnswerDepth(20, 35, True, False, 1),
            3: ExpectedAnswerDepth(40, 60, True, True, 2),
            5: ExpectedAnswerDepth(80, 120, True, True, 3)
        }

        # Configuration mapping marks to expected answer depths for Class 8
        depth_class_8 = {
            1: ExpectedAnswerDepth(10, 20, False, False, 0),
            2: ExpectedAnswerDepth(30, 50, True, False, 1),
            3: ExpectedAnswerDepth(50, 80, True, True, 2),
            5: ExpectedAnswerDepth(100, 150, True, True, 4)
        }

        # Configuration mapping marks to expected answer depths for Class 10 (Strict CBSE Layout)
        depth_class_10 = {
            1: ExpectedAnswerDepth(10, 25, False, False, 0),
            2: ExpectedAnswerDepth(30, 60, False, False, 2),
            3: ExpectedAnswerDepth(60, 100, True, True, 3),
            5: ExpectedAnswerDepth(120, 200, True, True, 5)
        }

        # Class 6 Progression Profile
        self._progression_map[AcademicClass.CLASS_6] = ClassProgressionProfile(
            academic_class=AcademicClass.CLASS_6,
            maturity_level=ConceptualMaturityLevel.CONCRETE_OBSERVATIONAL,
            reasoning_expectation=ReasoningExpectation.DIRECT_IDENTIFICATION,
            numerical_complexity=NumericalComplexityLevel.ARITHMETIC_BASIC,
            answer_depth_by_marks=depth_class_6,
            description="Focuses on tangible phenomena. Questions must rely on sensory experiences, simple "
                        "categorization (e.g., sorting materials), and direct physical descriptions. Avoid "
                        "microscopic models like molecular structures or abstract mathematical derivations."
        )

        # Class 7 Progression Profile
        self._progression_map[AcademicClass.CLASS_7] = ClassProgressionProfile(
            academic_class=AcademicClass.CLASS_7,
            maturity_level=ConceptualMaturityLevel.TRANSITIONAL_EMPIRICAL,
            reasoning_expectation=ReasoningExpectation.SINGLE_VARIABLE_CORRELATION,
            numerical_complexity=NumericalComplexityLevel.RATIO_CONVERSION,
            answer_depth_by_marks=depth_class_6,  # Reuses base sizing with marginal increases internally
            description="Students begin recognizing patterns and correlations (e.g., heat transfer rate vs. material "
                        "type). Inferences are mostly binary and direct. Numerical problems involve basic ratios "
                        "and single-stage metric conversions."
        )

        # Class 8 Progression Profile
        self._progression_map[AcademicClass.CLASS_8] = ClassProgressionProfile(
            academic_class=AcademicClass.CLASS_8,
            maturity_level=ConceptualMaturityLevel.TRANSITIONAL_EMPIRICAL,
            reasoning_expectation=ReasoningExpectation.MULTI_FACTOR_CAUSAL_LINKS,
            numerical_complexity=NumericalComplexityLevel.ALGEBRAIC_SINGLE_STEP,
            answer_depth_by_marks=depth_class_8,
            description="Acts as a gateway to secondary school abstractions. Introduces unobservable systems "
                        "(e.g., cells, microorganisms, force fields). Demands tracing simple linear causal pathways "
                        "and solving basic single-variable algebraic physics formulations."
        )

        # Class 9 Progression Profile
        self._progression_map[AcademicClass.CLASS_9] = ClassProgressionProfile(
            academic_class=AcademicClass.CLASS_9,
            maturity_level=ConceptualMaturityLevel.SYSTEMIC_ANALYTICAL,
            reasoning_expectation=ReasoningExpectation.HYPOTHESIS_DEDUCTION,
            numerical_complexity=NumericalComplexityLevel.ALGEBRAIC_MULTI_STEP,
            answer_depth_by_marks=depth_class_10,
            description="Deep systemic analysis begins. Formal physical laws are framed mathematically (e.g., equations "
                        "of motion, law of gravitation). Chemistry introduces abstract particulate frameworks (atoms, "
                        "molecules). Multi-step numericals, unit balancing, and experimental hypothesis testing are core."
        )

        # Class 10 Progression Profile
        self._progression_map[AcademicClass.CLASS_10] = ClassProgressionProfile(
            academic_class=AcademicClass.CLASS_10,
            maturity_level=ConceptualMaturityLevel.ABSTRACT_QUALITATIVE,
            reasoning_expectation=ReasoningExpectation.SYSTEMIC_SYNTHESIS,
            numerical_complexity=NumericalComplexityLevel.GRAPHICAL_COMPUTATION,
            answer_depth_by_marks=depth_class_10,
            description="Highly abstract, qualitative and quantitative scientific representation. Tracing complex "
                        "systemic interactions (e.g., metabolic pathways, electromagnetic induction). Expects synthesis "
                        "of concepts, graphical analysis, and algebraic precision aligned with CBSE Board standards."
        )

    def get_profile(self, academic_class: AcademicClass) -> ClassProgressionProfile:
        """Retrieves the development profile for the requested class."""
        if academic_class not in self._progression_map:
            raise ValueError(f"No progression mapping registered for {academic_class.name}")
        return self._progression_map[academic_class]

    def validate_progression_depth(self, academic_class: AcademicClass, marks: int, word_count: int) -> Tuple[bool, str]:
        """Validates if a target word count aligns with class-level maturity bounds."""
        profile = self.get_profile(academic_class)
        available_marks = sorted(profile.answer_depth_by_marks.keys())
        if not available_marks:
            return True, "No sizing constraints declared."
        
        target_marks = marks
        if target_marks not in profile.answer_depth_by_marks:
            target_marks = min(available_marks, key=lambda x: abs(x - marks))

        depth = profile.answer_depth_by_marks[target_marks]
        if word_count < depth.min_word_count:
            return False, f"Word count ({word_count}) is below class progression baseline ({depth.min_word_count}) for a {marks}-mark question in {academic_class.value}."
        if word_count > depth.max_word_count:
            return False, f"Word count ({word_count}) exceeds progressive cognitive ceiling ({depth.max_word_count}) for a {marks}-mark question in {academic_class.value}."
        
        return True, "Word count complies with progression architecture."


# ==============================================================================
# 3. STREAM FOUNDATION
# ==============================================================================

class StreamType(Enum):
    """Core sub-disciplines of Science."""
    PHYSICS = "Physics"
    CHEMISTRY = "Chemistry"
    BIOLOGY = "Biology"
    INTEGRATED = "Integrated General Science"


class CognitiveStyle(Enum):
    """The prevailing cognitive mode required for a scientific stream."""
    MATHEMATICAL_MODELING = auto()  # Rigorous quantitative formulations, spatial geometry
    MICRO_MACRO_MAPPING = auto()    # Translating molecular reactions to sensory observations
    SYSTEMIC_FUNCTIONAL = auto()    # Tracing anatomical structures, taxonomies, and metabolic flows
    PHENOMENOLOGICAL = auto()       # High-level observable relations (light, shadows, environment)


@dataclass(frozen=True)
class TheoryPracticalRatio:
    """The balance ratio of theoretical descriptions to practical application."""
    theory_percentage: float
    practical_percentage: float

    def __post_init__(self) -> None:
        if not math.isclose(self.theory_percentage + self.practical_percentage, 100.0, rel_tol=1e-5):
            raise ValueError("Theory and Practical percentages must sum exactly to 100.")


@dataclass(frozen=True)
class StreamProfile:
    """Core characteristics defining a scientific stream's nature."""
    stream_type: StreamType
    cognitive_style: CognitiveStyle
    preferred_question_types: List[str]  # Mapped via QuestionTypeCode
    diagram_frequency_coefficient: float  # Scale of 0.0 to 1.0
    numerical_weightage_coefficient: float  # Scale of 0.0 to 1.0
    theory_practical_ratio: TheoryPracticalRatio
    core_focus_description: str


class StreamFoundationEngine:
    """Enforces specific cognitive styles, diagram frequencies, and math metrics per stream."""

    def __init__(self) -> None:
        self._stream_profiles: Dict[StreamType, StreamProfile] = {}
        self._initialize_streams()

    def _initialize_streams(self) -> None:
        # Physics Stream Profile
        self._stream_profiles[StreamType.PHYSICS] = StreamProfile(
            stream_type=StreamType.PHYSICS,
            cognitive_style=CognitiveStyle.MATHEMATICAL_MODELING,
            preferred_question_types=["NUMERICAL", "DIAGRAM", "HOTS", "MCQ"],
            diagram_frequency_coefficient=0.75,
            numerical_weightage_coefficient=0.60,
            theory_practical_ratio=TheoryPracticalRatio(60.0, 40.0),
            core_focus_description="Governs motion, force, electricity, light, and energy. Demands dimensional analysis, "
                                    "vector notation, algebraic extraction of system values, and geometric optics."
        )

        # Chemistry Stream Profile
        self._stream_profiles[StreamType.CHEMISTRY] = StreamProfile(
            stream_type=StreamType.CHEMISTRY,
            cognitive_style=CognitiveStyle.MICRO_MACRO_MAPPING,
            preferred_question_types=["EXPERIMENTAL", "ASSERTION_REASON", "MCQ", "SHORT_ANSWER"],
            diagram_frequency_coefficient=0.45,
            numerical_weightage_coefficient=0.30,
            theory_practical_ratio=TheoryPracticalRatio(50.0, 50.0),
            core_focus_description="Governs properties of matter, chemical equations, acids/bases, metals, and carbon carbon rings. "
                                    "Demands tracking physical changes, balancing chemical pathways, and parsing lab observations."
        )

        # Biology Stream Profile
        self._stream_profiles[StreamType.BIOLOGY] = StreamProfile(
            stream_type=StreamType.BIOLOGY,
            cognitive_style=CognitiveStyle.SYSTEMIC_FUNCTIONAL,
            preferred_question_types=["DIAGRAM", "CASE_STUDY", "LONG_ANSWER", "COMPETENCY"],
            diagram_frequency_coefficient=0.90,
            numerical_weightage_coefficient=0.05,
            theory_practical_ratio=TheoryPracticalRatio(70.0, 30.0),
            core_focus_description="Governs life processes, cellular biology, genetic inheritance, ecosystems, and anatomy. "
                                    "Demands complex classification pathways, labeling accuracy, and structural reasoning."
        )

        # Integrated Science Stream Profile (Classes 6-7 General Science)
        self._stream_profiles[StreamType.INTEGRATED] = StreamProfile(
            stream_type=StreamType.INTEGRATED,
            cognitive_style=CognitiveStyle.PHENOMENOLOGICAL,
            preferred_question_types=["MCQ", "SHORT_ANSWER", "DIAGRAM"],
            diagram_frequency_coefficient=0.50,
            numerical_weightage_coefficient=0.15,
            theory_practical_ratio=TheoryPracticalRatio(80.0, 20.0),
            core_focus_description="Unified natural science framework combining primary aspects of nature, energy, plants, "
                                    "and water cycles. Designed to stimulate observational scientific curiosity."
        )

    def get_profile(self, stream_type: StreamType) -> StreamProfile:
        """Fetches the stream constraints template."""
        if stream_type not in self._stream_profiles:
            raise ValueError(f"Stream {stream_type.name} profile not cataloged.")
        return self._stream_profiles[stream_type]

    def get_recommended_stream(self, academic_class: AcademicClass, topic_hint: str) -> StreamType:
        """Determines the academic stream based on class levels and text triggers."""
        if academic_class in [AcademicClass.CLASS_6, AcademicClass.CLASS_7]:
            return StreamType.INTEGRATED

        normalized = topic_hint.lower()
        physics_triggers = ["force", "motion", "speed", "electricity", "circuit", "mirror", "lens", "refraction", "light", "watt", "ohm", "ampere", "magnetic"]
        chemistry_triggers = ["acid", "base", "salt", "reaction", "equation", "element", "metal", "non-metal", "carbon", "bond", "atom", "molecule", "solution"]
        biology_triggers = ["cell", "tissue", "organ", "plant", "animal", "reproduction", "digestive", "respiration", "heredity", "gene", "neuron", "brain", "ecosystem"]

        for trigger in physics_triggers:
            if trigger in normalized:
                return StreamType.PHYSICS
        for trigger in chemistry_triggers:
            if trigger in normalized:
                return StreamType.CHEMISTRY
        for trigger in biology_triggers:
            if trigger in normalized:
                return StreamType.BIOLOGY

        if academic_class == AcademicClass.CLASS_8:
            return StreamType.INTEGRATED

        return StreamType.PHYSICS


# ==============================================================================
# 4. QUESTION TYPE FOUNDATION
# ==============================================================================

class QuestionTypeCode(Enum):
    """Strict standard categorizations of question types."""
    MCQ = "Multiple Choice Question"
    ASSERTION_REASON = "Assertion & Reason"
    CASE_STUDY = "Case-Study / Passage-based"
    NUMERICAL = "Numerical Calculation"
    DIAGRAM = "Diagrammatic / Graphical Interpretation"
    EXPERIMENTAL = "Experimental Setup & Lab Procedure"
    HOTS = "Higher Order Thinking Skills"
    COMPETENCY = "Real-world Competency Evaluation"
    SHORT_ANSWER = "Short Answer (Descriptive)"
    LONG_ANSWER = "Long Answer (Comprehensive)"


@dataclass(frozen=True)
class RubricComponent:
    """Visual structural mapping of marks allocation."""
    component_name: str
    marks_allocated: int
    validation_rule_description: str


@dataclass(frozen=True)
class QuestionTypeProfile:
    """Defines strict templates and execution metadata for question types."""
    code: QuestionTypeCode
    base_marks_range: Tuple[int, int]
    target_blooms_levels: Set[str]  # Bloom's level labels
    minutes_per_mark_coefficient: float  # Estimated testing duration weight
    requires_stimulus_context: bool
    rubric_backbone: List[RubricComponent]
    description: str


class QuestionTypeRegistry:
    """Core validation and structural catalog for CBSE Science question classes."""

    def __init__(self) -> None:
        self._registry: Dict[QuestionTypeCode, QuestionTypeProfile] = {}
        self._initialize_registry()

    def _initialize_registry(self) -> None:
        # 1. MCQ Profile
        self._registry[QuestionTypeCode.MCQ] = QuestionTypeProfile(
            code=QuestionTypeCode.MCQ,
            base_marks_range=(1, 1),
            target_blooms_levels={"REMEMBER", "UNDERSTAND", "APPLY"},
            minutes_per_mark_coefficient=1.5,
            requires_stimulus_context=False,
            rubric_backbone=[
                RubricComponent("Correct Option Selection", 1, "Exactly match key with correct physical value")
            ],
            description="Single correct choice out of four options. Aligned to conceptual triggers or simple formulas."
        )

        # 2. Assertion & Reason Profile
        self._registry[QuestionTypeCode.ASSERTION_REASON] = QuestionTypeProfile(
            code=QuestionTypeCode.ASSERTION_REASON,
            base_marks_range=(1, 1),
            target_blooms_levels={"UNDERSTAND", "ANALYZE"},
            minutes_per_mark_coefficient=2.0,
            requires_stimulus_context=False,
            rubric_backbone=[
                RubricComponent("Logical Assessment & Code Selection", 1,
                                "Evaluate Truth value of Assertion and Reason independently, then check direct causal link.")
            ],
            description="Two-part statement testing causal linkages. Core CBSE Board standard item."
        )

        # 3. Case-Study Profile
        self._registry[QuestionTypeCode.CASE_STUDY] = QuestionTypeProfile(
            code=QuestionTypeCode.CASE_STUDY,
            base_marks_range=(4, 4),
            target_blooms_levels={"UNDERSTAND", "APPLY", "ANALYZE"},
            minutes_per_mark_coefficient=2.5,
            requires_stimulus_context=True,
            rubric_backbone=[
                RubricComponent("Part A (Direct Comprehension)", 1, "Verify comprehension of paragraph parameters"),
                RubricComponent("Part B (Analytical Correlation)", 1, "Cross-reference theory with reading data"),
                RubricComponent("Part C (Application/Reasoning)", 2, "Apply core science laws to the stated clinical/real-world context")
            ],
            description="A comprehensive case profile (textual/tabular/diagrammatic) followed by sub-questions."
        )

        # 4. Numerical Profile
        self._registry[QuestionTypeCode.NUMERICAL] = QuestionTypeProfile(
            code=QuestionTypeCode.NUMERICAL,
            base_marks_range=(2, 5),
            target_blooms_levels={"APPLY", "ANALYZE"},
            minutes_per_mark_coefficient=2.2,
            requires_stimulus_context=False,
            rubric_backbone=[
                RubricComponent("Given Listing & Formula Stating", 1, "State correct values with SI units and standard math formula"),
                RubricComponent("Calculation Steps", 1, "Show clean intermediate algebraic transformations"),
                RubricComponent("Final Answer with SI Unit", 1, "Final correct scalar with exact units (mandatory)")
            ],
            description="Mathematical calculations requiring structured steps, SI units, and formula listing."
        )

        # 5. Diagram-based Profile
        self._registry[QuestionTypeCode.DIAGRAM] = QuestionTypeProfile(
            code=QuestionTypeCode.DIAGRAM,
            base_marks_range=(2, 5),
            target_blooms_levels={"REMEMBER", "UNDERSTAND", "APPLY", "ANALYZE"},
            minutes_per_mark_coefficient=2.0,
            requires_stimulus_context=True,
            rubric_backbone=[
                RubricComponent("Drafting/Accuracy", 1, "Correct geometric placement of lines, paths, or labels"),
                RubricComponent("Labeling", 1, "Naming critical parts accurately"),
                RubricComponent("Conceptual Explanation", 1, "Relating the diagram parts to physiological/physical functions")
            ],
            description="Questions requiring creation, labeling, modification, or analytical reading of visual schemas."
        )

        # 6. Experimental / Lab Profile
        self._registry[QuestionTypeCode.EXPERIMENTAL] = QuestionTypeProfile(
            code=QuestionTypeCode.EXPERIMENTAL,
            base_marks_range=(2, 4),
            target_blooms_levels={"APPLY", "ANALYZE", "EVALUATE"},
            requires_stimulus_context=True,
            minutes_per_mark_coefficient=2.2,
            rubric_backbone=[
                RubricComponent("Apparatus Alignment", 1, "Specify correct setups and chemical reagents"),
                RubricComponent("Observation Mapping", 1, "State visual, thermal, or gas-evolution changes"),
                RubricComponent("Conclusion/Safety Core", 1, "Scientific inference aligned to experimental controls")
            ],
            description="Rooted in core board practicals. Tests procedures, precautions, indicators, and observations."
        )

        # 7. HOTS Profile
        self._registry[QuestionTypeCode.HOTS] = QuestionTypeProfile(
            code=QuestionTypeCode.HOTS,
            base_marks_range=(3, 5),
            target_blooms_levels={"ANALYZE", "EVALUATE", "CREATE"},
            minutes_per_mark_coefficient=2.5,
            requires_stimulus_context=True,
            rubric_backbone=[
                RubricComponent("Hypothesis Formulation", 1, "Define anomalous physics/chemistry behavior"),
                RubricComponent("Causal Link Chains", 2, "Construct logical arguments avoiding standard linear recall templates"),
                RubricComponent("Synthesized Resolution", 1, "Propose testable solutions or structural equations")
            ],
            description="Higher Order Thinking Skills. Requires transfer of principles to novel, non-textbook paradigms."
        )

        # 8. Competency-based Profile
        self._registry[QuestionTypeCode.COMPETENCY] = QuestionTypeProfile(
            code=QuestionTypeCode.COMPETENCY,
            base_marks_range=(2, 5),
            target_blooms_levels={"APPLY", "ANALYZE", "EVALUATE"},
            minutes_per_mark_coefficient=2.4,
            requires_stimulus_context=True,
            rubric_backbone=[
                RubricComponent("Real-world Parameter Isolation", 1, "Convert everyday variables into standard physics/chemistry units"),
                RubricComponent("Application of Science Model", 2, "Map biological processes or mechanics to solve daily issues"),
                RubricComponent("Critical Evaluation", 1, "Justify solutions using empirical indicators")
            ],
            description="NEP aligned competency questions. Evaluates utility of science outside the bounds of memory."
        )

        # 9. Short Answer Profile
        self._registry[QuestionTypeCode.SHORT_ANSWER] = QuestionTypeProfile(
            code=QuestionTypeCode.SHORT_ANSWER,
            base_marks_range=(2, 3),
            target_blooms_levels={"REMEMBER", "UNDERSTAND", "APPLY"},
            minutes_per_mark_coefficient=2.0,
            requires_stimulus_context=False,
            rubric_backbone=[
                RubricComponent("Core Concept Statement", 1, "State defining physical/chemical rules"),
                RubricComponent("Elaboration/Example", 1, "Provide corroborating details or equation examples")
            ],
            description="Classic SA-I and SA-II items. Focused on explaining mechanisms and contrasting phenomena."
        )

        # 10. Long Answer Profile
        self._registry[QuestionTypeCode.LONG_ANSWER] = QuestionTypeProfile(
            code=QuestionTypeCode.LONG_ANSWER,
            base_marks_range=(5, 5),
            target_blooms_levels={"UNDERSTAND", "APPLY", "ANALYZE", "EVALUATE"},
            minutes_per_mark_coefficient=2.0,
            requires_stimulus_context=False,
            rubric_backbone=[
                RubricComponent("Part-wise Structured Answers", 2, "Address sub-parts (a, b, c) of the multi-tiered question"),
                RubricComponent("Technical Vocabulary & Keywords", 2, "Must contain standard physiological, chemical, or physics terms"),
                RubricComponent("Supporting Diagrams/Equations", 1, "Provide visual proofs or balanced chemical balance structures")
            ],
            description="5-mark high-depth questions. Almost always split into sub-questions (e.g., 3 + 2 marks) in CBSE."
        )

    def get_profile(self, code: QuestionTypeCode) -> QuestionTypeProfile:
        """Retrieves profile configuration for the requested question code."""
        if code not in self._registry:
            raise KeyError(f"Question code {code.name} is not registered.")
        return self._registry[code]

    def validate_marks_range(self, code: QuestionTypeCode, marks: int) -> bool:
        """Validates if the target marks fall within standard academic guidelines for the type."""
        profile = self.get_profile(code)
        low, high = profile.base_marks_range
        return low <= marks <= high


# ==============================================================================
# 5. MARKS DEPTH ENGINE
# ==============================================================================

@dataclass(frozen=True)
class MarksDepthProfile:
    """Strict evaluation criteria mapping specific marks to grading rules."""
    marks_value: int
    cognitive_load_index: float  # Scale of 0.0 to 1.0
    minimum_reasoning_steps: int  # Required logical links in proof/derivation
    word_count_boundaries: Tuple[int, int]
    rubric_credit_allocation: str
    expected_competency_depth: str


class MarksDepthEngine:
    """Dictates the structural and grading expectations based purely on assigned question marks."""

    def __init__(self) -> None:
        self._depth_profiles: Dict[int, MarksDepthProfile] = {}
        self._initialize_marks_depths()

    def _initialize_marks_depths(self) -> None:
        # 1-Mark Question Depth
        self._depth_profiles[1] = MarksDepthProfile(
            marks_value=1,
            cognitive_load_index=0.15,
            minimum_reasoning_steps=1,
            word_count_boundaries=(5, 30),
            rubric_credit_allocation="Binary credit: 1 mark for correct selection/fact, 0 for incorrect. No halves.",
            expected_competency_depth="Retrieval or direct empirical identification."
        )

        # 2-Mark Question Depth
        self._depth_profiles[2] = MarksDepthProfile(
            marks_value=2,
            cognitive_load_index=0.35,
            minimum_reasoning_steps=2,
            word_count_boundaries=(30, 60),
            rubric_credit_allocation="1 mark for core definition/law, 1 mark for example, balanced equation, or unit.",
            expected_competency_depth="Low-level conceptual translation or direct explanation."
        )

        # 3-Mark Question Depth
        self._depth_profiles[3] = MarksDepthProfile(
            marks_value=3,
            cognitive_load_index=0.60,
            minimum_reasoning_steps=3,
            word_count_boundaries=(50, 100),
            rubric_credit_allocation="1 mark for principle, 1 mark for logical steps/diagram, 1 mark for conclusion/units.",
            expected_competency_depth="Multifactor causation, tracing physical changes or system operations."
        )

        # 4-Mark Question Depth
        self._depth_profiles[4] = MarksDepthProfile(
            marks_value=4,
            cognitive_load_index=0.75,
            minimum_reasoning_steps=4,
            word_count_boundaries=(80, 150),
            rubric_credit_allocation="Multi-tier credit: split clearly into sub-parts of 1 + 1 + 2 marks or 2 + 2 marks.",
            expected_competency_depth="Hypothesis testing, dataset analysis, and translating paragraphs to mathematical systems."
        )

        # 5-Mark Question Depth
        self._depth_profiles[5] = MarksDepthProfile(
            marks_value=5,
            cognitive_load_index=0.90,
            minimum_reasoning_steps=5,
            word_count_boundaries=(120, 250),
            rubric_credit_allocation="Highly structured step grading: 1 mark for conceptual setup, 2 marks for derivation/calculations "
                                    "or anatomical details, 1 mark for fully labeled schematic, 1 mark for final units/synthesis.",
            expected_competency_depth="Cross-disciplinary synthesis, analytical defense of theories, and advanced modeling."
        )

    def get_profile(self, marks: int) -> MarksDepthProfile:
        """Fetches the strict profile based on marks."""
        if marks not in self._depth_profiles:
            raise ValueError(f"Marks level {marks} not cataloged in depth profiles.")
        return self._depth_profiles[marks]

    def estimate_completion_time(self, marks: int, question_type: QuestionTypeCode) -> float:
        """Estimates target execution time in minutes for a student based on marks and question type."""
        base_time = marks * 1.8
        registry = QuestionTypeRegistry()
        try:
            profile = registry.get_profile(question_type)
            coef = profile.minutes_per_mark_coefficient
            return round(base_time * coef, 1)
        except Exception:
            return round(base_time, 1)


# ==============================================================================
# 6. BLOOM'S TAXONOMY ENGINE
# ==============================================================================

class BloomsLevel(Enum):
    """The six standard levels of cognitive domain taxonomy (Revised Bloom's)."""
    REMEMBER = "Recall of core facts, terminology, and standard formulas"
    UNDERSTAND = "Grasping meaning, translating mechanisms, and explaining systems"
    APPLY = "Using rules, laws, and mathematical equations in concrete scenarios"
    ANALYZE = "Breaking systems into parts, isolating variables, and detecting bias"
    EVALUATE = "Critiquing evidence, verifying methodologies, and judging arguments"
    CREATE = "Formulating novel hypotheses, structuring new procedures, and synthesizing designs"


@dataclass(frozen=True)
class BloomsVerb:
    """Scientific cognitive verbs aligned to CBSE standard assessments."""
    verb: str
    target_stream_contexts: Set[StreamType]
    sample_phrase_template: str


@dataclass(frozen=True)
class BloomsTaxonomyProfile:
    """Taxonomical constraints and characteristics governing a Bloom's tier."""
    level: BloomsLevel
    cognitive_weight_index: float  # Scale of 1.0 to 6.0
    action_verbs: List[BloomsVerb]
    difficulty_coefficient_range: Tuple[float, float]
    description: str


class BloomsTaxonomyEngine:
    """Manages cognitive demands, action verb bindings, and difficulty calibrations."""

    def __init__(self) -> None:
        self._taxonomy_profiles: Dict[BloomsLevel, BloomsTaxonomyProfile] = {}
        self._initialize_taxonomy()

    def _initialize_taxonomy(self) -> None:
        # 1. REMEMBER
        self._taxonomy_profiles[BloomsLevel.REMEMBER] = BloomsTaxonomyProfile(
            level=BloomsLevel.REMEMBER,
            cognitive_weight_index=1.0,
            action_verbs=[
                BloomsVerb("State", {StreamType.PHYSICS, StreamType.CHEMISTRY}, "State Ohm's law."),
                BloomsVerb("Define", {StreamType.BIOLOGY, StreamType.INTEGRATED}, "Define photosynthesis."),
                BloomsVerb("Label", {StreamType.BIOLOGY}, "Label the parts of the human heart in the given diagram.")
            ],
            difficulty_coefficient_range=(0.1, 0.4),
            description="Testing memory retrieval. Simplest cognitive layer. Limited to direct curriculum statements."
        )

        # 2. UNDERSTAND
        self._taxonomy_profiles[BloomsLevel.UNDERSTAND] = BloomsTaxonomyProfile(
            level=BloomsLevel.UNDERSTAND,
            cognitive_weight_index=2.0,
            action_verbs=[
                BloomsVerb("Explain", {StreamType.PHYSICS, StreamType.BIOLOGY}, "Explain the mechanism of transport of water in plants."),
                BloomsVerb("Differentiate", {StreamType.CHEMISTRY, StreamType.BIOLOGY}, "Differentiate between metals and non-metals based on physical properties."),
                BloomsVerb("Illustrate", {StreamType.PHYSICS}, "Illustrate the formation of a real image by a concave mirror.")
            ],
            difficulty_coefficient_range=(0.3, 0.6),
            description="Testing comprehension. Expects students to re-phrase core processes without memorization."
        )

        # 3. APPLY
        self._taxonomy_profiles[BloomsLevel.APPLY] = BloomsTaxonomyProfile(
            level=BloomsLevel.APPLY,
            cognitive_weight_index=3.5,
            action_verbs=[
                BloomsVerb("Calculate", {StreamType.PHYSICS, StreamType.CHEMISTRY}, "Calculate the refractive index of glass with respect to air."),
                BloomsVerb("Balance", {StreamType.CHEMISTRY}, "Balance the following chemical reaction: Fe + H2O -> Fe3O4 + H2."),
                BloomsVerb("Predict", {StreamType.BIOLOGY, StreamType.PHYSICS}, "Predict the phenotype of the F2 generation in a monohybrid cross.")
            ],
            difficulty_coefficient_range=(0.5, 0.8),
            description="Testing operational capacity. Requires selecting correct laws/equations for new datasets."
        )

        # 4. ANALYZE
        self._taxonomy_profiles[BloomsLevel.ANALYZE] = BloomsTaxonomyProfile(
            level=BloomsLevel.ANALYZE,
            cognitive_weight_index=4.8,
            action_verbs=[
                BloomsVerb("Isolate", {StreamType.PHYSICS}, "Isolate the experimental variables that cause changes in resistance."),
                BloomsVerb("Deduce", {StreamType.CHEMISTRY, StreamType.BIOLOGY}, "Deduce the nature of compound X based on its reaction with sodium bicarbonate."),
                BloomsVerb("Compare", {StreamType.INTEGRATED}, "Compare the efficiency of different soil types in water retention.")
            ],
            difficulty_coefficient_range=(0.6, 0.9),
            description="Deconstructing components. Requires determining how pieces fit to form a macro system."
        )

        # 5. EVALUATE
        self._taxonomy_profiles[BloomsLevel.EVALUATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.EVALUATE,
            cognitive_weight_index=5.5,
            action_verbs=[
                BloomsVerb("Justify", {StreamType.BIOLOGY, StreamType.PHYSICS}, "Justify why parallel circuits are preferred over series configurations in domestic wiring."),
                BloomsVerb("Critique", {StreamType.CHEMISTRY}, "Critique the validity of Mendeleev's periodic classification vs the Modern periodic layout."),
                BloomsVerb("Assess", {StreamType.INTEGRATED}, "Assess the environmental impacts of plastic accumulation in water bodies.")
            ],
            difficulty_coefficient_range=(0.7, 0.95),
            description="Judging validity. Demands assessing systems using criteria, testing methods, or safety protocols."
        )

        # 6. CREATE
        self._taxonomy_profiles[BloomsLevel.CREATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.CREATE,
            cognitive_weight_index=6.0,
            action_verbs=[
                BloomsVerb("Design", {StreamType.PHYSICS, StreamType.CHEMISTRY}, "Design an experimental protocol to isolate pure oxygen from air."),
                BloomsVerb("Formulate", {StreamType.BIOLOGY}, "Formulate a biological defense system utilizing selective breeding methods."),
                BloomsVerb("Synthesize", {StreamType.CHEMISTRY}, "Synthesize a visual framework mapping carbon hydrocarbon chains to chemical properties.")
            ],
            difficulty_coefficient_range=(0.8, 1.0),
            description="Synthesizing new schema. Proposing research designs or modeling unified theory systems."
        )

    def get_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        """Fetches the taxonomy constraints block."""
        if level not in self._taxonomy_profiles:
            raise KeyError(f"Bloom's level {level.name} is not registered.")
        return self._taxonomy_profiles[level]

    def verify_action_verb(self, level: BloomsLevel, verb: str) -> bool:
        """Checks if a testing verb is grammatically bound to the target Bloom's cognitive layer."""
        profile = self.get_profile(level)
        return any(v.verb.lower() == verb.lower() for v in profile.action_verbs)


# ==============================================================================
# 7. EXAM TYPE ENGINE
# ==============================================================================

class ExamType(Enum):
    """Supported assessment frameworks."""
    UNIT_TEST = "Unit Test (Topic-specific diagnostic)"
    PERIODIC_TEST = "Periodic Assessment (Short term milestone)"
    MIDTERM = "Midterm Examination (Comprehensive half-yearly)"
    FINAL = "Annual Board-style Examination"
    REVISION_PAPER = "Targeted Review Framework"
    COMPETENCY_ASSESSMENT = "Skill-specific Application Audit"


@dataclass(frozen=True)
class SectionBlueprint:
    """Blueprint constraints governing individual question paper sections."""
    section_id: str
    question_type: QuestionTypeCode
    question_count: int
    marks_per_question: int
    internal_choice_count: int

    def get_total_marks(self) -> int:
        """Calculates the sum weight of this section."""
        return self.question_count * self.marks_per_question


@dataclass(frozen=True)
class ExamBlueprint:
    """Master layout specifications defining exam structures, times, and streams."""
    exam_type: ExamType
    academic_class: AcademicClass
    duration_minutes: int
    total_marks: int
    sections: List[SectionBlueprint]
    bloom_distribution_target: Dict[BloomsLevel, float]
    stream_distribution_target: Dict[StreamType, float]
    difficulty_target: Dict[str, float]


class ExamBlueprintRegistry:
    """Factory containing master structures conforming strictly to modern CBSE layouts."""

    def __init__(self) -> None:
        self._blueprints: Dict[Tuple[ExamType, AcademicClass], ExamBlueprint] = {}
        self._initialize_blueprints()

    def _initialize_blueprints(self) -> None:
        # Class 10 CBSE Science Board Exam Blueprint (Strict 80-Mark Structure)
        sections_class_10_final = [
            SectionBlueprint("A", QuestionTypeCode.MCQ, 20, 1, 0),
            SectionBlueprint("B", QuestionTypeCode.SHORT_ANSWER, 6, 2, 2),
            SectionBlueprint("C", QuestionTypeCode.SHORT_ANSWER, 7, 3, 2),
            SectionBlueprint("D", QuestionTypeCode.LONG_ANSWER, 3, 5, 3),
            SectionBlueprint("E", QuestionTypeCode.CASE_STUDY, 3, 4, 1)
        ]

        stream_target_class_10 = {
            StreamType.PHYSICS: 0.33,
            StreamType.CHEMISTRY: 0.33,
            StreamType.BIOLOGY: 0.34
        }

        bloom_target_class_10 = {
            BloomsLevel.REMEMBER: 0.20,
            BloomsLevel.UNDERSTAND: 0.40,
            BloomsLevel.APPLY: 0.20,
            BloomsLevel.ANALYZE: 0.10,
            BloomsLevel.EVALUATE: 0.08,
            BloomsLevel.CREATE: 0.02
        }

        difficulty_target_class_10 = {
            "EASY": 0.30,
            "AVERAGE": 0.50,
            "DIFFICULT": 0.20
        }

        self._blueprints[(ExamType.FINAL, AcademicClass.CLASS_10)] = ExamBlueprint(
            exam_type=ExamType.FINAL,
            academic_class=AcademicClass.CLASS_10,
            duration_minutes=180,
            total_marks=80,
            sections=sections_class_10_final,
            bloom_distribution_target=bloom_target_class_10,
            stream_distribution_target=stream_target_class_10,
            difficulty_target=difficulty_target_class_10
        )

        # Class 8 Science Midterm Blueprint (Integrated/Hybrid 50-Mark Structure)
        sections_class_8_midterm = [
            SectionBlueprint("A", QuestionTypeCode.MCQ, 10, 1, 0),
            SectionBlueprint("B", QuestionTypeCode.SHORT_ANSWER, 5, 2, 1),
            SectionBlueprint("C", QuestionTypeCode.SHORT_ANSWER, 6, 3, 1),
            SectionBlueprint("D", QuestionTypeCode.LONG_ANSWER, 2, 5, 1)
        ]

        stream_target_class_8 = {
            StreamType.PHYSICS: 0.30,
            StreamType.CHEMISTRY: 0.30,
            StreamType.BIOLOGY: 0.30,
            StreamType.INTEGRATED: 0.10
        }

        bloom_target_class_8 = {
            BloomsLevel.REMEMBER: 0.35,
            BloomsLevel.UNDERSTAND: 0.45,
            BloomsLevel.APPLY: 0.15,
            BloomsLevel.ANALYZE: 0.05,
            BloomsLevel.EVALUATE: 0.0,
            BloomsLevel.CREATE: 0.0
        }

        difficulty_target_class_8 = {
            "EASY": 0.40,
            "AVERAGE": 0.50,
            "DIFFICULT": 0.10
        }

        self._blueprints[(ExamType.MIDTERM, AcademicClass.CLASS_8)] = ExamBlueprint(
            exam_type=ExamType.MIDTERM,
            academic_class=AcademicClass.CLASS_8,
            duration_minutes=120,
            total_marks=50,
            sections=sections_class_8_midterm,
            bloom_distribution_target=bloom_target_class_8,
            stream_distribution_target=stream_target_class_8,
            difficulty_target=difficulty_target_class_8
        )

        # Class 6 Science Unit Test Blueprint (Concrete 20-Mark Structure)
        sections_class_6_ut = [
            SectionBlueprint("A", QuestionTypeCode.MCQ, 5, 1, 0),
            SectionBlueprint("B", QuestionTypeCode.SHORT_ANSWER, 3, 2, 0),
            SectionBlueprint("C", QuestionTypeCode.SHORT_ANSWER, 3, 3, 1)
        ]

        stream_target_class_6 = {
            StreamType.INTEGRATED: 1.0
        }

        bloom_target_class_6 = {
            BloomsLevel.REMEMBER: 0.50,
            BloomsLevel.UNDERSTAND: 0.40,
            BloomsLevel.APPLY: 0.10,
            BloomsLevel.ANALYZE: 0.0,
            BloomsLevel.EVALUATE: 0.0,
            BloomsLevel.CREATE: 0.0
        }

        difficulty_target_class_6 = {
            "EASY": 0.50,
            "AVERAGE": 0.40,
            "DIFFICULT": 0.10
        }

        self._blueprints[(ExamType.UNIT_TEST, AcademicClass.CLASS_6)] = ExamBlueprint(
            exam_type=ExamType.UNIT_TEST,
            academic_class=AcademicClass.CLASS_6,
            duration_minutes=45,
            total_marks=20,
            sections=sections_class_6_ut,
            bloom_distribution_target=bloom_target_class_6,
            stream_distribution_target=stream_target_class_6,
            difficulty_target=difficulty_target_class_6
        )

    def get_blueprint(self, exam_type: ExamType, academic_class: AcademicClass) -> ExamBlueprint:
        """Retrieves default exam blueprint or raises exception if config doesn't exist."""
        key = (exam_type, academic_class)
        if key not in self._blueprints:
            raise KeyError(f"No registered blueprint config for {exam_type.value} in {academic_class.value}")
        return self._blueprints[key]

    def register_custom_blueprint(self, blueprint: ExamBlueprint) -> None:
        """Allows real-time injection of external structural layouts."""
        key = (blueprint.exam_type, blueprint.academic_class)
        self._blueprints[key] = blueprint


# ==============================================================================
# 9. CURRICULUM DIRECTORY ENGINE
# ==============================================================================

@dataclass(frozen=True)
class LearningObjective:
    """Granular educational objective mapped to academic benchmarks."""
    objective_code: str
    statement: str
    target_blooms: BloomsLevel


@dataclass(frozen=True)
class ChapterProfile:
    """Comprehensive academic description of an individual curriculum chapter."""
    chapter_number: int
    chapter_name: str
    stream: StreamType
    academic_class: AcademicClass
    base_weightage_percentage: float
    conceptual_keywords: List[str]
    learning_objectives: List[LearningObjective]
    contains_practical_experiments: bool
    description: str


class CurriculumDirectoryEngine:
    """Acts as the authoritative directory of all CBSE Science chapters, topics, and learning criteria."""

    def __init__(self) -> None:
        self._chapters: Dict[AcademicClass, List[ChapterProfile]] = {}
        self._initialize_curriculum()

    def _initialize_curriculum(self) -> None:
        # --- CLASS 6 CURRICULUM ---
        self._chapters[AcademicClass.CLASS_6] = [
            ChapterProfile(
                chapter_number=1,
                chapter_name="Components of Food",
                stream=StreamType.INTEGRATED,
                academic_class=AcademicClass.CLASS_6,
                base_weightage_percentage=10.0,
                conceptual_keywords=["proteins", "carbohydrates", "fats", "vitamins", "minerals", "roughage", "balanced diet", "deficiency"],
                learning_objectives=[
                    LearningObjective("L6.1.1", "Identify dietary sources of major nutrients", BloomsLevel.REMEMBER),
                    LearningObjective("L6.1.2", "Demonstrate testing for starch, protein, and fats in foodstuffs", BloomsLevel.APPLY),
                    LearningObjective("L6.1.3", "Analyze visual indicators of nutritional deficiencies", BloomsLevel.ANALYZE)
                ],
                contains_practical_experiments=True,
                description="Study of nutrients, balanced dietary formulation, biological indicators, and deficiency pathologies."
            ),
            ChapterProfile(
                chapter_number=2,
                chapter_name="Sorting Materials into Groups",
                stream=StreamType.INTEGRATED,
                academic_class=AcademicClass.CLASS_6,
                base_weightage_percentage=8.0,
                conceptual_keywords=["lustre", "roughness", "solubility", "density", "transparency", "conduction", "floatation"],
                learning_objectives=[
                    LearningObjective("L6.2.1", "Classify common substances by lustre and solubility criteria", BloomsLevel.UNDERSTAND),
                    LearningObjective("L6.2.2", "Conduct floatation and solubility screening diagnostics", BloomsLevel.APPLY)
                ],
                contains_practical_experiments=True,
                description="Empirical classification based on tangible physical properties (lustre, solubility, density, transparency)."
            ),
            ChapterProfile(
                chapter_number=3,
                chapter_name="Separation of Substances",
                stream=StreamType.INTEGRATED,
                academic_class=AcademicClass.CLASS_6,
                base_weightage_percentage=12.0,
                conceptual_keywords=["winnowing", "sieving", "sedimentation", "decantation", "filtration", "evaporation", "condensation", "saturation"],
                learning_objectives=[
                    LearningObjective("L6.3.1", "Explain separation techniques based on particulate sizing differences", BloomsLevel.UNDERSTAND),
                    LearningObjective("L6.3.2", "Execute multi-stage separation strategies for heterogeneous mixtures", BloomsLevel.APPLY)
                ],
                contains_practical_experiments=True,
                description="Study of physical segregation of particulate systems, solutions, solubility, and phase change separations."
            ),
            ChapterProfile(
                chapter_number=4,
                chapter_name="Getting to Know Plants",
                stream=StreamType.INTEGRATED,
                academic_class=AcademicClass.CLASS_6,
                base_weightage_percentage=15.0,
                conceptual_keywords=["herbs", "shrubs", "trees", "roots", "taproot", "fibrous root", "venation", "transpiration", "pistil", "stamen"],
                learning_objectives=[
                    LearningObjective("L6.4.1", "Differentiate between venation layout configurations in angiosperms", BloomsLevel.UNDERSTAND),
                    LearningObjective("L6.4.2", "Sketch anatomical layouts of common flower systems with accurate organ labels", BloomsLevel.APPLY)
                ],
                contains_practical_experiments=True,
                description="Introduction to plant morphology, vascular pathways, transpiration, and structural reproductive systems."
            ),
            ChapterProfile(
                chapter_number=5,
                chapter_name="Electricity and Circuits",
                stream=StreamType.INTEGRATED,
                academic_class=AcademicClass.CLASS_6,
                base_weightage_percentage=15.0,
                conceptual_keywords=["cell", "filament", "terminal", "switch", "conductor", "insulator", "closed circuit"],
                learning_objectives=[
                    LearningObjective("L6.5.1", "Trace paths of electric charge flows in single-source circuits", BloomsLevel.UNDERSTAND),
                    LearningObjective("L6.5.2", "Construct operational switches using household conduction proxies", BloomsLevel.APPLY)
                ],
                contains_practical_experiments=True,
                description="Elementary circuitry, switches, conduction testing, safety protocols, and load paths."
            )
        ]

        # --- CLASS 8 CURRICULUM ---
        self._chapters[AcademicClass.CLASS_8] = [
            ChapterProfile(
                chapter_number=1,
                chapter_name="Crop Production and Management",
                stream=StreamType.BIOLOGY,
                academic_class=AcademicClass.CLASS_8,
                base_weightage_percentage=12.0,
                conceptual_keywords=["kharif", "rabi", "ploughing", "irrigation", "drip system", "weedicides", "silos", "nitrogen fixation"],
                learning_objectives=[
                    LearningObjective("L8.1.1", "Differentiate agrarian crop cycles based on climatic intervals", BloomsLevel.UNDERSTAND),
                    LearningObjective("L8.1.2", "Evaluate modern irrigation architectures against dry soil criteria", BloomsLevel.ANALYZE)
                ],
                contains_practical_experiments=False,
                description="Agrarian methods, mechanical technologies, pest containment, crop rotations, and soil science."
            ),
            ChapterProfile(
                chapter_number=2,
                chapter_name="Cell - Structure and Functions",
                stream=StreamType.BIOLOGY,
                academic_class=AcademicClass.CLASS_8,
                base_weightage_percentage=18.0,
                conceptual_keywords=["membrane", "cytoplasm", "nucleus", "organelles", "mitochondria", "plastids", "vacuoles", "prokaryote", "eukaryote"],
                learning_objectives=[
                    LearningObjective("L8.2.1", "Compare structural envelopes of animal and plant cellular systems", BloomsLevel.UNDERSTAND),
                    LearningObjective("L8.2.2", "State the functional assignments of vacuoles and chloroplasts", BloomsLevel.REMEMBER),
                    LearningObjective("L8.2.3", "Analyze anatomical differences between eukaryotic and prokaryotic cells", BloomsLevel.ANALYZE)
                ],
                contains_practical_experiments=True,
                description="Cytology foundation, membrane physiology, genetic compartmentalization, and comparative cellular structures."
            ),
            ChapterProfile(
                chapter_number=3,
                chapter_name="Force and Pressure",
                stream=StreamType.PHYSICS,
                academic_class=AcademicClass.CLASS_8,
                base_weightage_percentage=20.0,
                conceptual_keywords=["contact force", "electrostatic force", "gravity", "pascal", "atmospheric pressure", "hydraulic", "area"],
                learning_objectives=[
                    LearningObjective("L8.3.1", "Calculate mechanical pressure variations resulting from alterations in contact surfaces", BloomsLevel.APPLY),
                    LearningObjective("L8.3.2", "Demonstrate hydrostatic pressure depth-dependence using liquid vessels", BloomsLevel.APPLY)
                ],
                contains_practical_experiments=True,
                description="Vector interaction forces, pressure scaling, non-contact fields, and fluid dynamics introduction."
            )
        ]

        # --- CLASS 10 CURRICULUM ---
        self._chapters[AcademicClass.CLASS_10] = [
            ChapterProfile(
                chapter_number=1,
                chapter_name="Chemical Reactions and Equations",
                stream=StreamType.CHEMISTRY,
                academic_class=AcademicClass.CLASS_10,
                base_weightage_percentage=15.0,
                conceptual_keywords=["stoichiometry", "exothermic", "endothermic", "displacement", "redox", "oxidation", "precipitate", "catalyst"],
                learning_objectives=[
                    LearningObjective("L10.1.1", "Balance complex chemical reaction equations via stoichiometric adjustments", BloomsLevel.APPLY),
                    LearningObjective("L10.1.2", "Identify oxidizing and reducing agents in given redox reactions", BloomsLevel.ANALYZE),
                    LearningObjective("L10.1.3", "Predict precipitate formation based on salt dissociation parameters", BloomsLevel.ANALYZE)
                ],
                contains_practical_experiments=True,
                description="Quantitative chemical reactions, stoichiometric equations, thermal shifts, redox, and kinetic reaction classes."
            ),
            ChapterProfile(
                chapter_number=2,
                chapter_name="Acids, Bases and Salts",
                stream=StreamType.CHEMISTRY,
                academic_class=AcademicClass.CLASS_10,
                base_weightage_percentage=15.0,
                conceptual_keywords=["hydronium", "alkali", "pH indicator", "chlor-alkali", "bleaching powder", "gypsum", "plaster of paris"],
                learning_objectives=[
                    LearningObjective("L10.2.1", "Explain pH scaling mechanisms based on logarithm hydrogen ion dilution", BloomsLevel.UNDERSTAND),
                    LearningObjective("L10.2.2", "Deduce reactant configurations for industrial chlor-alkali manufacturing processes", BloomsLevel.ANALYZE)
                ],
                contains_practical_experiments=True,
                description="Study of aqueous pH systems, indicators, strong vs weak ions, salt crystallization, and industrial chemical manufacturing."
            ),
            ChapterProfile(
                chapter_number=3,
                chapter_name="Life Processes",
                stream=StreamType.BIOLOGY,
                academic_class=AcademicClass.CLASS_10,
                base_weightage_percentage=22.0,
                conceptual_keywords=["autotrophic", "stomata", "nephron", "alveoli", "systole", "diastole", "translocation", "hemoglobin", "peristalsis"],
                learning_objectives=[
                    LearningObjective("L10.3.1", "Trace metabolic processing phases in human gastrointestinal systems", BloomsLevel.UNDERSTAND),
                    LearningObjective("L10.3.2", "Draw the structural anatomy of a human kidney nephron with labeling", BloomsLevel.APPLY),
                    LearningObjective("L10.3.3", "Analyze hydrostatic filtration changes during mammalian cardiovascular cycles", BloomsLevel.ANALYZE)
                ],
                contains_practical_experiments=True,
                description="Core mammalian and plant physiology: metabolic pathways, systemic circulation, respiration, and excretion."
            ),
            ChapterProfile(
                chapter_number=4,
                chapter_name="Light - Reflection and Refraction",
                stream=StreamType.PHYSICS,
                academic_class=AcademicClass.CLASS_10,
                base_weightage_percentage=25.0,
                conceptual_keywords=["concave", "convex", "focal length", "magnification", "refractive index", "snell's law", "real image", "virtual image"],
                learning_objectives=[
                    LearningObjective("L10.4.1", "Construct geometric ray path tracings for concave mirror systems", BloomsLevel.APPLY),
                    LearningObjective("L10.4.2", "Solve complex algebraic lens equation challenges using Cartesian sign rules", BloomsLevel.APPLY),
                    LearningObjective("L10.4.3", "Deduce wave propagation velocity alterations across composite media", BloomsLevel.ANALYZE)
                ],
                contains_practical_experiments=True,
                description="Geometric optics: mirrors, lenses, reflection boundaries, Snell's refraction law, and Cartesian signs."
            ),
            ChapterProfile(
                chapter_number=5,
                chapter_name="Electricity",
                stream=StreamType.PHYSICS,
                academic_class=AcademicClass.CLASS_10,
                base_weightage_percentage=23.0,
                conceptual_keywords=["potential difference", "resistance", "resistivity", "joule heating", "series circuit", "parallel circuit", "ammeter"],
                learning_objectives=[
                    LearningObjective("L10.5.1", "Formulate electrical equivalent resistance loads for complex parallel systems", BloomsLevel.APPLY),
                    LearningObjective("L10.5.2", "Explain resistive energy dissipation rates utilizing Joule heating formulas", BloomsLevel.UNDERSTAND)
                ],
                contains_practical_experiments=True,
                description="Electrodynamics, Ohm's law, material resistivity vectors, series/parallel load systems, and thermal power dissipation."
            )
        ]

    def get_chapters(self, academic_class: AcademicClass) -> List[ChapterProfile]:
        """Retrieves all chapters cataloged for the target class."""
        return self._chapters.get(academic_class, [])

    def query_chapters_by_stream(self, academic_class: AcademicClass, stream: StreamType) -> List[ChapterProfile]:
        """Filters chapter catalog to target stream files."""
        return [ch for ch in self.get_chapters(academic_class) if ch.stream == stream]

    def search_objectives_by_keyword(self, academic_class: AcademicClass, keyword: str) -> List[Tuple[ChapterProfile, LearningObjective]]:
        """Scans objectives database matching keyword triggers."""
        results = []
        normalized = keyword.lower()
        for ch in self.get_chapters(academic_class):
            for obj in ch.learning_objectives:
                if normalized in obj.statement.lower() or any(normalized in kw.lower() for kw in ch.conceptual_keywords):
                    results.append((ch, obj))
        return results



# ==============================================================================
# 10. MULTI-DIMENSIONAL RUBRIC SYSTEM
# ==============================================================================

class GradingDimension(Enum):
    """Core evaluation metrics analyzed during grading assessment."""
    CONCEPTUAL_ACCURACY = "Accuracy of stated scientific facts and definitions"
    MATHEMATICAL_RIGOR = "SI unit compliance, variable declarations, and computational accuracy"
    DIAGRAMMATIC_FIDELITY = "Fidelity of drawn anatomical structures, optical paths, and component labels"
    LOGICAL_DEDUCTION = "Causal linkages, hypothesis structures, and analytical critiques"
    TECHNICAL_TERMINOLOGY = "Use of domain-specific scientific words over colloquial phrases"


@dataclass(frozen=True)
class RubricTier:
    """Assigned credit limits for specific performance tiers."""
    tier_name: str  # e.g., "Excellent", "Competent", "Marginal", "Incorrect"
    marks_multiplier: float  # Percentage of available marks awarded (0.0 to 1.0)
    criteria_description: str


class DynamicRubricGenerator:
    """Generates detailed, modular grading rubrics custom-tailored to scientific streams."""

    @staticmethod
    def generate_rubric(stream: StreamType, blooms_level: BloomsLevel, total_marks: int) -> Dict[GradingDimension, List[RubricTier]]:
        """Constructs a multidimensional rubric for question evaluations."""
        rubric: Dict[GradingDimension, List[RubricTier]] = {}

        # Conceptual Accuracy is universally evaluated
        rubric[GradingDimension.CONCEPTUAL_ACCURACY] = [
            RubricTier("Fully Accurate", 1.0, "Core scientific principles, reactions, or laws are flawlessly stated with zero misconception."),
            RubricTier("Partially Misaligned", 0.5, "States standard terms correctly but displays emergent flaws in biological/physical explanations."),
            RubricTier("Completely Deficient", 0.0, "States scientifically invalid or unrelated concepts.")
        ]

        # Physics/Chemistry numericals or calculations require Mathematical Rigor
        if stream in [StreamType.PHYSICS, StreamType.CHEMISTRY] and blooms_level in [BloomsLevel.APPLY, BloomsLevel.ANALYZE]:
            rubric[GradingDimension.MATHEMATICAL_RIGOR] = [
                RubricTier("Rigorous Steps", 1.0, "All variables isolated, formula written first, clean math transformations, final answer features correct SI units."),
                RubricTier("Unit / Sign Error", 0.7, "Computational math is correct, but final units are missing or mirror Cartesian signs are reversed."),
                RubricTier("Basic Setup Only", 0.3, "Correct formula written, but calculation steps or variables are fundamentally incorrect."),
                RubricTier("No Rigor", 0.0, "Equations and numbers written at random without structured calculation pathways.")
            ]

        # Biology and Physics require visual drawing fidelity
        if stream in [StreamType.BIOLOGY, StreamType.PHYSICS] and blooms_level in [BloomsLevel.REMEMBER, BloomsLevel.APPLY, BloomsLevel.UNDERSTAND]:
            rubric[GradingDimension.DIAGRAMMATIC_FIDELITY] = [
                RubricTier("Technical Excellence", 1.0, "Ray paths feature correct arrow directions, organ components are scaled properly, all vital parts labeled."),
                RubricTier("Minor Annotation Gaps", 0.6, "Geometrical lines are correct, but some annotation labels are missing or misspelled."),
                RubricTier("Structural Failure", 0.2, "Drawn lines or organs represent a distorted visual structure with no academic clarity."),
                RubricTier("No Diagram", 0.0, "Visual model completely absent.")
            ]

        # High cognitive levels require logical deduction
        if blooms_level in [BloomsLevel.ANALYZE, BloomsLevel.EVALUATE, BloomsLevel.CREATE]:
            rubric[GradingDimension.LOGICAL_DEDUCTION] = [
                RubricTier("Systemic Integration", 1.0, "Traces full variable sequences (A -> B -> C), justifies choices using evidence-based parameters."),
                RubricTier("Linear Reasoning", 0.5, "States direct recall facts, but fails to tie multi-factor variables together."),
                RubricTier("Fragmented logic", 0.0, "Isolated words without coherent causal arguments.")
            ]

        return rubric


# ==============================================================================
# 8. VALIDATION FOUNDATION (MODULAR POLICIES & ORCHESTRATION)
# ==============================================================================

class ValidationSeverity(Enum):
    """Categorized status for rule compliance checks."""
    INFO = "Non-blocking diagnostic metrics"
    WARNING = "Aesthetic or optional ratio recommendations"
    ERROR = "Academic policy violations (MUST repair before orchestration)"


@dataclass(frozen=True)
class ValidationError:
    """Explicit mapping of validation issues."""
    rule_name: str
    severity: ValidationSeverity
    affected_element: str
    error_message: str
    suggested_remediation: str


@dataclass
class ValidationReport:
    """Rich report packaging all errors, logs, and blueprint statuses."""
    is_valid: bool
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    errors: List[ValidationError] = field(default_factory=list)

    def display_report_json(self) -> str:
        """Outputs a clean JSON report structure."""
        report = {
            "is_valid": self.is_valid,
            "diagnostics": self.diagnostics,
            "errors": [
                {
                    "rule": err.rule_name,
                    "severity": err.severity.name,
                    "element": err.affected_element,
                    "message": err.error_message,
                    "remediation": err.suggested_remediation
                }
                for err in self.errors
            ]
        }
        return json.dumps(report, indent=4)


class IValidationRule:
    """Interface implementation pattern for modular policy rule testing."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        """Runs the validation checks, compiling errors as they occur."""
        raise NotImplementedError


class MarksSumRule(IValidationRule):
    """Validates that all configured section sum weights match the total declared exam marks."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        calculated_sum = sum(sec.get_total_marks() for sec in blueprint.sections)
        
        if calculated_sum != blueprint.total_marks:
            errors.append(ValidationError(
                rule_name="MarksSumRule",
                severity=ValidationSeverity.ERROR,
                affected_element="Sections Configuration",
                error_message=f"Calculated sum of section marks ({calculated_sum}) does not match Master Blueprint Total ({blueprint.total_marks}).",
                suggested_remediation=f"Adjust section question counts or individual marks value to equal exactly {blueprint.total_marks}."
            ))
        return errors


class SectionSequenceRule(IValidationRule):
    """Enforces typical board aesthetics: questions must increase strictly in marks as sections progress."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        last_marks = 0
        
        for sec in blueprint.sections:
            if sec.marks_per_question < last_marks:
                errors.append(ValidationError(
                    rule_name="SectionSequenceRule",
                    severity=ValidationSeverity.WARNING,
                    affected_element=f"Section {sec.section_id}",
                    error_message=f"Section {sec.section_id} drops cognitive step-sizing. Marks per question ({sec.marks_per_question}) is lower than prior section ({last_marks}).",
                    suggested_remediation="CBSE standards recommend ascending marks structures: 1-mark section -> 2-mark section -> 3-mark section etc."
                ))
            last_marks = sec.marks_per_question
        return errors


class StreamBalanceRule(IValidationRule):
    """Ensures Physics, Chemistry, and Biology percentage splits fall within acceptable thresholds."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        stream_marks = target_data.get("stream_marks")
        if not stream_marks:
            return errors

        total_actual_marks = sum(stream_marks.values())
        if total_actual_marks == 0:
            return errors

        if blueprint.academic_class in [AcademicClass.CLASS_6, AcademicClass.CLASS_7]:
            return errors

        for stream, target_ratio in blueprint.stream_distribution_target.items():
            actual_ratio = stream_marks.get(stream, 0) / total_actual_marks
            if abs(actual_ratio - target_ratio) > 0.05:
                errors.append(ValidationError(
                    rule_name="StreamBalanceRule",
                    severity=ValidationSeverity.WARNING,
                    affected_element=f"Stream Balance - {stream.value}",
                    error_message=f"Actual weightage allocation for {stream.value} is {actual_ratio:.2%}, expected target was {target_ratio:.2%}.",
                    suggested_remediation="Shift question subject categories to maintain an equal split across sub-disciplines."
                ))
        return errors


class ClassMaturityRule(IValidationRule):
    """Enforces progression ceilings: lower classes must not be assigned highly advanced Bloom levels."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        bloom_data = target_data.get("bloom_distribution")
        if not bloom_data:
            return errors

        restricted_levels = {BloomsLevel.EVALUATE, BloomsLevel.CREATE}
        is_junior_class = blueprint.academic_class in [AcademicClass.CLASS_6, AcademicClass.CLASS_7, AcademicClass.CLASS_8]

        if is_junior_class:
            for level in restricted_levels:
                actual_weight = bloom_data.get(level, 0.0)
                if actual_weight > 0.0:
                    errors.append(ValidationError(
                        rule_name="ClassMaturityRule",
                        severity=ValidationSeverity.ERROR,
                        affected_element=f"Cognitive Bloom - {level.name}",
                        error_message=f"Cognitive tier {level.name} is mapped inside {blueprint.academic_class.value} blueprint. This violates child development progression bounds.",
                        suggested_remediation="Redistribute these marks to REMEMBER, UNDERSTAND or APPLY questions."
                    ))
        return errors


class OrchestratedValidator:
    """Aggregates and executes all structured academic validation policies."""

    def __init__(self) -> None:
        self._rules: List[IValidationRule] = [
            MarksSumRule(),
            SectionSequenceRule(),
            StreamBalanceRule(),
            ClassMaturityRule()
        ]

    def add_rule(self, rule: IValidationRule) -> None:
        """Dynamically appends custom policies to the validator queue."""
        self._rules.append(rule)

    def validate(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> ValidationReport:
        """Executes verification and compiles results."""
        report = ValidationReport(is_valid=True)
        all_errors = []

        for rule in self._rules:
            try:
                rule_errors = rule.execute(blueprint, target_data)
                all_errors.extend(rule_errors)
            except Exception as e:
                all_errors.append(ValidationError(
                    rule_name=rule.__class__.__name__,
                    severity=ValidationSeverity.ERROR,
                    affected_element="Engine Validator Execution",
                    error_message=f"Validation crashed on execution: {str(e)}",
                    suggested_remediation="Review rule logic constraints and datatypes inside target_data."
                ))

        report.errors = all_errors
        has_blocking_errors = any(err.severity == ValidationSeverity.ERROR for err in all_errors)
        report.is_valid = not has_blocking_errors

        report.diagnostics["total_blueprint_marks"] = blueprint.total_marks
        report.diagnostics["sections_parsed"] = [sec.section_id for sec in blueprint.sections]
        report.diagnostics["validated_class"] = blueprint.academic_class.value
        report.diagnostics["validator_rule_count"] = len(self._rules)

        return report


# ==============================================================================
# HIGH-FIDELITY DEMONSTRATION & INITIALIZATION DATA
# ==============================================================================

@dataclass
class QuestionInstance:
    """Represents a structured academic question conforming to AOS foundation rules."""
    question_id: str
    academic_class: AcademicClass
    stream: StreamType
    question_type: QuestionTypeCode
    blooms_level: BloomsLevel
    assigned_marks: int
    content_text: str
    expected_word_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


def bootstrap_demo_question_paper() -> Dict[str, Any]:
    """Generates sample question instances and exercises the validation engine."""
    metadata_engine = SubjectMetadataEngine()
    progression_engine = ClassProgressionEngine()
    stream_engine = StreamFoundationEngine()
    type_registry = QuestionTypeRegistry()
    depth_engine = MarksDepthEngine()
    taxonomy_engine = BloomsTaxonomyEngine()
    blueprint_registry = ExamBlueprintRegistry()
    curriculum_engine = CurriculumDirectoryEngine()
    validator = OrchestratedValidator()

    # Fetch Class 10 CBSE Board blueprint
    blueprint = blueprint_registry.get_blueprint(ExamType.FINAL, AcademicClass.CLASS_10)

    # Mock list of fully detailed question objects conforming to Class 10 Board Standards
    mock_questions = [
        QuestionInstance(
            question_id="Q1",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.PHYSICS,
            question_type=QuestionTypeCode.MCQ,
            blooms_level=BloomsLevel.APPLY,
            assigned_marks=1,
            content_text="A cylindrical conductor of length l and uniform area of cross-section A has resistance R. "
                         "Another conductor of length 2l and resistance R of the same material has area of cross-section...",
            expected_word_count=18,
            metadata={"options": ["A/2", "3A/2", "2A", "3A"], "correct_answer": "2A"}
        ),
        QuestionInstance(
            question_id="Q2",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.CHEMISTRY,
            question_type=QuestionTypeCode.MCQ,
            blooms_level=BloomsLevel.REMEMBER,
            assigned_marks=1,
            content_text="Which of the following is a displacement reaction? "
                         "(a) CaCO3 -> CaO + CO2 "
                         "(b) 2H2 + O2 -> 2H2O "
                         "(c) Fe + CuSO4 -> FeSO4 + Cu...",
            expected_word_count=12,
            metadata={"options": ["(a)", "(b)", "(c)", "None"], "correct_answer": "(c)"}
        ),
        QuestionInstance(
            question_id="Q21",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.BIOLOGY,
            question_type=QuestionTypeCode.ASSERTION_REASON,
            blooms_level=BloomsLevel.UNDERSTAND,
            assigned_marks=1,
            content_text="Assertion (A): In human beings, the respiratory pigment is hemoglobin. "
                         "Reason (R): Hemoglobin has a very high affinity for carbon dioxide.",
            expected_word_count=22,
            metadata={"options": ["Both A and R are true and R is correct explanation", "A is true but R is false"]}
        ),
        QuestionInstance(
            question_id="Q22",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.PHYSICS,
            question_type=QuestionTypeCode.SHORT_ANSWER,
            blooms_level=BloomsLevel.APPLY,
            assigned_marks=2,
            content_text="An object is placed at a distance of 10 cm in front of a convex mirror of focal length 15 cm. "
                         "Find the position and nature of the image formed.",
            expected_word_count=45
        ),
        QuestionInstance(
            question_id="Q23",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.CHEMISTRY,
            question_type=QuestionTypeCode.SHORT_ANSWER,
            blooms_level=BloomsLevel.UNDERSTAND,
            assigned_marks=2,
            content_text="Why do ionic compounds have high melting and boiling points? Explain with physical reasons.",
            expected_word_count=50
        ),
        QuestionInstance(
            question_id="Q28",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.BIOLOGY,
            question_type=QuestionTypeCode.SHORT_ANSWER,
            blooms_level=BloomsLevel.UNDERSTAND,
            assigned_marks=3,
            content_text="Explain the process of double fertilization in angiosperms with a neat developmental flow.",
            expected_word_count=75
        ),
        QuestionInstance(
            question_id="Q35",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.BIOLOGY,
            question_type=QuestionTypeCode.LONG_ANSWER,
            blooms_level=BloomsLevel.UNDERSTAND,
            assigned_marks=5,
            content_text="Draw a neat labeled schematic of the human digestive system and explain the functions of "
                         "pepsin, trypsin, and lipase in protein and fat breakdown.",
            expected_word_count=180
        ),
        QuestionInstance(
            question_id="Q38",
            academic_class=AcademicClass.CLASS_10,
            stream=StreamType.PHYSICS,
            question_type=QuestionTypeCode.CASE_STUDY,
            blooms_level=BloomsLevel.ANALYZE,
            assigned_marks=4,
            content_text="A student investigates the behavior of a semiconductor photoresistor. She records the following "
                         "resistance values under different light illuminations... (detailed data table provided). "
                         "Analyze the correlation and answer sub-questions...",
            expected_word_count=110
        )
    ]

    test_stream_marks = {
        StreamType.PHYSICS: 27,
        StreamType.CHEMISTRY: 25,
        StreamType.BIOLOGY: 28
    }

    test_bloom_distribution = {
        BloomsLevel.REMEMBER: 0.20,
        BloomsLevel.UNDERSTAND: 0.40,
        BloomsLevel.APPLY: 0.22,
        BloomsLevel.ANALYZE: 0.12,
        BloomsLevel.EVALUATE: 0.06,
        BloomsLevel.CREATE: 0.0
    }

    validation_payload = {
        "stream_marks": test_stream_marks,
        "bloom_distribution": test_bloom_distribution
    }

    report = validator.validate(blueprint, validation_payload)

    return {
        "metadata_engine": metadata_engine,
        "progression_engine": progression_engine,
        "stream_engine": stream_engine,
        "type_registry": type_registry,
        "depth_engine": depth_engine,
        "taxonomy_engine": taxonomy_engine,
        "blueprint_registry": blueprint_registry,
        "curriculum_engine": curriculum_engine,
        "validator": validator,
        "validation_report": report,
        "questions_parsed": len(mock_questions)
    }


# ==============================================================================
# ENTERPRISE EXTENSION: BLUEPRINT BUILDER
# ==============================================================================

class ExamBlueprintBuilder:
    """Builder pattern ensuring programmatic, validation-safe creation of new blueprints."""

    def __init__(self, exam_type: ExamType, academic_class: AcademicClass) -> None:
        self._exam_type = exam_type
        self._academic_class = academic_class
        self._duration_minutes = 180
        self._total_marks = 80
        self._sections: List[SectionBlueprint] = []
        self._bloom_distribution_target: Dict[BloomsLevel, float] = {}
        self._stream_distribution_target: Dict[StreamType, float] = {}
        self._difficulty_target: Dict[str, float] = {"EASY": 0.3, "AVERAGE": 0.5, "DIFFICULT": 0.2}

    def set_duration(self, minutes: int) -> "ExamBlueprintBuilder":
        """Sets the examination duration."""
        self._duration_minutes = minutes
        return self

    def set_total_marks(self, marks: int) -> "ExamBlueprintBuilder":
        """Sets the total marks baseline."""
        self._total_marks = marks
        return self

    def add_section(self, section_id: str, question_type: QuestionTypeCode, count: int, marks: int, choices: int = 0) -> "ExamBlueprintBuilder":
        """Appends a new section layout to the blueprint."""
        self._sections.append(SectionBlueprint(
            section_id=section_id,
            question_type=question_type,
            question_count=count,
            marks_per_question=marks,
            internal_choice_count=choices
        ))
        return self

    def set_bloom_targets(self, targets: Dict[BloomsLevel, float]) -> "ExamBlueprintBuilder":
        """Sets custom Bloom cognitive targets."""
        s = sum(targets.values())
        normalized = {k: v / s for k, v in targets.items()}
        self._bloom_distribution_target = normalized
        return self

    def set_stream_targets(self, targets: Dict[StreamType, float]) -> "ExamBlueprintBuilder":
        """Sets custom subject stream targets."""
        s = sum(targets.values())
        normalized = {k: v / s for k, v in targets.items()}
        self._stream_distribution_target = normalized
        return self

    def set_difficulty_targets(self, targets: Dict[str, float]) -> "ExamBlueprintBuilder":
        """Sets custom easy/average/hard targets."""
        s = sum(targets.values())
        normalized = {k.upper(): v / s for k, v in targets.items()}
        self._difficulty_target = normalized
        return self

    def build(self) -> ExamBlueprint:
        """Assembles, checks basic rules, and outputs the ExamBlueprint."""
        if not self._sections:
            raise ValueError("An ExamBlueprint must contain at least one SectionBlueprint.")
        
        calculated_marks = sum(sec.get_total_marks() for sec in self._sections)
        if calculated_marks != self._total_marks:
            raise ValueError(f"Structural validation error in builder: Sum of section marks ({calculated_marks}) "
                             f"must equal total marks ({self._total_marks}).")

        if not self._bloom_distribution_target:
            self._bloom_distribution_target = {
                BloomsLevel.REMEMBER: 0.30,
                BloomsLevel.UNDERSTAND: 0.40,
                BloomsLevel.APPLY: 0.20,
                BloomsLevel.ANALYZE: 0.10,
                BloomsLevel.EVALUATE: 0.0,
                BloomsLevel.CREATE: 0.0
            }
        
        if not self._stream_distribution_target:
            if self._academic_class in [AcademicClass.CLASS_6, AcademicClass.CLASS_7]:
                self._stream_distribution_target = {StreamType.INTEGRATED: 1.0}
            else:
                self._stream_distribution_target = {
                    StreamType.PHYSICS: 0.33,
                    StreamType.CHEMISTRY: 0.33,
                    StreamType.BIOLOGY: 0.34
                }

        return ExamBlueprint(
            exam_type=self._exam_type,
            academic_class=self._academic_class,
            duration_minutes=self._duration_minutes,
            total_marks=self._total_marks,
            sections=self._sections,
            bloom_distribution_target=self._bloom_distribution_target,
            stream_distribution_target=self._stream_distribution_target,
            difficulty_target=self._difficulty_target
        )


# ==============================================================================
# RIGOROUS TESTS & VALIDATION SUITE (INTEGRATED UNIT TESTING FRAMEWORK)
# ==============================================================================

class FoundationalEngineUnitTestSuite:
    """Autonomous self-testing suite validating the complete integrity of the infrastructure."""

    @staticmethod
    def run_all_tests() -> Dict[str, Any]:
        """Runs the complete suite, recording successes and capturing traceback errors."""
        results = {
            "total_assertions": 0,
            "passed_tests": 0,
            "failed_tests": [],
            "status": "INIT"
        }

        def assert_true(expression: bool, message: str) -> None:
            results["total_assertions"] += 1
            if expression:
                results["passed_tests"] += 1
            else:
                results["failed_tests"].append(message)
                raise AssertionError(message)

        try:
            # 1. Test Metadata Engine
            meta = SubjectMetadataEngine()
            assert_true(meta.is_class_supported(AcademicClass.CLASS_10), "Class 10 support check failed.")
            assert_true(meta.get_stream_mode(AcademicClass.CLASS_10) == StreamMode.SPLIT, "Class 10 split stream check failed.")
            assert_true(meta.get_stream_mode(AcademicClass.CLASS_6) == StreamMode.INTEGRATED, "Class 6 integrated stream check failed.")
            
            # 2. Test Class Progression Engine
            prog = ClassProgressionEngine()
            c10_profile = prog.get_profile(AcademicClass.CLASS_10)
            assert_true(c10_profile.maturity_level == ConceptualMaturityLevel.ABSTRACT_QUALITATIVE, "Class 10 maturity level mismatch.")
            assert_true(c10_profile.numerical_complexity == NumericalComplexityLevel.GRAPHICAL_COMPUTATION, "Class 10 math level mismatch.")
            
            ok_size, msg_size = prog.validate_progression_depth(AcademicClass.CLASS_10, 5, 150)
            assert_true(ok_size, f"Class 10 marks depth validation failed: {msg_size}")
            too_small, _ = prog.validate_progression_depth(AcademicClass.CLASS_10, 5, 50)
            assert_true(not too_small, "Class 10 marks depth progression ceiling failed to block short answer.")

            # 3. Test Stream Foundation
            stream = StreamFoundationEngine()
            bio = stream.get_profile(StreamType.BIOLOGY)
            assert_true(bio.cognitive_style == CognitiveStyle.SYSTEMIC_FUNCTIONAL, "Biology cognitive style mismatch.")
            assert_true(bio.diagram_frequency_coefficient == 0.90, "Biology diagram frequency mismatch.")
            
            rec_stream = stream.get_recommended_stream(AcademicClass.CLASS_10, "State Ohm's law and draw circuit diagram")
            assert_true(rec_stream == StreamType.PHYSICS, "Physics keyword trigger suggestion failed.")

            # 4. Test Question Type Registry
            qtype = QuestionTypeRegistry()
            mcq = qtype.get_profile(QuestionTypeCode.MCQ)
            assert_true(mcq.base_marks_range == (1, 1), "MCQ base marks bounds mismatch.")
            assert_true(not mcq.requires_stimulus_context, "MCQ stimulus check failed.")

            # 5. Test Marks Depth Engine
            depth = MarksDepthEngine()
            five_marker = depth.get_profile(5)
            assert_true(five_marker.minimum_reasoning_steps == 5, "5-mark expected reasoning steps mismatch.")
            assert_true(five_marker.cognitive_load_index == 0.90, "5-mark cognitive load index mismatch.")

            # 6. Test Bloom's Taxonomy Engine
            bloom = BloomsTaxonomyEngine()
            rem = bloom.get_profile(BloomsLevel.REMEMBER)
            assert_true(bloom.verify_action_verb(BloomsLevel.REMEMBER, "State"), "State verb check failed in REMEMBER.")
            assert_true(not bloom.verify_action_verb(BloomsLevel.REMEMBER, "Design"), "Design verb validation leakage detected in REMEMBER.")

            # 7. Test Curriculum Directory Engine
            curr = CurriculumDirectoryEngine()
            c10_chaps = curr.get_chapters(AcademicClass.CLASS_10)
            assert_true(len(c10_chaps) > 0, "Failed to load Class 10 chapters.")
            assert_true(c10_chaps[0].chapter_number == 1, "First chapter loaded was not number 1.")
            
            query_objs = curr.search_objectives_by_keyword(AcademicClass.CLASS_10, "circuit")
            assert_true(len(query_objs) > 0, "Failed to locate objectives with keyword 'circuit'.")

            # 8. Test Dynamic Rubric System
            rubric_map = DynamicRubricGenerator.generate_rubric(StreamType.PHYSICS, BloomsLevel.APPLY, 5)
            assert_true(GradingDimension.MATHEMATICAL_RIGOR in rubric_map, "Mathematical Rigor not generated for Physics Apply scenario.")

            # 9. Test Exam Blueprint Builder & Registry
            blueprints = ExamBlueprintRegistry()
            c10_final = blueprints.get_blueprint(ExamType.FINAL, AcademicClass.CLASS_10)
            assert_true(c10_final.total_marks == 80, "Class 10 final blueprint total marks mismatch.")
            
            custom_bp = (ExamBlueprintBuilder(ExamType.UNIT_TEST, AcademicClass.CLASS_9)
                         .set_duration(60)
                         .set_total_marks(25)
                         .add_section("A", QuestionTypeCode.MCQ, 5, 1)
                         .add_section("B", QuestionTypeCode.SHORT_ANSWER, 5, 2, 1)
                         .add_section("C", QuestionTypeCode.NUMERICAL, 2, 5)
                         .build())
            assert_true(custom_bp.total_marks == 25, "Custom builder validation sum mismatch.")
            assert_true(len(custom_bp.sections) == 3, "Custom builder sections count mismatch.")

            # 10. Test Orchestrated Validator
            validator = OrchestratedValidator()
            payload_valid = {
                "stream_marks": {StreamType.PHYSICS: 27, StreamType.CHEMISTRY: 25, StreamType.BIOLOGY: 28},
                "bloom_distribution": {
                    BloomsLevel.REMEMBER: 0.20,
                    BloomsLevel.UNDERSTAND: 0.40,
                    BloomsLevel.APPLY: 0.20,
                    BloomsLevel.ANALYZE: 0.10,
                    BloomsLevel.EVALUATE: 0.08,
                    BloomsLevel.CREATE: 0.02
                }
            }
            report = validator.validate(c10_final, payload_valid)
            assert_true(report.is_valid, "Valid blueprint validation reported as invalid.")

            # Test invalid state (Maturity ceiling violation in Class 6 Unit Test blueprint)
            c6_ut = blueprints.get_blueprint(ExamType.UNIT_TEST, AcademicClass.CLASS_6)
            payload_invalid_bloom = {
                "bloom_distribution": {
                    BloomsLevel.CREATE: 0.20,
                    BloomsLevel.REMEMBER: 0.80
                }
            }
            report_invalid = validator.validate(c6_ut, payload_invalid_bloom)
            assert_true(not report_invalid.is_valid, "Invalid bloom maturity level was not flagged in validation.")
            assert_true(any(err.rule_name == "ClassMaturityRule" for err in report_invalid.errors),
                        "ClassMaturityRule failed to capture violation.")

            results["status"] = "SUCCESS"

        except Exception as e:
            results["status"] = "FAILED"
            results["exception"] = str(e)

        return results


# ==============================================================================
# MAIN ENGINE ACCESS POINT (CLI DIAGNOSTICS & EXPORTS)
# ==============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("ACADEMIC OPERATING SYSTEM - PHASE 1 FOUNDATIONAL ENGINE DIAGNOSTICS")
    print("=" * 80)
    
    test_run = FoundationalEngineUnitTestSuite.run_all_tests()
    print(f"Self-Test Status:   {test_run['status']}")
    print(f"Passed Assertions:  {test_run['passed_tests']} / {test_run['total_assertions']}")
    
    if test_run["status"] == "FAILED":
        print(f"Failure Exception:  {test_run.get('exception')}")
        print("Failed Details:")
        for fd in test_run.get("failed_tests", []):
            print(f"  - {fd}")
    else:
        print("Core architecture conforms 100% to board policies and progression engines.")

    print("-" * 80)
    
    demo = bootstrap_demo_question_paper()
    print("Bootstrap Demonstration Complete.")
    print(f"Questions Parsed: {demo['questions_parsed']}")
    print(f"Orchestrated Validation Status: "
          f"{'PASSED' if demo['validation_report'].is_valid else 'FAILED'}")
    
    print("\n--- Diagnostic JSON Validation Output ---")
    print(demo['validation_report'].display_report_json())
    print("=" * 80)
