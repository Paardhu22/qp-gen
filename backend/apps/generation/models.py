from django.db import models

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class GenerationHistory(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    prompt = models.TextField()
    settings = models.JSONField()
    result = models.JSONField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="history")

    class Meta:
        db_table = "GenerationHistory"


class PaperTemplate(TimeStampedModel):
    """A saved paper recipe: the teacher's instructions plus what they settled.

    Schools set the same paper over and over — a weekly test, a Friday recap,
    a chapter revision — and General Instructions Mode makes each one a fresh
    typing exercise. A template is that typing, kept.

    It stores BOTH halves on purpose. `instructions` is the prose the designer
    reads, so editing it still changes the paper; `settings` is what was filled
    in around it (difficulty, marks, sets, class, subject), so re-applying the
    template does not re-ask questions the teacher already answered once. The
    resolved paper structure is deliberately NOT stored: a template pinned to
    one frozen layout would stop responding to its own instructions, and a
    "Weekly Test" applied to next week's chapter should produce next week's
    paper, not last week's.

    Table and column names follow the legacy Prisma convention (see CLAUDE.md).
    """

    id = models.CharField(
        primary_key=True, max_length=32, default=generate_id, editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="paper_templates",
    )
    name = models.CharField(max_length=120)
    # Free-form instructions, exactly as typed. The paper designer's input.
    instructions = models.TextField(blank=True)
    # Generator-form fields the teacher settled: difficulty, marks,
    # numberOfSets, academicClass, subject, board. Field names match
    # `formSchema` in components/generator-form.tsx so applying a template is a
    # copy rather than a translation — the same contract `Conversation.spec`
    # keeps with the dashboard assistant.
    settings = models.JSONField(default=dict, blank=True)
    # Ordering signal for the picker: the template someone reaches for weekly
    # should not sink under one they made once and abandoned.
    last_used_at = models.DateTimeField(null=True, blank=True, db_column="lastUsedAt")

    class Meta:
        db_table = "PaperTemplate"
        ordering = ["-last_used_at", "-updated_at"]
        constraints = [
            # One "Weekly Test" per teacher. Two templates with the same name
            # are indistinguishable in the picker, which makes the picker a
            # guess; saving over the existing one is what the teacher meant.
            models.UniqueConstraint(
                fields=["user", "name"], name="unique_template_name_per_user"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class ApiUsage(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="userId",
        related_name="api_usage",
    )
    operation = models.CharField(max_length=64)
    model = models.CharField(max_length=64, blank=True)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)

    class Meta:
        db_table = "ApiUsage"
