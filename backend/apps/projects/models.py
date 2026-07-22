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

    class Meta:
        db_table = "Paper"


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


class Question(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    type = models.CharField(max_length=50)
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
