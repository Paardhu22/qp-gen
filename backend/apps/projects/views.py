from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.serializers import ProjectSerializer, SaveQuestionsSerializer
from services.project_service import list_projects_for_user, save_questions_to_project


class ProjectListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        projects = list_projects_for_user(request.user)
        return Response(ProjectSerializer(projects, many=True).data)


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
