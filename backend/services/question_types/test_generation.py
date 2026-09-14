"""A chosen question type changes what gets written — and nothing else does.

Model 1 is briefed on a variant only when one was chosen, the normaliser holds
each type to its own option rule, assembly prefers the exact type, and a type
whose content must never come from the textbook is routed to the generator
that writes it. The first test is the guard for everything that already
worked: a default batch's instruction is byte-for-byte what it always was.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from services.pool.schema import (
    PoolQuestion,
    PoolValidationError,
    _correct_letters,
    normalize_pool_question,
)
from utils.ids import generate_id


class BatchInstructionTests(SimpleTestCase):
    def test_a_default_batch_reads_exactly_as_before(self):
        from services.pool.model1 import _batch_instruction
        from services.pool.recipes import Batch, TypeQuota

        batch = Batch("objective", [TypeQuota("MCQ", 1, 30), TypeQuota("ASSERTION_REASON", 1, 10)])
        self.assertEqual(
            _batch_instruction(batch),
            "Write exactly 40 questions with this breakdown:\n"
            "\n"
            "  • 30 × MCQ worth 1 mark each\n"
            "  • 10 × ASSERTION_REASON worth 1 mark each\n"
            "\n"
            "Set each question's `type` and `marks` to exactly the values above. "
            "Return them as one flat JSON array in the order listed.",
        )

    def test_a_variant_is_briefed_with_its_structure_and_option_rule(self):
        from services.pool.model1 import _batch_instruction
        from services.pool.recipes import Batch, TypeQuota

        text = _batch_instruction(Batch("multi", [TypeQuota("MCQ", 2, 3, type_code="MCQ_MULTI")]))
        self.assertIn("3 × MCQ worth 2 marks each", text)
        self.assertIn("Write these as MCQ — Multiple Correct questions:", text)
        self.assertIn("Format example of the printed question (never reuse its content):", text)
        self.assertIn("4 to 5 options, two or more of them correct", text)
        self.assertIn("overrides rule 4", text)

    def test_the_label_is_never_offered_as_the_type_value(self):
        # Shown as "Type: MCQ — Fill Up", the writer copied the label into the
        # `type` field, and every question in the batch was thrown away.
        from services.pool.model1 import _batch_instruction
        from services.pool.recipes import Batch, TypeQuota

        text = _batch_instruction(Batch("fill", [TypeQuota("MCQ", 1, 2, type_code="MCQ_FILL")]))
        self.assertNotIn("Type:", text)
        self.assertIn("Keep `type` set to MCQ.", text)
        self.assertNotIn(" / ", text)
        self.assertIn("never repeated inside `question`", text)

    def test_original_types_are_told_to_invent_their_stimulus(self):
        from services.pool.model1 import _batch_instruction
        from services.pool.recipes import Batch, TypeQuota

        text = _batch_instruction(
            Batch("dialogue", [TypeQuota("CASE_STUDY", 2, 1, type_code="DIALOGUE_BASED")])
        )
        self.assertIn("overrides rule 1", text)
        self.assertIn("overrides rule 2", text)
        self.assertNotIn("overrides rule 4", text)


class OptionRuleTests(SimpleTestCase):
    _MULTI = {
        "type": "MCQ",
        "question": "Which of the following are renewable sources of energy? (Select all that apply.)",
        "options": ["Solar energy", "Coal", "Wind energy", "Natural gas", "Biomass"],
        "answer": "(a), (c), (e)",
        "marks": 2,
    }

    def _normalise(self, raw, type_hint=""):
        return normalize_pool_question(raw, subject="Science", chapter="Energy", type_hint=type_hint)

    def test_a_multiple_correct_question_may_have_five_options(self):
        question = self._normalise(self._MULTI, type_hint="MCQ_MULTI")
        self.assertEqual((question.type, question.type_code), ("MCQ", "MCQ_MULTI"))
        self.assertEqual(len(question.options), 5)

    def test_a_standard_mcq_still_needs_exactly_four(self):
        with self.assertRaises(PoolValidationError):
            self._normalise(self._MULTI)

    def test_a_multiple_correct_key_must_name_two_options(self):
        with self.assertRaises(PoolValidationError):
            self._normalise({**self._MULTI, "answer": "(a) Solar energy"}, type_hint="MCQ_MULTI")

    def test_answer_letters_are_read_in_either_form(self):
        self.assertEqual(_correct_letters("(a), (c), (e) — all-or-nothing"), {"a", "c", "e"})
        self.assertEqual(_correct_letters("a, c and e"), {"a", "c", "e"})
        self.assertEqual(_correct_letters("a solar panel converts light"), {"a"})

    def test_a_hint_of_another_shape_is_ignored(self):
        question = self._normalise(
            {"type": "SHORT_ANSWER", "question": "Why?", "marks": 2}, type_hint="MCQ_MULTI"
        )
        self.assertEqual(question.type_code, "SA")

    def test_model1_applies_the_batch_type_to_its_questions(self):
        from services.pool.model1 import _normalise_batch
        from services.pool.recipes import Batch, TypeQuota

        questions, invalid = _normalise_batch(
            [self._MULTI],
            batch=Batch("multi", [TypeQuota("MCQ", 2, 1, type_code="MCQ_MULTI")]),
            subject="Science",
            chapter_name="Energy",
            pool_id="pool",
            difficulty="medium",
        )
        self.assertEqual(invalid, 0)
        self.assertEqual(questions[0].type_code, "MCQ_MULTI")

    def test_a_type_written_as_its_label_keeps_the_question(self):
        # What the writer returned for a Fill Up batch, on every attempt.
        raw = {
            "type": "MCQ — Fill Up",
            "question": "A reaction in which two substances combine to form one product is called a ________ reaction.",
            "options": ["decomposition", "combination", "displacement", "redox"],
            "answer": "(b) combination",
            "marks": 1,
        }
        question = self._normalise(raw, type_hint="MCQ_FILL")
        self.assertEqual((question.type, question.type_code), ("MCQ", "MCQ_FILL"))
        # A hyphen for the dash, and no hint at all, read the same way.
        self.assertEqual(self._normalise({**raw, "type": "MCQ - Fill Up"}).type_code, "MCQ_FILL")

    def test_options_repeated_in_the_stem_are_removed(self):
        raw = {
            "type": "MCQ",
            "question": (
                "Choose the odd one out. (a) CaO + H2O → Ca(OH)2  (b) 2H2O → 2H2 + O2  "
                "(c) Fe + CuSO4 → FeSO4 + Cu  (d) Na2SO4 + BaCl2 → BaSO4 + 2NaCl"
            ),
            "options": [
                "CaO + H2O → Ca(OH)2",
                "2H2O → 2H2 + O2",
                "Fe + CuSO4 → FeSO4 + Cu",
                "Na2SO4 + BaCl2 → BaSO4 + 2NaCl",
            ],
            "answer": "(b)",
            "marks": 1,
        }
        self.assertEqual(self._normalise(raw).question, "Choose the odd one out.")

    def test_a_stem_that_only_mentions_a_letter_keeps_it(self):
        raw = {
            "type": "MCQ",
            "question": "Statement (a) above is incorrect. Which option corrects it?",
            "options": ["one", "two", "three", "four"],
            "answer": "(a)",
            "marks": 1,
        }
        self.assertEqual(self._normalise(raw).question, raw["question"])


class AssemblyPreferenceTests(SimpleTestCase):
    @staticmethod
    def _question(type_code: str) -> PoolQuestion:
        return PoolQuestion(
            id=generate_id(), subject="Science", chapter="Food", topic=type_code,
            type="MCQ", blooms="UNDERSTAND", difficulty="medium", marks=1,
            question=f"A {type_code} question", options=["a", "b", "c", "d"],
            type_code=type_code,
        )

    @staticmethod
    def _slot(index: int, type_code: str):
        return SimpleNamespace(
            index=index, marks=1, question_type="MCQ", legacy_type="MCQ",
            type_code=type_code, asset_type="", source="",
        )

    def test_each_slot_takes_the_exact_type_the_pool_holds(self):
        from services.pool.model2 import build_candidates

        pool = [self._question("MCQ_SINGLE"), self._question("MCQ_ODD_ONE_OUT")]
        assignments, unfilled = build_candidates(
            pool, [self._slot(1, "MCQ_ODD_ONE_OUT"), self._slot(2, "MCQ_SINGLE")],
            alternates=0, seed=7,
        )
        self.assertEqual(unfilled, [])
        self.assertEqual(
            [a.question.type_code for a in assignments], ["MCQ_ODD_ONE_OUT", "MCQ_SINGLE"]
        )

    def test_a_slot_short_of_its_type_is_still_filled(self):
        from services.pool.model2 import build_candidates

        assignments, unfilled = build_candidates(
            [self._question("MCQ_SINGLE")], [self._slot(1, "MCQ_ODD_ONE_OUT")],
            alternates=0, seed=7,
        )
        self.assertEqual(unfilled, [])
        self.assertEqual(assignments[0].question.type_code, "MCQ_SINGLE")

    def test_a_stand_in_never_takes_another_slots_exact_type(self):
        # The reported paper: five named MCQ types, and a pool holding only an
        # odd one out and a standard MCQ. Slots 1 and 2 took both as stand-ins
        # and the two slots that asked for them by name were left empty.
        from services.pool.model2 import build_candidates

        pool = [self._question("MCQ_ODD_ONE_OUT"), self._question("MCQ_SINGLE")]
        slots = [
            self._slot(1, "MCQ_STATEMENT_EVAL"),
            self._slot(2, "MCQ_FILL"),
            self._slot(3, "MCQ_ODD_ONE_OUT"),
            self._slot(4, "MCQ_SINGLE"),
            self._slot(5, "MCQ_ANALOGY"),
        ]
        assignments, unfilled = build_candidates(pool, slots, alternates=0, seed=7)
        self.assertEqual(
            {a.slot.index: a.question.type_code for a in assignments},
            {3: "MCQ_ODD_ONE_OUT", 4: "MCQ_SINGLE"},
        )
        self.assertEqual(sorted(u.slot.index for u in unfilled), [1, 2, 5])


class RoutingTests(SimpleTestCase):
    @staticmethod
    def _plan(*slots):
        from services.templates import TemplateBlueprint, blueprint_to_plan

        return blueprint_to_plan(TemplateBlueprint.from_dict({"slots": list(slots)}))

    def test_a_writing_type_goes_to_the_writing_generator(self):
        (slot,) = self._plan({"questionType": "COMPOSITION", "typeCode": "NOTICE_WRITING", "marks": 4})
        self.assertEqual((slot.generator, slot.asset_type), ("writing_asset_pool", "notice"))

    def test_a_grammar_type_names_its_grammar_points(self):
        (slot,) = self._plan({"questionType": "GRAMMAR", "typeCode": "ERROR_CORRECTION", "marks": 2})
        self.assertEqual(slot.generator, "grammar_asset_pool")
        self.assertEqual(slot.constraints["grammar_topics"], ["error_correction_table"])

    def test_textbook_types_stay_with_model1(self):
        (slot,) = self._plan({"questionType": "LONG_ANSWER", "marks": 5})
        self.assertEqual(slot.generator, "question_pool")

    def test_an_engine_routed_slot_is_never_rerouted(self):
        (slot,) = self._plan(
            {
                "questionType": "LETTER",
                "marks": 5,
                "passthrough": {"generator": "question_pool", "legacy_type": "LONG"},
            }
        )
        self.assertEqual(slot.generator, "question_pool")

    def test_an_asset_question_keeps_only_a_type_of_its_own_shape(self):
        from services.assets.schema import build_pool_question

        def build(type_code):
            return build_pool_question(
                question="Fill in the blanks.", answer="went", marks=3, subject="English",
                chapter="Grammar", topic="Tenses", question_type="GRAMMAR",
                generator="grammar_asset_pool", asset_type="grammar_task_set",
                source_type="asset", type_code=type_code,
            ).type_code

        self.assertEqual(build("GAP_FILL_GRAMMAR"), "GAP_FILL_GRAMMAR")
        self.assertEqual(build("NOTICE_WRITING"), "GRAMMAR_ITEM")
