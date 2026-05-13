from django.db import models
from pgvector.django import VectorField

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class Document(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    title = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=255, default="pdf", db_column="type")
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="documents")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="projectId",
        related_name="documents",
    )

    class Meta:
        db_table = "Document"


class DocumentChunk(models.Model):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    content = models.TextField()
    page = models.IntegerField(null=True, blank=True)
    chunk_index = models.IntegerField(db_column="chunkIndex")
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, db_column="documentId", related_name="chunks")

    class Meta:
        db_table = "DocumentChunk"
        indexes = [models.Index(fields=["document"], name="document_chunk_document_idx")]
