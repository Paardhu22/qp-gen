import os

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from services.cognito_service import (
    add_user_to_group,
    create_cognito_user,
    ensure_cognito_group,
    get_cognito_user_by_email,
)

DEFAULT_SUPERADMIN_EMAIL = "superadmin@hsatedu.in"
DEFAULT_SUPERADMIN_PASSWORD = "SuperAdmin@123!"


class Command(BaseCommand):
    help = "Idempotently create/ensure the platform superadmin Cognito user + local User row."

    def handle(self, *args, **options):
        email = os.environ.get("SUPERADMIN_EMAIL", DEFAULT_SUPERADMIN_EMAIL)
        password = os.environ.get("SUPERADMIN_PASSWORD", DEFAULT_SUPERADMIN_PASSWORD)

        self.stdout.write(f"Ensuring Cognito group 'superadmin' exists...")
        ensure_cognito_group("superadmin", description="Platform-wide superadmin")

        existing = get_cognito_user_by_email(email)
        if existing:
            username = existing["Username"]
            self.stdout.write(f"Cognito user {email} already exists (username={username}).")
        else:
            self.stdout.write(f"Creating Cognito user {email}...")
            username = create_cognito_user(email=email, name="Super Admin", password=password)
            self.stdout.write(self.style.SUCCESS(f"Created Cognito user {email} (username={username})."))

        add_user_to_group(username, "superadmin")
        add_user_to_group(username, "approved")

        user_id = username.replace("-", "")
        user, created = User.objects.update_or_create(
            id=user_id,
            defaults={
                "email": email,
                "name": "Super Admin",
                "status": "admin",
                "is_superadmin": True,
            },
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} local superadmin User row ({user.id})."))
        self.stdout.write(self.style.SUCCESS(f"Superadmin login: {email} / {password}"))
