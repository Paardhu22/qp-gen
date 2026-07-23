from django.urls import path

from .views import ProjectListView, SaveQuestionsView, PaperListView, PaperDetailView, QuestionDetailView, ClearAllQuestionsView, ClearAllPapersView, QuestionTypeListView

urlpatterns = [
    path("", ProjectListView.as_view(), name="project-list"),
    path("questions/save", SaveQuestionsView.as_view(), name="save-questions"),
    path("questions/clear", ClearAllQuestionsView.as_view(), name="clear-questions"),
    path("questions/types", QuestionTypeListView.as_view(), name="question-types"),
    path("questions/<str:question_id>/", QuestionDetailView.as_view(), name="question-detail"),
    path("papers/clear", ClearAllPapersView.as_view(), name="clear-papers"),
    path("papers/", PaperListView.as_view(), name="paper-list"),
    path("papers/<str:paper_id>/", PaperDetailView.as_view(), name="paper-detail"),
]
