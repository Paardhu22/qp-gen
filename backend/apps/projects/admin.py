from django.contrib import admin

from .models import Paper, Project, Question


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "created_at")
    search_fields = ("name", "user__email")


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "project", "user")
    search_fields = ("title", "project__name")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "marks", "project", "paper")
    search_fields = ("content",)
