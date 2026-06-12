from django.db import models
from django.contrib.postgres.fields import ArrayField

from apps.accounts.models import User
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
    content = models.TextField()
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
    # S3 keys for exported files — only the key is stored, never a presigned URL.
    # Mint fresh presigned URLs at use time via GET /api/storage/export-url/.
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

    class Meta:
        db_table = "Paper"



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
    options = ArrayField(models.TextField(), default=list, blank=True)
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

    class Meta:
        db_table = "Question"
