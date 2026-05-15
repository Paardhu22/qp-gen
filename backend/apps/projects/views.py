from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Count
from django.core.cache import cache
from django.http import Http404
from apps.projects.models import Paper
from apps.projects.serializers import (
    ProjectSerializer,
    SaveQuestionsSerializer,
    SavePaperSerializer,
    PaperListSerializer,
    PaperDetailSerializer,
)
from services.project_service import (
    list_projects_for_user,
    save_questions_to_project,
    save_paper_to_project,
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
            # Cache the full nested response for 30 seconds to reduce DB load on repeated requests
            cache_key = f"user_projects_full:{request.user.id}"
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return Response(cached_data)

            projects = list_projects_for_user(request.user)
            data = ProjectSerializer(projects, many=True).data
            cache.set(cache_key, data, timeout=30)
            return Response(data)

        # Lightweight summary path - cached for 20 seconds
        cache_key = f"user_projects_summary:{request.user.id}"
        data = cache.get(cache_key)
        if data is not None:
            return Response(data)

        # Return only essential fields to minimize serialization and DB work
        from apps.projects.models import Project
        qs = (
            Project.objects
            .filter(user=request.user)
            .annotate(question_count=Count("questions"))
            .order_by("-created_at")
            .values("id", "name", "description", "created_at", "updated_at", "question_count")
        )

        data = list(qs)
        # cache briefly to speed repeated simple requests
        cache.set(cache_key, data, timeout=20)
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
        cache_key = f"user_papers:{request.user.id}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        papers = list_papers_for_user(request.user)
        data = PaperListSerializer(papers, many=True).data
        cache.set(cache_key, data, timeout=30)
        return Response(data)

    def post(self, request):
        serializer = SavePaperSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        paper = save_paper_to_project(
            user=request.user,
            project_name=serializer.validated_data["projectName"],
            title=serializer.validated_data["title"],
            content=serializer.validated_data["content"],
            questions=serializer.validated_data.get("questions", []),
        )
        # Bust all relevant caches so the saved page reflects the new paper immediately
        cache.delete(f"user_papers:{request.user.id}")
        cache.delete(f"user_projects_full:{request.user.id}")
        cache.delete(f"user_projects_summary:{request.user.id}")
        return Response({"success": True, "paperId": paper.id}, status=201)


class PaperDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, paper_id: str):
        cache_key = f"user_paper:{request.user.id}:{paper_id}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        try:
            paper = get_paper_for_user(request.user, paper_id)
        except Exception as exc:
            raise Http404("Paper not found") from exc

        data = PaperDetailSerializer(paper).data
        cache.set(cache_key, data, timeout=30)
        return Response(data)

    def put(self, request, paper_id: str):
        serializer = SavePaperSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            paper = save_paper_to_project(
                user=request.user,
                project_name=serializer.validated_data["projectName"],
                title=serializer.validated_data["title"],
                content=serializer.validated_data["content"],
                questions=serializer.validated_data.get("questions", []),
                paper_id=paper_id,
            )
        except Paper.DoesNotExist:
            raise Http404("Paper not found")
        # Bust caches
        cache.delete(f"user_papers:{request.user.id}")
        cache.delete(f"user_paper:{request.user.id}:{paper_id}")
        cache.delete(f"user_projects_full:{request.user.id}")
        cache.delete(f"user_projects_summary:{request.user.id}")
        return Response({"success": True, "paperId": paper.id})

    def delete(self, request, paper_id: str):
        try:
            paper = Paper.objects.get(id=paper_id, user=request.user)
        except Paper.DoesNotExist:
            raise Http404("Paper not found")
        paper.delete()
        # Bust caches
        cache.delete(f"user_papers:{request.user.id}")
        cache.delete(f"user_paper:{request.user.id}:{paper_id}")
        cache.delete(f"user_projects_full:{request.user.id}")
        cache.delete(f"user_projects_summary:{request.user.id}")
        return Response({"success": True})


class QuestionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, question_id: str):
        from apps.projects.models import Question
        try:
            question = Question.objects.get(id=question_id, project__user=request.user)
        except Question.DoesNotExist:
            raise Http404("Question not found")
        question.delete()
        # Bust project caches so the questions list refreshes
        cache.delete(f"user_projects_full:{request.user.id}")
        cache.delete(f"user_projects_summary:{request.user.id}")
        return Response({"success": True})
