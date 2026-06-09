from django.db import models
from pgvector.django import VectorField
from utils.ids import generate_id

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from apps.projects.models import Paper


class HsatSource(TimeStampedModel):
    """
    Shared HSAT (high-school assessment textbook) ingestion record.

    One record per `(grade, subject, book)`. Unlike `PdfSource`, this is NOT
    scoped to a user — HSAT books are global shared content. Generation
    pipelines link to an HsatSource via `PaperHsatSource` to widen their RAG
    pool, but never duplicate the underlying chunks per user.
    """

    id = models.CharField(
        primary_key=True, max_length=255, default=generate_id, editable=False
    )
    grade = models.CharField(max_length=8)
    subject = models.CharField(max_length=64)
    book = models.CharField(max_length=128)
    status = models.CharField(max_length=20, default="pending")
    chunk_count = models.IntegerField(default=0)
    error = models.TextField(null=True, blank=True)
    chapter_errors = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "hsat_source"
        unique_together = ("grade", "subject", "book")
        indexes = [
            models.Index(fields=["grade", "subject", "book"], name="hsat_gsb_idx"),
            models.Index(fields=["status"], name="hsat_status_idx"),
        ]


class PaperHsatSource(TimeStampedModel):
    """Per-paper link to a shared HsatSource.

    Lets the RAG retriever union user-uploaded chunks with HSAT chunks
    without copying the underlying chunks per-paper. The same HsatSource
    can be linked to many Papers and many users at no extra cost.
    """

    id = models.CharField(
        primary_key=True, max_length=255, default=generate_id, editable=False
    )
    paper = models.ForeignKey(
        Paper,
        on_delete=models.CASCADE,
        db_column="paperId",
        related_name="hsat_sources",
    )
    hsat_source = models.ForeignKey(
        "HsatSource",
        on_delete=models.CASCADE,
        db_column="hsatSourceId",
        related_name="paper_links",
    )

    class Meta:
        db_table = "paper_hsat_source"
        unique_together = ("paper", "hsat_source")
        indexes = [
            models.Index(fields=["paper"], name="phs_paper_idx"),
        ]


class PdfSource(TimeStampedModel):
    """
    Temporary AI generation context. Stores an uploaded file's chunks and
    embeddings so questions can be generated from it.

    This is NOT a Question Bank entity or a Paper entity. It is decoupled
    from both systems — questions become persistent only when the user
    explicitly saves them.
    """

    id = models.CharField(
        primary_key=True, max_length=255, default=generate_id, editable=False
    )
    name = models.CharField(max_length=255)
    size = models.IntegerField()
    # url is kept for schema compatibility with the Prisma-created table;
    # backend uploads don't use a remote URL so it defaults to an empty string.
    url = models.CharField(max_length=2048, default="", blank=True)
    # `content_type` was created by an earlier Prisma migration with a NOT NULL
    # constraint; even after Django migration 0003 attempted to drop it, some
    # databases still carry the column (see migration 0004). Keeping it in the
    # model with a sane default means every INSERT supplies the value
    # regardless of whether the column was dropped, and the field is harmless
    # if the schema mismatch is resolved.
    content_type = models.CharField(
        max_length=255, default="application/pdf", blank=True
    )
    status = models.CharField(max_length=50, default="uploading")
    error = models.TextField(null=True, blank=True)
    # SHA256 hash of the file content for deduplication
    sha256 = models.CharField(max_length=64, db_index=True, null=True, blank=True)
    # AV scan status: 'pending', 'passed', 'failed', or null if AV disabled
    av_status = models.CharField(max_length=20, null=True, blank=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="pdf_sources",
    )

    class Meta:
        db_table = "pdf_source"


class DocumentChunk(models.Model):
    id = models.CharField(
        primary_key=True, max_length=255, default=generate_id, editable=False
    )
    content = models.TextField()
    page = models.IntegerField(null=True, blank=True)
    chunk_index = models.IntegerField(db_column="chunkIndex")
    metadata = models.JSONField(default=dict, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    # A chunk belongs to EITHER a PdfSource (user upload) or an HsatSource
    # (shared textbook). Exactly one of the two should be set; the constraint
    # is enforced at the application layer rather than via a DB CHECK so the
    # migration stays compatible with the existing Prisma-managed pdfSourceId
    # column.
    pdf_source = models.ForeignKey(
        PdfSource,
        on_delete=models.CASCADE,
        db_column="pdfSourceId",
        related_name="chunks",
        null=True,
        blank=True,
    )
    hsat_source = models.ForeignKey(
        HsatSource,
        on_delete=models.CASCADE,
        db_column="hsatSourceId",
        related_name="chunks",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "DocumentChunk"
        indexes = [
            models.Index(fields=["pdf_source"], name="document_chunk_pdf_source_idx"),
            models.Index(fields=["hsat_source"], name="document_chunk_hsat_source_idx"),
        ]
