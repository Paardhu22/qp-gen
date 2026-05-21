from django.db import models
from pgvector.django import VectorField
from utils.ids import generate_id

from apps.accounts.models import User
from apps.common.models import TimeStampedModel


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
    status = models.CharField(max_length=50, default="uploading")
    error = models.TextField(null=True, blank=True)
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
    pdf_source = models.ForeignKey(
        PdfSource,
        on_delete=models.CASCADE,
        db_column="pdfSourceId",
        related_name="chunks",
    )

    class Meta:
        db_table = "DocumentChunk"
        indexes = [
            models.Index(fields=["pdf_source"], name="document_chunk_pdf_source_idx"),
        ]
