from django.db import models

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class GenerationRun(TimeStampedModel):
    """A generation, decoupled from the request that asked for it.

    Generation used to run inside the streaming request: `stream_pool_questions`
    was consumed by `StreamingHttpResponse`, so the run existed only for as long
    as that HTTP connection did. Close the tab, reload the page, lose the
    network for a moment — the generator was garbage collected mid-paper and
    minutes of Model 1 work went with it, with nothing on the server that even
    remembered it had been asked for.

    A row here is that memory. The pipeline runs in a worker thread writing
    every event it emits to `GenerationRunEvent`, and the stream endpoint
    becomes a reader over those rows rather than the thing producing them. A
    client that disconnects and comes back replays what it missed and carries
    on.

    Two things fall out of that beyond durability:

    * `gunicorn --timeout` stops being a function of how long a paper takes to
      write. The request is now a cheap tail over a table, so a slow generation
      can no longer trip the worker timeout the way it could when the whole
      pipeline had to finish inside one request.
    * A run becomes inspectable. "It failed and I don't know why" is a row with
      an `error` on it.

    ## Heartbeats

    The worker is a daemon thread, so a deploy or a gunicorn restart kills it
    without warning and without unwinding. Nothing would move the row out of
    `running`, and the UI would show a paper being written by a thread that no
    longer exists — a spinner that never resolves, which is a worse failure than
    the one this replaces. `heartbeat_at` is bumped as the run works, and
    `reap_stale_runs()` fails anything that has stopped breathing.
    """

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    #: Statuses a run can still leave. Anything else is final.
    ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)

    id = models.CharField(
        primary_key=True, max_length=32, default=generate_id, editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="generation_runs",
    )
    # The editor's paper id, so a reattaching client can tell whether this run
    # belongs to the document it currently has open. Free-form: a local draft
    # id is not a row in any table.
    paper_id = models.CharField(max_length=64, blank=True, db_column="paperId")

    # The request as received. Kept whole so a run can be re-read, debugged, or
    # re-issued without reconstructing it from the client.
    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED
    )
    # Last human-readable stage, mirrored from the pipeline's own status events
    # so a reattaching client has something to show before the first replayed
    # event arrives.
    phase = models.CharField(max_length=200, blank=True)
    produced = models.IntegerField(default=0)
    total = models.IntegerField(default=0)

    # The assembled paper, written once on completion. Set A only; the derived
    # sets are carried in their own events.
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)

    # Set by a cancel request. The worker checks it between steps rather than
    # being killed, so a cancelled run stops at a coherent point.
    cancel_requested = models.BooleanField(
        default=False, db_column="cancelRequested"
    )

    heartbeat_at = models.DateTimeField(null=True, blank=True, db_column="heartbeatAt")
    finished_at = models.DateTimeField(null=True, blank=True, db_column="finishedAt")

    class Meta:
        db_table = "GenerationRun"
        ordering = ["-created_at"]
        indexes = [
            # The two queries this table exists to answer: "what is this user
            # running right now" and "what has gone stale".
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "heartbeat_at"]),
        ]

    def __str__(self) -> str:
        return f"GenerationRun({self.id}, {self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES


class GenerationRunEvent(models.Model):
    """One SSE event, kept so it can be replayed.

    This is the append-only log that makes reattaching possible. The worker
    writes each event as it emits it; the stream endpoint reads rows after the
    client's last-seen `seq` and tails for more.

    Rows rather than an in-memory queue because gunicorn runs several workers
    and may run several instances: the request that reattaches is usually not
    handled by the process running the job, so anything held in memory would be
    invisible to it. Postgres is the only thing both sides can see. (Redis is
    optional in this deployment — `REDIS_URL` unset falls back to a per-process
    LocMemCache — so it cannot be the transport either.)

    `seq` is per-run and assigned by the writer, which is single-threaded per
    run, so it needs no coordination.
    """

    id = models.BigAutoField(primary_key=True)
    run = models.ForeignKey(
        GenerationRun,
        on_delete=models.CASCADE,
        related_name="events",
        db_column="runId",
    )
    seq = models.IntegerField()
    event = models.CharField(max_length=32)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_column="createdAt")

    class Meta:
        db_table = "GenerationRunEvent"
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "seq"], name="generation_run_event_unique_seq"
            )
        ]
        indexes = [models.Index(fields=["run", "seq"])]

    def __str__(self) -> str:
        return f"GenerationRunEvent({self.run_id}#{self.seq} {self.event})"


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
