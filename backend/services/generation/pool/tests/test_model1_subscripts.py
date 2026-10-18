"""Indexed variables through Model 1: the prompt, the parse, and every field.

A question's stem, options, answer and explanation all reach the reader, so all
four must come out with ``x1`` typeset as ``x_{1}`` — and a reply that wrote its
LaTeX with single backslashes (illegal JSON) must be recovered, not dropped.
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from services.generation.pool.model1 import _system_prompt, generate_question_pool
from services.generation.pool.schema import normalize_pool_question
from services.generation.pool.tests.test_model1 import CHAPTER, _FakeProvider, _mcq


def _generate(subject, payload):
    provider = _FakeProvider(lambda _batch, _call: payload)
    with patch("services.generation.pool.model1.OpenAIProvider", return_value=provider):
        return generate_question_pool(
            chapter=CHAPTER,
            subject=subject,
            subject_norm=subject.lower(),
            chapter_name="Coordinate Geometry",
            class_num=10,
        )


class EveryFieldTests(TestCase):
    def test_stem_options_answer_and_explanation_are_all_typeset(self):
        payload = [
            _mcq(
                1,
                question="Find the distance between (x1, y1) and (x2, y2).",
                options=["x1 + x2", "x2 - x1", "y2 - y1", "x1 y1"],
                answer="x2 - x1",
                explanation="Take x1 and x2 as the abscissae, y1 and y2 as the ordinates.",
            )
        ]
        result = _generate("Mathematics", payload)
        (question,) = result.questions
        self.assertEqual(
            question.question,
            "Find the distance between \\((x_{1}, y_{1})\\) and \\((x_{2}, y_{2})\\).",
        )
        self.assertEqual(
            question.options,
            ["\\(x_{1}\\) + \\(x_{2}\\)", "\\(x_{2}\\) - \\(x_{1}\\)", "\\(y_{2}\\) - \\(y_{1}\\)", "\\(x_{1}\\) \\(y_{1}\\)"],
        )
        self.assertEqual(question.answer, "\\(x_{2}\\) - \\(x_{1}\\)")
        self.assertEqual(
            question.explanation,
            "Take \\(x_{1}\\) and \\(x_{2}\\) as the abscissae, \\(y_{1}\\) and \\(y_{2}\\) as the ordinates.",
        )

    def test_a_bare_exponent_in_an_option_is_typeset_too(self):
        # Options had no scrub at all: x^2 reached the paper as "x^2".
        payload = [_mcq(1, question="Which is the square of x?", options=["x^2", "2x", "x + 2", "x/2"])]
        (question,) = _generate("Mathematics", payload).questions
        self.assertEqual(question.options[0], "\\(x^2\\)")

    def test_science_subscripts_resistors(self):
        payload = [_mcq(1, question="Resistors R1 = 2 ohm and R2 = 4 ohm are in series. Find R.")]
        (question,) = _generate("Science", payload).questions
        self.assertIn("\\(R_{1}\\) = 2 ohm", question.question)
        self.assertIn("\\(R_{2}\\) = 4 ohm", question.question)

    def test_ict_keeps_its_spreadsheet_cells(self):
        text = "In a worksheet, copy the formula in cell A1 and cell A2 to B1."
        (question,) = _generate("ICT", [_mcq(1, question=text)]).questions
        self.assertEqual(question.question, text)

    def test_english_is_not_touched(self):
        text = "Read the notice for Class 10 x1 and x2."
        (question,) = _generate("English", [_mcq(1, question=text)]).questions
        self.assertEqual(question.question, text)


class SingleBackslashReplyTests(TestCase):
    def test_a_reply_with_single_backslashes_is_recovered_not_dropped(self):
        # As the model wrote it: "\(" is not a legal JSON escape, so this whole
        # object used to be discarded without a trace.
        reply = (
            '[{"topic": "Distance", "type": "MCQ", "blooms": "APPLY", "difficulty": "medium", '
            '"marks": 1, "question": "Find \\( (x_{1}, y_{1}) \\) and the value of \\frac{1}{2}.", '
            '"options": ["a", "b", "c", "d"], "answer": "a", "explanation": "e"}]'
        )
        with self.assertRaises(json.JSONDecodeError):
            json.loads(reply)
        (question,) = _generate("Mathematics", reply).questions
        self.assertIn("\\( (x_{1}, y_{1}) \\)", question.question)

    def test_a_valid_but_eaten_command_is_restored(self):
        # "\frac" is a LEGAL JSON escape (form feed), so this parses cleanly and
        # the fraction is silently destroyed unless it is put back.
        reply = (
            '[{"topic": "Fractions", "type": "MCQ", "blooms": "APPLY", "difficulty": "medium", '
            '"marks": 1, "question": "Evaluate \\frac{1}{2} + \\frac{1}{3}.", '
            '"options": ["1/6", "5/6", "2/5", "1/5"], "answer": "5/6", "explanation": "e"}]'
        )
        self.assertIn("\x0c", json.loads(reply)[0]["question"], "the premise: a naive parse eats it")
        (question,) = _generate("Mathematics", reply).questions
        self.assertNotIn("\x0c", question.question)
        self.assertIn("\\frac{1}{2}", question.question)


class NormaliserTests(SimpleTestCase):
    def test_an_eaten_command_in_an_option_is_restored_and_wrapped(self):
        raw = _mcq(1, question="Pick one", options=["\x0crac{1}{2}", "b", "c", "d"], answer="b")
        question = normalize_pool_question(
            raw, subject="Mathematics", chapter="c", pool_id="p", default_difficulty="medium"
        )
        self.assertEqual(question.options[0], "\\(\\frac{1}{2}\\)")


class PromptTests(SimpleTestCase):
    NOTATION = "Mathematical notation"

    def test_maths_and_science_prompts_carry_the_rule(self):
        for subject in ("Mathematics", "Science", "Applied Mathematics", "Physics"):
            with self.subTest(subject):
                prompt = _system_prompt(subject, 10, "medium")
                self.assertIn(self.NOTATION, prompt)
                self.assertIn("x_{1}", prompt)
                self.assertIn("double every backslash", prompt)

    def test_the_rule_sits_before_the_json_instructions(self):
        prompt = _system_prompt("Mathematics", 10, "medium")
        self.assertLess(prompt.index(self.NOTATION), prompt.index("Return ONLY a JSON array"))

    def test_subjects_without_variables_keep_their_prompt_exactly(self):
        for subject in ("English", "Hindi", "Social Science", "ICT", "Computer Science"):
            with self.subTest(subject):
                self.assertNotIn(self.NOTATION, _system_prompt(subject, 10, "medium"))
