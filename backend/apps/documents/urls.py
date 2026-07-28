from django.urls import path

from .views import (
    AnalyzePdfView,
    ConfirmUploadView,
    DetectSubjectView,
    DocumentStatusView,
    DocumentUploadView,
    PresignUploadView,
    ValidateMetadataView,
)

urlpatterns = [
    path("upload", DocumentUploadView.as_view(), name="upload"),
    path("presign", PresignUploadView.as_view(), name="presign-upload"),
    path("confirm", ConfirmUploadView.as_view(), name="confirm-upload"),
    path("detect-subject", DetectSubjectView.as_view(), name="detect-subject"),
    path("analyze-pdf", AnalyzePdfView.as_view(), name="analyze-pdf"),
    path("validate-metadata", ValidateMetadataView.as_view(), name="validate-metadata"),
    # Poll target for the async upload flow (no trailing slash — APPEND_SLASH=False).
    path("<str:source_id>/status", DocumentStatusView.as_view(), name="document-status"),
]
