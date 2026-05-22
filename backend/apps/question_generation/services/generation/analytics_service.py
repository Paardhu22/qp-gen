from typing import List

from ...domain.analytics.dashboard import DiagnosticsDashboardCalculator
from ...domain.datatypes import PaperAnalyticsDashboard, QuestionInstance


class AnalyticsService:
    def __init__(self) -> None:
        self._calculator = DiagnosticsDashboardCalculator()

    def compute(self, questions: List[QuestionInstance], concept_ids: List[str]) -> PaperAnalyticsDashboard:
        return self._calculator.compile_dashboard(questions, concept_ids)
