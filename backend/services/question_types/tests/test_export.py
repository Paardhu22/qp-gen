"""The checked-in projections must match the catalogue they project.

Two files are written from `services.question_types` and committed: the
newest migration's seed snapshot (0017) and the frontend module. Nothing regenerates them
at runtime, so without these tests a catalogue edit would reach neither the
database nor the editor — silently.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from services import question_types as qt
from services.question_types.export import (
    FRONTEND_MODULE_PATH,
    RENAMED_CODES,
    db_snapshot,
    frontend_module,
)

_SNAPSHOT = (
    Path(settings.BASE_DIR) / "apps" / "projects" / "migrations" / "data" / "question_types_0017.json"
)
_FRONTEND = Path(settings.BASE_DIR).parent / FRONTEND_MODULE_PATH


class ProjectionSyncTests(SimpleTestCase):
    def test_the_migration_snapshot_matches_the_catalogue(self):
        frozen = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(
            frozen,
            db_snapshot(),
            "The catalogue changed after migration 0017 was written. Add a new "
            "migration with a fresh snapshot: python manage.py "
            "export_question_types --snapshot apps/projects/migrations/data/question_types_00NN.json",
        )

    def test_the_frontend_module_is_current(self):
        if not _FRONTEND.exists():
            self.skipTest("No frontend checkout beside the backend.")
        self.assertEqual(
            _FRONTEND.read_text(encoding="utf-8"),
            frontend_module(),
            "Run `python manage.py export_question_types` to regenerate the frontend module.",
        )


class SeededCatalogueTests(TestCase):
    """What migrations 0016–0017 leave in the database (the test DB runs them)."""

    def test_every_catalogue_type_is_seeded_in_its_family(self):
        from apps.projects.models import QuestionType

        seeded = dict(QuestionType.objects.values_list("code", "family_id"))
        for spec in qt.all_types():
            with self.subTest(code=spec.code):
                self.assertEqual(seeded.get(spec.code), spec.family)

    def test_renamed_codes_survive_only_as_aliases(self):
        from apps.projects.models import QuestionType, QuestionTypeAlias

        for old, new in RENAMED_CODES.items():
            with self.subTest(old=old):
                self.assertFalse(QuestionType.objects.filter(code=old).exists())
                self.assertTrue(
                    QuestionTypeAlias.objects.filter(alias=old, type_id=new).exists()
                )

    def test_the_split_objective_family_is_gone(self):
        from apps.projects.models import QuestionFamily

        self.assertFalse(QuestionFamily.objects.filter(code="OBJECTIVE").exists())
        self.assertEqual(QuestionFamily.objects.count(), len(qt.FAMILIES))

    def test_competency_now_banks_as_the_application_type(self):
        from apps.projects.question_types import resolve_type_code

        self.assertEqual(resolve_type_code("COMPETENCY"), "APPLICATION_SCENARIO")
        self.assertEqual(resolve_type_code("MCQ"), "MCQ_SINGLE")
        self.assertEqual(resolve_type_code("MCQ_ODD_ONE_OUT"), "MCQ_ODD_ONE_OUT")
