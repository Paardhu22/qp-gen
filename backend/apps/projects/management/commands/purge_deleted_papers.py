"""Permanently remove papers that have sat in the recycle bin past its window.

Run from cron (daily is plenty). The bin also purges itself lazily whenever a
teacher opens it, so a deployment with no scheduler still honours the retention
promise — but only for teachers who look. This is what makes the promise true
for the ones who never open the bin again.
"""

from django.core.management.base import BaseCommand

from services.project_service import purge_expired_papers, trash_retention_days


class Command(BaseCommand):
    help = "Permanently delete papers deleted more than PAPER_TRASH_RETENTION_DAYS ago."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be purged without deleting anything.",
        )

    def handle(self, *args, **options):
        from datetime import timedelta

        from django.utils import timezone

        from apps.projects.models import Paper

        days = trash_retention_days()
        cutoff = timezone.now() - timedelta(days=days)
        expired = Paper.objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)

        if options.get("dry_run"):
            count = expired.count()
            self.stdout.write(
                f"Would permanently delete {count} paper(s) binned before {cutoff.isoformat()}."
            )
            return

        count = purge_expired_papers()
        self.stdout.write(
            self.style.SUCCESS(
                f"Permanently deleted {count} paper(s) binned more than {days} days ago."
            )
        )
