"""Internal-choice ("OR") support.

CBSE papers offer an internal choice on several slots, marked by
`choice_required` on the blueprint slot. The pool makes this cheap: a reserved
alternate is by construction the same question type and mark value as the main
question but on a different topic, which is exactly what an OR alternative
needs to be.
"""

from dataclasses import dataclass

from django.test import TestCase

from services.pool.model2 import build_candidates
from services.pool.rendering import (
    content_already_has_alternative,
    or_label_for,
    printable_content,
)
from services.pool.schema import PoolQuestion


@dataclass
class ChoiceSlot:
    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str = "Section B"
    choice_required: bool = False
    vi_required: bool = False
    subject: str = "Science"


def _question(qid, *, topic=None, marks=3, qtype="SHORT_ANSWER"):
    return PoolQuestion(
        id=qid, subject="Science", chapter="Electricity", topic=topic or qid,
        type=qtype, blooms="UNDERSTAND", difficulty="medium", marks=marks,
        question=f"Explain concept {qid}.", answer="a", explanation="because",
    )


class OrLabelTests(TestCase):
    def test_english_default(self):
        self.assertEqual(or_label_for("Science"), "OR")

    def test_hindi_and_telugu_use_their_own_separator(self):
        self.assertEqual(or_label_for("Hindi"), "अथवा")
        self.assertEqual(or_label_for("telugu"), "లేదా")


class PrintableContentTests(TestCase):
    def test_no_alternative_returns_the_stem_unchanged(self):
        self.assertEqual(printable_content("Explain Ohm's law."), "Explain Ohm's law.")

    def test_alternative_is_appended_under_the_label(self):
        result = printable_content(
            "Explain Ohm's law.",
            or_alternative="Explain Joule's law.",
            or_label="OR",
        )
        self.assertIn("Explain Ohm's law.", result)
        self.assertIn("OR", result)
        self.assertIn("Explain Joule's law.", result)
        self.assertLess(result.index("OR"), result.index("Explain Joule's law."))

    def test_inline_alternative_is_not_duplicated(self):
        # The stem already carries both halves — appending again is the
        # "every OR question prints twice" bug.
        content = "Explain Ohm's law.\n\nOR\n\nExplain Joule's law of heating."
        result = printable_content(
            content, or_alternative="Explain Joule's law of heating.", or_label="OR"
        )
        self.assertEqual(result.count("Explain Joule's law of heating."), 1)

    def test_hindi_label_is_used_when_asked(self):
        result = printable_content(
            "प्रश्न एक", or_alternative="प्रश्न दो", or_label="अथवा"
        )
        self.assertIn("अथवा", result)

    def test_vi_alternative_is_wrapped_in_its_notice(self):
        result = printable_content(
            "Observe the given figure.", vi_alternative="Describe a series circuit."
        )
        self.assertIn("Visually Impaired", result)
        self.assertIn("Describe a series circuit.", result)


class AlternativeDetectionTests(TestCase):
    def test_detects_a_match_despite_punctuation_and_case(self):
        self.assertTrue(
            content_already_has_alternative(
                "Q one.  OR  EXPLAIN   joules law, of heating!",
                "Explain Joule's law of heating",
            )
        )

    def test_does_not_false_positive_on_a_different_question(self):
        self.assertFalse(
            content_already_has_alternative(
                "Explain Ohm's law.", "Describe the structure of a nephron"
            )
        )

    def test_empty_alternative_is_never_a_match(self):
        self.assertFalse(content_already_has_alternative("anything", ""))


class ChoiceSlotAssignmentTests(TestCase):
    def test_choice_slot_gets_an_or_alternative(self):
        pool = [_question(f"q{i}") for i in range(6)]
        slots = [
            ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", choice_required=True),
        ]
        assignments, unfilled = build_candidates(pool, slots)

        self.assertEqual(unfilled, [])
        assignment = assignments[0]
        self.assertIsNotNone(assignment.or_choice)
        self.assertNotEqual(assignment.or_choice.id, assignment.question.id)

    def test_or_alternative_matches_type_and_marks(self):
        pool = [_question(f"q{i}") for i in range(6)]
        pool += [_question(f"long{i}", marks=5, qtype="LONG_ANSWER") for i in range(3)]
        slots = [ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", choice_required=True)]

        assignment = build_candidates(pool, slots)[0][0]

        self.assertEqual(assignment.or_choice.marks, 3)
        self.assertEqual(assignment.or_choice.type, "SHORT_ANSWER")

    def test_non_choice_slot_gets_no_or_alternative(self):
        pool = [_question(f"q{i}") for i in range(6)]
        slots = [ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", choice_required=False)]

        self.assertIsNone(build_candidates(pool, slots)[0][0].or_choice)

    def test_or_alternative_is_held_out_of_review_alternates(self):
        # Otherwise the review stage could swap the main question onto the OR
        # alternative and collapse the choice into a duplicate.
        pool = [_question(f"q{i}") for i in range(8)]
        slots = [ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", choice_required=True)]

        assignment = build_candidates(pool, slots, alternates=2)[0][0]

        alternate_ids = {a.id for a in assignment.alternates}
        self.assertNotIn(assignment.or_choice.id, alternate_ids)
        self.assertEqual(len(assignment.alternates), 2)

    def test_or_alternatives_are_not_shared_between_slots(self):
        pool = [_question(f"q{i}") for i in range(8)]
        slots = [
            ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", choice_required=True),
            ChoiceSlot(2, 3, "SHORT_ANSWER", "SHORT", choice_required=True),
        ]
        assignments, _ = build_candidates(pool, slots, alternates=0)

        used = []
        for assignment in assignments:
            used.append(assignment.question.id)
            used.append(assignment.or_choice.id)
        self.assertEqual(len(used), len(set(used)))

    def test_choice_slots_are_served_before_review_alternates(self):
        # Only 3 questions for 2 slots, one of which needs an OR. The OR must
        # win the scarce leftover — a missing OR is a structural defect, a
        # missing review alternate is not.
        pool = [_question(f"q{i}") for i in range(3)]
        slots = [
            ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", choice_required=False),
            ChoiceSlot(2, 3, "SHORT_ANSWER", "SHORT", choice_required=True),
        ]
        assignments, unfilled = build_candidates(pool, slots, alternates=2)

        self.assertEqual(unfilled, [])
        by_index = {a.slot.index: a for a in assignments}
        self.assertIsNotNone(
            by_index[2].or_choice, "The choice slot must get its alternative."
        )

    def test_vi_required_slot_prefers_a_question_carrying_vi_text(self):
        plain = _question("plain", topic="a")
        accessible = _question("accessible", topic="b")
        accessible.vi_alternative = "Describe a series circuit in words."

        slots = [ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", vi_required=True)]

        assignment = build_candidates([plain, accessible], slots, alternates=0)[0][0]

        self.assertEqual(
            assignment.question.id, "accessible",
            "A vi_required slot must take the question that has VI text.",
        )

    def test_thin_pool_leaves_or_choice_empty_rather_than_starving_a_slot(self):
        # Exactly two questions for two slots: both slots must still be filled,
        # even though nothing is left over for the OR.
        pool = [_question("a"), _question("b")]
        slots = [
            ChoiceSlot(1, 3, "SHORT_ANSWER", "SHORT", choice_required=True),
            ChoiceSlot(2, 3, "SHORT_ANSWER", "SHORT", choice_required=True),
        ]
        assignments, unfilled = build_candidates(pool, slots)

        self.assertEqual(len(assignments), 2)
        self.assertEqual(unfilled, [])
