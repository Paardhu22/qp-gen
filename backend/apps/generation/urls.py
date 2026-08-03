from django.conf import settings
from django.urls import path

from .design_views import (
    DesignPaperView,
    PaperTemplateDetailView,
    PaperTemplateListView,
    QuestionImageView,
    QuestionTypeCatalogView,
    TemplateResolveView,
)
from .run_views import (
    GenerationRunActiveView,
    GenerationRunCancelView,
    GenerationRunStartView,
    GenerationRunStreamView,
)
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
    # ── Durable runs ────────────────────────────────────────────────────
    # The generation above dies with its connection. These own the run in a
    # worker thread instead, so a reload or a dropped network can reattach to
    # a paper still being written rather than losing minutes of work.
    path("runs/", GenerationRunStartView.as_view(), name="generation-run-start"),
    path(
        "runs/active",
        GenerationRunActiveView.as_view(),
        name="generation-run-active",
    ),
    path(
        "runs/<str:run_id>/stream",
        GenerationRunStreamView.as_view(),
        name="generation-run-stream",
    ),
    path(
        "runs/<str:run_id>/cancel",
        GenerationRunCancelView.as_view(),
        name="generation-run-cancel",
    ),
    # Assemble a paper from saved questions — skips Model 1 entirely.
    path("paper-from-bank", PaperFromBankView.as_view(), name="paper-from-bank"),
    # Regenerate exactly one question, preserving its blueprint slot.
    path("replace-question", ReplaceQuestionView.as_view(), name="replace-question"),
    path("bank-summary", QuestionBankSummaryView.as_view(), name="bank-summary"),
    # General Instructions Mode: turn prose into a paper structure, and report
    # the constraints it did not settle. Cheap, writes nothing, safe to call
    # while the teacher is still typing.
    path("design-paper", DesignPaperView.as_view(), name="design-paper"),
    path("templates", PaperTemplateListView.as_view(), name="paper-templates"),
    # Compile a template (built-in or saved) into an editable blueprint. Writes
    # nothing — browsing the picker must not commit the teacher to anything.
    path("templates/resolve", TemplateResolveView.as_view(), name="template-resolve"),
    # The per-slot question-type menu for the Blueprint Builder.
    path("question-types", QuestionTypeCatalogView.as_view(), name="question-types"),
    # Draw a figure for one question, on request from the editor's hover menu.
    path("question-image", QuestionImageView.as_view(), name="question-image"),
    path(
        "templates/<str:template_id>",
        PaperTemplateDetailView.as_view(),
        name="paper-template-detail",
    ),
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
