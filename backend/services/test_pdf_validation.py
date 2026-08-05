"""Tests for cross-validating uploaded chapters against the paper.

The gap these pin: every consistency rule in `validate_pdf_metadata_list`
compares the uploads to *each other*, so one Physics chapter attached to a
Mathematics paper is perfectly self-consistent and passes. Only
`expected_subject` catches it.
"""

from django.test import SimpleTestCase

from services.pdf_validation_service import validate_pdf_metadata_list


def _doc(name="ch1.pdf", subject="Mathematics", **over):
    base = {
        "fileName": name,
        "subject": subject,
        "board": "CBSE",
        "class": "10",
        "chapter": "Real Numbers",
        "documentType": "textbook",
        "confidence": 0.97,
        "isEducational": True,
    }
    base.update(over)
    return base


class ExpectedSubjectTests(SimpleTestCase):
    def test_single_off_subject_file_is_caught(self):
        """The regression: self-consistent, high-confidence, educational —
        and still the wrong subject for this paper."""
        report = validate_pdf_metadata_list(
            [_doc(subject="Physics")], expected_subject="Mathematics"
        )

        self.assertFalse(report["valid"])
        self.assertEqual(report["errorType"], "SUBJECT_MISMATCH")
        self.assertEqual(report["expectedSubject"], "Mathematics")
        self.assertIn("Physics", report["message"])

    def test_matching_subject_passes(self):
        report = validate_pdf_metadata_list(
            [_doc(subject="Mathematics")], expected_subject="Mathematics"
        )
        self.assertTrue(report["valid"])

    def test_subject_comparison_ignores_case_and_padding(self):
        """The detector's vocabulary and the template catalog's labels are
        written by different code; a casing difference is not a mismatch."""
        report = validate_pdf_metadata_list(
            [_doc(subject="social science")], expected_subject="  Social Science "
        )
        self.assertTrue(report["valid"])

    def test_no_expected_subject_keeps_the_old_cross_file_behaviour(self):
        """Callers that do not know the paper's subject must not start
        failing — they get the same consistency-only check as before."""
        report = validate_pdf_metadata_list([_doc(subject="Physics")])
        self.assertTrue(report["valid"])

    def test_cross_file_mismatch_still_wins(self):
        report = validate_pdf_metadata_list(
            [_doc("a.pdf", subject="Physics"), _doc("b.pdf", subject="Biology")],
            expected_subject="Physics",
        )
        self.assertFalse(report["valid"])
        self.assertEqual(report["errorType"], "SUBJECT_MISMATCH")


class ExpectedClassTests(SimpleTestCase):
    def test_class_disagreement_warns_but_does_not_fail(self):
        """Grade is inferred far less reliably than subject — many chapters
        never state it — so it is worth mentioning and not worth blocking."""
        report = validate_pdf_metadata_list(
            [_doc(**{"class": "9"})],
            expected_subject="Mathematics",
            expected_class="10",
        )

        self.assertTrue(report["valid"])
        self.assertEqual(len(report["warnings"]), 1)
        self.assertIn("Class 9", report["warnings"][0])

    def test_matching_class_produces_no_warning(self):
        report = validate_pdf_metadata_list(
            [_doc(**{"class": "10"})],
            expected_subject="Mathematics",
            expected_class="10",
        )
        self.assertEqual(report["warnings"], [])
