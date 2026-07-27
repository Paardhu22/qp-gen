from rest_framework import serializers

from .models import ChatMessage, Conversation


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "attachments", "created_at"]
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    """A conversation without its messages — the history list."""

    class Meta:
        model = Conversation
        fields = ["id", "title", "spec", "created_at", "updated_at"]
        read_only_fields = fields


class ConversationDetailSerializer(ConversationSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ["messages"]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=True, trim_whitespace=False)
    attachments = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )

    def validate(self, attrs):
        if not (attrs.get("content") or "").strip() and not attrs.get("attachments"):
            raise serializers.ValidationError("Send a message or attach a file.")
        return attrs
