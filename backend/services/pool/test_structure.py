"""Structured questions: parts whose marks add up, printed the way they always were."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from services.pool.schema import PoolValidationError, normalize_pool_question
from services.pool.structure import StructureError, parse_structure


def _case_study(**overrides):
    raw = {
        "type": "CASE_STUDY",
        "marks": 4,
        "question": "Read the following and answer the questions.",
        "stimulus": "A farmer grew rice on the same field every year and his yield kept falling.",
        "parts": [
            {"question": "Why did the yield fall?", "marks": 1, "answer": "Continuous cropping depleted one nutrient."},
            {"question": "What crop could restore nitrogen?", "marks": 1, "answer": "Groundnut, a legume."},
            {"question": "Name the practice and give two benefits.", "marks": 2, "answer": "Crop rotation; pest control, better soil."},
        ],
    }
    raw.update(overrides)
    return raw


class ParseStructureTests(SimpleTestCase):
    def test_a_flat_question_has_no_structure(self):
        self.assertIsNone(parse_structure({"question": "Explain."}, marks=3))

    def test_a_case_study_prints_its_stimulus_then_numbered_parts(self):
        structure = parse_structure(_case_study(), marks=4, stimulus_kind="SCENARIO")
        content, answer, composite = structure.render("Read the following and answer the questions.")
        self.assertIn("A farmer grew rice", content)
        self.assertIn("(i) Why did the yield fall?   [1]", content)
        self.assertIn("(iii) Name the practice and give two benefits.   [2]", content)
        self.assertTrue(answer.startswith("(i) Continuous cropping"))
        self.assertEqual(len(composite["subQuestions"]), 3)
        self.assertEqual(composite["preamble"], "Read the following and answer the questions.")

    def test_three_one_mark_parts_become_the_board_pattern(self):
        raw = _case_study()
        for part in raw["parts"]:
            part["marks"] = 1
        structure = parse_structure(raw, marks=4, stimulus_kind="SCENARIO")
        self.assertEqual([part.marks for part in structure.parts], [1, 1, 2])

    def test_parts_that_cannot_add_up_are_rejected(self):
        raw = _case_study()
        raw["parts"][2]["marks"] = 3
        with self.assertRaises(StructureError):
            parse_structure(raw, marks=4)

    def test_every_part_needs_an_answer(self):
        raw = _case_study()
        raw["parts"][1]["answer"] = ""
        with self.assertRaises(StructureError):
            parse_structure(raw, marks=4)

    def test_a_required_stimulus_must_be_present(self):
        with self.assertRaises(StructureError):
            parse_structure(_case_study(stimulus=""), marks=4, stimulus_kind="SCENARIO")

    def test_a_table_stimulus_prints_as_pipe_rows(self):
        raw = _case_study(stimulus={"rows": [["City", "Rainfall (cm)"], ["Delhi", "79"]]})
        structure = parse_structure(raw, marks=4, stimulus_kind="TABLE")
        content, _, composite = structure.render("Study the table.")
        self.assertIn("| City | Rainfall (cm) |\n| Delhi | 79 |", content)
        self.assertIn("| Delhi | 79 |", composite["body"][0])

    def test_a_choice_pool_totals_only_the_attempted_parts(self):
        parts = [{"question": f"Question {n}?", "marks": 3, "answer": "An answer."} for n in range(5)]
        structure = parse_structure({"parts": parts, "attempt": 4}, marks=12)
        self.assertEqual((structure.attempt, structure.marks), (4, 12))

    def test_a_choice_pool_needs_equal_marks_and_a_real_choice(self):
        unequal = [{"question": "A?", "marks": 2, "answer": "a"}, {"question": "B?", "marks": 3, "answer": "b"}, {"question": "C?", "marks": 3, "answer": "c"}]
        with self.assertRaises(StructureError):
            parse_structure({"parts": unequal, "attempt": 2}, marks=6)
        equal = [{"question": "A?", "marks": 1, "answer": "a"}, {"question": "B?", "marks": 1, "answer": "b"}]
        with self.assertRaises(StructureError):
            parse_structure({"parts": equal, "attempt": 2}, marks=2)


class NormaliserStructureTests(SimpleTestCase):
    def _normalise(self, raw):
        return normalize_pool_question(raw, subject="Science", chapter="Agriculture")

    def test_a_structured_case_study_carries_its_pieces(self):
        question = self._normalise(_case_study())
        self.assertIn("(ii) What crop could restore nitrogen?   [1]", question.question)
        self.assertIn("(iii) Crop rotation", question.answer)
        self.assertEqual(len(question.metadata["structure"]["parts"]), 3)
        self.assertEqual(len(question.metadata["composite"]["subQuestions"]), 3)

    def test_a_flat_case_study_is_kept_exactly_as_before(self):
        flat = {"type": "CASE_STUDY", "marks": 4, "question": "Read the case.\n(i) One? [1]\n(ii) Two? [1]\n(iii) Three? [2]", "answer": "(i) a (ii) b (iii) c"}
        question = self._normalise(flat)
        self.assertEqual(question.question, flat["question"])
        self.assertNotIn("structure", question.metadata)

    def test_a_broken_structure_is_dropped(self):
        raw = _case_study()
        raw["parts"] = raw["parts"][:1]
        with self.assertRaises(PoolValidationError):
            self._normalise(raw)

    def test_parts_on_a_type_that_holds_none_are_ignored(self):
        question = self._normalise({"type": "SHORT_ANSWER", "marks": 2, "question": "Explain.", "parts": [{"question": "x"}]})
        self.assertEqual(question.question, "Explain.")
        self.assertEqual(question.metadata, {})

    def test_the_pieces_survive_model1_and_reach_the_wire(self):
        from services.pool.model1 import _normalise_batch
        from services.pool.pipeline import _question_to_wire
        from services.pool.recipes import Batch, TypeQuota

        questions, invalid = _normalise_batch(
            [_case_study()],
            batch=Batch("case_study", [TypeQuota("CASE_STUDY", 4, 1)]),
            subject="Science",
            chapter_name="Agriculture",
            pool_id="pool",
            difficulty="medium",
        )
        self.assertEqual(invalid, 0)
        wire = _question_to_wire(questions[0], slot=SimpleNamespace(index=36, subject="Science"), section_title="Section E")
        self.assertEqual(len(wire["metadata"]["composite"]["subQuestions"]), 3)


class StructureInstructionTests(SimpleTestCase):
    def _instruction(self, quota, **kwargs):
        from services.pool.model1 import _batch_instruction
        from services.pool.recipes import Batch

        return _batch_instruction(Batch("b", [quota]), **kwargs)

    def test_a_case_study_quota_asks_for_parts(self):
        from services.pool.recipes import TypeQuota

        text = self._instruction(TypeQuota("CASE_STUDY", 4, 6))
        self.assertIn("`parts` as a list", text)
        self.assertIn("must add up to 4", text)
        self.assertIn("scenario text", text)

    def test_a_language_paper_keeps_its_own_extract_form(self):
        from services.pool.recipes import TypeQuota

        self.assertNotIn("Structure:", self._instruction(TypeQuota("EXTRACT_PROSE", 3, 8), language_subject=True))
        chosen = TypeQuota("EXTRACT_PROSE", 3, 1, type_code="EXTRACT_SEEN")
        self.assertIn("Structure:", self._instruction(chosen, language_subject=True))

    def test_a_word_bank_asks_for_its_words(self):
        from services.pool.recipes import TypeQuota

        text = self._instruction(TypeQuota("FILL_IN_THE_BLANK", 3, 2, type_code="FILL_BLANK_BANK"))
        self.assertIn('{"words": [word, …]}', text)
