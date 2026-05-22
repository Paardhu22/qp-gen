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
            pdf_source_ids=serializer.validated_data["pdfSourceIds"],
            topic=serializer.validated_data["topic"],
            count=serializer.validated_data["count"],
            difficulty=serializer.validated_data["difficulty"],
            instructions=serializer.validated_data["instructions"],
            payload=request.data,
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

from rest_framework.permissions import AllowAny
import dataclasses

class TestScienceEngineView(APIView):
    """
    Isolated integration test view for the new AOS Academic Generation Facade.
    Executes a real generation pipeline for a single vertical slice:
    CBSE -> Class 10 -> Science -> Electricity chapter.
    """
    permission_classes = [AllowAny] # Set to AllowAny for testing the vertical slice

    def post(self, request):
        from q_instructions.master.facade import AcademicGenerationFacade, GeneratePaperRequest
        
        facade = AcademicGenerationFacade()
        
        # Hardcoded parameters for the isolated vertical slice test
        paper_req = GeneratePaperRequest(
            board="CBSE",
            academic_class="CLASS_10",
            exam_type="FINAL",
            chapters=["Electricity"],
            difficulty="medium",
            institution_id="DPS_E_DELHI",
            seed=42
        )
        
        try:
            # Execute the real generation flow
            response_dto = facade.generate_paper(paper_req)
            
            # Convert the dataclass to dict for JSON serialization
            response_data = dataclasses.asdict(response_dto)
            
            return Response({
                "status": "success",
                "message": "Science engine vertical slice executed successfully.",
                "data": response_data
            })
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=500)

