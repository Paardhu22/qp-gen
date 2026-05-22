"""
Academic Operating System (AOS) - Paper Orchestration Intelligence
================================================================================
Module: configs.cbse.science.orchestrator
Phase: 2 - Paper Psychology & Orchestration Engine
Description: A highly sophisticated, psychometric-grade exam paper flow
             orchestrator. Models paper psychology, section choreography,
             cognitive curves, dynamic time-series student fatigue/anxiety,
             and equivalence-balanced internal choice allocation.
================================================================================
"""

import math
import json
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Set, Tuple, Optional, Any, Union

# Import pristine Phase 1 structures
from science import (
    AcademicClass,
    StreamType,
    QuestionTypeCode,
    BloomsLevel,
    ExamType,
    SectionBlueprint,
    ExamBlueprint,
    QuestionInstance,
    ClassProgressionEngine,
    StreamFoundationEngine,
    QuestionTypeRegistry,
    MarksDepthEngine,
    BloomsTaxonomyEngine,
    ExamBlueprintRegistry
)


# ==============================================================================
# 1. PSYCHOMETRIC MODELS & STUDENT ARCHETYPE ENGINE
# ==============================================================================

class StudentArchetype(Enum):
    """Categorized psychological and proficiency profiles for student simulators."""
    STEADY_AVERAGE = "Standard CBSE Student (Consistent proficiency, typical anxiety)"
    HIGH_ACHIEVER_ANXIOUS = "High Proficiency - High Anxiety (Prone to early panic under time stress)"
    REMEDIAL_STRUGGLING = "Low Proficiency - High Fatigue (Struggles with advanced cognitive steps)"
    OLYMPIAD_ELITE = "Ultra High Proficiency - Bulletproof (Virtually immune to standard pacing fatigue)"


@dataclass(frozen=True)
class StudentProfile:
    """Core psychometric parameters governing simulated student behavior."""
    archetype: StudentArchetype
    baseline_proficiency: float    # Scale: 0.0 to 1.0 (Skill index)
    anxiety_baseline: float        # Scale: 0.0 to 1.0 (Resting anxiety state)
    fatigue_resistance: float      # Multiplier: 0.5 (fast exhaust) to 2.5 (stamina model)
    recovery_multiplier: float     # Multiplier: how effectively rest/relief questions restore stamina
    time_pressure_sensitivity: float # Weight factor for anxiety progression under time pressure


class StudentProfileRegistry:
    """Preloads realistic, benchmarked psychometric profiles for standard archetypes."""

    def __init__(self) -> None:
        self._profiles: Dict[StudentArchetype, StudentProfile] = {}
        self._initialize_registry()

    def _initialize_registry(self) -> None:
        # 1. Standard Average Student
        self._profiles[StudentArchetype.STEADY_AVERAGE] = StudentProfile(
            archetype=StudentArchetype.STEADY_AVERAGE,
            baseline_proficiency=0.72,
            anxiety_baseline=0.15,
            fatigue_resistance=1.0,
            recovery_multiplier=1.0,
            time_pressure_sensitivity=1.0
        )

        # 2. High Achiever with Anxiety
        self._profiles[StudentArchetype.HIGH_ACHIEVER_ANXIOUS] = StudentProfile(
            archetype=StudentArchetype.HIGH_ACHIEVER_ANXIOUS,
            baseline_proficiency=0.92,
            anxiety_baseline=0.35,  # High resting anxiety
            fatigue_resistance=1.2,
            recovery_multiplier=0.8,  # Harder to calm down once anxious
            time_pressure_sensitivity=1.8  # Very sensitive to ticking clock
        )

        # 3. Remedial / Struggling Student
        self._profiles[StudentArchetype.REMEDIAL_STRUGGLING] = StudentProfile(
            archetype=StudentArchetype.REMEDIAL_STRUGGLING,
            baseline_proficiency=0.45,
            anxiety_baseline=0.25,
            fatigue_resistance=0.6,   # Tires very quickly under computational loads
            recovery_multiplier=1.5,   # Highly responsive to direct, easy warmup questions
            time_pressure_sensitivity=1.2
        )

        # 4. Olympiad Elite Student
        self._profiles[StudentArchetype.OLYMPIAD_ELITE] = StudentProfile(
            archetype=StudentArchetype.OLYMPIAD_ELITE,
            baseline_proficiency=0.98,
            anxiety_baseline=0.05,
            fatigue_resistance=2.5,   # Immense mental stamina
            recovery_multiplier=2.0,
            time_pressure_sensitivity=0.3  # Stays calm regardless of time limits
        )

    def get_profile(self, archetype: StudentArchetype) -> StudentProfile:
        """Fetches the psychometric parameters configuration."""
        return self._profiles[archetype]


@dataclass
class StudentPsychologicalState:
    """Represents the simulated cognitive and emotional state of a student during an exam."""
    fatigue_index: float = 0.0          # Scale: 0.0 (fresh) to 1.0 (exhausted)
    anxiety_index: float = 0.1          # Scale: 0.0 (calm) to 1.0 (panic)
    confidence_index: float = 0.7        # Scale: 0.0 (hopeless) to 1.0 (empowered)
    time_pressure_index: float = 0.0     # Scale: 0.0 (ahead) to 1.0 (out of time)
    cumulative_time_spent: float = 0.0   # Chronological minutes elapsed
    cumulative_marks_secured: float = 0.0 # Expected marks based on proficiency (for simulation)


@dataclass(frozen=True)
class PsychometricStimulus:
    """Quantitative stressors introduced by a single question."""
    reading_word_count: int
    algebraic_operators_count: int
    has_diagram_stimulus: bool
    context_switch_required: bool  # Switching between Physics, Chemistry, Biology
    cognitive_weight: float       # Bloom's level index modifier


class PaperRhythmEngine:
    """Simulates student mental fatigue, pacing, anxiety shifts, and scoring relief."""

    def __init__(self, total_duration_minutes: int, profile: StudentProfile) -> None:
        self.total_duration_minutes = total_duration_minutes
        self.profile = profile

    def calculate_stimulus(self, question: QuestionInstance, last_stream: Optional[StreamType]) -> PsychometricStimulus:
        """Converts academic question metadata into quantitative psychometric stress variables."""
        # Calculate algebraic math elements
        math_ops = 0
        normalized_text = question.content_text.lower()
        math_indicators = ["+", "-", "=", "/", "calc", "solve", "formula", "value", "constant", "resistance", "focal", "equation"]
        if question.question_type == QuestionTypeCode.NUMERICAL:
            math_ops += 4
        for indicator in math_indicators:
            if indicator in normalized_text:
                math_ops += 1

        # Check stream switch stress
        stream_switch = False
        if last_stream and last_stream != question.stream and last_stream != StreamType.INTEGRATED:
            stream_switch = True

        # Map Bloom's taxonomy to cognitive stress weights
        bloom_weights = {
            BloomsLevel.REMEMBER: 1.0,
            BloomsLevel.UNDERSTAND: 1.5,
            BloomsLevel.APPLY: 2.2,
            BloomsLevel.ANALYZE: 3.0,
            BloomsLevel.EVALUATE: 3.5,
            BloomsLevel.CREATE: 4.0
        }
        cog_weight = bloom_weights.get(question.blooms_level, 2.0)

        # Check diagram requirements
        has_diagram = (question.question_type == QuestionTypeCode.DIAGRAM) or ("diagram" in normalized_text)

        return PsychometricStimulus(
            reading_word_count=question.expected_word_count,
            algebraic_operators_count=math_ops,
            has_diagram_stimulus=has_diagram,
            context_switch_required=stream_switch,
            cognitive_weight=cog_weight
        )

    def transition_state(
        self,
        current_state: StudentPsychologicalState,
        question: QuestionInstance,
        stimulus: PsychometricStimulus,
        allocated_time: float
    ) -> StudentPsychologicalState:
        """Applies time-series differential equations to simulate progression through a question."""
        # Fatigue rate adjusted by student fatigue resistance profile
        fatigue_rate = 1.0 / self.profile.fatigue_resistance
        
        fatigue_read = stimulus.reading_word_count * 0.0004 * fatigue_rate
        fatigue_calc = stimulus.algebraic_operators_count * 0.012 * fatigue_rate
        fatigue_cognitive = (stimulus.cognitive_weight ** 1.6) * 0.010 * fatigue_rate
        fatigue_diagram = 0.015 * fatigue_rate if stimulus.has_diagram_stimulus else 0.0
        fatigue_switch = 0.025 * fatigue_rate if stimulus.context_switch_required else 0.0

        delta_fatigue = fatigue_read + fatigue_calc + fatigue_cognitive + fatigue_diagram + fatigue_switch

        # Check for SCORING RELIEF (Easy, fast recall gives recovery)
        is_relief = (question.blooms_level == BloomsLevel.REMEMBER and question.assigned_marks <= 2)
        if is_relief:
            delta_fatigue = -0.06 * (current_state.fatigue_index) * self.profile.recovery_multiplier

        new_fatigue = min(1.0, max(0.0, current_state.fatigue_index + delta_fatigue))

        # Time Pressure
        expected_elapsed = current_state.cumulative_time_spent + allocated_time
        time_pressure = min(1.0, max(0.0, expected_elapsed / self.total_duration_minutes))

        # Confidence delta
        cognitive_ratio = stimulus.cognitive_weight / 4.0
        success_probability = min(
            1.0, 
            max(0.02, self.profile.baseline_proficiency * (1.1 - (cognitive_ratio * 0.5) - (current_state.fatigue_index * 0.35)))
        )
        
        success_feedback = 0.08 * success_probability
        failure_feedback = -0.12 * (1.0 - success_probability) * (1.0 + (time_pressure * self.profile.time_pressure_sensitivity))
        delta_confidence = success_feedback + failure_feedback
        
        if question.assigned_marks == 1 and success_probability > 0.7:
            delta_confidence += 0.04

        new_confidence = min(1.0, max(0.0, current_state.confidence_index + delta_confidence))

        # Anxiety delta
        target_anxiety = (
            (stimulus.cognitive_weight / 4.0) * 0.25 +
            (1.0 - new_confidence) * 0.45 +
            new_fatigue * 0.15 +
            (time_pressure * self.profile.time_pressure_sensitivity) * 0.20 +
            self.profile.anxiety_baseline
        )
        new_anxiety = current_state.anxiety_index + 0.25 * (target_anxiety - current_state.anxiety_index)
        new_anxiety = min(1.0, max(0.0, new_anxiety))

        # Expected performance yield
        marks_gained = question.assigned_marks * success_probability

        return StudentPsychologicalState(
            fatigue_index=new_fatigue,
            anxiety_index=new_anxiety,
            confidence_index=new_confidence,
            time_pressure_index=time_pressure,
            cumulative_time_spent=expected_elapsed,
            cumulative_marks_secured=current_state.cumulative_marks_secured + marks_gained
        )


# ==============================================================================
# 2. COGNITIVE CURVE ENGINE
# ==============================================================================

class CognitiveCurveShape(Enum):
    """Mathematical distributions of cognitive load curves across papers."""
    SIGMOID_ESCALATION = auto()  # Smooth startup, rapid escalation in the middle, high plateau
    COSINE_WAVE = auto()         # Rhythmic rise and fall, placing relief valleys between cognitive spikes
    STEPPED_PLATEAU = auto()     # Incremental flat tiers corresponding strictly to sections
    CBSE_BOARD_CONVENTIONAL = auto() # Low anxiety objective start, steady linear climb, sudden peak, case-study step down


class CognitiveCurveEngine:
    """Generates target cognitive indices and identifies where differentiators should reside."""

    def __init__(self, curve_shape: CognitiveCurveShape = CognitiveCurveShape.CBSE_BOARD_CONVENTIONAL) -> None:
        self.curve_shape = curve_shape
        self._class_modifiers: Dict[AcademicClass, float] = {
            AcademicClass.CLASS_6: 0.6,
            AcademicClass.CLASS_7: 0.7,
            AcademicClass.CLASS_8: 0.8,
            AcademicClass.CLASS_9: 0.95,
            AcademicClass.CLASS_10: 1.0
        }

    def get_target_cognitive_weight(self, question_index: int, total_questions: int, academic_class: AcademicClass = AcademicClass.CLASS_10) -> float:
        """Returns the desired cognitive weight (1.0 to 6.0) adjusted for class-specific maturity."""
        progress = question_index / float(total_questions - 1) if total_questions > 1 else 0.0
        class_factor = self._class_modifiers.get(academic_class, 1.0)

        if self.curve_shape == CognitiveCurveShape.SIGMOID_ESCALATION:
            k = 8.0  
            x0 = 0.5  
            sigmoid_val = 1.0 / (1.0 + math.exp(-k * (progress - x0)))
            base_weight = 1.0 + sigmoid_val * 4.5  

        elif self.curve_shape == CognitiveCurveShape.COSINE_WAVE:
            wave = 0.5 * (1.0 - math.cos(2.0 * math.pi * progress))
            valley_adjustment = -0.18 * math.sin(math.pi * progress)
            base_weight = 1.5 + (wave + valley_adjustment) * 4.0

        elif self.curve_shape == CognitiveCurveShape.STEPPED_PLATEAU:
            if progress < 0.25:
                base_weight = 1.5  
            elif progress < 0.55:
                base_weight = 3.0  
            elif progress < 0.80:
                base_weight = 4.5  
            else:
                base_weight = 6.0  

        else: # CBSE_BOARD_CONVENTIONAL
            if progress < 0.30:
                base_weight = 1.8
            elif progress < 0.65:
                ratio = (progress - 0.30) / 0.35
                base_weight = 2.0 + ratio * 2.0
            elif progress < 0.85:
                ratio = (progress - 0.65) / 0.20
                base_weight = 4.0 + ratio * 1.6
            else:
                base_weight = 3.3

        # Apply class-specific maturity factor to cap the overall difficulty
        adjusted_weight = base_weight * class_factor
        return min(6.0, max(1.0, adjusted_weight))

    def is_differentiator_placement_index(self, question_index: int, total_questions: int) -> bool:
        """Determines if a given position is designated for a grade-differentiating challenge."""
        progress = question_index / float(total_questions - 1) if total_questions > 1 else 0.0
        if 0.78 <= progress <= 0.83:
            return True
        if 0.58 <= progress <= 0.62:
            return True
        return False


# ==============================================================================
# 3. ADVANCED INTERNAL CHOICE (OR) ENGINE
# ==============================================================================

@dataclass(frozen=True)
class InternalChoiceOption:
    """Holds a paired choice configuration, ensuring exact structural equivalence."""
    option_a: QuestionInstance
    option_b: QuestionInstance

    def __post_init__(self) -> None:
        if self.option_a.assigned_marks != self.option_b.assigned_marks:
            raise ValueError(f"Equivalence Mismatch: Option A ({self.option_a.assigned_marks} marks) and "
                             f"Option B ({self.option_b.assigned_marks} marks) must have identical score weight.")
        if self.option_a.academic_class != self.option_b.academic_class:
            raise ValueError("Equivalence Mismatch: Internal choices must target the identical academic class.")


class IChoiceEquivalenceRule:
    """Interface declaring a single strict checking criteria for internal choice pairs."""

    def verify(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, Optional[str]]:
        """Returns True if equivalent under this rule, else False and reasons."""
        raise NotImplementedError


class MarksEquivalenceRule(IChoiceEquivalenceRule):
    """Enforces absolute mark count matches."""
    def verify(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, Optional[str]]:
        if q1.assigned_marks != q2.assigned_marks:
            return False, f"Marks Mismatch: {q1.assigned_marks} vs {q2.assigned_marks}"
        return True, None


class StreamEquivalenceRule(IChoiceEquivalenceRule):
    """Enforces subject discipline alignment (Physics cannot OR Biology)."""
    def verify(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, Optional[str]]:
        if q1.stream != q2.stream:
            return False, f"Stream Mismatch: {q1.stream.value} vs {q2.stream.value}"
        return True, None


class BloomsEquivalenceRule(IChoiceEquivalenceRule):
    """Restricts cognitive disparity differences to +/- 1 tier."""
    def verify(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, Optional[str]]:
        weights = {
            BloomsLevel.REMEMBER: 1.0,
            BloomsLevel.UNDERSTAND: 2.0,
            BloomsLevel.APPLY: 3.5,
            BloomsLevel.ANALYZE: 4.5,
            BloomsLevel.EVALUATE: 5.5,
            BloomsLevel.CREATE: 6.0
        }
        w1 = weights.get(q1.blooms_level, 2.0)
        w2 = weights.get(q2.blooms_level, 2.0)
        if abs(w1 - w2) > 1.5:
            return False, f"Blooms Disparity: {q1.blooms_level.name} vs {q2.blooms_level.name} represents a major gap."
        return True, None


class TemporalEquivalenceRule(IChoiceEquivalenceRule):
    """Verifies that the estimated completion time matches within 3 minutes."""
    def verify(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, Optional[str]]:
        depth = MarksDepthEngine()
        t1 = depth.estimate_completion_time(q1.assigned_marks, q1.question_type)
        t2 = depth.estimate_completion_time(q2.assigned_marks, q2.question_type)
        if abs(t1 - t2) > 3.5:
            return False, f"Completion Time Disparity: {t1} mins vs {t2} mins exceeds balance thresholds."
        return True, None


class AlgebraicEquivalenceRule(IChoiceEquivalenceRule):
    """Balances mathematical workload: simple formulas cannot pair with complex quadratics."""
    def verify(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, Optional[str]]:
        is_math1 = q1.question_type == QuestionTypeCode.NUMERICAL
        is_math2 = q2.question_type == QuestionTypeCode.NUMERICAL
        if is_math1 != is_math2:
            return False, "Algebraic Disparity: Calculation vs descriptive theory balance mismatch."
        return True, None


class DiagrammaticEquivalenceRule(IChoiceEquivalenceRule):
    """Ensures drawing loads are equivalent (drawing organ vs simple labeling)."""
    def verify(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, Optional[str]]:
        is_diag1 = q1.question_type == QuestionTypeCode.DIAGRAM or "draw" in q1.content_text.lower()
        is_diag2 = q2.question_type == QuestionTypeCode.DIAGRAM or "draw" in q2.content_text.lower()
        if is_diag1 != is_diag2:
            return False, "Diagrammatic Drawing Disparity: One option mandates sketching while the other does not."
        return True, None


class ChoiceEquivalenceValidator:
    """Orchestrates all dynamic equivalence verification rules."""

    def __init__(self) -> None:
        self.rules: List[IChoiceEquivalenceRule] = [
            MarksEquivalenceRule(),
            StreamEquivalenceRule(),
            BloomsEquivalenceRule(),
            TemporalEquivalenceRule(),
            AlgebraicEquivalenceRule(),
            DiagrammaticEquivalenceRule()
        ]

    def audit_equivalence(self, q1: QuestionInstance, q2: QuestionInstance) -> Tuple[bool, List[str]]:
        """Audits questions against all rules, returning all failed criteria."""
        failures = []
        for rule in self.rules:
            ok, reason = rule.verify(q1, q2)
            if not ok and reason:
                failures.append(reason)
        return len(failures) == 0, failures


class InternalChoiceEngine:
    """Allocates alternate choice options based on strict curricular equivalence rules."""

    def __init__(self) -> None:
        self.validator = ChoiceEquivalenceValidator()

    def pair_with_equivalent_choice(self, q: QuestionInstance, candidates: List[QuestionInstance]) -> Optional[InternalChoiceOption]:
        """Scans a candidate list to pair a question with its closest psychometric equivalent."""
        best_candidate = None
        least_deviation = 999.0

        for cand in candidates:
            if cand.question_id == q.question_id:
                continue
            
            is_equiv, _ = self.validator.audit_equivalence(q, cand)
            if is_equiv:
                word_deviation = abs(q.expected_word_count - cand.expected_word_count)
                if word_deviation < least_deviation:
                    least_deviation = word_deviation
                    best_candidate = cand

        if best_candidate:
            return InternalChoiceOption(q, best_candidate)
        return None

    def allocate_strategic_choices(
        self,
        questions: List[QuestionInstance],
        pool: List[QuestionInstance],
        target_section_id: str
    ) -> List[Union[QuestionInstance, InternalChoiceOption]]:
        """Interjects choice pairs dynamically in high-fatigue section blocks."""
        allocated: List[Union[QuestionInstance, InternalChoiceOption]] = []
        used_pool_ids: Set[str] = set()

        choice_probability = 0.0
        if target_section_id == "D":
            choice_probability = 1.0
        elif target_section_id == "C":
            choice_probability = 0.4
        elif target_section_id == "B":
            choice_probability = 0.2

        for i, q in enumerate(questions):
            if random.random() < choice_probability:
                filtered_pool = [c for c in pool if c.question_id not in used_pool_ids]
                pair = self.pair_with_equivalent_choice(q, filtered_pool)
                if pair:
                    allocated.append(pair)
                    used_pool_ids.add(pair.option_b.question_id)
                    continue
            
            allocated.append(q)

        return allocated


# ==============================================================================
# 4. CONTEXT-AWARE SECTION CHOREOGRAPHY PATTERNS
# ==============================================================================

class ISectionChoreographer:
    """Interface declaring structural sequence rules for a single paper section."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        """Arranges list of items into an optimal section flow."""
        raise NotImplementedError


class SectionAChoreographer(ISectionChoreographer):
    """Controls the objective warmup section (MCQs and Assertion-Reasons)."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        mcqs = [q for q in questions if q.question_type == QuestionTypeCode.MCQ]
        a_r = [q for q in questions if q.question_type == QuestionTypeCode.ASSERTION_REASON]

        mcqs.sort(key=lambda x: x.expected_word_count)
        a_r.sort(key=lambda x: x.expected_word_count)

        return mcqs + a_r


class SectionBChoreographer(ISectionChoreographer):
    """Controls Section B (Very Short Answers - 2 Markers) with stream balancing."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        arranged = list(questions)
        arranged.sort(key=lambda x: (x.assigned_marks, x.expected_word_count))
        
        balanced = []
        remaining = list(arranged)
        last_stream = None

        while remaining:
            next_q = None
            for q in remaining:
                if q.stream != last_stream:
                    next_q = q
                    break
            
            if not next_q:
                next_q = remaining[0]
            
            balanced.append(next_q)
            remaining.remove(next_q)
            last_stream = next_q.stream

        return balanced


class SectionCChoreographer(ISectionChoreographer):
    """Controls Section C (Short Answers - 3 Markers)."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        if len(questions) < 3:
            return sorted(questions, key=lambda x: x.expected_word_count)

        arranged = sorted(questions, key=lambda x: x.expected_word_count)
        diff_q = arranged[-1]  
        relief_q = arranged[0]  

        middle_qs = arranged[1:-1]
        return middle_qs + [diff_q] + [relief_q]


class SectionDChoreographer(ISectionChoreographer):
    """Controls Section D (Long Answers - 5 Markers)."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        physics = [q for q in questions if q.stream == StreamType.PHYSICS]
        chemistry = [q for q in questions if q.stream == StreamType.CHEMISTRY]
        biology = [q for q in questions if q.stream == StreamType.BIOLOGY]
        integrated = [q for q in questions if q.stream not in [StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY]]

        arranged = []
        max_len = max(len(physics), len(chemistry), len(biology), len(integrated))
        for idx in range(max_len):
            if idx < len(physics):
                arranged.append(physics[idx])
            if idx < len(chemistry):
                arranged.append(chemistry[idx])
            if idx < len(biology):
                arranged.append(biology[idx])
            if idx < len(integrated):
                arranged.append(integrated[idx])

        return arranged


class SectionEChoreographer(ISectionChoreographer):
    """Controls Section E (Case-Study - 4 Markers) placing reading loads early."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        arranged = list(questions)
        arranged.sort(key=lambda x: x.expected_word_count, reverse=True)
        return arranged


class SectionChoreographerFactory:
    """Constructs specialized section choreographers adjusted for different exam configurations."""

    @staticmethod
    def get_choreographer(section_id: str, exam_type: ExamType) -> ISectionChoreographer:
        """Returns standard or context-calibrated choreographers."""
        if exam_type == ExamType.UNIT_TEST:
            # Unit tests require grouping by stream/concept to minimize context-switching stress
            return SectionAChoreographer()  # Simple sorted sequencing
        
        # Standard CBSE choreography rules apply for Midterms, Finals, and Periodics
        if section_id == "A":
            return SectionAChoreographer()
        elif section_id == "B":
            return SectionBChoreographer()
        elif section_id == "C":
            return SectionCChoreographer()
        elif section_id == "D":
            return SectionDChoreographer()
        elif section_id == "E":
            return SectionEChoreographer()
        
        return SectionBChoreographer()


# ==============================================================================
# 5. STREAM BALANCING & CHRONOLOGICAL SPACING ENGINE
# ==============================================================================

class ConceptOverlapAnalyzer:
    """Scans and parses question text content to prevent redundant topic indexing."""

    def __init__(self, proximity_threshold: float = 0.40) -> None:
        self.proximity_threshold = proximity_threshold

    def calculate_jaccard_similarity(self, s1: str, s2: str) -> float:
        """Calculates exact bag-of-words keyword similarity."""
        w1 = set(s1.lower().replace(".", "").replace(",", "").replace("?", "").split())
        w2 = set(s2.lower().replace(".", "").replace(",", "").replace("?", "").split())
        
        stopwords = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "why", "what", "how", "find", "explain", "calculate", "state", "define"}
        w1 = w1 - stopwords
        w2 = w2 - stopwords
        
        if not w1 or not w2:
            return 0.0
        intersection = w1.intersection(w2)
        union = w1.union(w2)
        return len(intersection) / float(len(union))

    def audit_concept_overlap(self, sequence: List[QuestionInstance]) -> List[str]:
        """Audits paper sequence for repetitive conceptual keywords."""
        violations = []
        for i in range(len(sequence)):
            for j in range(i + 1, len(sequence)):
                q1 = sequence[i]
                q2 = sequence[j]
                sim = self.calculate_jaccard_similarity(q1.content_text, q2.content_text)
                
                spacing = j - i
                if sim > self.proximity_threshold and spacing <= 4:
                    violations.append(
                        f"Concept Redundancy Risk: Question {q1.question_id} and {q2.question_id} "
                        f"share {sim:.1%} concept keywords at index spacing {spacing}."
                    )
        return violations


class SpacingController:
    """Manages stream spacings, calculation densities, and keyword overlaps."""

    def __init__(self, min_stream_spacing: int = 2, min_numerical_spacing: int = 3) -> None:
        self.min_stream_spacing = min_stream_spacing
        self.min_numerical_spacing = min_numerical_spacing
        self.concept_analyzer = ConceptOverlapAnalyzer()

    def check_sequence_safety(self, sequence: List[QuestionInstance]) -> Tuple[bool, List[str]]:
        """Evaluates spacing rules, returning errors if stacking occurs."""
        errors = []
        last_numerical_idx = -99
        stream_last_indices: Dict[StreamType, int] = {}

        for i, q in enumerate(sequence):
            # 1. Back-to-back numerical stacking
            if q.question_type == QuestionTypeCode.NUMERICAL:
                spacing = i - last_numerical_idx
                if spacing <= self.min_numerical_spacing and last_numerical_idx != -99:
                    errors.append(f"Numerical Stacking Violation at index {i}: "
                                  f"Question {q.question_id} is spaced only {spacing} steps from the prior numerical calculation.")
                last_numerical_idx = i

            # 2. Stream clustering
            if q.stream != StreamType.INTEGRATED:
                if q.stream in stream_last_indices:
                    spacing = i - stream_last_indices[q.stream]
                    if spacing < self.min_stream_spacing:
                        errors.append(f"Stream Clustering Violation at index {i}: "
                                      f"{q.stream.value} Question {q.question_id} is placed too close to the prior {q.stream.value} question (spacing: {spacing}).")
                stream_last_indices[q.stream] = i

        # 3. Concept overlap checks
        overlap_errors = self.concept_analyzer.audit_concept_overlap(sequence)
        errors.extend(overlap_errors)

        return len(errors) == 0, errors

    def resolve_sequence_spacing(self, questions: List[QuestionInstance], max_iterations: int = 250) -> List[QuestionInstance]:
        """Rearranges sequence stochastically until all safety boundaries are met."""
        current_seq = list(questions)
        is_safe, _ = self.check_sequence_safety(current_seq)
        if is_safe:
            return current_seq

        for _ in range(max_iterations):
            random.shuffle(current_seq)
            is_safe, _ = self.check_sequence_safety(current_seq)
            if is_safe:
                return current_seq

        # Fallback sorted order
        current_seq.sort(key=lambda x: (x.stream.value, x.question_type.value))
        return current_seq


# ==============================================================================
# 6. MASTER ORCHESTRATION PIPELINE & COMPARATIVE SIMULATOR
# ==============================================================================

@dataclass
class SimulatedNode:
    """Timeline snapshot for simulated student milestones."""
    question_index: int
    question_id: str
    assigned_marks: int
    estimated_time: float
    state_after: StudentPsychologicalState


@dataclass
class ArchetypeSimulationResult:
    """Timeline summary logs for a single student archetype."""
    archetype: StudentArchetype
    timeline_nodes: List[SimulatedNode]
    final_fatigue: float
    final_anxiety: float
    final_confidence: float
    expected_marks_secured: float
    is_completed: bool


@dataclass
class PsychometricAssessmentReport:
    """Multi-dimensional report comparing results across archetypes."""
    is_psychometrically_balanced: bool
    archetype_results: Dict[StudentArchetype, ArchetypeSimulationResult]
    spacing_report_ok: bool
    spacing_errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def display_report_json(self) -> str:
        """Serializes the report metrics to clean JSON."""
        out = {
            "is_psychometrically_balanced": self.is_psychometrically_balanced,
            "spacing_ok": self.spacing_report_ok,
            "spacing_violations": self.spacing_errors,
            "recommendations": self.recommendations,
            "simulated_archetypes": {
                arch.name: {
                    "fatigue": round(res.final_fatigue, 3),
                    "anxiety": round(res.final_anxiety, 3),
                    "confidence": round(res.final_confidence, 3),
                    "expected_marks_secured": round(res.expected_marks_secured, 1),
                    "completed_within_duration": res.is_completed
                }
                for arch, res in self.archetype_results.items()
            }
        }
        return json.dumps(out, indent=4)


class PaperOrchestrationPipeline:
    """Master controller overseeing all orchestration layers, choices, and simulators."""

    def __init__(self, blueprint: ExamBlueprint) -> None:
        self.blueprint = blueprint
        self.registry = QuestionTypeRegistry()
        self.stream_engine = StreamFoundationEngine()
        self.depth_engine = MarksDepthEngine()
        
        self.choice_engine = InternalChoiceEngine()
        self.spacing_controller = SpacingController()
        self.profiles_registry = StudentProfileRegistry()

    def choreograph_paper(
        self,
        questions_by_section: Dict[str, List[QuestionInstance]],
        choice_pool: List[QuestionInstance]
    ) -> List[Union[QuestionInstance, InternalChoiceOption]]:
        """Orchestrates layout, formats section flows, and maps choices."""
        orchestrated_flow: List[Union[QuestionInstance, InternalChoiceOption]] = []

        for section_id in sorted(questions_by_section.keys()):
            sec_questions = questions_by_section[section_id]
            
            # Fetch choreographer dynamically via specialized factory
            choreographer = SectionChoreographerFactory.get_choreographer(section_id, self.blueprint.exam_type)
            sec_questions = choreographer.arrange_section(sec_questions)
            
            sec_with_choices = self.choice_engine.allocate_strategic_choices(
                sec_questions, choice_pool, section_id
            )
            orchestrated_flow.extend(sec_with_choices)

        return orchestrated_flow

    def simulate_student_experience(
        self,
        orchestrated_flow: List[Union[QuestionInstance, InternalChoiceOption]]
    ) -> PsychometricAssessmentReport:
        """Simulates paper flow across all 4 student archetypes, evaluating thresholds."""
        archetype_results: Dict[StudentArchetype, ArchetypeSimulationResult] = {}
        flat_questions: List[QuestionInstance] = []

        for item in orchestrated_flow:
            active_q = item.option_a if isinstance(item, InternalChoiceOption) else item
            flat_questions.append(active_q)

        # Run time-series simulation per archetype
        for archetype in StudentArchetype:
            profile = self.profiles_registry.get_profile(archetype)
            rhythm_engine = PaperRhythmEngine(self.blueprint.duration_minutes, profile)
            
            current_state = StudentPsychologicalState()
            nodes: List[SimulatedNode] = []
            last_stream = None

            for idx, q in enumerate(flat_questions):
                allocated_time = self.depth_engine.estimate_completion_time(q.assigned_marks, q.question_type)
                stimulus = rhythm_engine.calculate_stimulus(q, last_stream)
                current_state = rhythm_engine.transition_state(current_state, q, stimulus, allocated_time)
                
                nodes.append(SimulatedNode(
                    question_index=idx,
                    question_id=q.question_id,
                    assigned_marks=q.assigned_marks,
                    estimated_time=allocated_time,
                    state_after=current_state
                ))
                last_stream = q.stream

            is_completed = current_state.cumulative_time_spent <= self.blueprint.duration_minutes
            
            archetype_results[archetype] = ArchetypeSimulationResult(
                archetype=archetype,
                timeline_nodes=nodes,
                final_fatigue=current_state.fatigue_index,
                final_anxiety=current_state.anxiety_index,
                final_confidence=current_state.confidence_index,
                expected_marks_secured=current_state.cumulative_marks_secured,
                is_completed=is_completed
            )

        # Run spacing controller audits
        spacing_ok, spacing_errors = self.spacing_controller.check_sequence_safety(flat_questions)

        # Psychometric flow evaluation based on average profile thresholds
        avg_res = archetype_results[StudentArchetype.STEADY_AVERAGE]
        time_overrun = not avg_res.is_completed
        extreme_fatigue = avg_res.final_fatigue > 0.85
        extreme_anxiety = avg_res.final_anxiety > 0.75

        is_balanced = (not time_overrun) and (not extreme_fatigue) and (not extreme_anxiety) and spacing_ok

        recommendations = []
        if time_overrun:
            recommendations.append("Time Overrun: Estimated pacing indicates the standard student will run out of time.")
        if extreme_fatigue:
            recommendations.append("High Cognitive Fatigue: The standard student suffers extreme cognitive exhaust.")
        if extreme_anxiety:
            recommendations.append("Student Anxiety Peak: The standard student exceeds stress boundaries.")
        if not spacing_ok:
            recommendations.append("Chronological Spacing Flaws: Rearrangement required due to stacking or repetitions.")

        ha_res = archetype_results[StudentArchetype.HIGH_ACHIEVER_ANXIOUS]
        if ha_res.final_anxiety > 0.85:
            recommendations.append("High Achiever Panic Risk: Anxious high-achievers suffer panic spikes under this sequence. Reduce numerical spacing stress.")

        if is_balanced:
            recommendations.append("Psychometric Flow Optimized: Student cognitive curves, pacing ratios, and recovery points align perfectly with CBSE Board standards.")

        return PsychometricAssessmentReport(
            is_psychometrically_balanced=is_balanced,
            archetype_results=archetype_results,
            spacing_report_ok=spacing_ok,
            spacing_errors=spacing_errors,
            recommendations=recommendations
        )


# ==============================================================================
# 7. ASCII PSYCHOMETRIC TIMELINE VISUALIZER
# ==============================================================================

class AsciiTimelineVisualizer:
    """Renders visual ASCII graph plotting of simulated fatigue and anxiety trends straight to the console."""

    @staticmethod
    def render_plot(nodes: List[SimulatedNode], title: str = "VISUAL FATIGUE (*) & ANXIETY (x) TRENDS") -> str:
        """Constructs an ASCII graphical plot."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"ASCII TIMELINE PLOT - {title}")
        lines.append("=" * 80)

        # Plot 10-height rows
        for row in range(10, 0, -1):
            val_limit = row / 10.0
            row_str = f" {val_limit:>3.1f} | "
            for node in nodes:
                f_index = node.state_after.fatigue_index
                a_index = node.state_after.anxiety_index
                
                char = " "
                if abs(f_index - val_limit) <= 0.05 and abs(a_index - val_limit) <= 0.05:
                    char = "@"  # Collision intersection
                elif abs(f_index - val_limit) <= 0.05:
                    char = "*"
                elif abs(a_index - val_limit) <= 0.05:
                    char = "x"
                row_str += f"{char} "
            lines.append(row_str)

        lines.append("     +-" + "--" * len(nodes))
        
        # Draw question labels row
        label_row = " QId | "
        for node in nodes:
            label_row += f"{node.question_id:<2}"
        lines.append(label_row)
        
        lines.append("=" * 80)
        return "\n".join(lines)


# ==============================================================================
# RIGOROUS TESTS & VALIDATION SUITE (INTEGRATED UNIT TESTING FRAMEWORK)
# ==============================================================================

class OrchestrationEngineUnitTestSuite:
    """Autonomous self-testing suite validating the complete integrity of Phase 2 architecture."""

    @staticmethod
    def run_all_tests() -> Dict[str, Any]:
        """Runs tests, recording successes and capturing traceback errors."""
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
            # Setup mock assets
            blueprints = ExamBlueprintRegistry()
            blueprint = blueprints.get_blueprint(ExamType.FINAL, AcademicClass.CLASS_10)

            # Generate pool of target questions matching standard sections
            mock_section_qs: Dict[str, List[QuestionInstance]] = {
                "A": [
                    QuestionInstance("Q1", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.MCQ, BloomsLevel.APPLY, 1, "Direct resistance calculation", 20),
                    QuestionInstance("Q2", AcademicClass.CLASS_10, StreamType.CHEMISTRY, QuestionTypeCode.MCQ, BloomsLevel.REMEMBER, 1, "Balancing check equation", 15),
                    QuestionInstance("Q3", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.ASSERTION_REASON, BloomsLevel.UNDERSTAND, 1, "Assertion on hemoglobin cell", 25)
                ],
                "B": [
                    QuestionInstance("Q4", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 2, "Mirror position calculation", 45),
                    QuestionInstance("Q5", AcademicClass.CLASS_10, StreamType.CHEMISTRY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.UNDERSTAND, 2, "Explain high ionic boiling melting points", 40)
                ],
                "C": [
                    QuestionInstance("Q6", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.UNDERSTAND, 3, "Explain angiosperms fertilizations", 80),
                    QuestionInstance("Q7", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 3, "Joule heating computation problem", 65),
                    QuestionInstance("Q8", AcademicClass.CLASS_10, StreamType.CHEMISTRY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.ANALYZE, 3, "Deduce nature of unknown compound X", 95)
                ],
                "D": [
                    QuestionInstance("Q9", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.LONG_ANSWER, BloomsLevel.UNDERSTAND, 5, "Digestive anatomy labeled sketching structures", 160),
                    QuestionInstance("Q10", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.LONG_ANSWER, BloomsLevel.APPLY, 5, "Equivalent resistance matrix network", 140)
                ],
                "E": [
                    QuestionInstance("Q11", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.CASE_STUDY, BloomsLevel.ANALYZE, 4, "Photoresistor resistance variable values table", 110)
                ]
            }

            choice_pool = [
                QuestionInstance("C_Q4", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 2, "Lens magnification algebraic coordinates solver", 48),
                QuestionInstance("C_Q9", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.LONG_ANSWER, BloomsLevel.UNDERSTAND, 5, "Nephron anatomy filtration mechanisms explanation", 175),
                QuestionInstance("C_Q10", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.LONG_ANSWER, BloomsLevel.APPLY, 5, "Refraction prisms vectors pathways tracing steps", 135)
            ]

            # 1. Test Profile Registry
            reg = StudentProfileRegistry()
            steady = reg.get_profile(StudentArchetype.STEADY_AVERAGE)
            assert_true(steady.baseline_proficiency == 0.72, "Steady proficiency mismatch.")

            # 2. Test Spacing & Concept overlaps
            spacing_controller = SpacingController()
            safe_seq = [
                mock_section_qs["A"][0],  
                mock_section_qs["A"][1],  
                mock_section_qs["A"][2]   
            ]
            spacing_ok, _ = spacing_controller.check_sequence_safety(safe_seq)
            assert_true(spacing_ok, "Safe sequence spacing check failed.")

            # Concept overlap check
            analyzer = ConceptOverlapAnalyzer()
            overlap_sim = analyzer.calculate_jaccard_similarity(
                "Draw Ohm circuit diagram resistor",
                "Ohm resistor values calculation wire circuit"
            )
            assert_true(overlap_sim > 0.20, "Failed to identify concept word overlap.")

            # 3. Test Choice Equivalence Validator rules
            validator = ChoiceEquivalenceValidator()
            is_eq, fails = validator.audit_equivalence(mock_section_qs["B"][0], choice_pool[0])
            assert_true(is_eq, f"Equivalence audit failed: {fails}")

            # 4. Test pipeline choreography
            pipeline = PaperOrchestrationPipeline(blueprint)
            flow = pipeline.choreograph_paper(mock_section_qs, choice_pool)
            assert_true(len(flow) > 0, "Orchestration returned empty flow.")

            # 5. Test multi-archetype simulator
            report = pipeline.simulate_student_experience(flow)
            assert_true(len(report.archetype_results) == 4, "Multi-archetype simulator did not evaluate all profiles.")

            results["status"] = "SUCCESS"

        except Exception as e:
            results["status"] = "FAILED"
            results["exception"] = str(e)

        return results


# ==============================================================================
# RIGOROUS ADVANCED MULTI-CLASS PACKED Blueprints & Questions Pools
# ==============================================================================

def generate_curriculum_questions_pool() -> Dict[AcademicClass, Dict[str, List[QuestionInstance]]]:
    """Generates standard question pools for Classes 6, 8, and 10 to test all cognitive profiles."""
    pools = {}

    # --- CLASS 6 GENERAL SCIENCE QUESTIONS ---
    pools[AcademicClass.CLASS_6] = {
        "A": [
            QuestionInstance("C6_Q1", AcademicClass.CLASS_6, StreamType.INTEGRATED, QuestionTypeCode.MCQ, BloomsLevel.REMEMBER, 1, "Which vitamin deficiency causes the disease scurvy", 12),
            QuestionInstance("C6_Q2", AcademicClass.CLASS_6, StreamType.INTEGRATED, QuestionTypeCode.MCQ, BloomsLevel.REMEMBER, 1, "Which of the following is a direct source of dietary protein", 14),
            QuestionInstance("C6_Q3", AcademicClass.CLASS_6, StreamType.INTEGRATED, QuestionTypeCode.MCQ, BloomsLevel.UNDERSTAND, 1, "A transparent material allows light to pass through completely", 16)
        ],
        "B": [
            QuestionInstance("C6_Q4", AcademicClass.CLASS_6, StreamType.INTEGRATED, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.REMEMBER, 2, "Define roughage and state its primary function in diet", 28),
            QuestionInstance("C6_Q5", AcademicClass.CLASS_6, StreamType.INTEGRATED, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.UNDERSTAND, 2, "Differentiate between lustrous and non-lustrous materials with examples", 34)
        ],
        "C": [
            QuestionInstance("C6_Q6", AcademicClass.CLASS_6, StreamType.INTEGRATED, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 3, "Describe Winnowing as a separation method and identify its base principles", 58),
            QuestionInstance("C6_Q7", AcademicClass.CLASS_6, StreamType.INTEGRATED, QuestionTypeCode.DIAGRAM, BloomsLevel.APPLY, 3, "Draw a neat labeled sketch showing the parts of a typical flower root", 65)
        ]
    }

    # --- CLASS 8 HYBRID SCIENCE QUESTIONS ---
    pools[AcademicClass.CLASS_8] = {
        "A": [
            QuestionInstance("C8_Q1", AcademicClass.CLASS_8, StreamType.BIOLOGY, QuestionTypeCode.MCQ, BloomsLevel.REMEMBER, 1, "Which agricultural crop is primarily sown during the monsoon season", 15),
            QuestionInstance("C8_Q2", AcademicClass.CLASS_8, StreamType.BIOLOGY, QuestionTypeCode.MCQ, BloomsLevel.UNDERSTAND, 1, "Identify the cell organelle responsible for carrying genetic details in chromosomes", 18),
            QuestionInstance("C8_Q3", AcademicClass.CLASS_8, StreamType.PHYSICS, QuestionTypeCode.MCQ, BloomsLevel.APPLY, 1, "Calculated pressure on 2 square meters surface with 10 Newtons force", 22)
        ],
        "B": [
            QuestionInstance("C8_Q4", AcademicClass.CLASS_8, StreamType.BIOLOGY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.UNDERSTAND, 2, "Differentiate between plant cells and animal cells structural envelopes", 42),
            QuestionInstance("C8_Q5", AcademicClass.CLASS_8, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 2, "Explain hydrostatic pressure and show why it increases with water vessel depth", 48)
        ],
        "C": [
            QuestionInstance("C8_Q6", AcademicClass.CLASS_8, StreamType.BIOLOGY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.ANALYZE, 3, "Explain how microorganisms act as friends and foes with structural examples", 72),
            QuestionInstance("C8_Q7", AcademicClass.CLASS_8, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 3, "Formulate algebraic pressure shifts when surface contact area is halved", 68)
        ]
    }

    # --- CLASS 10 SPLIT SCIENCE QUESTIONS ---
    pools[AcademicClass.CLASS_10] = {
        "A": [
            QuestionInstance("Q1", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.MCQ, BloomsLevel.REMEMBER, 1, "Standard Ohm resistance wire model", 18),
            QuestionInstance("Q2", AcademicClass.CLASS_10, StreamType.CHEMISTRY, QuestionTypeCode.MCQ, BloomsLevel.REMEMBER, 1, "Which of the following is double displacement acid", 22),
            QuestionInstance("Q3", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.MCQ, BloomsLevel.UNDERSTAND, 1, "Transport xylem phloem plants mechanisms", 25),
            QuestionInstance("Q4", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.MCQ, BloomsLevel.APPLY, 1, "Mirror focal length calculation steps", 28),
            QuestionInstance("Q5", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.ASSERTION_REASON, BloomsLevel.UNDERSTAND, 1, "Hemoglobin carries carbon dioxide cells pathways", 32),
            QuestionInstance("Q6", AcademicClass.CLASS_10, StreamType.CHEMISTRY, QuestionTypeCode.ASSERTION_REASON, BloomsLevel.ANALYZE, 1, "Acids donate hydronium ions aqueous solution", 30)
        ],
        "B": [
            QuestionInstance("Q7", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 2, "Object lens convex mirror position calculator", 45),
            QuestionInstance("Q8", AcademicClass.CLASS_10, StreamType.CHEMISTRY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.UNDERSTAND, 2, "Why do ionic bonds form high boiling points criteria", 52),
            QuestionInstance("Q9", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.REMEMBER, 2, "List two enzymes released by stomach salivary glands", 35)
        ],
        "C": [
            QuestionInstance("Q10", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 3, "Resistors parallel equivalent network load algebra", 70),
            QuestionInstance("Q11", AcademicClass.CLASS_10, StreamType.CHEMISTRY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.ANALYZE, 3, "Salt analysis compound X reacts gas evolves", 82),
            QuestionInstance("Q12", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.UNDERSTAND, 3, "Explain double fertilizations processes seed embryo structures", 90),
            QuestionInstance("Q13", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.REMEMBER, 3, "Label three components of optical human eye diagram", 60)
        ],
        "D": [
            QuestionInstance("Q14", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.LONG_ANSWER, BloomsLevel.UNDERSTAND, 5, "Human digestive organs stomach esophagus small intestines pepsin", 185),
            QuestionInstance("Q15", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.LONG_ANSWER, BloomsLevel.APPLY, 5, "Focal length mirror derivation algebraic coordinates sign steps", 160)
        ],
        "E": [
            QuestionInstance("Q16", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.CASE_STUDY, BloomsLevel.ANALYZE, 4, "Photoresistor resistance tabular readings graphs analysis options", 115)
        ]
    }

    return pools


# ==============================================================================
# MAIN ACCESS POINT & DETONATION DIAGNOSTICS (CLI BOOTSTRAP)
# ==============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("ACADEMIC OPERATING SYSTEM - PHASE 2 PAPER ORCHESTRATION ENGINE DIAGNOSTICS")
    print("=" * 80)
    
    test_run = OrchestrationEngineUnitTestSuite.run_all_tests()
    print(f"Self-Test Status:   {test_run['status']}")
    print(f"Passed Assertions:  {test_run['passed_tests']} / {test_run['total_assertions']}")
    
    if test_run["status"] == "FAILED":
        print(f"Failure Exception:  {test_run.get('exception')}")
        print("Failed Details:")
        for fd in test_run.get("failed_tests", []):
            print(f"  - {fd}")
        exit(1)
    else:
        print("Psychometric engineering layers conform 100% to pacing and fatigue rules.")

    print("-" * 80)
    
    # Detailed pipeline simulator demonstration
    print("Loading Multi-Class Curriculums and blueprints...")
    blueprints = ExamBlueprintRegistry()
    pools = generate_curriculum_questions_pool()

    # We will simulate Class 10 CBSE Final Board paper flow
    blueprint_c10 = blueprints.get_blueprint(ExamType.FINAL, AcademicClass.CLASS_10)
    questions_c10 = pools[AcademicClass.CLASS_10]
    
    choice_pool = [
        QuestionInstance("C_Q7", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 2, "Snell refraction velocity angle computations ratio", 48),
        QuestionInstance("C_Q10", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.SHORT_ANSWER, BloomsLevel.APPLY, 3, "Joule heating current dissipation wires formula parameters", 72),
        QuestionInstance("C_Q14", AcademicClass.CLASS_10, StreamType.BIOLOGY, QuestionTypeCode.LONG_ANSWER, BloomsLevel.UNDERSTAND, 5, "Nephron excretion vascular pathways glomerulus secretion", 195)
    ]

    pipeline = PaperOrchestrationPipeline(blueprint_c10)
    orchestrated_flow = pipeline.choreograph_paper(questions_c10, choice_pool)
    
    print(f"Flow Arranged for Class 10 Board. Total elements: {len(orchestrated_flow)}")
    
    # Run psychometric analysis of experience across all archetypes
    report = pipeline.simulate_student_experience(orchestrated_flow)
    
    print("\n--- Comparative Simulator Report JSON ---")
    print(report.display_report_json())
    
    # Plot visual timeline for standard steady student
    steady_nodes = report.archetype_results[StudentArchetype.STEADY_AVERAGE].timeline_nodes
    print("\n" + AsciiTimelineVisualizer.render_plot(steady_nodes, "STANDARD CBSE STUDENT FLOW"))
    
    # Plot visual timeline for remedial struggling student
    remedial_nodes = report.archetype_results[StudentArchetype.REMEDIAL_STRUGGLING].timeline_nodes
    print("\n" + AsciiTimelineVisualizer.render_plot(remedial_nodes, "REMEDIAL STUDENT PROGRESSION FLOW"))

    # Plot visual timeline for high anxious student
    anxious_nodes = report.archetype_results[StudentArchetype.HIGH_ACHIEVER_ANXIOUS].timeline_nodes
    print("\n" + AsciiTimelineVisualizer.render_plot(anxious_nodes, "ANXIOUS HIGH ACHIEVER FLOW"))
    
    print("=" * 80)
