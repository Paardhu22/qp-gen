from django.contrib import admin

from .models import Membership, Organization, OrganizationInvite


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(OrganizationInvite)
class OrganizationInviteAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "status", "organization", "expires_at", "created_at")
    search_fields = ("email",)
    list_filter = ("status",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "organization", "role", "status", "created_at")
    search_fields = ("user__email", "organization__name")
    list_filter = ("role", "status")
