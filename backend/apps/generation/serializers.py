from rest_framework import serializers

from apps.generation.models import GenerationHistory


class GenerationHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GenerationHistory
        fields = ["id", "prompt", "settings", "result", "created_at"]


class QuestionGenerationSerializer(serializers.Serializer):
    documentIds = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    topic = serializers.CharField()
    count = serializers.IntegerField(min_value=1, max_value=50)
    difficulty = serializers.CharField()
    instructions = serializers.CharField(required=False, allow_blank=True, default="")


class AnswerKeySerializer(serializers.Serializer):
    paperContentHTML = serializers.CharField()
