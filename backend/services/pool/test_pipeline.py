"""End-to-end tests for the pool pipeline and the bank flow.

These are the tests that would catch a broken cutover: the SSE contract the
frontend depends on, auto-save actually writing rows, dedup on regeneration,
and the bank path producing a paper without ever invoking Model 1.
"""

import json
from dataclasses import dataclass
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

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
    choice_required: bool = False
    #: "generate" | "saved" — the Blueprint Builder's per-slot source.
    source: str = "generate"


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


class ExactPoolTargetTests(TestCase):
    """How many questions Model 1 is asked to write.

    Exactly what the paper needs, plus only the spares something requires.
    This replaced a flat pool of 80-90 — over-provisioning existed so Model 2
    could select, and with the Blueprint Builder the teacher has already
    decided what each slot is.
    """

    def _slots(self, count, *, question_type="SHORT_ANSWER", choice=False):
        return [
            FakeSlot(i, 2, question_type, "SHORT", choice_required=choice)
            for i in range(1, count + 1)
        ]

    @override_settings(POOL_EXACT_MARGIN_PERCENT=0)
    def test_with_no_margin_the_target_is_literally_exact(self):
        from services.pool.pipeline import _exact_pool_target

        self.assertEqual(_exact_pool_target(slots=self._slots(20)), 20)

    @override_settings(POOL_EXACT_MARGIN_PERCENT=0)
    def test_an_empty_plan_asks_for_nothing(self):
        from services.pool.pipeline import _exact_pool_target

        self.assertEqual(_exact_pool_target(slots=[]), 0)

    @override_settings(POOL_EXACT_MARGIN_PERCENT=0)
    def test_each_or_slot_costs_exactly_one_spare(self):
        # A slot promising "attempt Q27 OR Q27a" needs a second question, or
        # the paper offers a choice it cannot honour.
        from services.pool.pipeline import _exact_pool_target

        slots = self._slots(10) + self._slots(4, choice=True)
        self.assertEqual(_exact_pool_target(slots=slots), 14 + 4)

    @override_settings(POOL_EXACT_MARGIN_PERCENT=0)
    def test_a_single_set_budgets_no_variant_spares(self):
        from services.pool.pipeline import _exact_pool_target

        self.assertEqual(_exact_pool_target(slots=self._slots(30), num_sets=1), 30)

    @override_settings(POOL_EXACT_MARGIN_PERCENT=0)
    def test_extra_sets_budget_spares_to_swap_from(self):
        # Sets B and C are derived by swapping unused pool questions in. With
        # no spares there is nothing to swap and multi-set silently produces
        # three identical papers.
        from services.pool.pipeline import _exact_pool_target

        one = _exact_pool_target(slots=self._slots(30), num_sets=1)
        two = _exact_pool_target(slots=self._slots(30), num_sets=2)
        three = _exact_pool_target(slots=self._slots(30), num_sets=3)

        self.assertGreater(two, one)
        self.assertGreater(three, two)
        # 30 replaceable slots x 30% = 9 per extra set.
        self.assertEqual(two, 30 + 9)
        self.assertEqual(three, 30 + 18)

    @override_settings(POOL_EXACT_MARGIN_PERCENT=0)
    def test_mcq_slots_are_fixed_across_sets_so_cost_no_spares(self):
        # `set_variants.DEFAULT_FIXED_TYPES` keeps MCQs identical across sets,
        # so budgeting replacements for them would buy questions never used.
        from services.pool.pipeline import _exact_pool_target

        mcqs = [FakeSlot(i, 1, "MCQ", "MCQ") for i in range(1, 21)]
        self.assertEqual(_exact_pool_target(slots=mcqs, num_sets=3), 20)

    def test_the_margin_absorbs_normalisation_losses(self):
        # Model 1 output is normalised on the way in — malformed dropped,
        # duplicates dropped by content hash — so asking for exactly N
        # reliably yields slightly under N.
        from services.pool.pipeline import _exact_pool_target

        target = _exact_pool_target(slots=self._slots(40))
        self.assertGreater(target, 40)
        self.assertEqual(target, 40 + 6)  # 15% of 40, rounded up

    def test_a_board_paper_costs_far_less_than_the_old_flat_pool(self):
        # The regression this guards: the previous behaviour generated 80-90
        # questions to place 38, whatever the paper actually needed.
        from services.pool.pipeline import _exact_pool_target

        slots = self._slots(32) + self._slots(6, choice=True)
        target = _exact_pool_target(slots=slots, num_sets=1)
        self.assertLess(
            target, 60, "exact generation must be well under the old 80-90 pool"
        )
        self.assertGreaterEqual(target, 38, "every slot still needs a question")


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


class SavedVsGeneratedSplitTests(TestCase):
    """The Blueprint Builder's per-slot source has to mean something.

    A modal that lets a teacher say "12 of these from my bank" and then writes
    all 38 fresh is worse than one that never offered the control.
    """

    def _pool(self, *, fresh_ids, bank_ids):
        pool = []
        for qid in fresh_ids:
            pool.append(_pool_question(qid, qtype="MCQ", marks=1, pool_id="fresh"))
        for qid in bank_ids:
            pool.append(_pool_question(qid, qtype="MCQ", marks=1, pool_id="old-run"))
        return pool

    def test_a_saved_slot_prefers_a_banked_question(self):
        from services.pool.model2 import build_candidates

        pool = self._pool(fresh_ids=["f1"], bank_ids=["b1"])
        slot = FakeSlot(1, 1, "MCQ", "MCQ", source="saved")

        assignments, unfilled = build_candidates(
            pool, [slot], alternates=0, fresh_pool_id="fresh"
        )
        self.assertEqual(unfilled, [])
        self.assertEqual(assignments[0].question.id, "b1")

    def test_a_generate_slot_prefers_a_fresh_question(self):
        from services.pool.model2 import build_candidates

        pool = self._pool(fresh_ids=["f1"], bank_ids=["b1"])
        slot = FakeSlot(1, 1, "MCQ", "MCQ", source="generate")

        assignments, unfilled = build_candidates(
            pool, [slot], alternates=0, fresh_pool_id="fresh"
        )
        self.assertEqual(unfilled, [])
        self.assertEqual(assignments[0].question.id, "f1")

    def test_a_saved_slot_still_fills_when_the_bank_is_empty(self):
        # A preference, not a filter. A teacher who asked for bank questions
        # wants a complete paper far more than they want provably banked ones.
        from services.pool.model2 import build_candidates

        pool = self._pool(fresh_ids=["f1"], bank_ids=[])
        slot = FakeSlot(1, 1, "MCQ", "MCQ", source="saved")

        assignments, unfilled = build_candidates(
            pool, [slot], alternates=0, fresh_pool_id="fresh"
        )
        self.assertEqual(unfilled, [], "an empty bank must not leave the slot blank")
        self.assertEqual(assignments[0].question.id, "f1")

    def test_a_slot_with_no_source_is_unaffected(self):
        # Every plan the blueprint engine compiles, and every pre-Builder
        # client, has no `source` — those must behave exactly as before.
        from services.pool.model2 import build_candidates

        pool = self._pool(fresh_ids=["f1"], bank_ids=["b1"])
        slot = FakeSlot(1, 1, "MCQ", "MCQ")
        slot.source = ""

        assignments, unfilled = build_candidates(
            pool, [slot], alternates=0, fresh_pool_id="fresh"
        )
        self.assertEqual(unfilled, [])
        self.assertIn(assignments[0].question.id, {"f1", "b1"})

    def test_with_no_fresh_pool_id_everything_counts_as_banked(self):
        # The paper-from-bank path passes no fresh id: nothing was written
        # this run, so there is no "fresh" half to prefer.
        from services.pool.model2 import build_candidates

        pool = self._pool(fresh_ids=[], bank_ids=["b1", "b2"])
        slot = FakeSlot(1, 1, "MCQ", "MCQ", source="saved")

        assignments, unfilled = build_candidates(pool, [slot], alternates=0)
        self.assertEqual(unfilled, [])
