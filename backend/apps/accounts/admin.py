from django.contrib import admin

from .models import Account, Session, User, Verification


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "name", "created_at")
    search_fields = ("email", "name")


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("id", "provider_id", "account_id", "user")
    search_fields = ("provider_id", "account_id", "user__email")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "expires_at")
    search_fields = ("user__email", "token")


@admin.register(Verification)
class VerificationAdmin(admin.ModelAdmin):
    list_display = ("id", "identifier", "expires_at")
    search_fields = ("identifier",)
