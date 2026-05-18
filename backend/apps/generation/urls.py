from django.urls import path

from .views import AnswerKeyView, GenerationHistoryListView, QuestionGenerationStreamView

urlpatterns = [
    path("questions/stream", QuestionGenerationStreamView.as_view(), name="question-stream"),
    path("answer-key", AnswerKeyView.as_view(), name="answer-key"),
    path("history", GenerationHistoryListView.as_view(), name="generation-history"),
]
