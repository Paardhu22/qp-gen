from rest_framework import serializers

from apps.projects.models import Project, Question, Paper


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ["id", "type", "content", "answer", "options", "marks", "bloom_taxonomy", "grade_class", "subject", "inferred_topic", "inferred_chapter", "source_pdf", "difficulty"]
        read_only_fields = ["id"]


class ProjectSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = ["id", "name", "description", "questions", "created_at", "updated_at"]


class PaperListSerializer(serializers.ModelSerializer):
    projectName = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = Paper
        fields = ["id", "title", "projectName", "created_at", "updated_at"]


class PaperDetailSerializer(serializers.ModelSerializer):
    projectName = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = Paper
        fields = ["id", "title", "content", "projectName", "created_at", "updated_at"]


class SaveQuestionsSerializer(serializers.Serializer):
    projectName = serializers.CharField(required=False, allow_null=True, default=None)
    questions = QuestionSerializer(many=True)


class SavePaperSerializer(serializers.Serializer):
    projectName = serializers.CharField()
    title = serializers.CharField()
    content = serializers.CharField()
    questions = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
