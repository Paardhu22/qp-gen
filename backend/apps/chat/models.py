"""Persistence for the dashboard assistant.

The assistant is a plain conversational model (see `services/chat_service.py`)
and is deliberately NOT the paper generator. It talks to a teacher, asks the
follow-up questions a half-specified request leaves open, and accumulates the
answers into a paper spec. Producing the paper is still the pool pipeline's
job — the spec is handed to it, nothing more.

Table and column names follow the legacy Prisma convention the rest of the
schema uses (capitalized table, camelCase columns); see CLAUDE.md.
"""

from django.db import models

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class Conversation(TimeStampedModel):
    id = models.CharField(
        primary_key=True, max_length=32, default=generate_id, editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="conversations",
    )
    title = models.CharField(max_length=255, default="New chat")
    # The paper spec built up over the conversation: board, class, subject,
    # difficulty, marks and so on. Held on the conversation rather than on a
    # message because it is cumulative — each turn may fill in one more field,
    # and the handoff to the generator reads the latest state, not a
    # transcript.
    spec = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "Conversation"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.id})"


class ChatMessage(TimeStampedModel):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "User"), (ROLE_ASSISTANT, "Assistant")]

    id = models.CharField(
        primary_key=True, max_length=32, default=generate_id, editable=False
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        db_column="conversationId",
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField(blank=True)
    # PDFs the teacher attached to this turn, as [{"id": ..., "name": ...}]
    # referencing already-ingested document sources. Only the reference is
    # kept: the file itself lives wherever the documents app put it.
    attachments = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "ChatMessage"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"
