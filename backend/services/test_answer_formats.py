"""Which answer format a marking scheme asks for, question by question."""

import json

from django.test import SimpleTestCase

from services.answer_script_service import (
    SYSTEM_PROMPT,
    _FORMAT_RULES,
    _answer_format,
    _classify_question_type,
    _extract_questions_from_content,
)
from services.question_types import SHAPES, all_types

#: The labels the original format rules were written against.
_FIRST_FORMATS = {"MCQ", "ASSERTION_REASON", "SHORT_ANSWER", "LONG_ANSWER", "CBQ", "MAP"}


class AnswerFormatTests(SimpleTestCase):
    def test_the_labels_the_rules_were_written_for_read_as_before(self):
        cases = {
            "MCQ": "MCQ",
            "MULTIPLE_CHOICE": "MCQ",
            "AR": "ASSERTION_REASON",
            "ASSERTION_REASON": "ASSERTION_REASON",
            "SHORT_ANSWER": "SHORT_ANSWER",
            "SHORT": "SHORT_ANSWER",
            "VSA": "SHORT_ANSWER",
            "LONG_ANSWER": "LONG_ANSWER",
            "LONG": "LONG_ANSWER",
            "CASE_STUDY": "CBQ",
            "CBQ": "CBQ",
            "CASE_BASED": "CBQ",
            "MAP": "MAP",
            "anything else": "SHORT_ANSWER",
            "": "SHORT_ANSWER",
        }
        for raw, label in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_answer_format(raw), label)
                self.assertEqual(_classify_question_type(raw), label)

    def test_the_catalogue_type_decides_the_format(self):
        cases = [
            ("MCQ", "MCQ_MULTI", "MCQ_MULTI"),
            ("MCQ", "MCQ_ODD_ONE_OUT", "MCQ"),
            ("TRUE_FALSE", "TRUE_FALSE", "TRUE_FALSE"),
            ("FILL_IN_THE_BLANK", "FILL_BLANK_BANK", "FILL_BLANK"),
            ("MATCH_THE_FOLLOWING", "MATCH_FOLLOWING", "MATCH"),
            ("CASE_STUDY", "DATA_INTERPRETATION", "CBQ"),
            ("READING_COMP", "PASSAGE_UNSEEN", "CBQ"),
            ("LETTER", "LETTER_WRITING", "WRITING"),
            ("NUMERICAL", "WORD_PROBLEM", "NUMERICAL"),
            ("GRAMMAR", "ERROR_CORRECTION", "GRAMMAR"),
            ("DIAGRAM", "MAP_SKILL", "MAP"),
            ("DIAGRAM", "DIAGRAM_DRAW", "DIAGRAM"),
        ]
        for shape, code, label in cases:
            with self.subTest(code=code):
                self.assertEqual(_answer_format(shape, code), label)

    def test_a_shape_alone_is_enough(self):
        self.assertEqual(_answer_format("TRUE_FALSE"), "TRUE_FALSE")
        self.assertEqual(_answer_format("LETTER"), "WRITING")

    def test_every_format_a_type_can_need_has_a_rule(self):
        # A label no rule mentions is a question answered with no format at all.
        needed = {_answer_format(spec.shape, spec.code) for spec in all_types()}
        needed |= {_answer_format(shape.code) for shape in SHAPES}
        for label in needed - _FIRST_FORMATS:
            with self.subTest(label=label):
                self.assertIn(label, _FORMAT_RULES)
                self.assertIn(_FORMAT_RULES[label], SYSTEM_PROMPT)

    def test_the_saved_marking_scheme_keeps_its_old_labels(self):
        # The document stores this as each block's questionType, and the editor
        # reads it back, so the catalogue must not change what is written there.
        self.assertEqual(_classify_question_type("LETTER"), "SHORT_ANSWER")
        self.assertEqual(_classify_question_type("TRUE_FALSE"), "SHORT_ANSWER")

    def test_extraction_carries_the_catalogue_type(self):
        def block(attrs):
            return {
                "type": "questionBlock",
                "attrs": attrs,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Which are metals?"}]}
                ],
            }

        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "page",
                    "attrs": {"pageId": "p1"},
                    "content": [
                        block({"marks": 2, "questionType": "MCQ", "typeCode": "MCQ_MULTI"}),
                        block({"marks": 2, "questionType": "MCQ"}),
                    ],
                }
            ],
        }
        questions = _extract_questions_from_content(json.dumps(doc))
        self.assertEqual([q["typeCode"] for q in questions], ["MCQ_MULTI", ""])
