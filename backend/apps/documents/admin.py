from django.contrib import admin

from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "doc_type", "user", "project")
    search_fields = ("title", "user__email")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "page", "chunk_index")
    search_fields = ("document__title",)
