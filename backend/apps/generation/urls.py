from django.urls import path

from .views import (
    AnswerKeyView,
    AnswerScriptGenerateView,
    GenerationHistoryListView,
    PaperFromBankView,
    QuestionBankSummaryView,
    QuestionGenerationStreamView,
    TestScienceEngineView,
)

urlpatterns = [
    path("questions/stream", QuestionGenerationStreamView.as_view(), name="question-stream"),
    # Assemble a paper from saved questions — skips Model 1 entirely.
    path("paper-from-bank", PaperFromBankView.as_view(), name="paper-from-bank"),
    path("bank-summary", QuestionBankSummaryView.as_view(), name="bank-summary"),
    path("answer-key", AnswerKeyView.as_view(), name="answer-key"),
    path("history", GenerationHistoryListView.as_view(), name="generation-history"),
    path("test-science-engine", TestScienceEngineView.as_view(), name="test-science-engine"),
    path("papers/<str:paper_id>/generate-answer-script/", AnswerScriptGenerateView.as_view(), name="generate-answer-script"),
]
