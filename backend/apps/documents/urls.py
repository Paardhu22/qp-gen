from django.urls import path

from .views import DocumentUploadView, PresignUploadView, ConfirmUploadView

urlpatterns = [
    path("upload", DocumentUploadView.as_view(), name="upload"),
    path("presign", PresignUploadView.as_view(), name="presign-upload"),
    path("confirm", ConfirmUploadView.as_view(), name="confirm-upload"),
]
