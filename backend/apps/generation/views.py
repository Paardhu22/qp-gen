from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.generation.models import GenerationHistory
from apps.generation.serializers import (
    AnswerKeySerializer,
    GenerationHistorySerializer,
    PaperFromBankSerializer,
    QuestionGenerationSerializer,
)
from services.openai_service import generate_answer_key
from services.pool.pipeline import stream_pool_questions


class QuestionGenerationStreamView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = QuestionGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        stream = stream_pool_questions(
            user=request.user,
            pdf_source_ids=serializer.validated_data.get("pdfSourceIds") or [],
            topic=serializer.validated_data["topic"],
            count=serializer.validated_data["count"],
            difficulty=serializer.validated_data["difficulty"],
            instructions=serializer.validated_data["instructions"],
            payload=request.data,
            hsat_source_ids=serializer.validated_data.get("hsatSourceIds") or [],
        )

        response = StreamingHttpResponse(stream, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class PaperFromBankView(APIView):
    """POST /api/generation/paper-from-bank

    Assembles a paper from the user's saved questions. Model 1 never runs, so
    a chapter that has been generated once costs a single Model 2 call to
    re-paper — the reuse payoff of persisting the pool per-row.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from services.pool.from_bank import stream_paper_from_bank

        serializer = PaperFromBankSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        stream = stream_paper_from_bank(
            request.user,
            subject=data.get("subject") or "",
            class_num=int(data.get("class") or 10),
            chapters=data.get("chapters") or [],
            project_ids=data.get("projectIds") or [],
            topic=data.get("topic") or "",
            difficulty=data.get("difficulty") or "medium",
            instructions=data.get("instructions") or "",
            count=int(data.get("count", -1)),
            count_variation=data.get("countVariation") or "cbse",
            qp_type=data.get("qp_type") or "board",
            deterministic=bool(data.get("deterministic")),
            payload=request.data,
        )

        response = StreamingHttpResponse(stream, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class QuestionBankSummaryView(APIView):
    """GET /api/generation/bank-summary

    Per-chapter counts, so the "Create Paper from Saved Questions" picker can
    show what is available before the teacher commits to a selection.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from services.pool.store import bank_summary

        return Response({"chapters": bank_summary(user=request.user)})


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

import dataclasses

class TestScienceEngineView(APIView):
    """
    Isolated integration test view for the new AOS Academic Generation Facade.
    Executes a real generation pipeline for a single vertical slice:
    CBSE -> Class 10 -> Science -> Electricity chapter.

    Auth required: this endpoint triggers REAL LLM calls (it spends OpenAI
    budget), so it must never be reachable anonymously on a deployed host.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.conf import settings

        if settings.QG_NEW_ENGINE_ENABLED:
            from apps.question_generation.services.facade import AcademicGenerationFacade, GeneratePaperRequest
        else:
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
            seed=42,
        )
        
        try:
            # Execute the real generation flow
            if settings.QG_NEW_ENGINE_ENABLED:
                response_dto = facade.generate_paper(paper_req)
            else:
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


class AnswerScriptGenerateView(APIView):
    """
    POST /api/generation/papers/<paper_id>/generate-answer-script/

    Generates a CBSE-style marking scheme / answer script for an existing
    paper. The answer script is saved as a NEW separate paper.

    Returns:
        { "answer_script_paper_id": "...", "editor_url": "/editor?paperId=..." }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, paper_id: str):
        from services.answer_script_service import generate_answer_script

        try:
            result = generate_answer_script(paper_id=paper_id, user=request.user)
            return Response(result, status=201)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=400)
        except Exception as exc:
            import logging
            logging.getLogger("[ANSWER_SCRIPT_VIEW]").error(
                "Answer script generation failed: %s", exc, exc_info=True
            )
            return Response(
                {"error": "Failed to generate answer script. Please try again."},
                status=500,
            )

