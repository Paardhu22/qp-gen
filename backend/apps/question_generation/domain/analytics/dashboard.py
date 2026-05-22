"""
Question Generation Domain - Diagnostics Dashboard
"""

from typing import Dict, List

from ..datatypes import PaperAnalyticsDashboard, QuestionInstance
from ..enums import BloomsLevel, StreamType


class DiagnosticsDashboardCalculator:
    def compile_dashboard(self, questions: List[QuestionInstance], concept_ids: List[str]) -> PaperAnalyticsDashboard:
        total_marks = sum(q.assigned_marks for q in questions)
        total_qs = len(questions)

        if total_qs == 0:
            return PaperAnalyticsDashboard(0, 0, 0.0, "Empty", {}, {}, [])

        avg_marks = total_marks / total_qs
        blooms: Dict[BloomsLevel, int] = {}
        for q in questions:
            blooms[q.blooms_level] = blooms.get(q.blooms_level, 0) + 1

        streams: Dict[StreamType, float] = {}
        for q in questions:
            streams[q.stream] = streams.get(q.stream, 0.0) + q.assigned_marks

        stream_dist = {s: marks / total_marks for s, marks in streams.items()}

        avg_difficulty = sum(q.assigned_marks * 0.15 for q in questions) / total_qs
        skew = "Balanced Pace"
        if avg_difficulty > 0.70:
            skew = "Cognitive Fatigue Risk"
        elif avg_difficulty < 0.35:
            skew = "Factual Recall Heavy"

        return PaperAnalyticsDashboard(
            total_marks=total_marks,
            total_questions=total_qs,
            average_difficulty=avg_difficulty,
            difficulty_skewness=skew,
            blooms_distribution=blooms,
            stream_distribution=stream_dist,
            nep_competency_coverage=concept_ids,
        )
