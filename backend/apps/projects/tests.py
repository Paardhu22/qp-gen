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
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.projects.models import Draft, Paper, PaperSet, Project
from services.paper_content_service import read_set_content, set_content_s3_key
from services.project_service import save_paper_to_project

PCS = "services.paper_content_service"
BACKFILL_CMD = "apps.projects.management.commands.backfill_set_content_to_s3"


def _make_user(uid: str, email: str) -> User:
    return User.objects.create(id=uid, name="Test", email=email, status="approved")


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


class QuestionImagePersistenceTests(TestCase):
    """A diagram question must keep its diagram, in and out of the bank.

    The failure this pins: a question generated with a figure showed the image
    while it streamed, then lost it the moment it came back out of the question
    bank. Two independent gaps, both silent —

      * `QuestionSerializer` listed neither `image_url` nor `explanation`, so
        the READ dropped them. `buildFigureNode` received `undefined` and
        skipped the figure, leaving "using the given figure…" above nothing.
      * `save_questions_to_bank` never passed them to `Question(...)`, so the
        WRITE discarded them too — that one is unrecoverable, the column went
        in NULL.

    The pool's own auto-save (`PoolQuestion.to_model_kwargs`) always wrote
    both, which is why the image was still in the DB for pool-generated rows
    and the symptom looked like a rendering bug.
    """

    IMAGE = "/media/generated_diagrams/punnett-square-f2.png"

    def setUp(self):
        # `ProjectListView` caches the nested response for 30s under a
        # per-user key, and LocMemCache outlives the per-test database. Without
        # this, one test's listing is served to the next one.
        cache.clear()
        self.user = _make_user("u-img", "img@example.com")
        self.project = Project.objects.create(name="Class 10 — Science", user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _question(self, **overrides):
        from apps.projects.models import Question

        defaults = dict(
            content="Using the given figure showing the inheritance pattern…",
            answer="3:1",
            options=[],
            marks=3,
            project=self.project,
            image_url=self.IMAGE,
            explanation="The F2 ratio follows from independent assortment.",
            bloom_taxonomy="ANALYZE",
        )
        defaults.update(overrides)
        return Question.objects.create(**defaults)

    def test_the_serializer_carries_the_image_and_explanation(self):
        from apps.projects.serializers import QuestionSerializer

        data = QuestionSerializer(self._question()).data
        self.assertEqual(data["image_url"], self.IMAGE)
        self.assertIn("independent assortment", data["explanation"])

    def test_a_question_without_an_image_serialises_without_one(self):
        from apps.projects.serializers import QuestionSerializer

        data = QuestionSerializer(self._question(image_url=None, explanation=None)).data
        self.assertIn("image_url", data, "the key must exist even when empty")
        self.assertIsNone(data["image_url"])

    def test_the_bank_listing_includes_the_image(self):
        # The path the editor's "insert from bank" reads. Without the image the
        # inserted block is a question about a figure that is not there.
        self._question()
        response = self.client.get("/api/projects/?withQuestions=true")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        projects = payload if isinstance(payload, list) else payload.get("results", [])
        images = [
            question.get("image_url")
            for project in projects
            for question in project.get("questions", [])
        ]
        self.assertIn(self.IMAGE, images)

    def test_saving_questions_by_hand_keeps_the_image(self):
        from apps.projects.models import Question
        from services.project_service import save_questions_to_project

        save_questions_to_project(
            self.user,
            "Class 10 — Science",
            [
                {
                    "content": "Identify the labelled part in the diagram.",
                    "answer": "Xylem",
                    "type": None,
                    "marks": 2,
                    "options": [],
                    "grade_class": "10",
                    "subject": "Science",
                    "image_url": self.IMAGE,
                    "explanation": "Xylem carries water upward.",
                    "bloom_taxonomy": "UNDERSTAND",
                }
            ],
        )

        saved = Question.objects.get(content="Identify the labelled part in the diagram.")
        self.assertEqual(saved.image_url, self.IMAGE, "the write path dropped the image")
        self.assertEqual(saved.explanation, "Xylem carries water upward.")
        self.assertEqual(saved.bloom_taxonomy, "UNDERSTAND")

    def test_a_hand_saved_question_without_an_image_still_saves(self):
        from apps.projects.models import Question
        from services.project_service import save_questions_to_project

        save_questions_to_project(
            self.user,
            "Class 10 — Science",
            [{"content": "Define osmosis.", "type": None, "marks": 1}],
        )
        saved = Question.objects.get(content="Define osmosis.")
        self.assertIsNone(saved.image_url)

    def test_the_image_survives_a_full_write_then_read(self):
        # The round trip that was broken end to end: save a diagram question,
        # read it back the way the editor does, and still have the figure.
        from services.project_service import save_questions_to_project

        save_questions_to_project(
            self.user,
            "Class 10 — Science",
            [
                {
                    "content": "Study the ray diagram and state the image type.",
                    "type": None,
                    "marks": 3,
                    "grade_class": "10",
                    "subject": "Science",
                    "image_url": self.IMAGE,
                }
            ],
        )

        response = self.client.get("/api/projects/?withQuestions=true")
        payload = response.json()
        projects = payload if isinstance(payload, list) else payload.get("results", [])
        match = next(
            question
            for project in projects
            for question in project.get("questions", [])
            if question["content"].startswith("Study the ray diagram")
        )
        self.assertEqual(match["image_url"], self.IMAGE)


class PaperRecycleBinTests(TestCase):
    """Deleting a paper is survivable. See `Paper.deleted_at`."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create(
            id="ff111111111111111111111111111111",
            name="Teacher",
            email="bin@example.com",
            status="approved",
        )
        self.other = User.objects.create(
            id="ff222222222222222222222222222222",
            name="Other",
            email="other-bin@example.com",
            status="approved",
        )
        self.client.force_authenticate(user=self.user)
        self.paper = self._make_paper("Term 1 Science")

    def _make_paper(self, title, user=None):
        project, _ = Project.objects.get_or_create(name="P", user=user or self.user)
        paper = Paper.objects.create(title=title, project=project, user=user or self.user)
        PaperSet.objects.create(paper=paper, label="A", order=1, content="<p>Q1</p>")
        return paper

    def test_delete_moves_the_paper_to_the_bin_rather_than_destroying_it(self):
        response = self.client.delete(f"/api/projects/papers/{self.paper.id}/")

        self.assertEqual(response.status_code, 200)
        self.paper.refresh_from_db()
        self.assertIsNotNone(self.paper.deleted_at)

    def test_a_binned_paper_is_gone_from_the_library(self):
        self.client.delete(f"/api/projects/papers/{self.paper.id}/")
        response = self.client.get("/api/projects/papers/")
        self.assertEqual(response.data, [])

    def test_a_binned_paper_cannot_be_opened(self):
        self.client.delete(f"/api/projects/papers/{self.paper.id}/")
        response = self.client.get(f"/api/projects/papers/{self.paper.id}/")
        self.assertEqual(response.status_code, 404)

    def test_a_binned_paper_cannot_be_written_back_to_life_by_a_stale_tab(self):
        self.client.delete(f"/api/projects/papers/{self.paper.id}/")

        response = self.client.put(
            f"/api/projects/papers/{self.paper.id}/",
            {
                "projectName": "P",
                "title": "Resurrected",
                "sets": [{"label": "A", "order": 1, "content": "<p>x</p>"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.paper.refresh_from_db()
        self.assertIsNotNone(self.paper.deleted_at)

    def test_the_bin_lists_it_with_the_retention_window(self):
        self.client.delete(f"/api/projects/papers/{self.paper.id}/")
        response = self.client.get("/api/projects/papers/trash")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["papers"]), 1)
        self.assertEqual(response.data["papers"][0]["id"], self.paper.id)
        self.assertGreater(response.data["retention_days"], 0)

    def test_restoring_puts_it_back_in_the_library(self):
        self.client.delete(f"/api/projects/papers/{self.paper.id}/")

        response = self.client.post(f"/api/projects/papers/{self.paper.id}/restore")

        self.assertEqual(response.status_code, 200)
        self.paper.refresh_from_db()
        self.assertIsNone(self.paper.deleted_at)
        self.assertEqual(len(self.client.get("/api/projects/papers/").data), 1)

    def test_permanent_delete_is_a_separate_deliberate_step(self):
        self.client.delete(f"/api/projects/papers/{self.paper.id}/")

        response = self.client.delete(
            f"/api/projects/papers/{self.paper.id}/?permanent=true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Paper.objects.filter(id=self.paper.id).exists())

    def test_clear_all_bins_rather_than_destroys(self):
        self._make_paper("Second")
        response = self.client.delete("/api/projects/papers/clear")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Paper.objects.filter(user=self.user).count(), 2)
        self.assertEqual(
            Paper.objects.filter(user=self.user, deleted_at__isnull=True).count(), 0
        )

    def test_another_teachers_bin_is_not_reachable(self):
        theirs = self._make_paper("Theirs", user=self.other)
        theirs.deleted_at = timezone.now()
        theirs.save(update_fields=["deleted_at"])

        self.assertEqual(self.client.get("/api/projects/papers/trash").data["papers"], [])
        self.assertEqual(
            self.client.post(f"/api/projects/papers/{theirs.id}/restore").status_code, 404
        )

    @override_settings(PAPER_TRASH_RETENTION_DAYS=30)
    def test_a_paper_past_the_window_is_purged_and_cannot_be_restored(self):
        self.paper.deleted_at = timezone.now() - timedelta(days=31)
        self.paper.save(update_fields=["deleted_at"])

        # Listing the bin purges what has aged out, so a deployment with no
        # scheduler still honours the promise the UI makes.
        response = self.client.get("/api/projects/papers/trash")

        self.assertEqual(response.data["papers"], [])
        self.assertFalse(Paper.objects.filter(id=self.paper.id).exists())

    @override_settings(PAPER_TRASH_RETENTION_DAYS=30)
    def test_the_purge_command_leaves_papers_inside_the_window_alone(self):
        keep = self._make_paper("Recent")
        keep.deleted_at = timezone.now() - timedelta(days=2)
        keep.save(update_fields=["deleted_at"])
        self.paper.deleted_at = timezone.now() - timedelta(days=45)
        self.paper.save(update_fields=["deleted_at"])

        call_command("purge_deleted_papers")

        self.assertTrue(Paper.objects.filter(id=keep.id).exists())
        self.assertFalse(Paper.objects.filter(id=self.paper.id).exists())

    def test_a_live_paper_is_never_purged(self):
        call_command("purge_deleted_papers")
        self.assertTrue(Paper.objects.filter(id=self.paper.id).exists())


class PaperListPaginationTests(TestCase):
    """The library is unbounded; one request for it must not be."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create(
            id="ff333333333333333333333333333333",
            name="Teacher",
            email="page@example.com",
            status="approved",
        )
        self.client.force_authenticate(user=self.user)
        project = Project.objects.create(name="P", user=self.user)
        for i in range(5):
            paper = Paper.objects.create(title=f"Paper {i}", project=project, user=self.user)
            PaperSet.objects.create(
                paper=paper, label="A", order=1, content="<p>a very long document</p>"
            )

    def test_without_a_limit_the_response_is_unchanged(self):
        response = self.client.get("/api/projects/papers/")
        self.assertEqual(len(response.data), 5)
        self.assertEqual(response["X-Total-Count"], "5")

    def test_a_page_carries_the_full_total_in_a_header(self):
        response = self.client.get("/api/projects/papers/?limit=2")

        self.assertEqual(len(response.data), 2)
        self.assertEqual(response["X-Total-Count"], "5")
        self.assertEqual(response["X-Limit"], "2")

    def test_offset_walks_the_library(self):
        first = self.client.get("/api/projects/papers/?limit=2").data
        second = self.client.get("/api/projects/papers/?limit=2&offset=2").data

        self.assertEqual(len(second), 2)
        self.assertNotEqual({p["id"] for p in first}, {p["id"] for p in second})

    def test_an_absurd_limit_is_capped(self):
        response = self.client.get("/api/projects/papers/?limit=100000")
        self.assertEqual(response["X-Limit"], "200")

    def test_a_nonsense_limit_does_not_error(self):
        response = self.client.get("/api/projects/papers/?limit=abc&offset=-4")
        self.assertEqual(response.status_code, 200)

    def test_the_list_never_ships_the_document_bodies(self):
        # `content` and `answers` are whole TipTap documents; a table of titles
        # and dates has no use for them.
        row = self.client.get("/api/projects/papers/").data[0]
        self.assertNotIn("content", row["sets"][0])
        self.assertNotIn("answers", row["sets"][0])

    def test_the_list_does_not_scale_its_queries_with_the_number_of_papers(self):
        cache.clear()
        with self.assertNumQueries(3):
            # papers + prefetched sets + the count for the total header.
            self.client.get("/api/projects/papers/")

        project = Project.objects.get(user=self.user)
        for i in range(20):
            paper = Paper.objects.create(title=f"More {i}", project=project, user=self.user)
            PaperSet.objects.create(paper=paper, label="A", order=1, content="x")
        cache.clear()
        with self.assertNumQueries(3):
            self.client.get("/api/projects/papers/")


class DraftServerSyncTests(TestCase):
    """The server's copy of unsaved work. See services/draft_service.py."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create(
            id="aa444444444444444444444444444444",
            name="Teacher",
            email="drafts@example.com",
            status="approved",
        )
        self.other = User.objects.create(
            id="aa555555555555555555555555555555",
            name="Other",
            email="other-drafts@example.com",
            status="approved",
        )
        self.client.force_authenticate(user=self.user)

    def _push(self, *, scope="draft-abc", set_label="A", title="Term 1", at=1000, user=None):
        if user:
            self.client.force_authenticate(user=user)
        return self.client.put(
            "/api/projects/drafts",
            {
                "scope": scope,
                "setLabel": set_label,
                "clientUpdatedAt": at,
                "document": {
                    "title": title,
                    "editorJSON": {"type": "doc", "content": []},
                    "metadata": {"title": title, "className": "10", "subject": "Science"},
                },
            },
            format="json",
        )

    def test_a_draft_is_stored_and_read_back_whole(self):
        self.assertEqual(self._push().status_code, 200)

        response = self.client.get("/api/projects/drafts/draft-abc")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["document"]["title"], "Term 1")

    def test_the_list_omits_the_document_bodies(self):
        # The strip renders titles and dates; loading a dozen whole TipTap
        # documents to draw them is the difference between fast and slow.
        self._push()
        response = self.client.get("/api/projects/drafts")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("document", response.data["drafts"][0])
        self.assertEqual(response.data["drafts"][0]["title"], "Term 1")

    def test_pushing_again_updates_rather_than_duplicates(self):
        self._push(at=1000, title="First")
        self._push(at=2000, title="Second")

        self.assertEqual(Draft.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Draft.objects.get(user=self.user).title, "Second")

    def test_an_older_push_never_overwrites_newer_work(self):
        # Two devices are ordered by when the teacher typed, not by whose
        # request happened to arrive first over a slow connection.
        self._push(at=5000, title="Newer")
        response = self._push(at=1000, title="Older, arrived late")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["stored"])
        # The winning document comes back, so the client can reconcile rather
        # than keep typing into a stale copy.
        self.assertEqual(response.data["draft"]["document"]["title"], "Newer")
        self.assertEqual(Draft.objects.get(user=self.user).title, "Newer")

    def test_each_set_tab_is_its_own_row(self):
        self._push(set_label="A")
        self._push(set_label="B")

        self.assertEqual(Draft.objects.filter(user=self.user, scope="draft-abc").count(), 2)
        self.assertEqual(len(self.client.get("/api/projects/drafts/draft-abc").data), 2)

    def test_deleting_a_scope_takes_every_set_tab_with_it(self):
        self._push(set_label="A")
        self._push(set_label="B")

        response = self.client.delete("/api/projects/drafts/draft-abc")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Draft.objects.filter(user=self.user).count(), 0)

    def test_an_unknown_set_label_is_refused(self):
        response = self._push(set_label="Z")
        self.assertEqual(response.status_code, 400)

    def test_an_oversized_document_is_refused_with_a_usable_message(self):
        response = self.client.put(
            "/api/projects/drafts",
            {
                "scope": "draft-big",
                "setLabel": "A",
                "clientUpdatedAt": 1,
                "document": {"blob": "x" * (3 * 1024 * 1024)},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", response.data["error"].lower())
        self.assertFalse(Draft.objects.filter(scope="draft-big").exists())

    def test_another_teachers_drafts_are_invisible(self):
        self._push(user=self.other, scope="theirs")
        self.client.force_authenticate(user=self.user)

        self.assertEqual(self.client.get("/api/projects/drafts").data["drafts"], [])
        self.assertEqual(self.client.get("/api/projects/drafts/theirs").data, [])

    def test_another_teachers_draft_cannot_be_deleted(self):
        self._push(user=self.other, scope="theirs")
        self.client.force_authenticate(user=self.user)

        self.client.delete("/api/projects/drafts/theirs")

        self.assertTrue(Draft.objects.filter(user=self.other, scope="theirs").exists())

    def test_two_teachers_may_hold_the_same_scope_independently(self):
        # Scopes are only unique within a user — "current" is shared by every
        # account that predates per-draft ids.
        self._push(scope="current", set_label="", title="Mine")
        self._push(scope="current", set_label="", title="Theirs", user=self.other)

        self.assertEqual(Draft.objects.filter(scope="current").count(), 2)

    @override_settings(DRAFT_RETENTION_DAYS=10)
    def test_a_draft_past_the_window_is_purged_when_the_list_is_read(self):
        self._push()
        Draft.objects.filter(user=self.user).update(
            updated_at=timezone.now() - timedelta(days=11)
        )

        response = self.client.get("/api/projects/drafts")

        self.assertEqual(response.data["drafts"], [])
        self.assertFalse(Draft.objects.filter(user=self.user).exists())

    @override_settings(DRAFT_RETENTION_DAYS=10)
    def test_the_purge_command_leaves_recent_drafts_alone(self):
        self._push(scope="recent")
        self._push(scope="stale")
        Draft.objects.filter(scope="stale").update(
            updated_at=timezone.now() - timedelta(days=30)
        )

        call_command("purge_expired_drafts")

        self.assertTrue(Draft.objects.filter(scope="recent").exists())
        self.assertFalse(Draft.objects.filter(scope="stale").exists())

    def test_the_response_states_the_retention_window(self):
        # The strip tells the teacher how long a draft is kept; it has to read
        # that from the server rather than duplicate the policy.
        response = self.client.get("/api/projects/drafts")
        self.assertGreater(response.data["retention_days"], 0)

    def test_a_pending_teacher_cannot_reach_the_draft_store(self):
        pending = User.objects.create(
            id="aa666666666666666666666666666666",
            name="Pending",
            email="pending-drafts@example.com",
            status="pending",
        )
        self.client.force_authenticate(user=pending)

        self.assertEqual(self.client.get("/api/projects/drafts").status_code, 403)
