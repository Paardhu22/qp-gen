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


class TemplateFolder(TimeStampedModel):
    """A teacher's own filing for their templates.

    Schools accumulate templates the way they accumulate paperwork — "Term 1",
    "Class 10 Boards", "Weekly tests" — and a flat list stops being findable
    somewhere around a dozen. Folders are the teacher's structure, not ours:
    nothing in generation reads them, and a template with no folder is
    perfectly usable. This is filing, not taxonomy.

    Nesting is supported by the model (`parent`) because "Term 1 / Unit tests"
    is how people actually describe where something lives. The depth is capped
    in the API rather than here — see MAX_FOLDER_DEPTH — because a cap is a
    product decision and a self-FK cannot express one.

    Deleting a folder deletes its subfolders but NEVER its templates: the
    templates fall back to unfiled (`PaperTemplate.folder` is SET_NULL).
    Losing a paper recipe because you tidied up your filing would be the worst
    possible reading of "delete folder".

    Table and column names follow the legacy Prisma convention (see CLAUDE.md).
    """

    id = models.CharField(
        primary_key=True, max_length=32, default=generate_id, editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="template_folders",
    )
    name = models.CharField(max_length=80)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="parentId",
        related_name="children",
    )

    class Meta:
        db_table = "TemplateFolder"
        ordering = ["name"]
        constraints = [
            # Two constraints rather than one because `parent` is nullable and
            # SQL treats NULLs as distinct — a single UniqueConstraint over
            # (user, parent, name) would happily allow two root folders both
            # called "Term 1". Postgres 15+ could express this as
            # `nulls_distinct=False`, but that is silently ignored on SQLite,
            # which is what the test suite runs on. Two constraints hold
            # everywhere.
            models.UniqueConstraint(
                fields=["user", "parent", "name"],
                name="unique_subfolder_name_per_parent",
            ),
            models.UniqueConstraint(
                fields=["user", "name"],
                condition=models.Q(parent__isnull=True),
                name="unique_root_folder_name_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


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
    # The edited slot list, when there is one. See services/templates.py for
    # why a template has two kinds:
    #
    #   empty    — instruction-driven. Re-resolved from `instructions` +
    #              `settings` on every use, so "Weekly Test" applied to next
    #              week's chapter produces next week's paper. This is what the
    #              class docstring above argues for, and it is still the
    #              default.
    #   present  — pinned. The teacher opened the Blueprint Builder and changed
    #              slots; re-deriving from prose would silently discard that,
    #              so the stored blueprint wins.
    #
    # Shape is `{"slots": [...]}` per `TemplateBlueprint.as_dict()`. Totals are
    # NOT stored — they are recomputed from the slots on read, because a stored
    # total is a second source of truth that can disagree with the slots it
    # claims to describe.
    blueprint = models.JSONField(default=dict, blank=True)
    # Which built-in this was customised from, for provenance in the picker
    # ("based on CBSE Class 10 Science"). A free-form catalog id rather than an
    # FK: the catalog is generated code, not rows.
    base_template_id = models.CharField(
        max_length=64, blank=True, default="", db_column="baseTemplateId"
    )
    # Where questions come from and which sources feed them: the saved-vs-
    # generated split plus the selected uploads/HSAT books. Kept beside the
    # blueprint because "40 from my bank, 20 fresh, from these two chapters" is
    # part of the recipe a teacher is saving, not part of one run.
    source_config = models.JSONField(
        default=dict, blank=True, db_column="sourceConfig"
    )
    # Ordering signal for the picker: the template someone reaches for weekly
    # should not sink under one they made once and abandoned.
    last_used_at = models.DateTimeField(null=True, blank=True, db_column="lastUsedAt")
    # Where the teacher filed this. Null means unfiled, which is a normal
    # resting state and not a defect — most templates never get filed at all.
    # SET_NULL rather than CASCADE: deleting a folder must never destroy the
    # recipes inside it. See `TemplateFolder`.
    folder = models.ForeignKey(
        TemplateFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="folderId",
        related_name="templates",
    )

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
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_usage",
    )
    operation = models.CharField(max_length=64)
    model = models.CharField(max_length=64, blank=True)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)

    class Meta:
        db_table = "ApiUsage"


class GenerationRun(TimeStampedModel):
    """One generation, as a thing that exists apart from the request that started it.

    Generation streams SSE for anywhere from thirty seconds to several minutes.
    Before this, that stream *was* the run: close the laptop, lose signal, or
    let a phone sleep, and the paper was gone — the pool questions had been
    auto-saved to the bank, but the assembled paper the teacher was waiting for
    had nowhere to be delivered and no way to be asked for again.

    Recording the run separates producing the work from delivering it. The
    pipeline writes frames here; an HTTP response reads them. A client can
    disconnect and re-attach with `?cursor=`, replaying what it missed and then
    following the rest live.

    **What this does not promise.** The producer is a daemon thread inside a
    gunicorn worker, so a run survives a client disconnect but not a worker
    restart — `max-requests` recycling, a deploy, or an OOM kill all end it
    mid-flight. That is why `heartbeat_at` exists: a run whose producer has
    died stops being reported as running instead of hanging there forever. A
    guarantee across restarts needs a real task queue, and this is deliberately
    not pretending to be one.
    """

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    #: The producer stopped updating its heartbeat — almost always a worker
    #: restart. Distinct from `failed`, which means the pipeline itself raised.
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    TERMINAL_STATUSES = frozenset(
        {STATUS_COMPLETED, STATUS_FAILED, STATUS_ABANDONED}
    )

    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="generation_runs",
    )
    #: Which stream this is — "questions", "paper_from_bank". Free text rather
    #: than choices because the set grows with the product and a migration per
    #: new stream would be friction for no safety.
    kind = models.CharField(max_length=32)
    status = models.CharField(max_length=16, default=STATUS_RUNNING, choices=STATUS_CHOICES)

    #: What was asked for. Kept so a resumed run can be described to the
    #: teacher ("Class 10 Science, 80 marks") without replaying its events, and
    #: so a failed run can be re-submitted without retyping the form.
    request = models.JSONField(default=dict, blank=True)

    #: Last time the producer wrote anything. See the class docstring — this is
    #: how a run whose worker died stops being reported as still running.
    heartbeat_at = models.DateTimeField(auto_now_add=True, db_column="heartbeatAt")
    finished_at = models.DateTimeField(null=True, blank=True, db_column="finishedAt")
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "GenerationRun"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="genrun_user_recent_idx"),
            models.Index(fields=["status", "heartbeat_at"], name="genrun_status_beat_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES


class GenerationEvent(models.Model):
    """One SSE frame of a run, stored verbatim.

    Verbatim, and as its own row per frame, for two reasons. The frame is
    already the wire format, so replaying a run is writing bytes back out
    rather than reconstructing them — there is no second serializer to drift.
    And appending is an INSERT: accumulating frames into a JSON column on the
    run would rewrite the whole column on every one of a few hundred events.

    `seq` is the cursor a re-attaching client sends. Monotonic per run, so
    "everything after 47" is a single indexed range scan.
    """

    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    run = models.ForeignKey(
        GenerationRun, on_delete=models.CASCADE, related_name="events"
    )
    seq = models.IntegerField()
    #: The SSE event name ("question", "done", "error", …), lifted out of the
    #: frame so a run can be summarised without parsing every frame back.
    name = models.CharField(max_length=64, blank=True, default="")
    #: The complete `event: …\ndata: …\n\n` block, ready to write to the wire.
    frame = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "GenerationEvent"
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(fields=["run", "seq"], name="unique_event_seq_per_run")
        ]
        indexes = [
            models.Index(fields=["run", "seq"], name="genevent_run_seq_idx"),
        ]

    def __str__(self) -> str:
        return f"#{self.seq} {self.name or 'message'}"
