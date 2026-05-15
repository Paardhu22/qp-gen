from django.urls import path

from .views import ProjectListView, SaveQuestionsView, PaperListView, PaperDetailView, QuestionDetailView

urlpatterns = [
    path("", ProjectListView.as_view(), name="project-list"),
    path("questions/save", SaveQuestionsView.as_view(), name="save-questions"),
    path("questions/<str:question_id>/", QuestionDetailView.as_view(), name="question-detail"),
    path("papers/", PaperListView.as_view(), name="paper-list"),
    path("papers/<str:paper_id>/", PaperDetailView.as_view(), name="paper-detail"),
]
