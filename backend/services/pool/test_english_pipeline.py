"""End-to-end: the English paper is assembled from two independent pools.

This is the test that would catch the bug the split exists to fix. The
regression it guards is not "a question is worded badly" — it is structural:
Reading, Grammar and Writing drawing on the uploaded textbook, so a paper's
first two sections read as Literature under the wrong headings.

Model 1 is stubbed with a pool that COULD, on type and marks alone, fill every
slot on the paper. If provenance routing ever regresses, those textbook
questions will land in Section A and these tests fail.
"""

from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.documents.models import DocumentChunk, PdfSource
from apps.projects.models import Question
from services.assets.base import AssetBatchResult
from services.pool.model1 import PoolGenerationResult
from services.pool.schema import PoolQuestion, compute_content_hash
from services.pool.test_pipeline import _parse_sse
from utils.ids import generate_id

#: Every (type, marks) shape the English blueprint asks for, including the
#: five that belong to asset generators. A textbook pool holding all of these
#: is exactly the situation the provenance gate has to survive.
#: `(type, marks, asset_type)` — asset_type is what Model 1 now stamps from
#: the plan-derived recipe.
_ENGLISH_SHAPES = [
    ("EXTRACT_PROSE", 5, "extract_prose"),
    ("EXTRACT_POETRY", 5, "extract_poetry"),
    ("SHORT_ANSWER", 12, "short_answer_bundle"),
    ("SHORT_ANSWER", 6, "short_answer_bundle"),
    ("LONG_ANSWER", 6, "long_answer"),
    # Shapes the asset generators own — deliberately present in the textbook
    # pool so the gate is actually exercised.
    ("READING_COMP", 10, "discursive_passage"),
    ("GRAMMAR", 10, "grammar_task_set"),
    ("LETTER", 5, "formal_letter_to_authority"),
    ("ANALYTICAL_PARAGRAPH", 5, "analytical_paragraph"),
]


def _textbook_question(index, qtype, marks, asset_type="", chapter="The Thief's Story"):
    text = f"Textbook {qtype} {marks}m #{index} about the chapter's events?"
    return PoolQuestion(
        id=f"tb{index}", subject="English", chapter=chapter,
        topic=f"chapter-topic-{index}", type=qtype, blooms="UNDERSTAND",
        difficulty="medium", marks=marks, question=text, answer="an answer",
        explanation="because", pool_id="pool1", asset_type=asset_type,
        content_hash=compute_content_hash("English", chapter, text),
    )


def _textbook_pool(per_shape=4):
    return [
        _textbook_question(f"{i}-{n}", qtype, marks, asset_type)
        for i, (qtype, marks, asset_type) in enumerate(_ENGLISH_SHAPES)
        for n in range(per_shape)
    ]


def _asset_question(slot, index):
    """What an asset generator would return for `slot`."""
    text = f"{slot.asset_type} candidate {index} — original material, no textbook."
    return PoolQuestion(
        id=generate_id(), subject="English",
        chapter=f"{slot.generator} bank", topic=f"{slot.asset_type}-{index}",
        type=slot.question_type, blooms="ANALYZE", difficulty="medium",
        marks=slot.marks, question=text, answer="marking scheme",
        generator=slot.generator, asset_type=slot.asset_type,
        source_type=slot.generator.replace("_pool", ""), pool_id="pool1",
        content_hash=compute_content_hash("English", slot.generator, text),
        metadata={"generator": slot.generator, "assetType": slot.asset_type},
    )


def _fake_assets(plan, **kwargs):
    from services.assets.registry import DEFAULT_GENERATOR

    result = AssetBatchResult()
    for slot in plan:
        if getattr(slot, "generator", DEFAULT_GENERATOR) == DEFAULT_GENERATOR:
            continue
        wanted = 3 if getattr(slot, "choice_required", False) else 2
        for index in range(wanted):
            result.questions.append(_asset_question(slot, index))
            result.generated += 1
    reports = [
        {
            "generator": name,
            "label": name,
            "slots": 1,
            "elapsedSeconds": 0.0,
            "produced": 0,
            "generated": 0,
            "reused": 0,
            "failures": [],
            "validationWarnings": [],
        }
        for name in sorted(
            {
                slot.generator
                for slot in plan
                if getattr(slot, "generator", DEFAULT_GENERATOR) != DEFAULT_GENERATOR
            }
        )
    ]
    return result, reports


class EnglishPipelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            id="engpipe00000000000000000000001", name="Eng", email="eng@test.local"
        )
        self.source = PdfSource.objects.create(
            name="footprints.pdf", size=100, status="ready", user=self.user
        )
        for i in range(3):
            DocumentChunk.objects.create(
                content=(
                    "# The Thief's Story\n## Hari Singh\n\n"
                    f"Paragraph {i}. Anil taught Hari Singh to write his name."
                ),
                page=1, chunk_index=i,
                metadata={"chapter": "The Thief's Story", "heading": "Hari Singh",
                          "sourcePdf": "footprints.pdf"},
                pdf_source=self.source,
            )

    def _run(self, *, with_source=True, assets=_fake_assets):
        from services.pool.pipeline import stream_pool_questions

        pool = _textbook_pool()

        def fake_model1(**kwargs):
            on_question = kwargs.get("on_question")
            for question in pool:
                if on_question:
                    on_question(question)
            return PoolGenerationResult(pool_id="pool1", questions=list(pool))

        with patch("services.pool.pipeline.generate_question_pool", side_effect=fake_model1), \
             patch("services.pool.pipeline.generate_assets_for_plan", side_effect=assets), \
             patch("services.pool.model2._run_review", return_value=(False, 0, "stubbed")):
            chunks = list(
                stream_pool_questions(
                    user=self.user,
                    pdf_source_ids=[self.source.id] if with_source else [],
                    topic="The Thief's Story",
                    count=-1,
                    difficulty="medium",
                    instructions="",
                    payload={"subject": "English", "class": 10, "board": "CBSE",
                             "qp_type": "board", "countVariation": "cbse"},
                )
            )
        return _parse_sse(chunks)

    # ── The paper ───────────────────────────────────────────────────────

    def test_the_paper_is_complete_and_worth_eighty_marks(self):
        done = next(d for n, d in self._run() if n == "done")
        meta = done["result"]["meta"]
        self.assertEqual(meta["totalQuestions"], 11)
        self.assertEqual(meta["totalMarks"], 80)
        self.assertEqual(meta["unfilledSlots"], 0)

    def test_reading_grammar_and_writing_never_come_from_the_textbook(self):
        """The headline assertion. The stubbed textbook pool contains
        READING_COMP/GRAMMAR/LETTER questions of exactly the right marks, so
        only provenance keeps them out of Sections A and B."""
        done = next(d for n, d in self._run() if n == "done")

        for section in done["result"]["sections"]:
            for question in section["questions"]:
                generator = question["metadata"].get("generator", "question_pool")
                if "Literature" in section["title"]:
                    self.assertEqual(generator, "question_pool", section["title"])
                    self.assertIn("Textbook", question["content"])
                else:
                    self.assertNotEqual(generator, "question_pool", section["title"])
                    self.assertNotIn("Textbook", question["content"])

    def test_exactly_forty_marks_come_from_the_upload(self):
        done = next(d for n, d in self._run() if n == "done")
        by_source = {}
        for section in done["result"]["sections"]:
            for question in section["questions"]:
                key = question["metadata"].get("generator", "question_pool")
                by_source[key] = by_source.get(key, 0) + question["marks"]

        self.assertEqual(by_source["question_pool"], 40)
        self.assertEqual(by_source["reading_asset_pool"], 20)
        self.assertEqual(by_source["grammar_asset_pool"], 10)
        self.assertEqual(by_source["writing_asset_pool"], 10)

    def test_every_slot_gets_the_shape_its_blueprint_declared(self):
        """Marks and type alone cannot separate a prose extract from a poetry
        extract, or a discursive passage from a case-based one — both pairs are
        interchangeable on those two fields. The declared asset type is what
        keeps each slot's material in the right place."""
        done = next(d for n, d in self._run() if n == "done")
        by_slot = {
            q["metadata"]["slotIndex"]: q["metadata"].get("assetType")
            for section in done["result"]["sections"]
            for q in section["questions"]
        }
        self.assertEqual(by_slot[1], "discursive_passage")
        self.assertEqual(by_slot[2], "case_based_passage")
        self.assertEqual(by_slot[3], "grammar_task_set")
        self.assertEqual(by_slot[6], "extract_prose")
        self.assertEqual(by_slot[7], "extract_poetry")

    def test_the_sections_match_the_official_paper(self):
        done = next(d for n, d in self._run() if n == "done")
        sections = {s["title"]: s for s in done["result"]["sections"]}

        self.assertEqual(
            list(sections),
            [
                "Section A - Reading Skills",
                "Section B - Grammar and Writing Skills",
                "Section C - Literature Textbook",
            ],
        )
        marks = {
            title: sum(q["marks"] for q in section["questions"])
            for title, section in sections.items()
        }
        self.assertEqual(marks["Section A - Reading Skills"], 20)
        self.assertEqual(marks["Section B - Grammar and Writing Skills"], 20)
        self.assertEqual(marks["Section C - Literature Textbook"], 40)

    # ── The stream ──────────────────────────────────────────────────────

    def test_the_plan_event_publishes_the_routing(self):
        plan = next(d for n, d in self._run() if n == "plan")
        routing = {e["generator"]: e for e in plan["routing"]}

        self.assertTrue(routing["question_pool"]["usesUploadedContent"])
        for name in ("reading_asset_pool", "grammar_asset_pool", "writing_asset_pool"):
            self.assertFalse(routing[name]["usesUploadedContent"], name)

    def test_the_sse_contract_is_unchanged(self):
        names = [n for n, _ in self._run()]
        for required in ("plan", "question", "update", "done"):
            self.assertIn(required, names)
        self.assertLess(names.index("plan"), names.index("question"))
        self.assertEqual(names[-1], "done")

    def test_model_1_is_only_asked_for_the_literature_shapes(self):
        """Sizing the textbook pool off the whole plan would generate 84
        Literature questions for the six slots that can use them."""
        seen = {}

        def fake_model1(**kwargs):
            seen["plan"] = kwargs.get("plan")
            seen["target"] = kwargs.get("target_total")
            return PoolGenerationResult(pool_id="pool1", questions=_textbook_pool())

        from services.pool.pipeline import stream_pool_questions

        with patch("services.pool.pipeline.generate_question_pool", side_effect=fake_model1), \
             patch("services.pool.pipeline.generate_assets_for_plan", side_effect=_fake_assets), \
             patch("services.pool.model2._run_review", return_value=(False, 0, "stubbed")):
            list(
                stream_pool_questions(
                    user=self.user, pdf_source_ids=[self.source.id],
                    topic="The Thief's Story", count=-1, difficulty="medium",
                    payload={"subject": "English", "class": 10, "board": "CBSE",
                             "qp_type": "board", "countVariation": "cbse"},
                )
            )

        recipe_plan = seen["plan"]
        self.assertEqual(len(recipe_plan), 6)
        self.assertTrue(all(s.generator == "question_pool" for s in recipe_plan))
        self.assertNotIn(
            "READING_COMP", {s.question_type for s in recipe_plan}
        )

    # ── No upload at all ────────────────────────────────────────────────
    #
    # Attaching a source is a blanket product rule (enforced first by
    # `QuestionGenerationSerializer`, then again by `stream_pool_questions`
    # itself for any caller that bypasses the serializer), independent of
    # whether the resulting plan would have read it. An English paper is no
    # exception: even though Reading, Grammar and Writing do not touch the
    # upload once generation is under way, a teacher still has to attach one
    # before generation is allowed to start at all.

    def test_an_english_paper_with_no_upload_is_a_hard_error(self):
        events = self._run(with_source=False)
        self.assertEqual([n for n, _ in events][-1], "error")

    def test_a_science_paper_with_no_upload_is_a_hard_error(self):
        from services.pool.pipeline import stream_pool_questions

        with patch("services.pool.model2._run_review", return_value=(False, 0, "stub")):
            events = _parse_sse(
                stream_pool_questions(
                    user=self.user, pdf_source_ids=[], topic="Electricity",
                    count=-1, difficulty="medium",
                    payload={"subject": "Science", "class": 10, "board": "CBSE",
                             "qp_type": "board", "countVariation": "cbse"},
                )
            )
        self.assertEqual([n for n, _ in events][-1], "error")

    # ── Persistence ─────────────────────────────────────────────────────

    def test_assets_are_banked_under_their_own_projects(self):
        self._run()
        chapters = set(
            Question.objects.filter(user=self.user).values_list(
                "inferred_chapter", flat=True
            )
        )
        self.assertIn("The Thief's Story", chapters)
        self.assertIn("reading_asset_pool bank", chapters)

    def test_provenance_survives_a_round_trip_through_the_bank(self):
        self._run()
        row = Question.objects.filter(
            user=self.user, inferred_chapter="grammar_asset_pool bank"
        ).first()
        self.assertIsNotNone(row)

        restored = PoolQuestion.from_model(row)
        self.assertEqual(restored.generator, "grammar_asset_pool")
        self.assertEqual(restored.asset_type, "grammar_task_set")
        self.assertFalse(restored.uses_uploaded_content)

    def test_a_legacy_row_without_provenance_reads_back_as_textbook(self):
        self._run()
        row = Question.objects.filter(
            user=self.user, inferred_chapter="The Thief's Story"
        ).first()
        row.metadata = {k: v for k, v in (row.metadata or {}).items() if k != "generator"}
        row.save(update_fields=["metadata"])

        restored = PoolQuestion.from_model(row)
        self.assertEqual(restored.generator, "question_pool")
        self.assertTrue(restored.uses_uploaded_content)


class EnglishFromBankTests(TestCase):
    """"Create Paper from Saved Questions" must not lose the asset sections."""

    def setUp(self):
        self.user = User.objects.create(
            id="engbank0000000000000000000001", name="Bank", email="bank@test.local"
        )

    def _seed_literature(self):
        from services.pool import store

        store.persist_pool(
            user=self.user,
            questions=[
                q for q in _textbook_pool()
                if (q.type, q.marks) in {
                    ("EXTRACT_PROSE", 5), ("EXTRACT_POETRY", 5),
                    ("SHORT_ANSWER", 12), ("SHORT_ANSWER", 6), ("LONG_ANSWER", 6),
                }
            ],
            subject="English",
            chapter="The Thief's Story",
            class_num=10,
        )

    def _run(self):
        from services.pool.from_bank import stream_paper_from_bank

        with patch("services.pool.from_bank.generate_assets_for_plan",
                   side_effect=_fake_assets), \
             patch("services.pool.model2._run_review", return_value=(False, 0, "stub")):
            return _parse_sse(
                stream_paper_from_bank(
                    self.user, subject="English", class_num=10,
                    chapters=["The Thief's Story"], count=-1,
                    count_variation="cbse", deterministic=True,
                )
            )

    def test_asset_slots_are_generated_when_the_bank_cannot_cover_them(self):
        self._seed_literature()
        done = next(d for n, d in self._run() if n == "done")
        meta = done["result"]["meta"]

        self.assertEqual(meta["totalQuestions"], 11)
        self.assertEqual(meta["totalMarks"], 80)

    def test_chapter_selection_does_not_filter_out_the_assets(self):
        """Assets have no chapter. Scoping them by the teacher's chapter
        picker would silently delete half the paper."""
        self._seed_literature()
        done = next(d for n, d in self._run() if n == "done")

        titles = [s["title"] for s in done["result"]["sections"]]
        self.assertIn("Section A - Reading Skills", titles)
        self.assertIn("Section B - Grammar and Writing Skills", titles)

    def test_generated_assets_are_banked_for_next_time(self):
        self._seed_literature()
        self._run()
        self.assertTrue(
            Question.objects.filter(
                user=self.user, source_type="reading_asset"
            ).exists()
        )
