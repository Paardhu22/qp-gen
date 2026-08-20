from django.db import models

from apps.accounts.models import User
from apps.common.fields import PortableArrayField
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class Project(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="projects")

    class Meta:
        db_table = "Project"


class Paper(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    title = models.CharField(max_length=255)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, db_column="projectId", related_name="papers")
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="papers")
    # Stores the ID of the generated answer script paper (if any).
    # Nullable — not every paper has an answer script yet.
    answer_script_id = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        db_column="answerScriptId",
    )
    # New aggregate root fields
    subject = models.CharField(max_length=255, null=True, blank=True)
    grade_class = models.CharField(max_length=100, null=True, blank=True, db_column="gradeClass")
    board = models.CharField(max_length=100, null=True, blank=True)
    instructions = models.TextField(null=True, blank=True)
    blueprint = models.JSONField(null=True, blank=True)
    question_pool_id = models.CharField(
        max_length=32, null=True, blank=True, db_column="questionPoolId"
    )

    #: When the teacher deleted this paper, or null while it is live.
    #:
    #: Delete is one click sitting next to "open", and what it destroys is a
    #: term's worth of work — a paper carries its blueprint, three set variants,
    #: an answer key and every question in it. A hard delete makes that click
    #: unsurvivable, and "are you sure?" is not a safety net, it is a speed
    #: bump people learn to click through.
    #:
    #: A stamp rather than a boolean because the retention window is measured
    #: from it: `PAPER_TRASH_RETENTION_DAYS` after this moment the row is
    #: genuinely removed. Every list must filter on it — a paper in the bin is
    #: deleted as far as the rest of the product is concerned.
    deleted_at = models.DateTimeField(
        null=True, blank=True, db_column="deletedAt"
    )

    class Meta:
        db_table = "Paper"
        indexes = [
            # Every papers listing is "mine, not deleted, newest first".
            models.Index(
                fields=["user", "deleted_at", "-updated_at"],
                name="paper_user_deleted_idx",
            ),
        ]


class PaperSet(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column="paperId", related_name="sets")
    label = models.CharField(max_length=255)
    order = models.IntegerField(default=1)
    content = models.TextField()
    answers = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # S3 exports for this specific set
    s3_pdf_key = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        db_column="s3PdfKey",
    )
    s3_docx_key = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        db_column="s3DocxKey",
    )
    s3_content_key = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        db_column="s3ContentKey",
    )

    class Meta:
        db_table = "PaperSet"
        ordering = ["order"]
class Draft(TimeStampedModel):
    """An unsaved paper, kept on the server instead of only in one browser.

    Drafts used to live solely in IndexedDB. That made them invisible outside
    the browser that made them, which is wrong in the two ways that matter to
    a teacher: a paper started on a laptop at home cannot be finished on the
    staffroom PC, and clearing site data — or a browser doing it for you —
    destroys work with no copy anywhere. The local store is still the
    authority for *speed*; this is the copy that survives the device.

    One row per set tab, which is how the editor already writes them: a
    three-set paper is three drafts sharing a `scope`. Folding them into one
    row would mean rewriting the whole paper on every keystroke in any tab.

    `document` is the editor's own payload, stored whole rather than unpacked
    into columns. The alternative is a schema that has to be migrated in step
    with the editor's document shape, and the server has no opinion about that
    shape — it stores and returns it. The denormalised `title`, `class_name`
    and `subject` beside it exist only so the drafts list can be drawn without
    loading every document body.

    A draft stops being a draft the moment it is saved as a paper: it gets a
    real Paper row, and `DraftListView` deletes it. That is also what takes it
    off the retention clock — the clock only ever runs on work left unsaved.
    """

    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="drafts",
    )
    #: The base paper id the editor puts back into `?paperId=` — "draft-abc",
    #: or "current" for the pre-set-tabs scope. NOT the set-suffixed id.
    scope = models.CharField(max_length=64)
    #: "A", "B", "C", or "" for the legacy un-suffixed document.
    set_label = models.CharField(max_length=8, blank=True, default="")

    title = models.CharField(max_length=255, blank=True, default="")
    class_name = models.CharField(max_length=100, blank=True, default="", db_column="className")
    subject = models.CharField(max_length=255, blank=True, default="")

    #: The editor's `LiveEditorDocument`, verbatim. See the class docstring.
    document = models.JSONField(default=dict, blank=True)

    #: The client's own clock at the moment of the edit, in epoch ms.
    #:
    #: Conflict resolution is last-write-wins on THIS, not on `updated_at`:
    #: two devices editing the same draft must be ordered by when the teacher
    #: typed, not by which push happened to reach the server first over a slow
    #: connection. Client clocks are imperfect, but a request arriving late is
    #: the far more common failure and this is the one that handles it.
    client_updated_at = models.BigIntegerField(default=0, db_column="clientUpdatedAt")

    class Meta:
        db_table = "Draft"
        ordering = ["-client_updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scope", "set_label"],
                name="unique_draft_per_scope_and_set",
            )
        ]
        indexes = [
            models.Index(fields=["user", "-client_updated_at"], name="draft_user_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title or 'Untitled draft'} ({self.scope}{self.set_label})"


class ExportRecord(TimeStampedModel):
    """Tracks question_bank exports that are not tied to a specific Paper."""

    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="export_records",
    )
    s3_key = models.CharField(max_length=1024, db_column="s3Key")
    file_format = models.CharField(max_length=10, db_column="fileFormat")  # 'pdf' or 'docx'

    class Meta:
        db_table = "ExportRecord"


class QuestionFamily(models.Model):
    code = models.CharField(primary_key=True, max_length=50)
    name = models.CharField(max_length=255)
    response_mode = models.CharField(max_length=50)
    is_auto_markable = models.BooleanField()
    sort_order = models.IntegerField()

    class Meta:
        db_table = "QuestionFamily"
        ordering = ["sort_order"]


class QuestionType(models.Model):
    code = models.CharField(primary_key=True, max_length=50)
    family = models.ForeignKey(QuestionFamily, on_delete=models.PROTECT, related_name="types")
    name = models.CharField(max_length=255)
    description = models.TextField()
    purpose = models.TextField(null=True, blank=True)
    is_container = models.BooleanField(default=False)
    requires_stimulus = models.BooleanField(default=False)
    requires_options = models.BooleanField(default=False)
    requires_figure = models.BooleanField(default=False)
    produces_figure = models.BooleanField(default=False)
    is_auto_markable = models.BooleanField(default=False)
    is_competency_default = models.BooleanField(default=False)
    needs_answer_space = models.BooleanField(default=True)
    default_answer_space_lines = models.IntegerField(null=True, blank=True)
    is_internal_only = models.BooleanField(default=False)
    content_schema = models.JSONField(default=dict, blank=True)
    answer_schema = models.JSONField(default=dict, blank=True)
    deprecated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "QuestionType"


class QuestionTypeAlias(models.Model):
    type = models.ForeignKey(QuestionType, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=255)
    locale = models.CharField(max_length=10, null=True, blank=True)
    board_code = models.CharField(max_length=50, null=True, blank=True)
    source = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "QuestionTypeAlias"
        unique_together = (("type", "alias", "locale", "board_code"),)
        indexes = [
            models.Index(fields=["alias"], name="question_type_alias_idx"),
        ]


class Question(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    type = models.ForeignKey(QuestionType, on_delete=models.PROTECT, db_column="type", null=True, blank=True)
    content = models.TextField()
    answer = models.TextField(null=True, blank=True)
    # PortableArrayField, not ArrayField: identical `text[]` column on
    # Postgres (and migration-invisible), but round-trips as JSON on SQLite so
    # the auto-save path is testable. See apps/common/fields.py.
    options = PortableArrayField(models.TextField(), default=list, blank=True)
    marks = models.IntegerField(default=1)
    bloom_taxonomy = models.CharField(max_length=50, null=True, blank=True, db_column="bloomTaxonomy")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, db_column="projectId", related_name="questions")
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, null=True, blank=True, db_column="paperId", related_name="questions")
    grade_class = models.CharField(max_length=100, null=True, blank=True, db_column="gradeClass")
    subject = models.CharField(max_length=255, null=True, blank=True)
    inferred_topic = models.CharField(max_length=255, null=True, blank=True, db_column="inferredTopic")
    inferred_chapter = models.CharField(max_length=255, null=True, blank=True, db_column="inferredChapter")
    source_pdf = models.CharField(max_length=255, null=True, blank=True, db_column="sourcePdf")
    difficulty = models.CharField(max_length=50, null=True, blank=True)

    # ── Question Pool fields ────────────────────────────────────────────
    # Model 1 emits a full pool (~80 questions) per chapter; every question
    # is persisted as its own row (never one JSON blob) so the bank stays
    # filterable/searchable and papers can later be assembled straight from
    # saved questions without re-running Model 1.

    #: Worked explanation for the answer. Distinct from `answer` — the answer
    #: is what a marking scheme expects, the explanation is why.
    explanation = models.TextField(null=True, blank=True)

    #: Figure attached to this question. Stores an S3 KEY or a stable
    #: /media/<path> URL, never a presigned URL (those expire) — resolve at
    #: render time the same way Paper.s3_pdf_key does.
    image_url = models.CharField(
        max_length=2048, null=True, blank=True, db_column="imageUrl"
    )

    #: Direct owner FK. Questions were previously reachable only via
    #: project.user, which forced a join for every bank query and made
    #: per-user dedup awkward. Nullable + backfilled so the migration is safe
    #: against the live Prisma-created table.
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="userId",
        related_name="questions",
    )

    #: SHA256 of (subject|chapter|normalised question text). Lets a chapter be
    #: regenerated without duplicating rows. Deliberately a plain index rather
    #: than a UNIQUE constraint: the live table may already hold duplicates
    #: from the pre-pool flow, and a unique index would fail to build against
    #: them. Dedup is enforced in pool_store.persist_pool().
    content_hash = models.CharField(
        max_length=64, null=True, blank=True, db_column="contentHash"
    )

    #: Groups every question emitted by one Model 1 run, so a pool can be
    #: re-assembled into a different paper later without re-generating.
    pool_id = models.CharField(
        max_length=32, null=True, blank=True, db_column="poolId"
    )

    #: Provenance: "pool" (Model 1), "synthetic_image" (image model), or
    #: "curriculum_fallback". Drives the review-tray badge — a teacher should
    #: vet AI-drawn figures before they reach a real exam.
    source_type = models.CharField(
        max_length=32, null=True, blank=True, db_column="sourceType"
    )

    #: Small per-question extras (image prompt, slot index, generation model).
    #: Per-question detail only — the pool itself is rows, not a blob.
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "Question"
        indexes = [
            # "Create Paper from Saved Questions" filters the bank by owner
            # then narrows on subject/class — this index serves both.
            models.Index(
                fields=["user", "subject", "grade_class"],
                name="question_user_subj_class_idx",
            ),
            # Dedup lookup on regeneration: one query per (user, hash) batch.
            models.Index(
                fields=["user", "content_hash"], name="question_user_hash_idx"
            ),
            models.Index(fields=["pool_id"], name="question_pool_idx"),
        ]
