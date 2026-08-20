from django.urls import path

from .views import (
    ClearAllPapersView,
    ClearAllQuestionsView,
    DraftListView,
    DraftScopeView,
    PaperDetailView,
    PaperListView,
    PaperRestoreView,
    PaperTrashView,
    ProjectListView,
    QuestionDetailView,
    QuestionTypeListView,
    SaveQuestionsView,
)

urlpatterns = [
    path("", ProjectListView.as_view(), name="project-list"),
    path("drafts", DraftListView.as_view(), name="draft-list"),
    path("drafts/<str:scope>", DraftScopeView.as_view(), name="draft-scope"),
    path("questions/save", SaveQuestionsView.as_view(), name="save-questions"),
    path("questions/clear", ClearAllQuestionsView.as_view(), name="clear-questions"),
    path("questions/types", QuestionTypeListView.as_view(), name="question-types"),
    path("questions/<str:question_id>/", QuestionDetailView.as_view(), name="question-detail"),
    # Literal paper routes before `<str:paper_id>` — Django matches in order,
    # and the id pattern would otherwise swallow "clear" and "trash".
    path("papers/clear", ClearAllPapersView.as_view(), name="clear-papers"),
    path("papers/trash", PaperTrashView.as_view(), name="paper-trash"),
    path("papers/", PaperListView.as_view(), name="paper-list"),
    path("papers/<str:paper_id>/restore", PaperRestoreView.as_view(), name="paper-restore"),
    path("papers/<str:paper_id>/", PaperDetailView.as_view(), name="paper-detail"),
]
