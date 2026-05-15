from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Count
from django.core.cache import cache
from django.http import Http404
from apps.projects.serializers import (
    ProjectSerializer,
    SaveQuestionsSerializer,
    PaperListSerializer,
    PaperDetailSerializer,
)
from services.project_service import (
    list_projects_for_user,
    save_questions_to_project,
    list_papers_for_user,
    get_paper_for_user,
)


class ProjectListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # By default return a lightweight project summary (no nested questions)
        # Clients can request nested questions by setting ?withQuestions=true
        with_questions = str(request.query_params.get("withQuestions", "false")).lower() == "true"

        if with_questions:
            projects = list_projects_for_user(request.user)
            return Response(ProjectSerializer(projects, many=True).data)

        cache_key = f"user_projects_summary:{request.user.id}"
        data = cache.get(cache_key)
        if data is not None:
            return Response(data)

        qs = (
            # annotate once with a question count and only fetch required fields
            # to minimize DB and serialization work for simple views
            __import__("apps.projects.models", fromlist=["Project"]).Project.objects
            .filter(user=request.user)
            .annotate(question_count=Count("questions"))
            .order_by("-created_at")
            .values("id", "name", "description", "created_at", "updated_at", "question_count")
        )

        data = list(qs)
        # cache briefly to speed repeated simple requests
        cache.set(cache_key, data, timeout=10)
        return Response(data)


class SaveQuestionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SaveQuestionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = save_questions_to_project(
            user=request.user,
            project_name=serializer.validated_data["projectName"],
            questions=serializer.validated_data["questions"],
        )
        return Response({"success": True, "projectId": project.id})


class PaperListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        papers = list_papers_for_user(request.user)
        return Response(PaperListSerializer(papers, many=True).data)


class PaperDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, paper_id: str):
        try:
            paper = get_paper_for_user(request.user, paper_id)
        except Exception as exc:
            raise Http404("Paper not found") from exc

        return Response(PaperDetailSerializer(paper).data)
