from django.contrib import admin

from .models import DocumentChunk, PdfSource


@admin.register(PdfSource)
class PdfSourceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "size", "status", "user", "created_at")
    search_fields = ("name", "user__email")
    list_filter = ("status",)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "pdf_source", "page", "chunk_index")
    search_fields = ("pdf_source__name",)
