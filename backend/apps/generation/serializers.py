from rest_framework import serializers

from apps.generation.models import GenerationHistory, PaperTemplate, TemplateFolder


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
    #: -1 means "the blueprint decides", which is the normal case: a request
    #: carrying a blueprint (or the CBSE board pattern) has no free-standing
    #: question count to send. This was required-with-no-default until the
    #: Blueprint Builder shipped a payload that legitimately omits it, and the
    #: resulting 400 surfaced on the client as an unexplained stream failure.
    #: `PaperFromBankSerializer` has always defaulted it this way — match it.
    count = serializers.IntegerField(
        min_value=-1, max_value=50, required=False, default=-1
    )
    difficulty = serializers.CharField(
        required=False, allow_blank=True, default="medium"
    )
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


class ReplacementSlotSerializer(serializers.Serializer):
    """The blueprint identity of one question, as the editor knows it.

    Mirrors the `slotMeta` blob stamped on a generated question block. Every
    field is optional except the ones that decide eligibility (`marks`,
    `type`), because a question saved before `slotMeta` existed still carries
    enough for a sensible replacement.
    """

    slotIndex = serializers.IntegerField(required=False, default=0)
    section = serializers.CharField(required=False, allow_blank=True, default="")
    marks = serializers.IntegerField(min_value=1, max_value=40)
    type = serializers.CharField()
    generator = serializers.CharField(
        required=False, allow_blank=True, default="question_pool"
    )
    assetType = serializers.CharField(required=False, allow_blank=True, default="")
    chapter = serializers.CharField(required=False, allow_blank=True, default="")
    topic = serializers.CharField(required=False, allow_blank=True, default="")
    difficulty = serializers.CharField(
        required=False, allow_blank=True, default="medium"
    )
    subject = serializers.CharField(required=False, allow_blank=True, default="")
    classNum = serializers.IntegerField(required=False, default=10)
    poolId = serializers.CharField(required=False, allow_blank=True, default="")
    questionId = serializers.CharField(required=False, allow_blank=True, default="")


class ReplaceQuestionSerializer(serializers.Serializer):
    """Regenerate one slot. `excludeIds` keeps the paper free of duplicates."""

    slot = ReplacementSlotSerializer()
    #: Question ids already on the paper — never offered as a replacement.
    excludeIds = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    #: Content hashes already on the paper, for questions with no id (e.g. a
    #: set variant rendered before the bank write completed).
    excludeHashes = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    #: Needed only when the bank is exhausted AND the slot is textbook-backed,
    #: so Model 1 can re-read the chapter.
    pdfSourceIds = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    hsatSourceIds = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False, default=list
    )
    #: False restricts the replacement to the bank — instant and free, but it
    #: can fail when nothing else fits.
    allowGeneration = serializers.BooleanField(required=False, default=True)


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


class TemplateFolderSerializer(serializers.ModelSerializer):
    """One filing folder, plus how much is in it.

    `templateCount` counts only templates filed directly here, not in
    subfolders. A folder rail that showed rolled-up counts would make an empty
    folder look populated, and the number a teacher wants beside "Term 1" is
    how many papers are in Term 1.
    """

    parentId = serializers.CharField(source="parent_id", allow_null=True, read_only=True)
    templateCount = serializers.SerializerMethodField()

    class Meta:
        model = TemplateFolder
        fields = ["id", "name", "parentId", "templateCount", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_templateCount(self, obj) -> int:
        # Uses the annotation when the view supplied one, so listing N folders
        # stays one query instead of N.
        annotated = getattr(obj, "template_count", None)
        if annotated is not None:
            return annotated
        return obj.templates.count()


class PaperTemplateSerializer(serializers.ModelSerializer):
    """A saved paper template.

    `settings` goes out as stored: its keys are generator-form field names, so
    applying a template on the client is a copy, not a translation.

    `blueprint` is re-serialised through `TemplateBlueprint` rather than handed
    over raw, so totals on the wire are always recomputed from the slots. A
    stored total could disagree with the slots it describes; a computed one
    cannot. The extra keys (`builtin`, `pinned`) let one picker render built-in
    catalog entries and saved templates from the same list without the client
    inferring the difference from which fields happen to be present.
    """

    blueprint = serializers.SerializerMethodField()
    pinned = serializers.SerializerMethodField()
    builtin = serializers.SerializerMethodField()
    folderId = serializers.CharField(source="folder_id", allow_null=True, read_only=True)

    class Meta:
        model = PaperTemplate
        fields = [
            "id",
            "name",
            "instructions",
            "settings",
            "blueprint",
            "pinned",
            "builtin",
            "base_template_id",
            "source_config",
            "folderId",
            "last_used_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_used_at", "created_at", "updated_at"]

    def get_blueprint(self, obj) -> dict:
        from services.templates import TemplateBlueprint

        if not obj.blueprint:
            return TemplateBlueprint().as_dict()
        return TemplateBlueprint.from_dict(obj.blueprint).as_dict()

    def get_pinned(self, obj) -> bool:
        """True when this template carries an edited slot list."""
        return bool((obj.blueprint or {}).get("slots"))

    def get_builtin(self, obj) -> bool:
        # Always False for a row: built-ins are generated by
        # services/template_catalog.py and never persisted. Present so the
        # client can treat both list shapes identically.
        return False
