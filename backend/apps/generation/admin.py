from django.contrib import admin

from .models import GenerationHistory


@admin.register(GenerationHistory)
class GenerationHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at")
    search_fields = ("user__email", "prompt")
