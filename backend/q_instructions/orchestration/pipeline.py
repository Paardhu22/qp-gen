"""
AOS Orchestration — Psychometric Simulation Pipeline
========================================================
Runs high-fidelity student simulators over generated papers to audit
cognitive pacing, fatigue buildup, and anxiety spikes chronologically.
"""

from dataclasses import dataclass
from typing import List, Dict

from q_instructions.core.enums import StudentArchetype, BloomsLevel
from q_instructions.core.datatypes import QuestionInstance, StudentPsychologicalState
from q_instructions.orchestration.psychology import StudentProfileRegistry, PaperRhythmEngine


@dataclass(frozen=True)
class SimulationStepResult:
    """Psychometric state of a student at a single question milestone."""
    question_id: str
    fatigue: float
    anxiety: float
    time_elapsed: float
    cognitive_load: float


@dataclass(frozen=True)
class ArchetypeSimulationResult:
    """Full exam-take simulation results for a specific student archetype."""
    archetype: StudentArchetype
    steps: List[SimulationStepResult]
    completed: bool
    final_fatigue: float
    final_anxiety: float
    total_time_minutes: float


@dataclass(frozen=True)
class PsychometricAssessmentReport:
    """Full paper audit report aggregating all simulation results."""
    paper_id: str
    archetype_results: Dict[StudentArchetype, ArchetypeSimulationResult]
    has_cognitive_collapse_risk: bool
    remediation_suggestions: List[str]


class PaperOrchestrationPipeline:
    """Simulates multi-archetype exam taking to audit structural rhythm."""

    def __init__(self) -> None:
        self.profile_registry = StudentProfileRegistry()

    def audit_paper_rhythm(
        self, paper_id: str, questions: List[QuestionInstance]
    ) -> PsychometricAssessmentReport:
        """Runs simulations across all four student archetypes to audit paper rhythm."""
        results: Dict[StudentArchetype, ArchetypeSimulationResult] = {}
        collapse_risk = False
        remediations: List[str] = []

        for arch in StudentArchetype:
            profile = self.profile_registry.get_profile(arch)
            engine = PaperRhythmEngine(profile)
            state = StudentPsychologicalState()
            steps: List[SimulationStepResult] = []

            for idx, q in enumerate(questions):
                # Estimate duration based on marks and Bloom level
                base_time = q.assigned_marks * 120  # 2 minutes per mark
                if q.blooms_level in [BloomsLevel.ANALYZE, BloomsLevel.EVALUATE]:
                    base_time = int(base_time * 1.3)

                stimulus = engine.calculate_stimulus(q.blooms_level, base_time, idx)
                state = engine.transition_state(state, stimulus)

                steps.append(SimulationStepResult(
                    question_id=q.question_id,
                    fatigue=state.current_fatigue,
                    anxiety=state.current_anxiety,
                    time_elapsed=state.time_elapsed_minutes,
                    cognitive_load=state.cognitive_load_cumulative
                ))

            # Audit final levels
            if state.current_fatigue > 0.85 or state.current_anxiety > 0.80:
                if arch in [StudentArchetype.STEADY_AVERAGE, StudentArchetype.REMEDIAL_STRUGGLING]:
                    collapse_risk = True
                    remediations.append(
                        f"Archetype '{arch.value}' experiences extreme fatigue/panic near question '{questions[-1].question_id}'."
                    )

            results[arch] = ArchetypeSimulationResult(
                archetype=arch,
                steps=steps,
                completed=state.time_elapsed_minutes <= 180.0,
                final_fatigue=state.current_fatigue,
                final_anxiety=state.current_anxiety,
                total_time_minutes=state.time_elapsed_minutes
            )

        if collapse_risk:
            remediations.append("Aesthetic recommendation: Interleave low-marks recall relief questions before cognitive spikes.")

        return PsychometricAssessmentReport(
            paper_id=paper_id,
            archetype_results=results,
            has_cognitive_collapse_risk=collapse_risk,
            remediation_suggestions=remediations
        )


class AsciiTimelineVisualizer:
    """Renders textual psychometric progression bars for paper logs."""

    @staticmethod
    def render_timeline(result: ArchetypeSimulationResult) -> str:
        """Returns ASCII bar chart showing fatigue buildup over course of exam."""
        lines = [f"=== Psychometric Simulation Timeline: {result.archetype.value} ==="]
        for step in result.steps:
            bar_len = int(step.fatigue * 20)
            bar = "#" * bar_len + "-" * (20 - bar_len)
            lines.append(f" {step.question_id:10} |[{bar}]| Fatigue: {step.fatigue:.2f} | Anxiety: {step.anxiety:.2f}")
        return "\n".join(lines)
