from django.urls import path

from .views import ProjectListView, SaveQuestionsView

urlpatterns = [
    path("", ProjectListView.as_view(), name="project-list"),
    path("questions/save", SaveQuestionsView.as_view(), name="save-questions"),
]
