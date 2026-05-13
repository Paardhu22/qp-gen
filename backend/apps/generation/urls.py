from django.urls import path

from .views import AnswerKeyView, QuestionGenerationStreamView

urlpatterns = [
    path("questions/stream", QuestionGenerationStreamView.as_view(), name="question-stream"),
    path("answer-key", AnswerKeyView.as_view(), name="answer-key"),
]
