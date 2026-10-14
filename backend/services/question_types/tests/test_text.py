"""Finding a question type in a teacher's own words."""

from django.test import SimpleTestCase

from services.question_types import find_type_in_text, get


class FindTypeInTextTests(SimpleTestCase):
    def test_a_named_type_is_found_inside_a_sentence(self):
        self.assertEqual(
            find_type_in_text("Section B: 2 odd one out questions").code,
            "MCQ_ODD_ONE_OUT",
        )
        self.assertEqual(find_type_in_text("write a letter").code, "LETTER_WRITING")

    def test_the_longest_phrase_wins(self):
        # "very short answers" also contains "short answer".
        self.assertEqual(find_type_in_text("3 very short answers").code, "VSA")

    def test_a_retired_shape_still_carries_its_attribute(self):
        found = find_type_in_text("5 HOTS questions")
        self.assertEqual(found.code, "SA")
        self.assertIn("hots", found.attributes)

    def test_a_type_that_cannot_be_generated_is_never_found(self):
        for text in ("3 picture based questions", "2 map work questions"):
            found = find_type_in_text(text)
            with self.subTest(text=text):
                self.assertTrue(found is None or get(found.code).is_available)

    def test_short_codes_and_meta_clauses_are_not_types(self):
        self.assertIsNone(find_type_in_text("2 sa and 1 la"))
        self.assertIsNone(find_type_in_text("I have uploaded 2 PDFs"))
        self.assertIsNone(find_type_in_text(""))
        self.assertIsNone(find_type_in_text(None))


class LabelResolutionTests(SimpleTestCase):
    """A type named by its display label, the way a writer echoes it back."""

    def test_a_label_resolves_to_its_type(self):
        from services.question_types import resolve, shape_of

        self.assertEqual(resolve("MCQ — Fill Up").code, "MCQ_FILL")
        self.assertEqual(resolve("mcq - fill up").code, "MCQ_FILL")
        self.assertEqual(shape_of("MCQ — Analogy"), "MCQ")

    def test_codes_and_aliases_still_win_over_labels(self):
        from services.question_types import resolve

        self.assertEqual(resolve("Short Answer").code, "SA")
        self.assertEqual(resolve("MCQ").code, "MCQ_SINGLE")

    def test_an_unknown_label_resolves_to_nothing(self):
        from services.question_types import resolve

        self.assertIsNone(resolve("MCQ — Interpretive Dance"))
