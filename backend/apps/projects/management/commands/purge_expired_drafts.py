"""Remove server-side drafts nobody has touched inside the retention window.

Run from cron alongside `purge_deleted_papers`. The list endpoint also purges
lazily whenever a teacher opens their drafts, so this exists for the accounts
where nobody looks — which are exactly the accounts whose drafts should not
accumulate forever.
"""

from django.core.management.base import BaseCommand

from services.draft_service import purge_expired_drafts, retention_days


class Command(BaseCommand):
    help = "Delete server-side drafts untouched for more than DRAFT_RETENTION_DAYS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be purged without deleting anything.",
        )

    def handle(self, *args, **options):
        from datetime import timedelta

        from django.utils import timezone

        from apps.projects.models import Draft

        days = retention_days()
        cutoff = timezone.now() - timedelta(days=days)

        if options.get("dry_run"):
            count = Draft.objects.filter(updated_at__lt=cutoff).count()
            self.stdout.write(
                f"Would delete {count} draft(s) untouched since {cutoff.isoformat()}."
            )
            return

        count = purge_expired_drafts()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} draft(s) untouched for more than {days} days."
            )
        )
