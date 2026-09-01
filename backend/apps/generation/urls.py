from django.urls import path

from .design_views import (
    DesignPaperView,
    PaperTemplateDetailView,
    PaperTemplateDuplicateView,
    PaperTemplateForkView,
    PaperTemplateListView,
    QuestionImageView,
    QuestionTypeCatalogView,
    TemplateFolderDetailView,
    TemplateFolderListView,
    TemplateResolveView,
)
from .views import (
    AnswerKeyView,
    AnswerScriptGenerateView,
    GenerationHistoryListView,
    GenerationRunEventsView,
    GenerationRunListView,
    PaperFromBankView,
    QuestionBankSummaryView,
    QuestionGenerationStreamView,
    ReplaceQuestionView,
)

urlpatterns = [
    path("questions/stream", QuestionGenerationStreamView.as_view(), name="question-stream"),
    # Assemble a paper from saved questions — skips Model 1 entirely.
    path("paper-from-bank", PaperFromBankView.as_view(), name="paper-from-bank"),
    # Regenerate exactly one question, preserving its blueprint slot.
    path("replace-question", ReplaceQuestionView.as_view(), name="replace-question"),
    path("bank-summary", QuestionBankSummaryView.as_view(), name="bank-summary"),
    # Durable runs: find a generation you lost, and re-attach to it.
    path("runs", GenerationRunListView.as_view(), name="generation-runs"),
    path(
        "runs/<str:run_id>/events",
        GenerationRunEventsView.as_view(),
        name="generation-run-events",
    ),
    # General Instructions Mode: turn prose into a paper structure, and report
    # the constraints it did not settle. Cheap, writes nothing, safe to call
    # while the teacher is still typing.
    path("design-paper", DesignPaperView.as_view(), name="design-paper"),
    path("templates", PaperTemplateListView.as_view(), name="paper-templates"),
    # Compile a template (built-in or saved) into an editable blueprint. Writes
    # nothing — browsing the picker must not commit the teacher to anything.
    path("templates/resolve", TemplateResolveView.as_view(), name="template-resolve"),
    # Turn a built-in catalog entry into a row the teacher owns, so it can be
    # edited and filed like anything else. This is the one place a built-in
    # stops being generated code and becomes data.
    path("templates/fork", PaperTemplateForkView.as_view(), name="template-fork"),
    # The teacher's filing. Nothing in generation reads folders — see
    # `TemplateFolder` — so these are pure organisation endpoints.
    path(
        "template-folders",
        TemplateFolderListView.as_view(),
        name="template-folders",
    ),
    path(
        "template-folders/<str:folder_id>",
        TemplateFolderDetailView.as_view(),
        name="template-folder-detail",
    ),
    # The per-slot question-type menu for the Blueprint Builder.
    path("question-types", QuestionTypeCatalogView.as_view(), name="question-types"),
    # Draw a figure for one question, on request from the editor's hover menu.
    path("question-image", QuestionImageView.as_view(), name="question-image"),
    # Must stay below `templates/resolve` and `templates/fork`: this pattern
    # would otherwise swallow them as template ids.
    path(
        "templates/<str:template_id>/duplicate",
        PaperTemplateDuplicateView.as_view(),
        name="paper-template-duplicate",
    ),
    path(
        "templates/<str:template_id>",
        PaperTemplateDetailView.as_view(),
        name="paper-template-detail",
    ),
    path("answer-key", AnswerKeyView.as_view(), name="answer-key"),
    path("history", GenerationHistoryListView.as_view(), name="generation-history"),
    path("papers/<str:paper_id>/generate-answer-script/", AnswerScriptGenerateView.as_view(), name="generate-answer-script"),
]
