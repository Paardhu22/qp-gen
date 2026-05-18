from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.generation.models import GenerationHistory
from apps.generation.serializers import AnswerKeySerializer, GenerationHistorySerializer, QuestionGenerationSerializer
from services.generation_service import stream_generated_questions
from services.openai_service import generate_answer_key


class QuestionGenerationStreamView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = QuestionGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        stream = stream_generated_questions(
            user=request.user,
            document_ids=serializer.validated_data["documentIds"],
            topic=serializer.validated_data["topic"],
            count=serializer.validated_data["count"],
            difficulty=serializer.validated_data["difficulty"],
            instructions=serializer.validated_data["instructions"],
        )

        response = StreamingHttpResponse(stream, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class AnswerKeyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AnswerKeySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answer_key_html = generate_answer_key(serializer.validated_data["paperContentHTML"], user=request.user)
        return Response({"answerKeyHtml": answer_key_html})


class GenerationHistoryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        history = GenerationHistory.objects.filter(user=request.user).order_by("-created_at")
        serializer = GenerationHistorySerializer(history, many=True)
        return Response(serializer.data)

    def delete(self, request):
        deleted_count, _ = GenerationHistory.objects.filter(user=request.user).delete()
        return Response({"deleted": deleted_count})
