"""Backfill existing Paper rows' content to the S3 mirror (P2).

    python manage.py backfill_paper_content_to_s3 [--force] [--dry-run]

Runs AFTER the dual-write deploy, in the background — launch does not block
on it. Properties:

* Idempotent: papers that already have ``s3_content_key`` are skipped
  (``--force`` re-pushes them; the mirror key is deterministic, so a
  re-push is a same-key overwrite, never a duplicate).
* Resumable: each paper is handled independently; failures are logged and
  counted but never abort the run. A failed paper keeps a NULL key, so the
  next run simply picks it up again.
* Exits non-zero when any paper failed, so a cron/deploy wrapper notices.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.projects.models import Paper
from services.paper_content_service import (
    dual_write_paper_content,
    is_configured,
    paper_content_s3_key,
)


class Command(BaseCommand):
    help = (
        "Idempotently mirror Paper.content to S3 at "
        "paper-content/{userId}/{paperId}.json. Skips papers that already "
        "have s3_content_key unless --force is given."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-upload even when s3_content_key is already set.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be pushed without uploading anything.",
        )

    def handle(self, *args, **options):
        if not is_configured():
            self.stderr.write(
                self.style.ERROR(
                    "S3 is not configured (AWS_STORAGE_BUCKET_NAME / "
                    "HSAT_S3_BUCKET missing) — cannot backfill."
                )
            )
            raise SystemExit(1)

        force: bool = options["force"]
        dry_run: bool = options["dry_run"]
        pushed = skipped = failed = 0

        queryset = (
            Paper.objects.all()
            .order_by("created_at")
            .only("id", "content", "s3_content_key", "user")
        )
        for paper in queryset.iterator(chunk_size=100):
            if paper.s3_content_key and not force:
                skipped += 1
                continue
            if dry_run:
                pushed += 1
                self.stdout.write(
                    f"would push {paper.id} -> {paper_content_s3_key(paper)}"
                )
                continue
            if dual_write_paper_content(paper):
                pushed += 1
            else:
                failed += 1
                self.stderr.write(self.style.WARNING(f"FAILED {paper.id}"))

        summary = (
            f"backfill_paper_content_to_s3: pushed={pushed} "
            f"skipped={skipped} failed={failed}"
            + (" (dry run)" if dry_run else "")
        )
        if failed:
            self.stderr.write(self.style.ERROR(summary))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(summary))
