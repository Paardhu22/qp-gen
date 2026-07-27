from django.conf import settings
from django.urls import path

from .views import (
    AnswerKeyView,
    AnswerScriptGenerateView,
    GenerationHistoryListView,
    PaperFromBankView,
    QuestionBankSummaryView,
    QuestionGenerationStreamView,
    ReplaceQuestionView,
    TestScienceEngineView,
)

urlpatterns = [
    path("questions/stream", QuestionGenerationStreamView.as_view(), name="question-stream"),
    # Assemble a paper from saved questions — skips Model 1 entirely.
    path("paper-from-bank", PaperFromBankView.as_view(), name="paper-from-bank"),
    # Regenerate exactly one question, preserving its blueprint slot.
    path("replace-question", ReplaceQuestionView.as_view(), name="replace-question"),
    path("bank-summary", QuestionBankSummaryView.as_view(), name="bank-summary"),
    path("answer-key", AnswerKeyView.as_view(), name="answer-key"),
    path("history", GenerationHistoryListView.as_view(), name="generation-history"),
    path("papers/<str:paper_id>/generate-answer-script/", AnswerScriptGenerateView.as_view(), name="generate-answer-script"),
]

# Diagnostic vertical-slice runner. Every POST triggers a REAL blueprint
# generation and spends OpenAI budget on a hard-coded Class 10 Science paper
# that no user asked for, so it is not routed on a deployed host: any
# authenticated account could run up the bill, and nothing in the product
# calls it. Enable deliberately with ENABLE_TEST_ENDPOINTS=true (or DEBUG) when
# you actually want to exercise the engine.
if settings.ENABLE_TEST_ENDPOINTS:
    urlpatterns.append(
        path(
            "test-science-engine",
            TestScienceEngineView.as_view(),
            name="test-science-engine",
        )
    )
