from django.urls import path

from .views import (
    ConfirmUploadView,
    DocumentStatusView,
    DocumentUploadView,
    PresignUploadView,
)

urlpatterns = [
    path("upload", DocumentUploadView.as_view(), name="upload"),
    path("presign", PresignUploadView.as_view(), name="presign-upload"),
    path("confirm", ConfirmUploadView.as_view(), name="confirm-upload"),
    # Poll target for the async upload flow (no trailing slash — APPEND_SLASH=False).
    path("<str:source_id>/status", DocumentStatusView.as_view(), name="document-status"),
]
