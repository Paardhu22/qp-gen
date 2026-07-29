"""End-to-end tests for the pool pipeline and the bank flow.

These are the tests that would catch a broken cutover: the SSE contract the
frontend depends on, auto-save actually writing rows, dedup on regeneration,
and the bank path producing a paper without ever invoking Model 1.
"""

import json
from dataclasses import dataclass
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.accounts.models import User
from apps.documents.models import DocumentChunk, PdfSource
from apps.projects.models import Project, Question
from services.pool import store
from services.pool.chapters import Chapter
from services.pool.model1 import PoolGenerationResult
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


class PoolTargetTests(TestCase):
    """How many questions Model 1 is asked to write.

    The floor used to be a flat 40. It is now contextual: never below
    POOL_TARGET_MIN, climbing toward POOL_TARGET_MAX as the run gains context,
    and always at least two questions per slot so Model 2 has an alternative
    for everything it places.
    """

    def _chapters(self, count):
        return [
            Chapter(
                number=i + 1,
                title=f"Chapter {i + 1}",
                markdown="text",
                char_count=4000,
            )
            for i in range(count)
        ]

    def test_the_narrowest_possible_run_sits_exactly_on_the_minimum(self):
        # One chapter, one slot: as little context as a generation can have.
        from services.pool.pipeline import _contextual_pool_target

        self.assertEqual(
            _contextual_pool_target(slot_count=1, chapters=self._chapters(1)),
            settings.POOL_TARGET_MIN,
        )

    def test_slot_count_alone_interpolates_within_the_band(self):
        # Pins the interpolation itself, so a change to the curve is a visible
        # test edit rather than a silent shift in what every paper costs.
        # 10 of 40 slots is a quarter of the way up a 10-question band.
        from services.pool.pipeline import _contextual_pool_target

        self.assertEqual(
            _contextual_pool_target(slot_count=10, chapters=self._chapters(1)),
            82,
        )
        self.assertEqual(
            _contextual_pool_target(slot_count=20, chapters=self._chapters(1)),
            85,
        )

    def test_the_floor_never_drops_below_the_configured_minimum(self):
        # The regression this pins: the old flat floor of 40 meant a 12-slot
        # test drew on a pool of 40, which is not enough spread for Model 2 to
        # be selecting rather than accepting.
        from services.pool.pipeline import _contextual_pool_target

        for slots in (1, 5, 12, 20):
            self.assertGreaterEqual(
                _contextual_pool_target(
                    slot_count=slots, chapters=self._chapters(1)
                ),
                settings.POOL_TARGET_MIN,
                f"{slots} slots fell below the floor",
            )

    def test_more_chapters_widen_the_floor_toward_the_maximum(self):
        from services.pool.pipeline import _contextual_pool_target

        one = _contextual_pool_target(slot_count=1, chapters=self._chapters(1))
        two = _contextual_pool_target(slot_count=1, chapters=self._chapters(2))
        three = _contextual_pool_target(slot_count=1, chapters=self._chapters(3))
        six = _contextual_pool_target(slot_count=1, chapters=self._chapters(6))

        self.assertEqual(one, settings.POOL_TARGET_MIN)
        self.assertEqual(three, settings.POOL_TARGET_MAX)
        self.assertLess(one, two)
        self.assertLess(two, three)
        # Three chapters is already as wide as the floor cares about.
        self.assertEqual(six, three)

    def test_a_full_board_paper_reaches_the_maximum_on_slots_alone(self):
        # 40 slots is a full board paper. Even from a single chapter it needs
        # the wider pool, because the same questions must cover far more slots.
        from services.pool.pipeline import _contextual_pool_target

        self.assertEqual(
            _contextual_pool_target(slot_count=40, chapters=self._chapters(1)),
            max(80, settings.POOL_TARGET_MAX),
        )

    def test_two_per_slot_wins_when_the_paper_is_larger_than_the_floor(self):
        # A 60-slot paper needs 120, not the 90 ceiling — the floor is a floor,
        # never a cap.
        from services.pool.pipeline import _contextual_pool_target

        self.assertEqual(
            _contextual_pool_target(slot_count=60, chapters=self._chapters(2)),
            120,
        )

    def test_the_target_is_within_the_configured_band_for_normal_papers(self):
        # The band the product actually asks for: 80-90 for anything up to a
        # full board paper.
        from services.pool.pipeline import _contextual_pool_target

        for slots in (10, 20, 30, 38, 40):
            for chapters in (1, 2, 3, 6):
                target = _contextual_pool_target(
                    slot_count=slots, chapters=self._chapters(chapters)
                )
                self.assertGreaterEqual(target, 80)
                self.assertLessEqual(target, 90)


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

    def _run(self, *, pool_size=60):
        from services.pool.pipeline import stream_pool_questions

        pool = _realistic_pool(pool_size)

        def fake_model1(**kwargs):
            on_question = kwargs.get("on_question")
            for question in pool:
                if on_question:
                    on_question(question)
            return PoolGenerationResult(pool_id="pool1", questions=list(pool))

        with patch("services.pool.pipeline.generate_question_pool", side_effect=fake_model1), \
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

    def test_no_image_questions_are_produced_at_all(self):
        # The image stage was removed from the cycle. Nothing in a fresh pool
        # carries a figure, and the AI-diagram warning that existed for them
        # must not appear on a paper that has none.
        events = self._run()

        notices = [data for name, data in events if name == "notice"]
        self.assertFalse(
            any("AI-generated diagram" in n.get("message", "") for n in notices),
            f"a synthetic-image notice survived the removal: {notices}",
        )

        update = next(data for name, data in events if name == "update")
        self.assertNotIn("syntheticImageCount", update["meta"])
        self.assertEqual(update["meta"]["footerNotes"], [])

        questions = [
            q
            for section in update["sections"]
            for q in section["questions"]
        ]
        self.assertTrue(questions, "expected a paper")
        self.assertTrue(
            all(not q.get("image_url") for q in questions),
            "a generated question carried an image_url",
        )

        pool_event = next(data for name, data in events if name == "pool")
        for gone in (
            "imageStrategy",
            "imagesGenerated",
            "imagesReused",
            "imageCacheHits",
            "estimatedImageCostUsd",
        ):
            self.assertNotIn(gone, pool_event)

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
