"""P2 statelessness-pass tests: Paper.content dual-write to S3, the
flag-gated read accessor, and the backfill command.

Design under test (services/paper_content_service.py):
  * DB column `Paper.content` stays the source of truth — every test
    asserts the DB row is fully populated regardless of S3 behaviour.
  * Saves dual-write a best-effort S3 mirror; S3 failure NEVER breaks a save.
  * Reads go through `read_paper_content`; PAPER_CONTENT_SOURCE="db"
    (default) never touches S3, "s3" tries the mirror and falls back to DB.

All S3 traffic is patched at the single choke point
`services.paper_content_service.{is_configured,upload_bytes,download_to_buffer}`.
"""

import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.projects.models import Paper, Project
from services.paper_content_service import paper_content_s3_key, read_paper_content
from services.project_service import save_paper_to_project

PCS = "services.paper_content_service"
BACKFILL_CMD = "apps.projects.management.commands.backfill_paper_content_to_s3"


def _make_user(uid: str, email: str) -> User:
    return User.objects.create(id=uid, name="Test", email=email)


class ProjectsTests(TestCase):
    def test_placeholder(self):
        self.assertTrue(True)


class PaperContentDualWriteTests(TestCase):
    """Every save_paper_to_project call mirrors content to S3 — and a broken
    mirror never breaks the authoritative DB save."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("dwuser0000000000000000000000001a", "dw@test.local")

    def test_create_dual_writes_content_and_records_key(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="Dual Write Paper",
                content='{"type":"doc"}',
            )

        expected_key = f"paper-content/{self.user.id}/{paper.id}.json"
        mock_upload.assert_called_once()
        args, kwargs = mock_upload.call_args
        self.assertEqual(args[0], expected_key)
        self.assertEqual(args[1], b'{"type":"doc"}')
        self.assertEqual(kwargs.get("content_type"), "application/json")

        paper.refresh_from_db()
        # DB column retained AND mirror key recorded.
        self.assertEqual(paper.content, '{"type":"doc"}')
        self.assertEqual(paper.s3_content_key, expected_key)

    def test_update_dual_writes_to_same_deterministic_key(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="V1",
                content="v1",
            )
            save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="V2",
                content="v2",
                paper_id=paper.id,
            )

        self.assertEqual(mock_upload.call_count, 2)
        first_key = mock_upload.call_args_list[0].args[0]
        second_key = mock_upload.call_args_list[1].args[0]
        # Same paper → same mirror key: the update overwrites in place,
        # never accumulates objects.
        self.assertEqual(first_key, second_key)
        self.assertEqual(mock_upload.call_args_list[1].args[1], b"v2")

        paper.refresh_from_db()
        self.assertEqual(paper.content, "v2")
        self.assertEqual(paper.s3_content_key, first_key)

    def test_s3_failure_never_breaks_the_save(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes", side_effect=RuntimeError("S3 down")):
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="Survives S3 outage",
                content="precious content",
            )

        paper.refresh_from_db()
        self.assertEqual(paper.content, "precious content")
        self.assertIsNone(paper.s3_content_key)  # retried later by backfill

    def test_s3_unconfigured_skips_mirror_silently(self):
        with patch(f"{PCS}.is_configured", return_value=False), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="Local dev",
                content="local-only",
            )

        mock_upload.assert_not_called()
        paper.refresh_from_db()
        self.assertEqual(paper.content, "local-only")
        self.assertIsNone(paper.s3_content_key)

    def test_dual_write_does_not_bump_updated_at(self):
        """The key bookkeeping uses queryset.update() so the mirror never
        changes the paper's edit timestamp."""
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes"):
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="TS",
                content="ts",
            )
        paper.refresh_from_db()
        ts_after_save = paper.updated_at

        from services.paper_content_service import dual_write_paper_content

        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes"):
            dual_write_paper_content(paper)
        paper.refresh_from_db()
        self.assertEqual(paper.updated_at, ts_after_save)


class PaperContentReadAccessorTests(TestCase):
    """read_paper_content: DB-authoritative by default, S3-first behind the
    PAPER_CONTENT_SOURCE flag with DB fallback on every failure mode."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("rauser0000000000000000000000001a", "ra@test.local")
        cls.project = Project.objects.create(name="RA", user=cls.user)
        cls.paper = Paper.objects.create(
            title="RA Paper",
            content="DB CONTENT",
            project=cls.project,
            user=cls.user,
            s3_content_key=f"paper-content/{cls.user.id}/somepaper.json",
        )

    def test_default_db_source_never_touches_s3(self):
        with patch(
            f"{PCS}.download_to_buffer",
            side_effect=AssertionError("S3 must not be consulted when source=db"),
        ):
            self.assertEqual(read_paper_content(self.paper), "DB CONTENT")

    @override_settings(PAPER_CONTENT_SOURCE="s3")
    def test_s3_source_reads_mirror_first(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.download_to_buffer", return_value=b"S3 CONTENT") as dl:
            self.assertEqual(read_paper_content(self.paper), "S3 CONTENT")
        dl.assert_called_once_with(self.paper.s3_content_key)

    @override_settings(PAPER_CONTENT_SOURCE="s3")
    def test_s3_error_falls_back_to_db(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.download_to_buffer", side_effect=RuntimeError("miss")):
            self.assertEqual(read_paper_content(self.paper), "DB CONTENT")

    @override_settings(PAPER_CONTENT_SOURCE="s3")
    def test_s3_source_without_key_uses_db(self):
        keyless = Paper.objects.create(
            title="No key yet",
            content="DB ONLY",
            project=self.project,
            user=self.user,
        )
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.download_to_buffer") as dl:
            self.assertEqual(read_paper_content(keyless), "DB ONLY")
        dl.assert_not_called()


class PaperDetailViewContentSourceTests(TestCase):
    """API-level: GET detail returns DB content under the default flag and
    behaves identically to the pre-pass endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("dvuser0000000000000000000000001a", "dv@test.local")
        cls.project = Project.objects.create(name="DV", user=cls.user)
        cls.paper = Paper.objects.create(
            title="Detail Paper",
            content='{"db": true}',
            project=cls.project,
            user=cls.user,
            s3_content_key=f"paper-content/{cls.user.id}/x.json",
        )

    def setUp(self):
        cache.clear()  # the detail view caches per user+paper for 30 s
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_detail_returns_db_content_by_default(self):
        with patch(
            f"{PCS}.download_to_buffer",
            side_effect=AssertionError("S3 must not be consulted when source=db"),
        ):
            response = self.client.get(f"/api/projects/papers/{self.paper.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["content"], '{"db": true}')


class BackfillCommandTests(TestCase):
    """backfill_paper_content_to_s3 is idempotent and resumable."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("bfuser0000000000000000000000001a", "bf@test.local")
        cls.project = Project.objects.create(name="BF", user=cls.user)
        cls.keyless = Paper.objects.create(
            title="Needs backfill",
            content="backfill me",
            project=cls.project,
            user=cls.user,
        )
        cls.keyed = Paper.objects.create(
            title="Already mirrored",
            content="already there",
            project=cls.project,
            user=cls.user,
            s3_content_key=f"paper-content/{cls.user.id}/keyed.json",
        )

    def _run(self, *args):
        # is_configured is bound in BOTH the command module (gate) and the
        # service module (dual_write internals) — patch each binding.
        with patch(f"{BACKFILL_CMD}.is_configured", return_value=True), \
             patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            call_command("backfill_paper_content_to_s3", *args)
        return mock_upload

    def test_first_run_pushes_only_keyless_papers(self):
        mock_upload = self._run()
        mock_upload.assert_called_once()
        self.assertEqual(
            mock_upload.call_args.args[0], paper_content_s3_key(self.keyless)
        )
        self.keyless.refresh_from_db()
        self.assertEqual(
            self.keyless.s3_content_key, paper_content_s3_key(self.keyless)
        )

    def test_second_run_is_a_noop(self):
        self._run()
        mock_upload = self._run()
        mock_upload.assert_not_called()  # idempotent

    def test_force_repushes_everything(self):
        self._run()
        mock_upload = self._run("--force")
        self.assertEqual(mock_upload.call_count, 2)

    def test_dry_run_uploads_nothing(self):
        mock_upload = self._run("--dry-run")
        mock_upload.assert_not_called()
        self.keyless.refresh_from_db()
        self.assertIsNone(self.keyless.s3_content_key)


class AnswerScriptDualWriteTests(TestCase):
    """Answer scripts are Paper rows: generating one must dual-write its
    content like any teacher-saved paper (design point 6)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("asuser0000000000000000000000001a", "as@test.local")
        cls.project = Project.objects.create(name="Class 10 — Science", user=cls.user)
        tiptap = {
            "type": "doc",
            "content": [
                {
                    "type": "page",
                    "attrs": {"pageId": "page-1"},
                    "content": [
                        {
                            "type": "questionBlock",
                            "attrs": {
                                "marks": 2,
                                "number": 1,
                                "questionType": "SHORT_ANSWER",
                            },
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Define electrical resistance and state its SI unit.",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        cls.paper = Paper.objects.create(
            title="Science Paper",
            content=json.dumps(tiptap),
            project=cls.project,
            user=cls.user,
        )

    def test_generated_answer_script_is_dual_written(self):
        from apps.documents.models import PdfSource

        PdfSource.objects.create(
            name="src.pdf", size=10, user=self.user, status="ready"
        )

        ASS = "services.answer_script_service"

        def fake_llm_answer(client, question_number, question, source_chunks, user):
            return question_number, {
                "question_number": question_number,
                "question_text": question["content"],
                "question_type": "SHORT_ANSWER",
                "marks": question.get("marks", 1),
                "answer": "Opposition to current flow; SI unit ohm.",
                "or_choice_text": None,
                "or_answer": None,
            }

        with patch(f"{ASS}.get_openai_client", return_value=MagicMock()), \
             patch(f"{ASS}.generate_embeddings", return_value=[[0.0] * 1536]), \
             patch(f"{ASS}.retrieve_relevant_chunks", return_value=[]), \
             patch(f"{ASS}._generate_single_answer_llm_only", side_effect=fake_llm_answer), \
             patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            from services.answer_script_service import generate_answer_script

            result = generate_answer_script(paper_id=self.paper.id, user=self.user)

        answer_paper = Paper.objects.get(id=result["answer_script_paper_id"])
        expected_key = f"paper-content/{self.user.id}/{answer_paper.id}.json"

        # DB stays authoritative AND the mirror was written.
        self.assertTrue(answer_paper.content)
        self.assertEqual(answer_paper.s3_content_key, expected_key)
        uploaded_keys = [c.args[0] for c in mock_upload.call_args_list]
        self.assertIn(expected_key, uploaded_keys)

        # Regression guard: source paper still links to its answer script.
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.answer_script_id, answer_paper.id)
