from rest_framework import serializers

from apps.projects.models import Project, Question


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ["id", "type", "content", "answer", "options", "marks", "bloom_taxonomy"]
        read_only_fields = ["id"]


class ProjectSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = ["id", "name", "description", "questions", "created_at", "updated_at"]


class SaveQuestionsSerializer(serializers.Serializer):
    projectName = serializers.CharField()
    questions = QuestionSerializer(many=True)
