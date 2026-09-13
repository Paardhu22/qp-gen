"""Regenerate the checked-in projections of the question type catalogue.

    python manage.py export_question_types            # rewrite the frontend module
    python manage.py export_question_types --check    # CI: fail if it is stale
    python manage.py export_question_types --snapshot apps/projects/migrations/data/question_types_00NN.json

`--snapshot` is only for writing a NEW migration after the catalogue changes.
An existing migration's snapshot is frozen and must never be rewritten.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Write the frontend question type module (and optionally a migration snapshot) from the catalogue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Write nothing; exit with an error if the frontend module is stale.",
        )
        parser.add_argument(
            "--snapshot",
            metavar="PATH",
            help="Also write the DB seed snapshot to PATH, for a new migration.",
        )

    def handle(self, *args, **options):
        from services.question_types.export import (
            FRONTEND_MODULE_PATH,
            frontend_module,
            snapshot_json,
        )

        target = Path(settings.BASE_DIR).parent / FRONTEND_MODULE_PATH
        expected = frontend_module()

        if options["check"]:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != expected:
                raise CommandError(
                    f"{FRONTEND_MODULE_PATH} is stale. Run `python manage.py export_question_types`."
                )
            self.stdout.write(f"{FRONTEND_MODULE_PATH} is current.")
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8")
        self.stdout.write(f"Wrote {FRONTEND_MODULE_PATH}.")

        if options.get("snapshot"):
            snapshot = Path(options["snapshot"])
            if not snapshot.is_absolute():
                snapshot = Path(settings.BASE_DIR) / snapshot
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_text(snapshot_json(), encoding="utf-8")
            self.stdout.write(f"Wrote {snapshot}.")
