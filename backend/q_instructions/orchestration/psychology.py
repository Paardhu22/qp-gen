"""
AOS Orchestration — Psychometric Simulation & Psychology Models
================================================================
Models student profile registries, psychometric states, stimulus deltas,
and cognitive progression curves for paper fatigue balancing.
"""

import math
from typing import Dict

from q_instructions.core.enums import StudentArchetype, CognitiveCurveShape, BloomsLevel
from q_instructions.core.datatypes import StudentProfile, StudentPsychologicalState, PsychometricStimulus


class StudentProfileRegistry:
    """Preloads realistic, benchmarked psychometric profiles for standard student archetypes."""

    def __init__(self) -> None:
        self._profiles: Dict[StudentArchetype, StudentProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        # Standard average student profile
        self._profiles[StudentArchetype.STEADY_AVERAGE] = StudentProfile(
            archetype=StudentArchetype.STEADY_AVERAGE,
            baseline_proficiency=0.72,
            anxiety_baseline=0.15,
            fatigue_resistance=1.0,
            recovery_multiplier=1.0,
            time_pressure_sensitivity=1.0
        )

        # High proficiency, but high resting anxiety
        self._profiles[StudentArchetype.HIGH_ACHIEVER_ANXIOUS] = StudentProfile(
            archetype=StudentArchetype.HIGH_ACHIEVER_ANXIOUS,
            baseline_proficiency=0.92,
            anxiety_baseline=0.35,
            fatigue_resistance=1.2,
            recovery_multiplier=0.8,
            time_pressure_sensitivity=1.8
        )

        # Remedial/struggling student profile
        self._profiles[StudentArchetype.REMEDIAL_STRUGGLING] = StudentProfile(
            archetype=StudentArchetype.REMEDIAL_STRUGGLING,
            baseline_proficiency=0.45,
            anxiety_baseline=0.25,
            fatigue_resistance=0.6,
            recovery_multiplier=1.5,
            time_pressure_sensitivity=1.2
        )

        # Olympiad elite student profile
        self._profiles[StudentArchetype.OLYMPIAD_ELITE] = StudentProfile(
            archetype=StudentArchetype.OLYMPIAD_ELITE,
            baseline_proficiency=0.98,
            anxiety_baseline=0.02,
            fatigue_resistance=2.5,
            recovery_multiplier=2.0,
            time_pressure_sensitivity=0.2
        )

    def get_profile(self, archetype: StudentArchetype) -> StudentProfile:
        """Fetches profile for given simulator archetype."""
        if archetype not in self._profiles:
            raise KeyError(f"Archetype {archetype.name} not registered.")
        return self._profiles[archetype]


class PaperRhythmEngine:
    """Calculates student state changes upon attempting examination questions."""

    def __init__(self, profile: StudentProfile) -> None:
        self.profile = profile

    def calculate_stimulus(
        self, bloom_level: BloomsLevel, duration_seconds: int, question_index: int
    ) -> PsychometricStimulus:
        """Determines fatigue and anxiety impacts of a question on a student."""
        # Baseline cognitive coefficients
        bloom_load = {
            BloomsLevel.REMEMBER: 1.0,
            BloomsLevel.UNDERSTAND: 1.8,
            BloomsLevel.APPLY: 3.2,
            BloomsLevel.ANALYZE: 4.5,
            BloomsLevel.EVALUATE: 5.2,
            BloomsLevel.CREATE: 6.0
        }.get(bloom_level, 2.0)

        # Calculate fatigue delta
        fatigue_delta = (duration_seconds / 60.0) * (bloom_load / 3.0) * (1.0 / self.profile.fatigue_resistance)

        # Calculate anxiety delta
        anxiety_delta = (bloom_load * 0.04) * self.profile.time_pressure_sensitivity
        if question_index < 3 and bloom_level in [BloomsLevel.REMEMBER, BloomsLevel.UNDERSTAND]:
            # Anxiety relief warmup bonus
            anxiety_delta *= -0.5

        # Identify relief questions
        is_relief = bloom_level == BloomsLevel.REMEMBER and question_index > 5

        return PsychometricStimulus(
            fatigue_delta=fatigue_delta,
            anxiety_delta=anxiety_delta,
            estimated_minutes=duration_seconds / 60.0,
            is_relief_question=is_relief,
            bloom_cognitive_load=bloom_load
        )

    def transition_state(
        self, state: StudentPsychologicalState, stimulus: PsychometricStimulus
    ) -> StudentPsychologicalState:
        """Transitions state based on stimulus."""
        # Calculate new fatigue
        if stimulus.is_relief_question:
            fatigue_decay = 0.08 * self.profile.recovery_multiplier
            new_fatigue = max(state.current_fatigue - fatigue_decay, 0.0)
        else:
            new_fatigue = min(state.current_fatigue + stimulus.fatigue_delta, 1.0)

        # Calculate new anxiety
        new_anxiety = min(state.current_anxiety + stimulus.anxiety_delta, 1.0)
        new_anxiety = max(new_anxiety, 0.0)

        return StudentPsychologicalState(
            current_fatigue=new_fatigue,
            current_anxiety=new_anxiety,
            questions_attempted=state.questions_attempted + 1,
            marks_attempted=state.marks_attempted,
            time_elapsed_minutes=state.time_elapsed_minutes + stimulus.estimated_minutes,
            cognitive_load_cumulative=state.cognitive_load_cumulative + stimulus.bloom_cognitive_load
        )


class CognitiveCurveEngine:
    """Models exam section-wise pacing and target difficulty levels."""

    def evaluate_cognitive_demand(
        self, shape: CognitiveCurveShape, x: float
    ) -> float:
        """Returns cognitive demand [0.0, 1.0] for a normalized position x [0.0, 1.0]."""
        if x < 0.0 or x > 1.0:
            raise ValueError("Position x must be in range [0.0, 1.0]")

        if shape == CognitiveCurveShape.LINEAR_ASCENDING:
            return 0.2 + 0.7 * x
        elif shape == CognitiveCurveShape.EXPONENTIAL_SPIKE:
            return 0.15 + 0.8 * (x ** 3)
        elif shape == CognitiveCurveShape.SINUSOIDAL_WAVE:
            return 0.4 + 0.3 * math.sin(x * 2.0 * math.pi)
        elif shape == CognitiveCurveShape.PLATEAU_SUSTAIN:
            if x < 0.2:
                return 0.2 + 2.5 * x
            return 0.7
        return 0.5
