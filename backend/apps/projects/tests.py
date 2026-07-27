"""P2 statelessness-pass tests: PaperSet.content dual-write to S3, the
flag-gated read accessor, and the backfill command.

Design under test (services/paper_content_service.py):
  * DB column `PaperSet.content` stays the source of truth — every test
    asserts the DB row is fully populated regardless of S3 behaviour.
  * Saves dual-write a best-effort S3 mirror; S3 failure NEVER breaks a save.
  * Reads go through `read_set_content`; PAPER_CONTENT_SOURCE="db"
    (default) never touches S3, "s3" tries the mirror and falls back to DB.

Ported from the paper-level API when content moved from `Paper.content` onto
`PaperSet.content` for multiple paper sets. The module previously imported
`paper_content_s3_key` / `read_paper_content`, which no longer exist — so it
failed to import and silently took every test in `apps.projects` with it.
That is exactly how the same rename went unnoticed in
`services/answer_script_service.py`, which shipped broken.

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
from apps.projects.models import Paper, PaperSet, Project
from services.paper_content_service import read_set_content, set_content_s3_key
from services.project_service import save_paper_to_project

PCS = "services.paper_content_service"
BACKFILL_CMD = "apps.projects.management.commands.backfill_set_content_to_s3"


def _make_user(uid: str, email: str) -> User:
    return User.objects.create(id=uid, name="Test", email=email)


def _set_a(content: str) -> list:
    """The single-set payload every save goes through post-multi-set."""
    return [{"label": "Set A", "order": 1, "content": content}]


def _make_paper_with_set(user, project, *, title, content, s3_content_key=None):
    paper = Paper.objects.create(title=title, project=project, user=user)
    paper_set = PaperSet.objects.create(
        paper=paper,
        label="Set A",
        order=1,
        content=content,
        s3_content_key=s3_content_key,
    )
    return paper, paper_set


class ProjectsTests(TestCase):
    def test_placeholder(self):
        self.assertTrue(True)


class SetContentDualWriteTests(TestCase):
    """Every save_paper_to_project call mirrors each set's content to S3 — and
    a broken mirror never breaks the authoritative DB save."""

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
                sets=_set_a('{"type":"doc"}'),
            )

        paper_set = paper.sets.get()
        expected_key = (
            f"paper-content/{self.user.id}/{paper.id}/{paper_set.id}.json"
        )
        mock_upload.assert_called_once()
        args, kwargs = mock_upload.call_args
        self.assertEqual(args[0], expected_key)
        self.assertEqual(args[1], b'{"type":"doc"}')
        self.assertEqual(kwargs.get("content_type"), "application/json")

        paper_set.refresh_from_db()
        # DB column retained AND mirror key recorded.
        self.assertEqual(paper_set.content, '{"type":"doc"}')
        self.assertEqual(paper_set.s3_content_key, expected_key)

    def test_every_set_gets_its_own_mirror_object(self):
        """A/B/C are separate documents, so each needs its own key — one
        object per set, never one blob per paper."""
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="Three Sets",
                sets=[
                    {"label": "Set A", "order": 1, "content": "a"},
                    {"label": "Set B", "order": 2, "content": "b"},
                    {"label": "Set C", "order": 3, "content": "c"},
                ],
            )

        self.assertEqual(mock_upload.call_count, 3)
        keys = {call.args[0] for call in mock_upload.call_args_list}
        self.assertEqual(len(keys), 3)
        self.assertEqual(
            keys, {set_content_s3_key(s) for s in paper.sets.all()}
        )
        self.assertEqual(
            {call.args[1] for call in mock_upload.call_args_list},
            {b"a", b"b", b"c"},
        )

    def test_update_rewrites_content(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="V1",
                sets=_set_a("v1"),
            )
            save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="V2",
                sets=_set_a("v2"),
                paper_id=paper.id,
            )

        self.assertEqual(mock_upload.call_count, 2)
        self.assertEqual(mock_upload.call_args_list[1].args[1], b"v2")

        paper_set = paper.sets.get()
        self.assertEqual(paper_set.content, "v2")
        self.assertEqual(paper_set.s3_content_key, set_content_s3_key(paper_set))

    def test_s3_failure_never_breaks_the_save(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes", side_effect=RuntimeError("S3 down")):
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="Survives S3 outage",
                sets=_set_a("precious content"),
            )

        paper_set = paper.sets.get()
        self.assertEqual(paper_set.content, "precious content")
        self.assertIsNone(paper_set.s3_content_key)  # retried later by backfill

    def test_s3_unconfigured_skips_mirror_silently(self):
        with patch(f"{PCS}.is_configured", return_value=False), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="Local dev",
                sets=_set_a("local-only"),
            )

        mock_upload.assert_not_called()
        paper_set = paper.sets.get()
        self.assertEqual(paper_set.content, "local-only")
        self.assertIsNone(paper_set.s3_content_key)

    def test_dual_write_does_not_bump_updated_at(self):
        """The key bookkeeping uses queryset.update() so the mirror never
        changes the set's edit timestamp."""
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes"):
            paper = save_paper_to_project(
                user=self.user,
                project_name="P2 Project",
                title="TS",
                sets=_set_a("ts"),
            )
        paper_set = paper.sets.get()
        ts_after_save = paper_set.updated_at

        from services.paper_content_service import dual_write_set_content

        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes"):
            dual_write_set_content(paper_set)
        paper_set.refresh_from_db()
        self.assertEqual(paper_set.updated_at, ts_after_save)


class SetPreservationTests(TestCase):
    """Saving must not destroy sets the payload does not mention.

    Editor autosave sends only Set A. The save path used to delete every set
    and recreate from the payload, which meant the first keystroke on an
    A/B/C paper deleted B and C — and minted new ids for A, discarding its
    export keys.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("spuser0000000000000000000000001a", "sp@test.local")

    def _three_set_paper(self):
        return save_paper_to_project(
            user=self.user,
            project_name="Sets Project",
            title="Board Paper",
            sets=[
                {"label": "Set A", "order": 1, "content": "a1"},
                {"label": "Set B", "order": 2, "content": "b1"},
                {"label": "Set C", "order": 3, "content": "c1"},
            ],
        )

    def test_autosaving_set_a_keeps_sets_b_and_c(self):
        paper = self._three_set_paper()

        # Exactly what updatePaperAction sends when the editor autosaves.
        save_paper_to_project(
            user=self.user,
            project_name="Sets Project",
            title="Board Paper",
            sets=[{"label": "Set A", "order": 1, "content": "a2"}],
            paper_id=paper.id,
        )

        by_label = {s.label: s for s in paper.sets.all()}
        self.assertEqual(sorted(by_label), ["Set A", "Set B", "Set C"])
        self.assertEqual(by_label["Set A"].content, "a2")
        self.assertEqual(by_label["Set B"].content, "b1")
        self.assertEqual(by_label["Set C"].content, "c1")

    def test_set_ids_and_export_keys_survive_a_save(self):
        paper = self._three_set_paper()
        set_a = paper.sets.get(label="Set A")
        original_id = set_a.id
        PaperSet.objects.filter(pk=set_a.pk).update(
            s3_pdf_key="question-papers/u/p/paper-a.pdf"
        )

        save_paper_to_project(
            user=self.user,
            project_name="Sets Project",
            title="Board Paper",
            sets=[{"label": "Set A", "order": 1, "content": "a2"}],
            paper_id=paper.id,
        )

        set_a.refresh_from_db()
        self.assertEqual(set_a.id, original_id)
        # A previously exported PDF is still reachable.
        self.assertEqual(set_a.s3_pdf_key, "question-papers/u/p/paper-a.pdf")

    def test_label_matching_ignores_the_set_prefix_and_case(self):
        """Generated sets are labelled "A"; saved ones "Set A". Both must
        resolve to the same row rather than duplicating it."""
        paper = save_paper_to_project(
            user=self.user,
            project_name="Sets Project",
            title="Prefix",
            sets=[{"label": "Set A", "order": 1, "content": "v1"}],
        )
        save_paper_to_project(
            user=self.user,
            project_name="Sets Project",
            title="Prefix",
            sets=[{"label": "A", "order": 1, "content": "v2"}],
            paper_id=paper.id,
        )
        self.assertEqual(paper.sets.count(), 1)
        self.assertEqual(paper.sets.get().content, "v2")

    def test_a_new_set_is_added_without_touching_the_others(self):
        paper = save_paper_to_project(
            user=self.user,
            project_name="Sets Project",
            title="Growing",
            sets=[{"label": "Set A", "order": 1, "content": "a1"}],
        )
        save_paper_to_project(
            user=self.user,
            project_name="Sets Project",
            title="Growing",
            sets=[
                {"label": "Set A", "order": 1, "content": "a1"},
                {"label": "Set B", "order": 2, "content": "b1"},
            ],
            paper_id=paper.id,
        )
        self.assertEqual(
            sorted(s.label for s in paper.sets.all()), ["Set A", "Set B"]
        )


class SetContentReadAccessorTests(TestCase):
    """read_set_content: DB-authoritative by default, S3-first behind the
    PAPER_CONTENT_SOURCE flag with DB fallback on every failure mode."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("rauser0000000000000000000000001a", "ra@test.local")
        cls.project = Project.objects.create(name="RA", user=cls.user)
        cls.paper, cls.paper_set = _make_paper_with_set(
            cls.user,
            cls.project,
            title="RA Paper",
            content="DB CONTENT",
            s3_content_key=f"paper-content/{cls.user.id}/p/somepaperset.json",
        )

    def test_default_db_source_never_touches_s3(self):
        with patch(
            f"{PCS}.download_to_buffer",
            side_effect=AssertionError("S3 must not be consulted when source=db"),
        ):
            self.assertEqual(read_set_content(self.paper_set), "DB CONTENT")

    @override_settings(PAPER_CONTENT_SOURCE="s3")
    def test_s3_source_reads_mirror_first(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.download_to_buffer", return_value=b"S3 CONTENT") as dl:
            self.assertEqual(read_set_content(self.paper_set), "S3 CONTENT")
        dl.assert_called_once_with(self.paper_set.s3_content_key)

    @override_settings(PAPER_CONTENT_SOURCE="s3")
    def test_s3_error_falls_back_to_db(self):
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.download_to_buffer", side_effect=RuntimeError("miss")):
            self.assertEqual(read_set_content(self.paper_set), "DB CONTENT")

    @override_settings(PAPER_CONTENT_SOURCE="s3")
    def test_s3_source_without_key_uses_db(self):
        _, keyless = _make_paper_with_set(
            self.user, self.project, title="No key yet", content="DB ONLY"
        )
        with patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.download_to_buffer") as dl:
            self.assertEqual(read_set_content(keyless), "DB ONLY")
        dl.assert_not_called()


class PaperDetailViewContentSourceTests(TestCase):
    """API-level: GET detail returns DB content under the default flag and
    behaves identically to the pre-pass endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("dvuser0000000000000000000000001a", "dv@test.local")
        cls.project = Project.objects.create(name="DV", user=cls.user)
        cls.paper, cls.paper_set = _make_paper_with_set(
            cls.user,
            cls.project,
            title="Detail Paper",
            content='{"db": true}',
            s3_content_key=f"paper-content/{cls.user.id}/p/x.json",
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
        sets = response.data["sets"]
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]["content"], '{"db": true}')


class BackfillCommandTests(TestCase):
    """backfill_set_content_to_s3 is idempotent and resumable."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("bfuser0000000000000000000000001a", "bf@test.local")
        cls.project = Project.objects.create(name="BF", user=cls.user)
        _, cls.keyless = _make_paper_with_set(
            cls.user, cls.project, title="Needs backfill", content="backfill me"
        )
        _, cls.keyed = _make_paper_with_set(
            cls.user,
            cls.project,
            title="Already mirrored",
            content="already there",
            s3_content_key=f"paper-content/{cls.user.id}/p/keyed.json",
        )

    def _run(self, *args):
        # is_configured is bound in BOTH the command module (gate) and the
        # service module (dual_write internals) — patch each binding.
        with patch(f"{BACKFILL_CMD}.is_configured", return_value=True), \
             patch(f"{PCS}.is_configured", return_value=True), \
             patch(f"{PCS}.upload_bytes") as mock_upload:
            call_command("backfill_set_content_to_s3", *args)
        return mock_upload

    def test_first_run_pushes_only_keyless_sets(self):
        mock_upload = self._run()
        mock_upload.assert_called_once()
        self.assertEqual(
            mock_upload.call_args.args[0], set_content_s3_key(self.keyless)
        )
        self.keyless.refresh_from_db()
        self.assertEqual(
            self.keyless.s3_content_key, set_content_s3_key(self.keyless)
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
    """Answer scripts are Paper+PaperSet rows: generating one must dual-write
    its set content like any teacher-saved paper (design point 6)."""

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
        cls.paper, cls.paper_set = _make_paper_with_set(
            cls.user, cls.project, title="Science Paper", content=json.dumps(tiptap)
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
        answer_set = answer_paper.sets.get()
        expected_key = set_content_s3_key(answer_set)

        # DB stays authoritative AND the mirror was written.
        self.assertTrue(answer_set.content)
        self.assertEqual(answer_set.s3_content_key, expected_key)
        uploaded_keys = [c.args[0] for c in mock_upload.call_args_list]
        self.assertIn(expected_key, uploaded_keys)

        # Regression guard: source paper still links to its answer script.
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.answer_script_id, answer_paper.id)

    def test_answer_script_reads_set_a_not_a_paper_column(self):
        """Regression: the generator used to read `Paper.content`, a column
        that no longer exists. It must read the paper's first set."""
        from services.answer_script_service import _read_primary_set_content

        self.assertIn("electrical resistance", _read_primary_set_content(self.paper))
