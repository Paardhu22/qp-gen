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
    # A conversation becomes a *paper session* the moment it is about making
    # a paper. The distinction is not cosmetic: a session carries a spec that
    # can be half-finished, and half-finished work has to be parkable. A
    # teacher interrupted mid-setup pauses it, starts another, and comes back
    # — which is only possible if the session is a thing with a state rather
    # than just the most recent messages.
    MODE_CHAT = "chat"
    MODE_PAPER = "paper"
    MODE_CHOICES = [(MODE_CHAT, "Chat"), (MODE_PAPER, "Paper session")]

    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_GENERATING = "generating"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_GENERATING, "Generating"),
        (STATUS_COMPLETED, "Completed"),
    ]

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
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_CHAT)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    # The paper this session produced, once it has produced one. Not a FK:
    # papers are deletable from the library and losing one should not take
    # the conversation that made it with it.
    paper_id = models.CharField(
        max_length=32, null=True, blank=True, db_column="paperId"
    )

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
