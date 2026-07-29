"""End-to-end tests for the pool pipeline and the bank flow.

These are the tests that would catch a broken cutover: the SSE contract the
frontend depends on, auto-save actually writing rows, dedup on regeneration,
and the bank path producing a paper without ever invoking Model 1.
"""

import json
from dataclasses import dataclass
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.documents.models import DocumentChunk, PdfSource
from apps.projects.models import Project, Question
from services.chapter_markdown import Figure
from services.pool import store
from services.pool.chapters import Chapter
from services.pool.model1 import PoolGenerationResult
from services.pool.image_model import ImageQuestionResult
from services.pool.schema import PoolQuestion, compute_content_hash


@dataclass
class FakeSlot:
    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str = "Section A"


def _pool_question(qid, *, subject="Science", chapter="Electricity", topic=None,
                   qtype="MCQ", marks=1, pool_id="pool1", source_type="pool",
                   text_key=None):
    # `text_key` lets a test vary the row id while keeping the question TEXT
    # identical — which is what content-hash dedup actually keys on.
    text = f"Question {text_key or qid} about circuits?"
    return PoolQuestion(
        id=qid, subject=subject, chapter=chapter, topic=topic or f"topic{qid}",
        type=qtype, blooms="UNDERSTAND", difficulty="medium", marks=marks,
        question=text, options=["a", "b", "c", "d"] if qtype == "MCQ" else [],
        answer="a", explanation="because", pool_id=pool_id,
        source_type=source_type,
        content_hash=compute_content_hash(subject, chapter, text),
    )


def _make_user(email="pipeline@test.local", uid="pipeuser000000000000000000000001"):
    return User.objects.create(id=uid, name="Pipe", email=email)


#: Shapes a real CBSE Class 10 blueprint asks for. A pool of nothing but
#: 1-mark MCQs leaves most of the paper unfillable, which makes any assertion
#: about the assembled paper meaningless.
_POOL_SHAPES = [
    ("MCQ", 1),
    ("ASSERTION_REASON", 1),
    ("VERY_SHORT_ANSWER", 1),
    ("SHORT_ANSWER", 2),
    ("SHORT_ANSWER", 3),
    ("LONG_ANSWER", 5),
    ("CASE_STUDY", 4),
]


class ImageBudgetTests(TestCase):
    def test_science_gets_a_small_contextual_image_budget(self):
        from services.pool.pipeline import _contextual_image_total

        plan = [
            FakeSlot(i, 1, "MCQ", "MCQ")
            for i in range(1, 39)
        ]
        chapters = [
            Chapter(
                number=1,
                title="Light",
                markdown="light",
                figures=[
                    Figure(url="/m/f1.png", caption="ray diagram"),
                    Figure(url="/m/f2.png", caption="lens diagram"),
                    Figure(url="/m/f3.png", caption="mirror diagram"),
                ],
                char_count=1200,
            )
        ]

        self.assertEqual(
            _contextual_image_total(
                plan=plan,
                chapters=chapters,
                subject_norm="science",
                configured_cap=8,
            ),
            3,
        )

    def test_social_science_uses_only_one_supporting_image_by_default(self):
        from services.pool.pipeline import _contextual_image_total

        plan = [FakeSlot(i, 1, "MCQ", "MCQ") for i in range(1, 39)]
        chapters = [
            Chapter(
                number=1,
                title="French Revolution",
                markdown="history",
                figures=[Figure(url="/m/f1.png", caption="political cartoon")],
                char_count=1000,
            )
        ]

        self.assertEqual(
            _contextual_image_total(
                plan=plan,
                chapters=chapters,
                subject_norm="social science",
                configured_cap=8,
            ),
            1,
        )

    def test_language_papers_do_not_get_supplemental_image_questions(self):
        from services.pool.pipeline import _contextual_image_total

        plan = [FakeSlot(i, 2, "SHORT_ANSWER", "SHORT") for i in range(1, 11)]
        chapters = [
            Chapter(
                number=1,
                title="Poem",
                markdown="poem",
                figures=[Figure(url="/m/f1.png", caption="illustration")],
                char_count=800,
            )
        ]

        self.assertEqual(
            _contextual_image_total(
                plan=plan,
                chapters=chapters,
                subject_norm="english",
                configured_cap=8,
            ),
            0,
        )

    def test_an_explicit_diagram_ask_beats_the_configured_default(self):
        # `IMAGE_QUESTIONS_PER_POOL` guards against images the teacher never
        # asked for. Clamping an EXPLICIT ask to it meant someone who wrote
        # "10 image based questions" silently got eight, with nothing saying
        # why — so a blueprint that declares DIAGRAM slots wins.
        from services.pool.pipeline import _contextual_image_total

        plan = [FakeSlot(i, 3, "DIAGRAM", "DIAGRAM") for i in range(1, 11)]
        plan.append(FakeSlot(11, 2, "SHORT_ANSWER", "SHORT"))

        self.assertEqual(
            _contextual_image_total(
                plan=plan,
                chapters=[],
                subject_norm="science",
                configured_cap=8,
            ),
            10,
            "ten requested figures must produce ten, not the default cap of 8",
        )

    def test_an_explicit_ask_is_still_bounded_by_the_hard_ceiling(self):
        # An explicit ask beating the default must not mean unbounded: a
        # runaway plan would be a runaway image bill.
        from services.pool.pipeline import (
            EXPLICIT_IMAGE_SLOT_CEILING,
            _contextual_image_total,
        )

        plan = [FakeSlot(i, 3, "DIAGRAM", "DIAGRAM") for i in range(500)]

        self.assertEqual(
            _contextual_image_total(
                plan=plan,
                chapters=[],
                subject_norm="science",
                configured_cap=8,
            ),
            EXPLICIT_IMAGE_SLOT_CEILING,
        )

    def test_a_zero_cap_still_disables_images_entirely(self):
        # IMAGE_QUESTIONS_PER_POOL=0 is the deliberate off switch — the one
        # setting that must survive an explicit ask, or there is no way to run
        # the product with images turned off.
        from services.pool.pipeline import _contextual_image_total

        plan = [FakeSlot(i, 3, "DIAGRAM", "DIAGRAM") for i in range(1, 11)]

        self.assertEqual(
            _contextual_image_total(
                plan=plan,
                chapters=[],
                subject_norm="science",
                configured_cap=0,
            ),
            0,
        )

    def test_image_slots_prefer_figure_rich_chapters_but_can_repeat(self):
        from services.pool.pipeline import _build_generation_units

        chapters = [
            Chapter(number=1, title="No Figures", markdown="text", char_count=1000),
            Chapter(
                number=2,
                title="Figures",
                markdown="text",
                figures=[
                    Figure(url="/m/f1.png", caption="figure 1"),
                    Figure(url="/m/f2.png", caption="figure 2"),
                ],
                char_count=1000,
            ),
        ]

        units = _build_generation_units(chapters, target_total=12, image_total=3)
        figure_unit = next(unit for unit in units if unit.bank_chapter == "Figures")

        self.assertGreaterEqual(figure_unit.image_count, 2)


def _realistic_pool(size, **overrides):
    """A pool spread across the shapes a board paper needs."""
    pool = []
    for i in range(size):
        qtype, marks = _POOL_SHAPES[i % len(_POOL_SHAPES)]
        pool.append(
            _pool_question(
                f"q{i}", qtype=qtype, marks=marks, topic=f"topic{i}", **overrides
            )
        )
    return pool


def _parse_sse(chunks):
    """Turn raw SSE text into [(event, data)]."""
    events = []
    for chunk in chunks:
        for block in chunk.strip().split("\n\n"):
            if not block.strip():
                continue
            event = "message"
            data = ""
            for line in block.split("\n"):
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data += line[5:].strip()
            if data:
                events.append((event, json.loads(data)))
    return events


class PersistPoolTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_saves_every_question_as_its_own_row(self):
        pool = [_pool_question(f"q{i}") for i in range(5)]
        result = store.persist_pool(
            user=self.user, questions=pool, subject="Science",
            chapter="Electricity", class_num=10,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.saved, 5)
        self.assertEqual(Question.objects.filter(user=self.user).count(), 5)

    def test_groups_into_a_project_per_chapter(self):
        store.persist_pool(
            user=self.user, questions=[_pool_question("a")], subject="Science",
            chapter="Electricity", class_num=10,
        )
        store.persist_pool(
            user=self.user, questions=[_pool_question("b", chapter="Magnetism")],
            subject="Science", chapter="Magnetism", class_num=10,
        )

        names = set(Project.objects.filter(user=self.user).values_list("name", flat=True))
        self.assertEqual(
            names,
            {"Class 10 — Science — Electricity", "Class 10 — Science — Magnetism"},
        )

    def test_regenerating_the_same_chapter_does_not_duplicate(self):
        pool = [_pool_question(f"q{i}") for i in range(5)]
        first = store.persist_pool(
            user=self.user, questions=pool, subject="Science",
            chapter="Electricity", class_num=10,
        )
        # Same question TEXT, fresh row ids — dedup keys on content, not id,
        # which is exactly the regeneration case.
        again = [
            _pool_question(f"regenerated{i}", text_key=f"q{i}") for i in range(5)
        ]
        second = store.persist_pool(
            user=self.user, questions=again, subject="Science",
            chapter="Electricity", class_num=10,
        )

        self.assertEqual(first.saved, 5)
        self.assertEqual(second.saved, 0)
        self.assertEqual(second.duplicates_skipped, 5)
        self.assertEqual(Question.objects.filter(user=self.user).count(), 5)

    def test_dedup_is_scoped_per_user(self):
        other = _make_user("other@test.local", "otheruser00000000000000000000001")
        pool = [_pool_question("shared")]

        store.persist_pool(
            user=self.user, questions=pool, subject="Science",
            chapter="Electricity", class_num=10,
        )
        result = store.persist_pool(
            user=other, questions=pool, subject="Science",
            chapter="Electricity", class_num=10,
        )

        self.assertEqual(result.saved, 1, "Another user's bank is independent.")

    def test_pool_fields_round_trip_onto_the_row(self):
        question = _pool_question("q1")
        question.image = "/media/generated_diagrams/abc.png"
        question.source_type = "synthetic_image"
        question.metadata = {"imagePrompt": "a circuit"}

        store.persist_pool(
            user=self.user, questions=[question], subject="Science",
            chapter="Electricity", class_num=10,
        )

        row = Question.objects.get(user=self.user)
        self.assertEqual(row.explanation, "because")
        self.assertEqual(row.image_url, "/media/generated_diagrams/abc.png")
        self.assertEqual(row.source_type, "synthetic_image")
        self.assertEqual(row.bloom_taxonomy, "UNDERSTAND")
        self.assertEqual(row.inferred_chapter, "Electricity")
        self.assertEqual(row.inferred_topic, "topicq1")
        self.assertEqual(row.pool_id, "pool1")
        self.assertEqual(row.metadata["imagePrompt"], "a circuit")
        # load_bank() filters on grade_class. If persist_pool leaves it null,
        # every saved question becomes invisible to "Create Paper from Saved
        # Questions" — silently, and only in production.
        self.assertEqual(row.grade_class, "10")

    def test_saved_questions_are_findable_by_class(self):
        store.persist_pool(
            user=self.user, questions=[_pool_question("a")], subject="Science",
            chapter="Electricity", class_num=10,
        )
        self.assertEqual(len(store.load_bank(user=self.user, class_num=10)), 1)

    def test_failure_is_reported_not_raised(self):
        with patch(
            "services.pool.store.Question.objects.bulk_create",
            side_effect=RuntimeError("db exploded"),
        ):
            result = store.persist_pool(
                user=self.user, questions=[_pool_question("a")],
                subject="Science", chapter="Electricity", class_num=10,
            )

        self.assertFalse(result.ok)
        self.assertIn("db exploded", result.error)

    def test_empty_pool_is_a_no_op(self):
        result = store.persist_pool(
            user=self.user, questions=[], subject="Science",
            chapter="Electricity", class_num=10,
        )
        self.assertEqual(result.saved, 0)
        self.assertEqual(Question.objects.count(), 0)


class LoadBankTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        store.persist_pool(
            user=self.user,
            questions=[_pool_question(f"e{i}") for i in range(3)],
            subject="Science", chapter="Electricity", class_num=10,
        )
        store.persist_pool(
            user=self.user,
            questions=[_pool_question(f"m{i}", chapter="Magnetism") for i in range(2)],
            subject="Science", chapter="Magnetism", class_num=10,
        )

    def test_loads_everything_for_the_user(self):
        self.assertEqual(len(store.load_bank(user=self.user)), 5)

    def test_filters_by_chapter(self):
        pool = store.load_bank(user=self.user, chapters=["Electricity"])
        self.assertEqual(len(pool), 3)
        self.assertTrue(all(q.chapter == "Electricity" for q in pool))

    def test_does_not_leak_across_users(self):
        other = _make_user("nope@test.local", "nopeuser000000000000000000000001")
        self.assertEqual(store.load_bank(user=other), [])

    def test_round_trips_into_pool_questions(self):
        pool = store.load_bank(user=self.user, chapters=["Electricity"])
        question = pool[0]
        self.assertIsInstance(question, PoolQuestion)
        self.assertEqual(question.type, "MCQ")
        self.assertEqual(question.blooms, "UNDERSTAND")
        self.assertEqual(len(question.options), 4)

    def test_bank_summary_counts_per_chapter(self):
        summary = {row["chapter"]: row["count"] for row in store.bank_summary(user=self.user)}
        self.assertEqual(summary, {"Electricity": 3, "Magnetism": 2})


class PipelineStreamTests(TestCase):
    """Drives the real pipeline with Model 1 / images / Model 2 stubbed."""

    def setUp(self):
        self.user = _make_user()
        self.source = PdfSource.objects.create(
            name="electricity.pdf", size=100, status="ready", user=self.user
        )
        for i in range(3):
            DocumentChunk.objects.create(
                content=f"# Electricity\n## Ohm's Law\n\nParagraph {i} about resistance.",
                page=1, chunk_index=i,
                metadata={"chapter": "Electricity", "heading": "Ohm's Law",
                          "sourcePdf": "electricity.pdf"},
                pdf_source=self.source,
            )

    def _run(self, *, pool_size=60, image_count=0):
        from services.pool.pipeline import stream_pool_questions

        pool = _realistic_pool(pool_size)
        # DIAGRAM questions must be shaped like something the CBSE blueprint
        # actually asks for, or Model 2 has no slot to put them in and the
        # synthetic-image path is never exercised.
        images = [
            _pool_question(f"img{i}", qtype="SHORT_ANSWER", marks=3,
                           topic=f"figure{i}", source_type="synthetic_image")
            for i in range(image_count)
        ]
        for question in images:
            question.image = f"/media/generated_diagrams/{question.id}.png"

        def fake_model1(**kwargs):
            on_question = kwargs.get("on_question")
            for question in pool:
                if on_question:
                    on_question(question)
            return PoolGenerationResult(pool_id="pool1", questions=list(pool))

        def fake_images(**kwargs):
            on_question = kwargs.get("on_question")
            for question in images:
                if on_question:
                    on_question(question)
            return ImageQuestionResult(
                questions=list(images), generated_count=len(images)
            )

        with patch("services.pool.pipeline.generate_question_pool", side_effect=fake_model1), \
             patch("services.pool.pipeline.generate_image_questions", side_effect=fake_images), \
             patch("services.pool.model2._run_review", return_value=(False, 0, "stubbed")):
            chunks = list(
                stream_pool_questions(
                    user=self.user,
                    pdf_source_ids=[self.source.id],
                    topic="Electricity",
                    count=-1,
                    difficulty="medium",
                    instructions="",
                    payload={"subject": "Science", "class": 10, "board": "CBSE",
                             "qp_type": "board", "countVariation": "cbse"},
                )
            )
        return _parse_sse(chunks)

    def test_emits_the_sse_contract_the_frontend_expects(self):
        events = self._run()
        names = [name for name, _ in events]

        for required in ("plan", "question", "update", "done"):
            self.assertIn(required, names, f"missing {required!r} event")

        # `plan` must precede questions, `done` must be last.
        self.assertLess(names.index("plan"), names.index("question"))
        self.assertEqual(names[-1], "done")

    def test_question_events_carry_the_editor_field_names(self):
        events = self._run()
        payload = next(data for name, data in events if name == "question")

        self.assertIn("index", payload)
        self.assertIn("section", payload)
        self.assertIn("sourceType", payload)

        question = payload["question"]
        for field in ("content", "type", "options", "answer", "marks", "image_url", "metadata"):
            self.assertIn(field, question, f"editor needs {field!r}")
        self.assertIn("slotIndex", question["metadata"])

    def test_done_result_has_sections_and_meta(self):
        events = self._run()
        done = next(data for name, data in events if name == "done")

        self.assertTrue(done["done"])
        result = done["result"]
        self.assertIn("sections", result)
        self.assertIn("generalInstructions", result)
        self.assertGreater(result["meta"]["totalQuestions"], 0)
        self.assertTrue(result["meta"]["poolId"])

    def test_whole_pool_is_auto_saved_not_just_the_paper(self):
        events = self._run(pool_size=60)
        done = next(data for name, data in events if name == "done")
        used = done["result"]["meta"]["totalQuestions"]
        saved = Question.objects.filter(user=self.user).count()

        self.assertEqual(saved, 60)
        self.assertGreater(saved, used, "The bank keeps more than the paper used.")

    def test_saved_event_reports_what_was_banked(self):
        events = self._run()
        saved = next(data for name, data in events if name == "saved")
        self.assertEqual(saved["saved"], 60)
        self.assertIn("question bank", saved["message"])

    def test_model_1_runs_once_per_detected_chapter_and_preserves_metadata(self):
        DocumentChunk.objects.create(
            content="# Magnetism\n## Poles\n\nMagnets have north and south poles.",
            page=12, chunk_index=10,
            metadata={"chapter": "Magnetism", "heading": "Poles",
                      "sourcePdf": "electricity.pdf"},
            pdf_source=self.source,
        )

        from services.pool.pipeline import stream_pool_questions

        calls = []

        def fake_model1(**kwargs):
            calls.append(kwargs["chapter_name"])
            chapter_name = kwargs["chapter_name"]
            metadata = kwargs.get("question_metadata") or {}
            pool = [
                _pool_question(
                    f"{chapter_name[:3]}{i}",
                    chapter=chapter_name,
                    topic=f"{chapter_name} topic {i}",
                )
                for i in range(45)
            ]
            for question in pool:
                question.metadata.update(metadata)
                question.metadata["marks"] = question.marks
                question.metadata["blooms"] = question.blooms
                question.metadata["difficulty"] = question.difficulty
                if kwargs.get("on_question"):
                    kwargs["on_question"](question)
            return PoolGenerationResult(
                pool_id=kwargs["pool_id"],
                questions=list(pool),
                chapter=chapter_name,
            )

        with patch("services.pool.pipeline.generate_question_pool", side_effect=fake_model1), \
             patch("services.pool.pipeline.generate_image_questions", return_value=ImageQuestionResult()), \
             patch("services.pool.model2._run_review", return_value=(False, 0, "stubbed")):
            events = _parse_sse(list(stream_pool_questions(
                user=self.user,
                pdf_source_ids=[self.source.id],
                topic="Electricity and Magnetism",
                count=-1,
                difficulty="medium",
                instructions="",
                payload={"subject": "Science", "class": 10, "board": "CBSE",
                         "qp_type": "board", "countVariation": "cbse"},
            )))

        self.assertEqual(set(calls), {"Electricity", "Magnetism"})
        done = next(data for name, data in events if name == "done")
        self.assertTrue(done["done"])
        chapters = set(
            Question.objects.filter(user=self.user)
            .values_list("inferred_chapter", flat=True)
        )
        self.assertEqual(chapters, {"Electricity", "Magnetism"})
        row = Question.objects.filter(user=self.user, inferred_chapter="Magnetism").first()
        self.assertEqual(row.source_pdf, "electricity.pdf")
        self.assertEqual(row.metadata["sourcePages"], [12, 12])
        self.assertIn("blooms", row.metadata)
        self.assertIn("marks", row.metadata)

    def test_synthetic_image_questions_are_flagged_in_a_notice(self):
        events = self._run(image_count=6)
        notices = [data for name, data in events if name == "notice"]
        self.assertTrue(
            any("AI-generated diagram" in n.get("message", "") for n in notices),
            f"expected a synthetic-image notice, got {notices}",
        )

    def test_chunkless_source_is_rejected_by_readiness_gate(self):
        # A source marked "ready" but with NO persisted chunks is a data anomaly
        # (in prod, extract_and_persist_chunks raises before marking ready). The
        # authoritative readiness gate catches it up front with a dedicated
        # DOCUMENTS_NOT_READY event instead of letting it build an empty chapter
        # and dead-end on the generic "No questions" error.
        from services.pool.pipeline import stream_pool_questions

        empty = PdfSource.objects.create(
            name="empty.pdf", size=1, status="ready", user=self.user
        )
        chunks = list(
            stream_pool_questions(
                user=self.user, pdf_source_ids=[empty.id], topic="X", count=-1,
                difficulty="medium", instructions="",
                payload={"subject": "Science", "class": 10, "board": "CBSE", "qp_type": "board"},
            )
        )
        events = _parse_sse(chunks)
        errors = [data for name, data in events if name == "error"]
        self.assertTrue(errors)
        self.assertEqual(errors[0].get("code"), "DOCUMENTS_NOT_READY")
        self.assertEqual(errors[0]["pendingDocuments"][0]["reason"], "no_chunks")
        self.assertEqual(errors[0]["pendingDocuments"][0]["name"], "empty.pdf")

    def test_ready_source_with_blank_chunks_reports_no_readable_content(self):
        # A source that IS ready and HAS chunks, but whose chunk content renders
        # to empty markdown, still reaches the pipeline's own empty-chapter guard
        # (the DOCUMENTS_NOT_READY gate only checks chunk existence, not content).
        from services.pool.pipeline import stream_pool_questions

        blank = PdfSource.objects.create(
            name="blank.pdf", size=1, status="ready", user=self.user
        )
        DocumentChunk.objects.create(
            content="   ", page=1, chunk_index=0,
            metadata={"sourcePdf": "blank.pdf"}, pdf_source=blank,
        )
        chunks = list(
            stream_pool_questions(
                user=self.user, pdf_source_ids=[blank.id], topic="X", count=-1,
                difficulty="medium", instructions="",
                payload={"subject": "Science", "class": 10, "board": "CBSE", "qp_type": "board"},
            )
        )
        events = _parse_sse(chunks)
        errors = [data for name, data in events if name == "error"]
        self.assertTrue(errors)
        self.assertIn("No readable content", errors[0]["error"])


class PaperFromBankTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        store.persist_pool(
            user=self.user,
            questions=_realistic_pool(60),
            subject="Science", chapter="Electricity", class_num=10,
        )

    def _run(self, **kwargs):
        from services.pool.from_bank import stream_paper_from_bank

        params = dict(
            subject="Science", class_num=10, chapters=["Electricity"],
            topic="Electricity", difficulty="medium", count=-1,
            count_variation="cbse", qp_type="board", deterministic=True,
        )
        params.update(kwargs)
        return _parse_sse(list(stream_paper_from_bank(self.user, **params)))

    def test_builds_a_paper_without_running_model_1(self):
        with patch("services.pool.model1.generate_question_pool") as model1:
            events = self._run()

        model1.assert_not_called()
        names = [name for name, _ in events]
        self.assertIn("done", names)

        done = next(data for name, data in events if name == "done")
        self.assertTrue(done["result"]["meta"]["fromBank"])
        self.assertGreater(done["result"]["meta"]["totalQuestions"], 0)

    def test_questions_are_marked_as_coming_from_the_bank(self):
        events = self._run()
        payload = next(data for name, data in events if name == "question")
        self.assertTrue(payload["question"]["metadata"]["fromBank"])

    def test_deterministic_mode_yields_the_identical_paper_twice(self):
        first = self._run(deterministic=True)
        second = self._run(deterministic=True)

        def stems(events):
            return [
                data["question"]["content"]
                for name, data in events
                if name == "question"
            ]

        self.assertEqual(stems(first), stems(second))

    def test_empty_bank_produces_a_clean_error(self):
        events = self._run(chapters=["No Such Chapter"])
        errors = [data for name, data in events if name == "error"]
        self.assertTrue(errors)
        self.assertIn("No saved questions match", errors[0]["error"])
