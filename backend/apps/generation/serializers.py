from rest_framework import serializers

from apps.generation.models import GenerationHistory


class GenerationHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GenerationHistory
        fields = ["id", "prompt", "settings", "result", "created_at"]


class QuestionGenerationSerializer(serializers.Serializer):
    pdfSourceIds = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    hsatSourceIds = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    topic = serializers.CharField(required=False, allow_blank=True, default="")
    count = serializers.IntegerField(min_value=-1, max_value=50)
    difficulty = serializers.CharField()
    instructions = serializers.CharField(required=False, allow_blank=True, default="")
    board = serializers.CharField(required=False, allow_blank=True, default="")
    subject = serializers.CharField(required=False, allow_blank=True, default="")
    class_level = serializers.CharField(source="class", required=False, allow_blank=True, default="")
    countVariation = serializers.CharField(required=False, allow_blank=True, default="")
    count_variation = serializers.CharField(required=False, allow_blank=True, default="")
    qp_type = serializers.CharField(required=False, allow_blank=True, default="board")
    qpType = serializers.CharField(required=False, allow_blank=True, default="")
    #: 1 (Set A only), 2 (A, B) or 3 (A, B, C). Set A is the master; extra sets
    #: are derived from the same pool without a second Model 1 run.
    sets = serializers.IntegerField(min_value=1, max_value=3, required=False, default=1)

    def validate(self, attrs):
        """At least one of pdfSourceIds / hsatSourceIds must be non-empty."""
        if not attrs.get("pdfSourceIds") and not attrs.get("hsatSourceIds"):
            raise serializers.ValidationError(
                {
                    "pdfSourceIds": (
                        "Provide at least one PDF source or HSAT source ID."
                    )
                }
            )
        return attrs


class AnswerKeySerializer(serializers.Serializer):
    paperContentHTML = serializers.CharField()


class PaperFromBankSerializer(serializers.Serializer):
    """Assemble a paper from questions already saved in the user's bank.

    No source IDs: Model 1 does not run, so there is nothing to ingest. The
    bank is narrowed by subject/class/chapters (or explicit project IDs) and
    Model 2 selects from whatever that returns.
    """

    subject = serializers.CharField(required=False, allow_blank=True, default="")
    class_level = serializers.IntegerField(source="class", required=False, default=10)
    chapters = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    projectIds = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    topic = serializers.CharField(required=False, allow_blank=True, default="")
    difficulty = serializers.CharField(required=False, allow_blank=True, default="medium")
    instructions = serializers.CharField(required=False, allow_blank=True, default="")
    count = serializers.IntegerField(min_value=-1, max_value=50, required=False, default=-1)
    countVariation = serializers.CharField(required=False, allow_blank=True, default="cbse")
    qp_type = serializers.CharField(required=False, allow_blank=True, default="board")
    #: Skips Model 2's review call, so the same bank + blueprint always yields
    #: the identical paper. Useful when two teachers must set the same paper.
    deterministic = serializers.BooleanField(required=False, default=False)
    #: 1, 2 or 3 sets. Set A is assembled from the bank; B and C are derived.
    sets = serializers.IntegerField(min_value=1, max_value=3, required=False, default=1)
