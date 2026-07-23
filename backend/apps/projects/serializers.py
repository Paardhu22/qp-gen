from rest_framework import serializers

from apps.projects.models import Project, Question, Paper, PaperSet, QuestionFamily, QuestionType


class QuestionFamilySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionFamily
        fields = "__all__"


class QuestionTypeSerializer(serializers.ModelSerializer):
    family = QuestionFamilySerializer(read_only=True)

    class Meta:
        model = QuestionType
        fields = "__all__"


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ["id", "type", "content", "answer", "options", "marks", "bloom_taxonomy", "grade_class", "subject", "inferred_topic", "inferred_chapter", "source_pdf", "difficulty", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProjectSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = ["id", "name", "description", "questions", "created_at", "updated_at"]


class PaperSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaperSet
        fields = ["id", "label", "order", "content", "answers", "metadata"]


class PaperListSerializer(serializers.ModelSerializer):
    projectName = serializers.CharField(source="project.name", read_only=True)
    answerScriptId = serializers.CharField(source="answer_script_id", read_only=True, allow_null=True)
    gradeClass = serializers.CharField(source="grade_class", read_only=True, allow_null=True)
    questionPoolId = serializers.CharField(source="question_pool_id", read_only=True, allow_null=True)
    sets = PaperSetSerializer(many=True, read_only=True)

    class Meta:
        model = Paper
        fields = ["id", "title", "subject", "gradeClass", "board", "projectName", "answerScriptId", "questionPoolId", "created_at", "updated_at", "sets"]


class PaperDetailSerializer(serializers.ModelSerializer):
    projectName = serializers.CharField(source="project.name", read_only=True)
    answerScriptId = serializers.CharField(source="answer_script_id", read_only=True, allow_null=True)
    gradeClass = serializers.CharField(source="grade_class", read_only=True, allow_null=True)
    questionPoolId = serializers.CharField(source="question_pool_id", read_only=True, allow_null=True)
    sets = PaperSetSerializer(many=True, read_only=True)

    class Meta:
        model = Paper
        fields = [
            "id", "title", "subject", "gradeClass", "board", "instructions", 
            "blueprint", "projectName", "answerScriptId", "questionPoolId", 
            "created_at", "updated_at", "sets"
        ]


class SaveQuestionsSerializer(serializers.Serializer):
    projectName = serializers.CharField(required=False, allow_null=True, default=None)
    questions = QuestionSerializer(many=True)


class SavePaperSetSerializer(serializers.Serializer):
    label = serializers.CharField()
    order = serializers.IntegerField(required=False, default=1)
    content = serializers.CharField()
    answers = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="")
    metadata = serializers.DictField(required=False, default=dict)


class SavePaperSerializer(serializers.Serializer):
    projectName = serializers.CharField()
    title = serializers.CharField()
    subject = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="")
    gradeClass = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="")
    board = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="")
    instructions = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="")
    blueprint = serializers.DictField(required=False, allow_null=True, default=None)
    questionPoolId = serializers.CharField(required=False, allow_null=True, allow_blank=True, default="")
    sets = SavePaperSetSerializer(many=True)
    
    questions = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    hsatSourceIds = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
