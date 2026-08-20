import os

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from services.cognito_service import (
    add_user_to_group,
    create_cognito_user,
    ensure_cognito_group,
    get_cognito_user_by_email,
)

DEFAULT_SUPERADMIN_EMAIL = "superadmin@hsatedu.in"


class Command(BaseCommand):
    help = "Idempotently create/ensure the platform superadmin Cognito user + local User row."

    def handle(self, *args, **options):
        email = os.environ.get("SUPERADMIN_EMAIL", DEFAULT_SUPERADMIN_EMAIL)
        password = os.environ.get("SUPERADMIN_PASSWORD")
        if not password:
            raise CommandError(
                "SUPERADMIN_PASSWORD is required. Refusing to create or reset "
                "a platform superadmin with a committed default password."
            )

        self.stdout.write(f"Ensuring Cognito group 'superadmin' exists...")
        ensure_cognito_group("superadmin", description="Platform-wide superadmin")

        # Everything below keys off `sub`, never the Cognito Username: the pool
        # uses email as an alias, so Usernames are opaque UUIDs unrelated to the
        # `sub` that authentication.py builds User.id from.
        existing = get_cognito_user_by_email(email)
        if existing:
            sub = next(
                (a["Value"] for a in existing.get("UserAttributes", []) if a["Name"] == "sub"),
                None,
            )
            if not sub:
                raise CommandError(f"Cognito user {email} exists but has no sub attribute.")
            self.stdout.write(f"Cognito user {email} already exists (sub={sub}).")
        else:
            self.stdout.write(f"Creating Cognito user {email}...")
            sub = create_cognito_user(email=email, name="Super Admin", password=password)
            self.stdout.write(self.style.SUCCESS(f"Created Cognito user {email} (sub={sub})."))

        # Group APIs take the pool Username or an alias — never the sub, which
        # is a different value for admin-created users. Email is the alias.
        add_user_to_group(email, "superadmin")
        add_user_to_group(email, "approved")

        user_id = sub.replace("-", "")
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
        self.stdout.write(self.style.SUCCESS(f"Superadmin login email: {email}"))
