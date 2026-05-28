from django.urls import path

from .views import AnswerKeyView, AnswerScriptGenerateView, GenerationHistoryListView, QuestionGenerationStreamView, TestScienceEngineView

urlpatterns = [
    path("questions/stream", QuestionGenerationStreamView.as_view(), name="question-stream"),
    path("answer-key", AnswerKeyView.as_view(), name="answer-key"),
    path("history", GenerationHistoryListView.as_view(), name="generation-history"),
    path("test-science-engine", TestScienceEngineView.as_view(), name="test-science-engine"),
    path("papers/<str:paper_id>/generate-answer-script/", AnswerScriptGenerateView.as_view(), name="generate-answer-script"),
]

