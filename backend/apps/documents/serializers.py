from rest_framework import serializers

from apps.documents.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title", "doc_type", "project", "user", "created_at", "updated_at"]


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    projectId = serializers.CharField(required=False, allow_blank=True)
