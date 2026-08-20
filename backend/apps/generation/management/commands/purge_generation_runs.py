"""Drop recorded generation runs past their retention window.

Runs are a delivery mechanism, not a record: the questions are already in the
teacher's bank and the paper in their library, and what is kept here is a few
hundred SSE frames whose only purpose is letting a dropped client re-attach.
Once nobody is going to re-attach, they are dead weight.

The list endpoint purges lazily too, so this is for the accounts nobody opens.
"""

from django.core.management.base import BaseCommand

from services.generation_runs import purge_expired_runs, retention_days


class Command(BaseCommand):
    help = "Delete generation runs older than GENERATION_RUN_RETENTION_DAYS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be purged without deleting anything.",
        )

    def handle(self, *args, **options):
        from datetime import timedelta

        from django.utils import timezone

        from apps.generation.models import GenerationRun

        days = retention_days()
        cutoff = timezone.now() - timedelta(days=days)

        if options.get("dry_run"):
            count = GenerationRun.objects.filter(created_at__lt=cutoff).count()
            self.stdout.write(
                f"Would delete {count} run(s) started before {cutoff.isoformat()}."
            )
            return

        count = purge_expired_runs()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} run(s) older than {days} days.")
        )
