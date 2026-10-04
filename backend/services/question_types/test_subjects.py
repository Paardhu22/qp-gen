"""The subject map is data. These tests keep it honest against the catalogue."""

from __future__ import annotations

from django.test import SimpleTestCase

from services import question_types as qt
from services.question_types.subjects import (
    CORE,
    OCCASIONAL,
    SUBJECT_TYPES,
    WEIGHTS,
    subject_types,
)
from services.starter_templates import STARTERS

_LISTED = {"available", "needs_picture"}


class SubjectMapIntegrityTests(SimpleTestCase):
    def test_every_graded_type_is_a_listed_catalogue_type(self):
        for subject, graded in SUBJECT_TYPES.items():
            for code, weight in graded.items():
                with self.subTest(subject=subject, code=code):
                    spec = qt.get(code)
                    self.assertIsNotNone(spec, "not in the catalogue")
                    self.assertEqual(spec.code, code, "an alias, not a code")
                    self.assertIn(spec.resolved_availability, _LISTED)
                    self.assertIn(weight, WEIGHTS)

    def test_a_subject_never_lists_a_type_reserved_for_others(self):
        # `TypeSpec.subjects` is the ceiling: the map selects and grades
        # within it, never past it.
        for subject, graded in SUBJECT_TYPES.items():
            for code in graded:
                spec = qt.get(code)
                if spec.subjects:
                    with self.subTest(subject=subject, code=code):
                        self.assertIn(subject, spec.subjects)

    def test_every_starter_uses_only_its_subjects_types(self):
        # A starter whose slot the picker does not offer would show a type the
        # teacher cannot pick again once they change it.
        for starter in STARTERS:
            graded = subject_types(starter.subject_key)
            self.assertIsNotNone(graded, starter.subject_key)
            for section in starter.sections:
                for code, _marks, _count in section.slots:
                    with self.subTest(starter=starter.id, code=code):
                        self.assertIn(code, graded)

    def test_every_subject_has_something_core_to_open_on_in_every_class(self):
        for subject, graded in SUBJECT_TYPES.items():
            for class_num in range(1, 11):
                with self.subTest(subject=subject, class_num=class_num):
                    opening = [
                        code
                        for code, weight in graded.items()
                        if weight == CORE
                        and qt.get(code).is_available
                        and qt.get(code).classes[0] <= class_num <= qt.get(code).classes[1]
                    ]
                    self.assertTrue(opening)


class SubjectMapContentTests(SimpleTestCase):
    """The corrections the research found in the old, subject-blind menu."""

    def test_science_no_longer_offers_code_maps_or_antonyms(self):
        science = subject_types("science")
        for code in (
            "CODE_OUTPUT", "CODE_DEBUG", "CODE_WRITE", "ALGORITHM_DESIGN",
            "FLOWCHART_DRAW", "OPPOSITE_WRITE", "MCQ_MAP", "MAP_SKILL", "TRACE_PATTERN",
        ):
            self.assertNotIn(code, science)

    def test_code_types_belong_to_computer_science(self):
        computer = subject_types("Computer Science")
        for code in ("CODE_OUTPUT", "CODE_WRITE", "ALGORITHM_DESIGN", "FLOWCHART_DRAW"):
            self.assertEqual(computer[code], CORE)
        self.assertNotIn("EXPERIMENT_BASED", computer)
        self.assertNotIn("UNIT_SYMBOL", computer)

    def test_ict_sets_application_skills_and_less_code(self):
        ict = subject_types("ICT")
        for code in (
            "SHORTCUT_KEY", "SOFTWARE_STEPS", "SPREADSHEET_FORMULA",
            "TOOL_IDENTIFY", "FULL_FORM", "SAFETY_PROCEDURE",
        ):
            self.assertEqual(ict[code], CORE)
        self.assertEqual(ict["CODE_WRITE"], OCCASIONAL)
        self.assertEqual(subject_types("computer science")["CODE_WRITE"], CORE)
        for code in ("EXPERIMENT_BASED", "MAP_SKILL", "SYNONYM_ANTONYM", "WORD_PROBLEM"):
            self.assertNotIn(code, ict)

    def test_maps_belong_to_social_science(self):
        social = subject_types("social science")
        self.assertEqual(social["MAP_SKILL"], CORE)
        self.assertEqual(social["MCQ_CHRONOLOGY"], CORE)

    def test_maths_is_not_offered_language_or_lab_types(self):
        maths = subject_types("mathematics")
        for code in ("SYNONYM_ANTONYM", "PASSAGE_UNSEEN", "EXPERIMENT_BASED", "DIAGRAM_LABEL"):
            self.assertNotIn(code, maths)
        self.assertEqual(maths["WORD_PROBLEM"], CORE)

    def test_hindi_and_telugu_set_translation_more_than_english(self):
        self.assertEqual(subject_types("hindi")["TRANSLATION"], CORE)
        self.assertEqual(subject_types("telugu")["TRANSLATION"], CORE)
        self.assertNotEqual(subject_types("english")["TRANSLATION"], CORE)

    def test_display_names_resolve(self):
        self.assertIs(subject_types("EVS"), SUBJECT_TYPES["science"])
        self.assertIs(subject_types("sanskrit"), SUBJECT_TYPES["hindi"])
        self.assertIs(
            subject_types("Information and Communication Technology"), SUBJECT_TYPES["ict"]
        )
        self.assertIs(subject_types("information technology"), SUBJECT_TYPES["ict"])
        self.assertIsNone(subject_types("general knowledge"))
        self.assertIsNone(subject_types(""))
