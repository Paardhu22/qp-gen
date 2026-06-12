from django.urls import path
from .views import ExportUrlView, UploadExportView

urlpatterns = [
    path("upload-export/", UploadExportView.as_view(), name="upload-export"),
    path("export-url/", ExportUrlView.as_view(), name="export-url"),
]
