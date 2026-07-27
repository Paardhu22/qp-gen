from rest_framework import serializers

from .models import ChatMessage, Conversation


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "attachments", "created_at"]
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    """A conversation without its messages — the history list."""

    ready = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "title",
            "spec",
            "mode",
            "status",
            "paper_id",
            "ready",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_ready(self, obj) -> bool:
        from services.chat_service import spec_is_ready

        return spec_is_ready(obj.spec)


class ConversationDetailSerializer(ConversationSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    next_prompt = serializers.SerializerMethodField()
    source_ids = serializers.SerializerMethodField()
    can_generate = serializers.SerializerMethodField()

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + [
            "messages",
            "next_prompt",
            "source_ids",
            "can_generate",
        ]
        read_only_fields = fields

    def _sources(self, obj) -> list:
        from services.chat_service import collect_source_ids

        if not hasattr(obj, "_cached_source_ids"):
            obj._cached_source_ids = collect_source_ids(obj.messages.all())
        return obj._cached_source_ids

    def get_source_ids(self, obj) -> list:
        return self._sources(obj)

    def get_can_generate(self, obj) -> bool:
        from services.chat_service import can_generate

        return can_generate(obj.spec, len(self._sources(obj)))

    def get_next_prompt(self, obj):
        """So a resumed session shows its follow-up widget immediately.

        Without this the teacher would reopen a half-finished paper and see
        the transcript but no way to answer the outstanding question until
        they typed something to provoke a fresh turn.
        """
        from services.chat_service import next_prompt

        if obj.mode != Conversation.MODE_PAPER:
            return None
        return next_prompt(obj.spec, len(self._sources(obj)))


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=True, trim_whitespace=False)
    attachments = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )

    def validate(self, attrs):
        if not (attrs.get("content") or "").strip() and not attrs.get("attachments"):
            raise serializers.ValidationError("Send a message or attach a file.")
        return attrs
