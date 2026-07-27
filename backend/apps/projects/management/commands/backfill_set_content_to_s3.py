"""Backfill existing PaperSet rows' content to the S3 mirror (P2).

    python manage.py backfill_set_content_to_s3 [--force] [--dry-run]

Runs AFTER the dual-write deploy, in the background — launch does not block
on it. Properties:

* Idempotent: sets that already have ``s3_content_key`` are skipped
  (``--force`` re-pushes them; the mirror key is deterministic, so a
  re-push is a same-key overwrite, never a duplicate).
* Resumable: each set is handled independently; failures are logged and
  counted but never abort the run. A failed set keeps a NULL key, so the
  next run simply picks it up again.
* Exits non-zero when any set failed, so a cron/deploy wrapper notices.

Renamed from ``backfill_paper_content_to_s3`` when paper content moved from
``Paper.content`` onto ``PaperSet.content`` for multiple paper sets. The old
name imported functions that no longer exist, so the command could not even
be loaded.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.projects.models import PaperSet
from services.paper_content_service import (
    dual_write_set_content,
    is_configured,
    set_content_s3_key,
)


class Command(BaseCommand):
    help = (
        "Idempotently mirror PaperSet.content to S3 at "
        "paper-content/{userId}/{paperId}/{setId}.json. Skips sets that "
        "already have s3_content_key unless --force is given."
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

        # select_related("paper"): the mirror key embeds the owning paper's id
        # and user id, so without it every set costs two extra queries.
        queryset = (
            PaperSet.objects.select_related("paper")
            .order_by("created_at")
            .iterator(chunk_size=100)
        )
        for paper_set in queryset:
            if paper_set.s3_content_key and not force:
                skipped += 1
                continue
            if dry_run:
                pushed += 1
                self.stdout.write(
                    f"would push {paper_set.id} -> {set_content_s3_key(paper_set)}"
                )
                continue
            if dual_write_set_content(paper_set):
                pushed += 1
            else:
                failed += 1
                self.stderr.write(self.style.WARNING(f"FAILED {paper_set.id}"))

        summary = (
            f"backfill_set_content_to_s3: pushed={pushed} "
            f"skipped={skipped} failed={failed}"
            + (" (dry run)" if dry_run else "")
        )
        if failed:
            self.stderr.write(self.style.ERROR(summary))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(summary))
