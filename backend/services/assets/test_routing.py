"""The routing engine: which generator owns which slot.

Two things are guarded here. First, that English routes Reading, Grammar and
Writing away from the textbook. Second — and this is the one that would hurt
most if it broke — that every other subject still routes entirely to the
textbook pool, because "must not break other subjects" is a constraint on this
refactor, not an aspiration.
"""

from dataclasses import dataclass, field
from typing import Any, Dict

from django.test import TestCase

from services.assets.registry import (
    DEFAULT_GENERATOR,
    generator_for_slot,
    get_generator,
    partition_plan,
    registered_generators,
    routing_summary,
)
from services.generation_router import build_question_plan


@dataclass
class BareSlot:
    """A slot with no routing fields at all — a GIM slot, or a bank slot."""

    index: int
    marks: int
    question_type: str = "SHORT_ANSWER"
    legacy_type: str = "SHORT"
    section_title: str = "Questions"


@dataclass
class RoutedSlot(BareSlot):
    generator: str = DEFAULT_GENERATOR
    asset_type: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)


def _plan(subject, class_num=10):
    return list(
        build_question_plan(
            topic=subject,
            difficulty="medium",
            count=-1,
            class_num=class_num,
            subject=subject,
            count_variation="cbse",
        )
    )


class GeneratorResolutionTests(TestCase):
    def test_a_slot_with_no_generator_means_the_textbook_pool(self):
        self.assertEqual(generator_for_slot(BareSlot(index=1, marks=3)), DEFAULT_GENERATOR)

    def test_an_explicit_generator_is_honoured(self):
        slot = RoutedSlot(index=1, marks=10, generator="reading_asset_pool")
        self.assertEqual(generator_for_slot(slot), "reading_asset_pool")

    def test_an_unregistered_generator_falls_back_rather_than_losing_the_slot(self):
        slot = RoutedSlot(index=1, marks=10, generator="listening_asset_pool")
        with self.assertLogs("[ASSETS]", level="WARNING"):
            self.assertEqual(generator_for_slot(slot), DEFAULT_GENERATOR)

    def test_the_built_in_generators_are_registered(self):
        names = {g.name for g in registered_generators()}
        self.assertEqual(
            names,
            {"reading_asset_pool", "grammar_asset_pool", "writing_asset_pool"},
        )

    def test_the_textbook_pool_is_not_an_asset_generator(self):
        self.assertIsNone(get_generator(DEFAULT_GENERATOR))


class PartitionTests(TestCase):
    def test_default_group_is_always_present(self):
        self.assertEqual(partition_plan([]), {DEFAULT_GENERATOR: []})

    def test_slots_keep_their_order_within_a_group(self):
        plan = [
            RoutedSlot(index=1, marks=10, generator="reading_asset_pool"),
            RoutedSlot(index=2, marks=5),
            RoutedSlot(index=3, marks=10, generator="reading_asset_pool"),
        ]
        groups = partition_plan(plan)
        self.assertEqual([s.index for s in groups["reading_asset_pool"]], [1, 3])
        self.assertEqual([s.index for s in groups[DEFAULT_GENERATOR]], [2])


class EnglishRoutingTests(TestCase):
    def setUp(self):
        self.plan = _plan("English")

    def test_half_the_paper_leaves_the_textbook_pipeline(self):
        marks = {
            entry["generator"]: entry["marks"] for entry in routing_summary(self.plan)
        }
        self.assertEqual(marks[DEFAULT_GENERATOR], 40)
        self.assertEqual(marks["reading_asset_pool"], 20)
        self.assertEqual(marks["grammar_asset_pool"], 10)
        self.assertEqual(marks["writing_asset_pool"], 10)
        self.assertEqual(sum(marks.values()), 80)

    def test_only_literature_is_marked_as_using_the_upload(self):
        for entry in routing_summary(self.plan):
            expected = entry["generator"] == DEFAULT_GENERATOR
            self.assertEqual(entry["usesUploadedContent"], expected, entry["generator"])

    def test_every_reading_and_writing_slot_sits_outside_section_c(self):
        for slot in self.plan:
            if slot.generator == DEFAULT_GENERATOR:
                self.assertIn("Literature", slot.section_title, f"Q{slot.index}")
            else:
                self.assertNotIn("Literature", slot.section_title, f"Q{slot.index}")

    def test_reading_and_writing_declare_their_validation_rules(self):
        from services.assets.validation import available_rules

        known = set(available_rules())
        for slot in self.plan:
            if slot.generator == DEFAULT_GENERATOR:
                continue
            self.assertTrue(slot.validation, f"Q{slot.index} declares no validation")
            unknown = set(slot.validation) - known
            self.assertFalse(unknown, f"Q{slot.index} names unknown rules {unknown}")

class OtherSubjectsAreUntouchedTests(TestCase):
    """The refactor's hard constraint, asserted subject by subject."""

    def test_science_social_and_maths_route_entirely_to_the_textbook(self):
        for subject in ("Science", "Social Science", "Mathematics"):
            with self.subTest(subject=subject):
                plan = _plan(subject)
                groups = partition_plan(plan)
                self.assertEqual(
                    list(groups),
                    [DEFAULT_GENERATOR],
                    f"{subject} acquired an asset generator",
                )
                self.assertEqual(len(groups[DEFAULT_GENERATOR]), len(plan))

    def test_hindi_and_telugu_are_deliberately_not_migrated(self):
        # They are the obvious next candidates, but migrating them is a
        # separate change. Until then they must behave exactly as before.
        for subject in ("Hindi", "Telugu"):
            with self.subTest(subject=subject):
                plan = _plan(subject)
                self.assertEqual(list(partition_plan(plan)), [DEFAULT_GENERATOR])

    def test_lower_class_science_is_unaffected(self):
        for class_num in (5, 8):
            with self.subTest(class_num=class_num):
                plan = _plan("Science", class_num=class_num)
                self.assertEqual(list(partition_plan(plan)), [DEFAULT_GENERATOR])
