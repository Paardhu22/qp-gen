"""Options arrive in several shapes; the paper must only ever see their text."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.assets.schema import GrammarAsset, SubQuestion
from services.pool.options import normalize_options


class NormalizeOptionsTests(SimpleTestCase):
    def test_plain_strings_pass_through(self):
        self.assertEqual(
            normalize_options(["many", "much", "few", "several"]),
            ["many", "much", "few", "several"],
        )

    def test_one_label_object_each(self):
        # The shape that printed as "A. {'A': 'headphones / headphone'}".
        self.assertEqual(
            normalize_options([{"A": "headphones / headphone"}, {"B": "is / are"}]),
            ["headphones / headphone", "is / are"],
        )

    def test_label_and_text_objects(self):
        self.assertEqual(
            normalize_options([{"label": "A", "text": "x"}, {"label": "B", "text": "y"}]),
            ["x", "y"],
        )

    def test_a_label_mapping_is_ordered_by_label(self):
        self.assertEqual(normalize_options({"B": "much", "A": "many"}), ["many", "much"])

    def test_options_banked_as_stringified_objects_are_repaired(self):
        self.assertEqual(
            normalize_options(["{'A': 'headphones / headphone'}", "{'B': 'is / are'}"]),
            ["headphones / headphone", "is / are"],
        )

    def test_a_label_written_into_the_text_is_dropped(self):
        # The renderer prints its own label; "A. A. many" is the alternative.
        self.assertEqual(
            normalize_options(["A. many", "B. much", "c) few", "(d) several"]),
            ["many", "much", "few", "several"],
        )

    def test_a_short_option_that_is_only_a_letter_is_kept(self):
        self.assertEqual(normalize_options(["a", "an", "the", "some"]), ["a", "an", "the", "some"])

    def test_a_label_out_of_position_is_kept(self):
        # "B. …" as the first option is content, not this option's own label.
        self.assertEqual(normalize_options(["B. much"]), ["B. much"])

    def test_blank_entries_are_dropped(self):
        self.assertEqual(normalize_options(["x", "  ", None, "y"]), ["x", "y"])


class AssetOptionParsingTests(SimpleTestCase):
    def test_a_grammar_task_with_object_options_prints_their_text(self):
        asset = GrammarAsset.from_raw(
            {
                "grammar_topic": "error correction",
                "question": 'Find the error in "This headphones is very comfortable."',
                "answer": "B",
                "options": [{"A": "headphones / headphone"}, {"B": "is / are"}],
            }
        )
        rendered = asset.render(0)
        self.assertIn("A. headphones / headphone", rendered)
        self.assertNotIn("{", rendered)

    def test_a_sub_question_with_object_options_prints_their_text(self):
        part = SubQuestion.from_raw(
            {"question": "Pick one.", "answer": "A", "options": {"A": "yes", "B": "no"}}
        )
        self.assertEqual(part.options, ["yes", "no"])
