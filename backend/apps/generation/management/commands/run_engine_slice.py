"""Run one generation slice straight through the academic facade.

This was a routed endpoint, `POST /api/generation/test-science-engine`. Its own
docstring warned that it "triggers REAL LLM calls (it spends OpenAI budget), so
it must never be reachable anonymously on a deployed host", and it was gated
behind an ENABLE_TEST_ENDPOINTS setting that defaulted to DEBUG. That setting
has since been removed: this command was its only reason to exist, and a
command is not reachable over HTTP for it to gate.

That gate was sound but the shape was wrong: a test fixture was being carried
as application code on the public router, and its safety rested on DEBUG being
false in every environment forever. A management command has the same value
with none of the exposure -- it cannot be reached over HTTP at all, and running
it is a deliberate act by someone with shell access rather than a request.

The parameters were hardcoded to CBSE / Class 10 / Science / Electricity. They
are flags here, defaulting to the same slice, so the original invocation is
`python manage.py run_engine_slice` with nothing after it.

    python manage.py run_engine_slice
    python manage.py run_engine_slice --chapter Magnetism --difficulty hard
    python manage.py run_engine_slice --engine new
"""

import dataclasses
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Execute one paper-generation slice through the academic facade."

    def add_arguments(self, parser):
        parser.add_argument("--board", default="CBSE")
        parser.add_argument("--academic-class", default="CLASS_10")
        parser.add_argument("--exam-type", default="FINAL")
        parser.add_argument(
            "--chapter",
            action="append",
            dest="chapters",
            help="Repeatable. Defaults to Electricity.",
        )
        parser.add_argument("--difficulty", default="medium")
        parser.add_argument("--institution-id", default="DPS_E_DELHI")
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Fixed by default so repeated runs stay comparable.",
        )
        parser.add_argument(
            "--engine",
            choices=("auto", "new", "legacy"),
            default="auto",
            help=(
                "Which facade to call. 'auto' follows QG_NEW_ENGINE_ENABLED, "
                "which is what the endpoint did. 'new' and 'legacy' pin one "
                "regardless, so the two can be compared without restarting "
                "with a different setting."
            ),
        )
        parser.add_argument(
            "--output",
            help="Write the response JSON here instead of to stdout.",
        )

    def handle(self, *args, **options):
        engine = options["engine"]
        use_new = (
            settings.QG_NEW_ENGINE_ENABLED if engine == "auto" else engine == "new"
        )

        if use_new:
            from apps.question_generation.services.facade import (
                AcademicGenerationFacade,
                GeneratePaperRequest,
            )
        else:
            from q_instructions.master.facade import (
                AcademicGenerationFacade,
                GeneratePaperRequest,
            )

        chapters = options["chapters"] or ["Electricity"]

        self.stdout.write(
            "Running slice through the "
            f"{'new' if use_new else 'legacy'} engine: "
            f"{options['board']} / {options['academic_class']} / "
            f"{', '.join(chapters)}"
        )
        self.stdout.write(
            self.style.WARNING("This makes real LLM calls and spends budget.")
        )

        request = GeneratePaperRequest(
            board=options["board"],
            academic_class=options["academic_class"],
            exam_type=options["exam_type"],
            chapters=chapters,
            difficulty=options["difficulty"],
            institution_id=options["institution_id"],
            seed=options["seed"],
        )

        try:
            response = AcademicGenerationFacade().generate_paper(request)
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator
            # The endpoint turned this into a 500 body. A command should fail
            # loudly instead, so a scripted run cannot mistake it for success.
            raise CommandError(f"Generation failed: {exc}") from exc

        payload = json.dumps(dataclasses.asdict(response), indent=2, default=str)

        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as handle:
                handle.write(payload)
            self.stdout.write(self.style.SUCCESS(f"Wrote {options['output']}"))
        else:
            self.stdout.write(payload)
            self.stdout.write(self.style.SUCCESS("Slice completed."))
