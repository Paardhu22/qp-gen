"""The regex reader behind General Instructions Mode and building from the bank."""

from django.test import SimpleTestCase

from services.pool.gim import _parse_gim_instructions
from services.pool.pipeline import _GimSlot, _legacy_type_for
from services.question_types import get as get_type


def _read(instructions):
    return [
        (slot["section_title"], slot["type"], slot["marks"], slot["count"])
        for slot in _parse_gim_instructions(instructions, 1)
    ]


class GimParserTests(SimpleTestCase):
    def test_the_phrasing_it_always_read_reads_the_same(self):
        self.assertEqual(
            _read("Section A: 5 MCQs, Section B: 3 short answers of 2 marks"),
            [("Section A", "MCQ", 1, 5), ("Section B", "SHORT_ANSWER", 2, 3)],
        )

    def test_a_type_the_catalogue_names_is_no_longer_dropped(self):
        self.assertEqual(
            _read(
                "Section A: 5 MCQs\n"
                "5 fill in the blanks\n"
                "Section B: 2 odd one out questions of 1 mark\n"
                "1 letter writing of 5 marks"
            ),
            [
                ("Section A", "MCQ", 1, 5),
                ("Section A", "FILL_BLANK", get_type("FILL_BLANK").marks, 5),
                ("Section B", "MCQ_ODD_ONE_OUT", 1, 2),
                ("Section B", "LETTER_WRITING", 5, 1),
            ],
        )

    def test_a_type_that_cannot_be_generated_is_not_made_a_slot(self):
        for _section, code, _marks, _count in _read("3 picture based questions"):
            spec = get_type(code)
            self.assertTrue(spec is None or spec.is_available, code)

    def test_a_catalogue_type_becomes_a_slot_model_2_can_fill(self):
        slot = _GimSlot(
            index=1,
            marks=1,
            question_type="MCQ_ODD_ONE_OUT",
            legacy_type=_legacy_type_for("MCQ_ODD_ONE_OUT"),
            section_title="Section B",
        )
        self.assertEqual(slot.type_code, "MCQ_ODD_ONE_OUT")
        self.assertEqual(slot.legacy_type, "MCQ")
