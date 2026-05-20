from rest_framework import serializers

from apps.documents.models import PdfSource


class PdfSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PdfSource
        fields = ["id", "name", "size", "status", "error", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "error", "created_at", "updated_at"]


class DocumentUploadSerializer(serializers.Serializer):
    """Accepts a file upload. PdfSources are NOT linked to projects."""

    file = serializers.FileField()
