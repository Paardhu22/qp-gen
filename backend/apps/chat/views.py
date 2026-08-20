"""Chat endpoints for the dashboard assistant.

Every view is scoped to `request.user`: a conversation is looked up through
the user's own related manager, never by bare id, so one account cannot read
or continue another's chat by guessing a uuid.
"""

import json
import logging

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from services.chat_service import (
    build_message_history,
    can_generate,
    collect_source_ids,
    extract_spec,
    next_prompt,
    spec_is_ready,
    stream_reply,
    suggest_title,
)
from services.pool.keepalive import keepalive
from services.usage_limits import UsageLimitExceeded, check_monthly_token_limit

from .models import ChatMessage, Conversation
from .serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
    SendMessageSerializer,
)

logger = logging.getLogger("[CHAT]")


def _sse(data: dict, event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ConversationListCreateView(APIView):
    """GET /api/chat/conversations — the user's chats, newest first.
    POST /api/chat/conversations — start a new one.
    """

    def get(self, request):
        conversations = request.user.conversations.all()
        return Response(ConversationSerializer(conversations, many=True).data)

    def post(self, request):
        conversation = Conversation.objects.create(
            user=request.user,
            title=(request.data.get("title") or "New chat")[:255],
        )
        return Response(
            ConversationDetailSerializer(conversation).data,
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(APIView):
    """GET a conversation with its messages, DELETE it, or PATCH its title."""

    def get_object(self, request, conversation_id):
        return get_object_or_404(request.user.conversations, id=conversation_id)

    def get(self, request, conversation_id):
        conversation = self.get_object(request, conversation_id)
        return Response(ConversationDetailSerializer(conversation).data)

    def patch(self, request, conversation_id):
        conversation = self.get_object(request, conversation_id)
        title = (request.data.get("title") or "").strip()
        if title:
            conversation.title = title[:255]
            conversation.save(update_fields=["title", "updated_at"])
        return Response(ConversationSerializer(conversation).data)

    def delete(self, request, conversation_id):
        conversation = self.get_object(request, conversation_id)
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationStatusView(APIView):
    """POST /api/chat/conversations/<id>/status — park or resume a session.

    Pausing changes nothing about the work; the spec and transcript are
    already durable. What it buys the teacher is a truthful list: a paper
    they walked away from reads as paused instead of sitting at the top
    pretending to be in progress.
    """

    ALLOWED = {
        Conversation.STATUS_ACTIVE,
        Conversation.STATUS_PAUSED,
        Conversation.STATUS_GENERATING,
        Conversation.STATUS_COMPLETED,
    }

    def post(self, request, conversation_id):
        conversation = get_object_or_404(request.user.conversations, id=conversation_id)

        status_value = str(request.data.get("status") or "").strip()
        if status_value not in self.ALLOWED:
            return Response(
                {"detail": f"Unknown status '{status_value}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fields = ["status", "updated_at"]
        conversation.status = status_value

        paper_id = request.data.get("paperId")
        if paper_id:
            conversation.paper_id = str(paper_id)[:32]
            fields.insert(1, "paper_id")

        conversation.save(update_fields=fields)
        return Response(ConversationSerializer(conversation).data)


class ChatMessageStreamView(APIView):
    """POST /api/chat/conversations/<id>/messages

    Persists the teacher's turn, streams the assistant's reply, then re-derives
    the paper spec and persists both. The reply is saved from inside the
    generator, after the last token — a stream the client abandons halfway
    still records what the model actually said.
    """

    def post(self, request, conversation_id):
        conversation = get_object_or_404(request.user.conversations, id=conversation_id)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = serializer.validated_data["content"]
        attachments = serializer.validated_data.get("attachments") or []

        try:
            check_monthly_token_limit(request.user)
        except UsageLimitExceeded as exc:
            return Response(exc.payload, status=status.HTTP_402_PAYMENT_REQUIRED)

        is_first_turn = not conversation.messages.exists()
        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.ROLE_USER,
            content=content,
            attachments=attachments,
        )
        if is_first_turn:
            conversation.title = suggest_title(content)
            conversation.save(update_fields=["title", "updated_at"])

        history = [
            {"role": m.role, "content": m.content}
            for m in conversation.messages.all()
        ]
        if attachments:
            names = ", ".join(
                str(a.get("name") or "a file") for a in attachments
            )
            history.append(
                {
                    "role": "user",
                    "content": f"(The teacher attached: {names})",
                }
            )

        user = request.user
        messages = build_message_history(history)

        def event_stream():
            reply_parts: list[str] = []
            try:
                for token in stream_reply(messages, user=user):
                    reply_parts.append(token)
                    yield _sse({"text": token}, event="delta")
            except Exception as exc:
                logger.exception("Chat reply failed")
                # The turn is already half-written; persist what arrived so the
                # transcript matches what the teacher saw before the error.
                if reply_parts:
                    ChatMessage.objects.create(
                        conversation=conversation,
                        role=ChatMessage.ROLE_ASSISTANT,
                        content="".join(reply_parts),
                    )
                yield _sse(
                    {"error": "The assistant could not finish that reply."},
                    event="error",
                )
                return

            reply = "".join(reply_parts)
            message = ChatMessage.objects.create(
                conversation=conversation,
                role=ChatMessage.ROLE_ASSISTANT,
                content=reply,
            )

            extraction = extract_spec(
                history + [{"role": "assistant", "content": reply}],
                previous=conversation.spec,
                user=user,
            )
            spec = extraction.spec

            updates = []
            if spec != conversation.spec:
                conversation.spec = spec
                updates.append("spec")
            # A conversation that turns out to be about a paper becomes a
            # session and stays one; it never reverts, because the teacher
            # wandering off-topic for a turn should not throw away the setup
            # they have done so far.
            if extraction.is_paper and conversation.mode != Conversation.MODE_PAPER:
                conversation.mode = Conversation.MODE_PAPER
                updates.append("mode")
            # Answering a question un-pauses: the teacher is plainly back.
            if conversation.status == Conversation.STATUS_PAUSED:
                conversation.status = Conversation.STATUS_ACTIVE
                updates.append("status")
            if updates:
                conversation.save(update_fields=[*updates, "updated_at"])

            source_ids = collect_source_ids(conversation.messages.all())
            is_paper = conversation.mode == Conversation.MODE_PAPER
            yield _sse(
                {
                    "spec": spec,
                    "ready": spec_is_ready(spec),
                    "canGenerate": can_generate(spec, len(source_ids)),
                    "sourceIds": source_ids,
                    "mode": conversation.mode,
                    # The next thing to ask for, as a widget. Sent only for
                    # paper sessions — a teacher asking about photosynthesis
                    # should not be handed a subject picker.
                    "nextPrompt": (
                        next_prompt(spec, len(source_ids)) if is_paper else None
                    ),
                },
                event="spec",
            )
            yield _sse(
                {"messageId": message.id, "content": reply}, event="done"
            )

        # The extraction call after the last token is a full round trip with
        # nothing on the wire behind it, and a slow first token does the same
        # at the front. Both are long enough for a proxy's idle read timeout;
        # see services/pool/keepalive.py.
        response = StreamingHttpResponse(
            keepalive(event_stream()), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
