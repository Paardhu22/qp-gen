"""Indexed variables as maths: ``x1`` → ``\\(x_{1}\\)``, and only when it is one.

The case table in ``subscript_cases.json`` is shared with the frontend twin
(``frontend/scripts/test-subscripts.mjs``), so both implementations answer the
same hand-written expectations and cannot drift apart. The cases that matter
most are the ones that must NOT change: ``A1`` is a spreadsheet cell, ``O2`` is
oxygen, ``6x2`` is a power, ``20 m2`` is an area.
"""

import json
import re
from pathlib import Path

from django.test import SimpleTestCase

from services.generation.rules import subscripts as S
from services.generation.rules.content_filters import clean_question_text
from services.generation.rules.subscripts import typeset_indices
from services.generation.rules.typesetting import MATH_PROMPT_RULES, normalize_math_text

CASES = json.loads((Path(__file__).parent / "subscript_cases.json").read_text(encoding="utf-8"))


class SharedCaseTableTests(SimpleTestCase):
    def test_every_case_in_the_table(self):
        for case in CASES:
            with self.subTest(group=case["group"], subject=case["subject"], text=case["text"]):
                self.assertEqual(
                    typeset_indices(case["text"], subject=case["subject"]), case["expected"]
                )

    def test_the_table_covers_what_the_task_names(self):
        groups = {case["group"] for case in CASES}
        self.assertTrue(
            {"coordinates", "statistics", "algebra", "explicit", "not-an-index", "subject"} <= groups
        )

    def test_the_stated_examples_verbatim(self):
        # "(x1, x2)" -> (x₁, x₂) and "(y1, y2)" -> (y₁, y₂), from the task.
        self.assertEqual(
            typeset_indices("(x1, x2)", subject="Mathematics"), "\\((x_{1}, x_{2})\\)"
        )
        self.assertEqual(
            typeset_indices("(y1, y2)", subject="Mathematics"), "\\((y_{1}, y_{2})\\)"
        )
        for name in ("a1, a2", "P1, P2"):
            with self.subTest(name):
                got = typeset_indices(name, subject="Mathematics")
                self.assertNotRegex(got, r"[A-Za-z]\d")
                self.assertEqual(got.count("\\("), 2)


class IdempotenceTests(SimpleTestCase):
    def test_running_twice_changes_nothing(self):
        for case in CASES:
            with self.subTest(text=case["text"]):
                once = typeset_indices(case["text"], subject=case["subject"])
                self.assertEqual(typeset_indices(once, subject=case["subject"]), once)

    def test_text_the_model_already_typeset_is_left_alone(self):
        for case in CASES:
            with self.subTest(text=case["expected"]):
                self.assertEqual(
                    typeset_indices(case["expected"], subject=case["subject"]), case["expected"]
                )

    def test_existing_maths_spans_survive_byte_for_byte(self):
        text = "Given \\(x1 + y2 = 3\\) and \\[ a1 b2 \\] find x1, x2."
        got = typeset_indices(text, subject="Mathematics")
        self.assertIn("\\(x1 + y2 = 3\\)", got)
        self.assertIn("\\[ a1 b2 \\]", got)


class PolicyTests(SimpleTestCase):
    def test_subjects_map_to_how_much_they_are_trusted(self):
        expected = {
            "Mathematics": S.MATHS,
            "Mathematics Standard": S.MATHS,
            "Applied Mathematics": S.MATHS,
            "Maths": S.MATHS,
            "Statistics": S.MATHS,
            "Science": S.SCIENCE,
            "Physics": S.SCIENCE,
            "Chemistry": S.SCIENCE,
            "Biology": S.SCIENCE,
            "Social Science": S.OFF,
            "English": S.OFF,
            "English Language & Literature": S.OFF,
            "Hindi Course B": S.OFF,
            "Telugu": S.OFF,
            "Sanskrit": S.OFF,
            "Computer Science": S.OFF,
            "ICT": S.OFF,
            "": S.DEFAULT,
            None: S.DEFAULT,
            "Something New": S.DEFAULT,
        }
        for subject, policy in expected.items():
            with self.subTest(subject=subject):
                self.assertIs(S.policy_for(subject), policy)

    def test_an_unknown_subject_never_subscripts_a_capital(self):
        # "P1 and P2" could be points, pressures, or phosphorus: not without a subject.
        self.assertEqual(typeset_indices("Points P1 and P2.", subject=""), "Points P1 and P2.")

    def test_social_science_is_off_even_though_it_contains_science(self):
        self.assertIs(S.policy_for("Social Science"), S.OFF)


class EdgeTests(SimpleTestCase):
    def test_empty_and_none_pass_through(self):
        self.assertEqual(typeset_indices(""), "")
        self.assertIsNone(typeset_indices(None))

    def test_a_long_text_is_not_slow(self):
        text = ("The points x1 and x2, (y1, y2) and 20 m2. " * 2000) + "A1 B2 " * 2000
        got = typeset_indices(text, subject="Mathematics")
        self.assertIn("\\(x_{1}\\)", got)

    def test_tokens_in_a_single_line_never_swallow_the_text_between(self):
        got = typeset_indices("x1 is a point and a long sentence follows x2", subject="Mathematics")
        self.assertEqual(
            got, "\\(x_{1}\\) is a point and a long sentence follows \\(x_{2}\\)"
        )

    def test_unicode_subscripts_are_left_as_they_are(self):
        # x₁ already displays as a subscript; rewriting it would turn H₂O italic.
        self.assertEqual(typeset_indices("x₁ and H₂O", subject="Mathematics"), "x₁ and H₂O")

    def test_every_output_span_is_balanced(self):
        for case in CASES:
            out = typeset_indices(case["text"], subject=case["subject"])
            with self.subTest(text=case["text"]):
                self.assertEqual(out.count("\\("), out.count("\\)"))
                self.assertEqual(out.count("\\["), out.count("\\]"))


class WiringTests(SimpleTestCase):
    def test_the_question_scrub_converts_for_a_maths_subject(self):
        self.assertEqual(
            clean_question_text("Find (x1, y1) and (x2, y2).", subject="Mathematics"),
            "Find \\((x_{1}, y_{1})\\) and \\((x_{2}, y_{2})\\).",
        )

    def test_the_question_scrub_without_a_subject_still_does_the_safe_cases(self):
        self.assertEqual(
            clean_question_text("Find (x1, y1).", subject=None), "Find \\((x_{1}, y_{1})\\)."
        )

    def test_subscripts_and_exponents_combine(self):
        # The exponent rescue runs first and takes the whole token.
        self.assertEqual(
            clean_question_text("Find x_1^2 + x_2^2.", subject="Mathematics"),
            "Find \\(x_1^2\\) + \\(x_2^2\\).",
        )

    def test_the_answer_normaliser_uses_the_same_rules(self):
        self.assertEqual(
            normalize_math_text("Hence x1 + x2 = 5 and x^2 = 4.", subject="Mathematics"),
            "Hence \\(x_{1}\\) + \\(x_{2}\\) = 5 and \\(x^2\\) = 4.",
        )

    def test_a_spreadsheet_answer_is_not_touched(self):
        text = "Type =SUM(A1, B2) in C1."
        self.assertEqual(normalize_math_text(text, subject="ICT"), text)

    def test_the_prompt_carries_the_rule_for_the_answer_script(self):
        self.assertIn("x_{1}", MATH_PROMPT_RULES)
        self.assertIn("(x_{1}, y_{1})", MATH_PROMPT_RULES)
        self.assertNotIn("@@INDEX_RULE@@", MATH_PROMPT_RULES)
        # …and says what must stay a plain digit.
        self.assertRegex(MATH_PROMPT_RULES, r"Class 10")
