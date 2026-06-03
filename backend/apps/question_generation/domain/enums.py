"""
Question Generation Domain - Canonical Enums
"""

from enum import Enum, auto


class EducationBoard(Enum):
    # Product ships CBSE only; other entries are reserved placeholders.
    CBSE = "Central Board of Secondary Education"
    IB = "International Baccalaureate"
    CAMBRIDGE = "Cambridge Assessment International Education"
    STATE_BOARD = "State Secondary Education Board"


class InstitutionType(Enum):
    BOARD_STANDARD = "Official Board Standard"
    DPS_NETWORK = "Delhi Public School Society Network"
    DAV_INSTITUTIONS = "DAV College Managing Committee"
    RYAN_INTERNATIONAL = "Ryan International Group of Institutions"
    TEACHER_CUSTOM = "Custom Teacher Classroom Format"


class AcademicClass(Enum):
    CLASS_1 = "Class 1"
    CLASS_2 = "Class 2"
    CLASS_3 = "Class 3"
    CLASS_4 = "Class 4"
    CLASS_5 = "Class 5"
    CLASS_6 = "Class 6" 
    CLASS_7 = "Class 7"
    CLASS_8 = "Class 8"
    CLASS_9 = "Class 9"
    CLASS_10 = "Class 10"


class SubjectCode(Enum):
    SCIENCE_GENERAL = "086"
    SOCIAL_SCIENCE = "087"
    SCIENCE_INTEGRATED = "SCI-INT"


class StreamType(Enum):
    PHYSICS = "Physics"
    CHEMISTRY = "Chemistry"
    BIOLOGY = "Biology"
    INTEGRATED = "Integrated General Science"


class StreamMode(Enum):
    INTEGRATED = "Integrated General Science (No formal stream boundaries)"
    HYBRID = "Hybrid General Science (Emergent stream grouping)"
    SPLIT = "Fully Split Science (Strict Physics, Chemistry, Biology boundaries)"


class CurriculumTier(Enum):
    FOUNDATION = "Remedial and Core Literacy"
    STANDARD = "Core CBSE Board Curriculum Alignment"
    ADVANCED = "HOTS, Exemplar, and Analytical Enrichment"
    OLYMPIAD = "Competitive and High-Cognitive Reasoning"


class BloomsLevel(Enum):
    REMEMBER = "Recall of core facts, terminology, and standard formulas"
    UNDERSTAND = "Grasping meaning, translating mechanisms, and explaining systems"
    APPLY = "Using rules, laws, and mathematical equations in concrete scenarios"
    ANALYZE = "Breaking systems into parts, isolating variables, and detecting bias"
    EVALUATE = "Critiquing evidence, verifying methodologies, and judging arguments"
    CREATE = "Formulating novel hypotheses, structuring new procedures, and synthesizing designs"


class CognitiveStyle(Enum):
    MATHEMATICAL_MODELING = auto()
    MICRO_MACRO_MAPPING = auto()
    SYSTEMIC_FUNCTIONAL = auto()
    PHENOMENOLOGICAL = auto()


class QuestionTypeCode(Enum):
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


class ExamType(Enum):
    UNIT_TEST = "Unit Test (Topic-specific diagnostic)"
    PERIODIC_TEST = "Periodic Assessment (Short term milestone)"
    MIDTERM = "Midterm Examination (Comprehensive half-yearly)"
    FINAL = "Annual Board-style Examination"
    REVISION_PAPER = "Targeted Review Framework"
    COMPETENCY_ASSESSMENT = "Skill-specific Application Audit"


class ValidationSeverity(Enum):
    INFO = "Non-blocking diagnostic metrics"
    WARNING = "Aesthetic or optional ratio recommendations"
    ERROR = "Academic policy violations (MUST repair before orchestration)"


class GradingDimension(Enum):
    CONCEPTUAL_ACCURACY = "Accuracy of stated scientific facts and definitions"
    MATHEMATICAL_RIGOR = "SI unit compliance, variable declarations, and computational accuracy"
    DIAGRAMMATIC_FIDELITY = "Fidelity of drawn anatomical structures, optical paths, and component labels"
    LOGICAL_DEDUCTION = "Causal linkages, hypothesis structures, and analytical critiques"
    TECHNICAL_TERMINOLOGY = "Use of domain-specific scientific words over colloquial phrases"


class AbstractionLevel(Enum):
    CONCRETE_OBSERVABLE = auto()
    MECHANISTIC_SYSTEMIC = auto()
    THEORETICAL_MOLECULAR = auto()
    QUANTITATIVE_FUNCTIONAL = auto()


class RelationshipType(Enum):
    PREREQUISITE = auto()
    EXTENDS = auto()
    APPLIES_IN = auto()
    CONTRASTS_WITH = auto()


class StudentArchetype(Enum):
    STEADY_AVERAGE = "Standard CBSE Student (Consistent proficiency, typical anxiety)"
    HIGH_ACHIEVER_ANXIOUS = "High Proficiency - High Anxiety (Prone to early panic under time stress)"
    REMEDIAL_STRUGGLING = "Low Proficiency - High Fatigue (Struggles with advanced cognitive steps)"
    OLYMPIAD_ELITE = "Ultra High Proficiency - Bulletproof (Virtually immune to standard pacing fatigue)"


class CognitiveCurveShape(Enum):
    LINEAR_ASCENDING = auto()
    EXPONENTIAL_SPIKE = auto()
    SINUSOIDAL_WAVE = auto()
    PLATEAU_SUSTAIN = auto()


class TokenKind(Enum):
    SECTION_HEADER = auto()
    GENERAL_INSTRUCTION = auto()
    QUESTION_NUM = auto()
    QUESTION_BODY = auto()
    MARKS_INDICATOR = auto()
    OR_SPLIT = auto()


class WordingPattern(Enum):
    DIRECTIVE_EXPLAIN = auto()
    DIRECTIVE_CALCULATE = auto()
    DIRECTIVE_DIAGRAM = auto()
    DIRECTIVE_JUSTIFY = auto()
    DIRECTIVE_DIFFERENTIATE = auto()
    DIRECTIVE_STATE = auto()
    DIRECTIVE_LIST = auto()
    DIRECTIVE_DESIGN = auto()


class MisconceptionType(Enum):
    ADDITIVE_CIRCUIT_ERROR = auto()
    INVERSE_PH_SCALE = auto()
    REVERSE_OPTICAL_SIGN = auto()
    MATHEMATICAL_SLIP = auto()


class ConceptualMaturityLevel(Enum):
    OBSERVATIONAL = "Primarily sensory and experiential"
    CORRELATIONAL = "Linking cause and effect across observations"
    ANALYTICAL = "Isolating variables and quantitative modeling"
    SYNTHETIC = "Integrating multi-domain frameworks into unified systems"


class ReasoningExpectation(Enum):
    RECALL_ONLY = "Direct factual recall without derivation"
    SINGLE_STEP = "One analytical step (apply a formula directly)"
    MULTI_STEP = "Two to four sequential reasoning steps"
    OPEN_ENDED = "Synthesis-level thinking with multiple valid pathways"


class NumericalComplexityLevel(Enum):
    NONE = "No numerical skills required"
    ARITHMETIC = "Basic arithmetic (integer operations)"
    ALGEBRAIC = "Algebraic manipulation (isolating variables, ratios)"
    GEOMETRIC = "Geometric reasoning with spatial visualization"
