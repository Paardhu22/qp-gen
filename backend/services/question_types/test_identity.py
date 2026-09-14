"""A question's catalogue type survives every hop, and HOTS is an attribute.

The teacher's exact choice ("MCQ_ODD_ONE_OUT") has to travel from the Builder
slot through Model 1's recipe, the pool, set variants, the wire and the bank
and back — while `type` stays the runtime shape every older consumer keys on.
Each test below is one of those hops.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from services import question_types as qt
from services.pool.schema import PoolQuestion, normalize_pool_question
from utils.ids import generate_id


def _question(**overrides) -> PoolQuestion:
    fields = dict(
        id=generate_id(),
        subject="Science",
        chapter="Food",
        topic="Fruits and vegetables",
        type="MCQ",
        blooms="UNDERSTAND",
        difficulty="medium",
        marks=1,
        question="Choose the odd one out.",
        options=["Mango", "Banana", "Potato", "Apple"],
    )
    fields.update(overrides)
    return PoolQuestion(**fields)


class ResolveSlotTypeTests(SimpleTestCase):
    def test_a_code_that_agrees_with_the_shape_wins(self):
        slot = qt.resolve_slot_type("MCQ_ODD_ONE_OUT", "MCQ")
        self.assertEqual((slot.code, slot.shape), ("MCQ_ODD_ONE_OUT", "MCQ"))

    def test_a_stale_code_loses_to_a_newer_shape(self):
        slot = qt.resolve_slot_type("MCQ_ODD_ONE_OUT", "LONG_ANSWER")
        self.assertEqual((slot.code, slot.shape), ("LA", "LONG_ANSWER"))

    def test_a_code_alone_is_enough(self):
        self.assertEqual(qt.resolve_slot_type("NOTICE_WRITING").shape, "COMPOSITION")

    def test_retired_names_become_attributes(self):
        hots = qt.resolve_slot_type("", "HOTS")
        self.assertEqual((hots.code, hots.shape, hots.hots), ("SA", "SHORT_ANSWER", True))
        competency = qt.resolve_slot_type("", "COMPETENCY")
        self.assertEqual(
            (competency.code, competency.competency), ("APPLICATION_SCENARIO", True)
        )

    def test_a_shape_word_keeps_its_shape_meaning(self):
        self.assertEqual(qt.resolve_slot_type("", "ESSAY").code, "LA")

    def test_nothing_recognised_falls_back_to_short_answer(self):
        slot = qt.resolve_slot_type("NOPE", "ALSO_NOPE")
        self.assertEqual((slot.code, slot.shape), ("SA", "SHORT_ANSWER"))


class PoolQuestionIdentityTests(SimpleTestCase):
    def test_a_bare_shape_carries_its_default_type(self):
        self.assertEqual(_question(type="MCQ").type_code, "MCQ_SINGLE")

    def test_the_normaliser_keeps_the_type_the_model_named(self):
        question = normalize_pool_question(
            {
                "type": "MCQ_ODD_ONE_OUT",
                "question": "Choose the odd one out.",
                "options": ["Mango", "Banana", "Potato", "Apple"],
                "answer": "(c) Potato",
            },
            subject="Science",
            chapter="Food",
        )
        self.assertEqual((question.type, question.type_code), ("MCQ", "MCQ_ODD_ONE_OUT"))

    def test_the_normaliser_turns_hots_into_an_attribute(self):
        question = normalize_pool_question(
            {"type": "HOTS", "question": "Why does a spoon look bent in water?", "marks": 3},
            subject="Science",
            chapter="Light",
        )
        self.assertEqual(
            (question.type, question.type_code, question.hots), ("SHORT_ANSWER", "SA", True)
        )

    def test_the_normaliser_reads_shape_words_as_shapes(self):
        question = normalize_pool_question(
            {"type": "ESSAY", "question": "Describe the water cycle.", "marks": 5},
            subject="Science",
            chapter="Water",
        )
        self.assertEqual((question.type, question.type_code), ("LONG_ANSWER", "LA"))

    def test_the_bank_round_trip_is_lossless(self):
        original = _question(type_code="MCQ_ODD_ONE_OUT", hots=True)
        seeded = {spec.code for spec in qt.all_types()}
        kwargs = original.to_model_kwargs(user=None, project=None, valid_type_codes=seeded)
        self.assertEqual(kwargs["type_id"], "MCQ_ODD_ONE_OUT")
        self.assertTrue(kwargs["metadata"]["hots"])

        row = SimpleNamespace(
            id=original.id,
            **{k: v for k, v in kwargs.items() if k not in {"user", "project", "paper"}},
        )
        restored = PoolQuestion.from_model(row)
        self.assertEqual(
            (restored.type, restored.type_code, restored.hots), ("MCQ", "MCQ_ODD_ONE_OUT", True)
        )


class BuilderSlotTests(SimpleTestCase):
    def test_a_catalogue_type_survives_the_builder_round_trip(self):
        from services.templates import SlotSpec

        spec = SlotSpec.from_dict(
            {"questionType": "MCQ", "typeCode": "MCQ_ODD_ONE_OUT", "marks": 1, "hots": True},
            index=1,
        )
        again = SlotSpec.from_dict(spec.as_dict(), index=1)
        self.assertEqual(
            (again.question_type, again.type_code, again.hots), ("MCQ", "MCQ_ODD_ONE_OUT", True)
        )

    def test_a_shape_changed_by_an_older_client_wins_over_its_stale_code(self):
        from services.templates import SlotSpec

        spec = SlotSpec.from_dict(
            {"questionType": "LONG_ANSWER", "typeCode": "MCQ_ODD_ONE_OUT", "marks": 5}, index=1
        )
        self.assertEqual((spec.question_type, spec.type_code), ("LONG_ANSWER", "LA"))

    def test_saved_hots_slots_still_load(self):
        from services.templates import SlotSpec

        spec = SlotSpec.from_dict({"questionType": "HOTS", "marks": 3}, index=1)
        self.assertEqual(
            (spec.question_type, spec.type_code, spec.hots), ("SHORT_ANSWER", "SA", True)
        )

    def test_designer_type_names_are_understood(self):
        # The designer says FILL_BLANK; a Builder slot used to fall back to
        # SHORT_ANSWER on it.
        from services.templates import SlotSpec

        spec = SlotSpec(index=1, section_title="A", question_type="FILL_BLANK", marks=1)
        self.assertEqual((spec.question_type, spec.type_code), ("FILL_IN_THE_BLANK", "FILL_BLANK"))

    def test_the_plan_carries_the_type_and_its_attributes(self):
        from services.templates import TemplateBlueprint, blueprint_to_plan

        plan = blueprint_to_plan(
            TemplateBlueprint.from_dict(
                {
                    "slots": [
                        {"questionType": "MCQ", "typeCode": "MCQ_ODD_ONE_OUT", "marks": 1},
                        {"questionType": "SHORT_ANSWER", "marks": 3, "hots": True},
                    ]
                }
            )
        )
        self.assertEqual(
            [(s.question_type, s.type_code, s.hots) for s in plan],
            [("MCQ", "MCQ_ODD_ONE_OUT", False), ("SHORT_ANSWER", "SA", True)],
        )
        self.assertEqual(plan[0].legacy_type, "MCQ")

    def test_engine_slots_default_to_their_shape_type(self):
        from services.generation_router import QuestionGenerationSlot

        slot = QuestionGenerationSlot(
            index=1, section_title="Section E", subject="Science", stream="INTEGRATED",
            question_type="CASE_STUDY", legacy_type="CASE_STUDY", marks=4,
            difficulty="medium", class_num=10, exact_instruction="", retrieval_query="",
        )
        self.assertEqual(slot.type_code, "CASE_STUDY")


class RecipeTests(SimpleTestCase):
    @staticmethod
    def _slot(**overrides):
        fields = dict(
            index=1, marks=1, question_type="MCQ", type_code="", hots=False,
            competency=False, asset_type="", instruction_hint="",
        )
        fields.update(overrides)
        return SimpleNamespace(**fields)

    def test_default_types_keep_their_batches_exactly(self):
        from services.pool.recipes import batches_from_plan

        batches = batches_from_plan([self._slot(), self._slot(index=2, type_code="MCQ_SINGLE")])
        self.assertEqual([batch.name for batch in batches], ["mcq_1m"])
        self.assertEqual(batches[0].quotas[0].type_code, "")
        self.assertEqual(batches[0].quotas[0].hints, ())

    def test_a_chosen_variant_gets_its_own_batch(self):
        from services.pool.recipes import batches_from_plan

        batches = batches_from_plan(
            [self._slot(), self._slot(index=2, type_code="MCQ_ODD_ONE_OUT")]
        )
        self.assertEqual([batch.name for batch in batches], ["mcq_1m", "mcq_1m_mcq_odd_one_out"])
        self.assertEqual(batches[1].quotas[0].type_code, "MCQ_ODD_ONE_OUT")

    def test_a_chosen_variant_carries_a_spare_and_a_default_does_not(self):
        # One question per named type left no room for a single bad answer from
        # the writer: the reported five-type paper lost three of its slots.
        from services.pool.recipes import batches_from_plan

        plan = [
            self._slot(index=position + 1, type_code=code)
            for position, code in enumerate(
                ["MCQ_STATEMENT_EVAL", "MCQ_FILL", "MCQ_ODD_ONE_OUT", "MCQ_SINGLE", "MCQ_ANALOGY"]
            )
        ]
        counts = {batch.name: batch.total for batch in batches_from_plan(plan, target_total=6)}
        self.assertEqual(counts.pop("mcq_1m"), 1)
        self.assertEqual(sorted(counts.values()), [2, 2, 2, 2])

    def test_hots_reaches_model1_as_a_hint(self):
        from services.pool.recipes import HOTS_HINT, batches_from_plan

        (batch,) = batches_from_plan(
            [self._slot(question_type="SHORT_ANSWER", marks=3, hots=True)]
        )
        self.assertTrue(batch.quotas[0].hots)
        self.assertIn(HOTS_HINT, batch.quotas[0].hints)

    def test_fixed_recipes_no_longer_ask_for_retired_types(self):
        from services.pool.recipes import batches_for_subject

        for subject in ("science", "mathematics", "english"):
            asked = {quota.type for batch in batches_for_subject(subject) for quota in batch.quotas}
            with self.subTest(subject=subject):
                self.assertFalse(asked & {"HOTS", "COMPETENCY"})

    def test_model1_stamps_the_quota_type_onto_what_it_wrote(self):
        from services.pool.model1 import _normalise_batch
        from services.pool.recipes import Batch, TypeQuota

        batch = Batch("odd", [TypeQuota("MCQ", 1, 1, type_code="MCQ_ODD_ONE_OUT")])
        questions, invalid = _normalise_batch(
            [
                {
                    "type": "MCQ",
                    "question": "Choose the odd one out.",
                    "options": ["Mango", "Banana", "Potato", "Apple"],
                    "answer": "(c) Potato",
                }
            ],
            batch=batch,
            subject="Science",
            chapter_name="Food",
            pool_id="pool",
            difficulty="medium",
        )
        self.assertEqual(invalid, 0)
        self.assertEqual(questions[0].type_code, "MCQ_ODD_ONE_OUT")


class DownstreamTests(SimpleTestCase):
    def test_set_variants_replace_a_variant_only_with_the_same_variant(self):
        from services.pool.set_variants import _matches

        original = _question(type_code="MCQ_ODD_ONE_OUT")
        self.assertFalse(_matches(_question(type_code="MCQ_SINGLE"), original, require_topic=False))
        self.assertTrue(_matches(_question(type_code="MCQ_ODD_ONE_OUT"), original, require_topic=False))

    def test_a_replacement_keeps_the_slot_variant_unless_retyped(self):
        from services.pool.replace import build_slot

        slot = build_slot({"type": "MCQ", "typeCode": "MCQ_ODD_ONE_OUT", "marks": 1})
        self.assertEqual((slot.question_type, slot.type_code), ("MCQ", "MCQ_ODD_ONE_OUT"))

        retyped = build_slot({"type": "LONG_ANSWER", "typeCode": "MCQ_ODD_ONE_OUT", "marks": 5})
        self.assertEqual(
            (retyped.question_type, retyped.legacy_type, retyped.type_code),
            ("LONG_ANSWER", "LONG", "LA"),
        )

    def test_the_wire_names_the_type(self):
        from services.pool.pipeline import _question_to_wire

        wire = _question_to_wire(
            _question(type_code="MCQ_ODD_ONE_OUT", hots=True),
            slot=SimpleNamespace(index=3, subject="Science"),
            section_title="Section A",
        )
        self.assertEqual(
            (wire["type"], wire["typeCode"], wire["typeLabel"]),
            ("MCQ", "MCQ_ODD_ONE_OUT", "MCQ — Odd One Out"),
        )
        self.assertTrue(wire["metadata"]["hots"])

    def test_writing_formats_name_their_types(self):
        cases = {
            "notice": "NOTICE_WRITING",
            "debate": "SPEECH_DEBATE",
            "letter_to_editor": "LETTER_WRITING",
            "no_such_format": "",
        }
        for asset_type, code in cases.items():
            with self.subTest(asset_type=asset_type):
                self.assertEqual(qt.type_for_route("writing_asset_pool", asset_type), code)
