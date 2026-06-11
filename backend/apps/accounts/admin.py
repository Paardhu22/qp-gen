from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "name", "status", "created_at")
    search_fields = ("email", "name")
    list_filter = ("status", "created_at")
