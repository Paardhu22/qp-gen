"""
Tests for the four new CBSE Class 10 subject plugins:
Mathematics Standard (041), English (184), Hindi Course B (085), Telugu Telangana (089).

Run with:  python -m unittest q_instructions.tests.test_new_subjects -v
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def _load_router():
    """Load generation_router via exec, stubbing out Django."""
    router_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'services', 'generation_router.py'
    )
    src = open(router_path, encoding="utf-8").read()
    src = src.replace('from django.conf import settings', '')
    globs = {'__builtins__': __builtins__, 'logging': __import__('logging')}
    exec(compile(src, router_path, 'exec'), globs)
    return globs


_router = _load_router()


class TestBlueprintMarksAndCount(unittest.TestCase):

    def _check(self, func_name, expected_q, expected_marks):
        entries = _router[func_name]()
        total_marks = sum(e["marks"] * e.get("count", 1) for e in entries)
        total_qs = sum(e.get("count", 1) for e in entries)
        self.assertEqual(total_marks, expected_marks,
                         f"{func_name}: expected {expected_marks} marks, got {total_marks}")
        self.assertEqual(total_qs, expected_q,
                         f"{func_name}: expected {expected_q} questions, got {total_qs}")

    def test_mathematics(self):
        self._check("_exact_class10_blueprint_entries_mathematics", 38, 80)

    def test_english(self):
        self._check("_exact_class10_blueprint_entries_english", 11, 80)

    def test_hindi(self):
        self._check("_exact_class10_blueprint_entries_hindi", 16, 80)

    def test_telugu(self):
        self._check("_exact_class10_blueprint_entries_telugu", 18, 80)


class TestEligibility(unittest.TestCase):

    def test_new_subjects_eligible_class10(self):
        for subj in ("mathematics", "english", "hindi", "telugu"):
            self.assertTrue(_router["is_eligible_for_new_engine"](subj, 10),
                            f"{subj} should be eligible at class 10")

    def test_new_subjects_ineligible_class9(self):
        for subj in ("mathematics", "english", "hindi", "telugu"):
            self.assertFalse(_router["is_eligible_for_new_engine"](subj, 9),
                             f"{subj} should NOT be eligible at class 9")


class TestSubjectAliases(unittest.TestCase):

    def test_aliases(self):
        cases = [
            ("maths",                          "mathematics"),
            ("math",                           "mathematics"),
            ("Mathematics Standard",           "mathematics"),
            ("Hindi B",                        "hindi"),
            ("Hindi Course B",                 "hindi"),
            ("English Language",               "english"),
            ("English Language and Literature","english"),
            ("Telugu Telangana",               "telugu"),
            ("sst",                            "social science"),
        ]
        for alias, expected in cases:
            with self.subTest(alias=alias):
                self.assertEqual(_router["normalize_subject"](alias), expected)


class TestMathematicsBlueprint(unittest.TestCase):

    def setUp(self):
        self.entries = _router["_exact_class10_blueprint_entries_mathematics"]()

    def test_mcq_count(self):
        mcq = [e for e in self.entries if e["qtype"] == "MCQ"]
        self.assertEqual(sum(e.get("count", 1) for e in mcq), 18)

    def test_assertion_reason_count(self):
        ar = [e for e in self.entries if e["qtype"] == "ASSERTION_REASON"]
        self.assertEqual(sum(e.get("count", 1) for e in ar), 2)

    def test_section_e_choice_required(self):
        sec_e = [e for e in self.entries if "Section E" in e.get("section", "")]
        self.assertEqual(len(sec_e), 3)
        for e in sec_e:
            self.assertTrue(e.get("choice_required"),
                            "Section E entries must have choice_required=True")

    def test_section_marks(self):
        totals = {}
        for e in self.entries:
            sec = e["section"]
            totals[sec] = totals.get(sec, 0) + e["marks"] * e.get("count", 1)
        self.assertEqual(totals["Section A - Objective Questions"], 20)
        self.assertEqual(totals["Section B - Very Short Answer"], 10)
        self.assertEqual(totals["Section C - Short Answer"], 18)
        self.assertEqual(totals["Section D - Long Answer"], 20)
        self.assertEqual(totals["Section E - Case Based Questions"], 12)


class TestEnglishBlueprint(unittest.TestCase):

    def setUp(self):
        self.entries = _router["_exact_class10_blueprint_entries_english"]()

    def test_question_count(self):
        self.assertEqual(sum(e.get("count", 1) for e in self.entries), 11)

    def test_reading_comp_entries(self):
        rc = [e for e in self.entries if e["qtype"] == "READING_COMP"]
        self.assertEqual(len(rc), 2)
        for e in rc:
            self.assertEqual(e["marks"], 10)

    def test_q8_spans_sources(self):
        # Q8 is one 12-mark bundle of five 3-mark questions, of which the
        # student answers four, each from a different part of the source
        # material. The requirement is expressed structurally rather than by
        # naming NCERT titles: the pool is built from whatever chapters the
        # teacher uploaded, so naming books the upload may not contain invited
        # the model to write from memory instead of from the source.
        q8 = [e for e in self.entries if e.get("hint", "").startswith("Q8")]
        self.assertEqual(len(q8), 1)
        entry = q8[0]
        self.assertEqual(entry["marks"], 12)
        self.assertEqual(entry["constraints"], {"questions": 5, "attempt": 4, "marks_each": 3})
        self.assertIn("DIFFERENT chapter", entry["hint"])

    def test_only_literature_uses_the_uploaded_textbook(self):
        """The whole point of the split: Sections A and B declare their own
        generators, so 40 of the 80 marks never touch an upload."""
        by_generator = {}
        for entry in self.entries:
            key = entry.get("generator", "question_pool")
            by_generator[key] = by_generator.get(key, 0) + entry["marks"] * entry.get("count", 1)

        self.assertEqual(by_generator["question_pool"], 40)
        self.assertEqual(by_generator["reading_asset_pool"], 20)
        self.assertEqual(by_generator["grammar_asset_pool"], 10)
        self.assertEqual(by_generator["writing_asset_pool"], 10)

    def test_asset_slots_declare_a_full_routing_contract(self):
        for entry in self.entries:
            if entry.get("generator", "question_pool") == "question_pool":
                continue
            label = entry["hint"][:40]
            self.assertTrue(entry.get("asset_type"), label)
            self.assertTrue(entry.get("constraints"), label)
            self.assertTrue(entry.get("validation"), label)


class TestHindiBlueprint(unittest.TestCase):

    def setUp(self):
        self.entries = _router["_exact_class10_blueprint_entries_hindi"]()

    def test_question_count(self):
        self.assertEqual(sum(e.get("count", 1) for e in self.entries), 16)

    def test_devanagari_in_hints(self):
        hints = " ".join(e.get("hint", "") for e in self.entries)
        has_devanagari = any('ऀ' <= ch <= 'ॿ' for ch in hints)
        self.assertTrue(has_devanagari, "Hindi hints should contain Devanagari Unicode")

    def test_apathit_entries(self):
        # "अपठित" appears in the section name, not necessarily in the hint
        apathit = [
            e for e in self.entries
            if "अपठित" in e.get("section", "") or "अपठित" in e.get("hint", "")
        ]
        self.assertGreaterEqual(len(apathit), 2)


class TestTeluguBlueprint(unittest.TestCase):

    def setUp(self):
        self.entries = _router["_exact_class10_blueprint_entries_telugu"]()

    def test_question_count(self):
        self.assertEqual(sum(e.get("count", 1) for e in self.entries), 18)

    def test_telugu_unicode_in_hints(self):
        hints = " ".join(e.get("hint", "") for e in self.entries)
        has_telugu = any('ఀ' <= ch <= '౿' for ch in hints)
        self.assertTrue(has_telugu, "Telugu hints should contain Telugu Unicode")

    def test_q1_is_reading_comp_10m(self):
        first = self.entries[0]
        # Telugu Q1 is a reading comprehension passage (READING_COMP) worth 10 marks
        self.assertIn(first["qtype"], ("CASE_STUDY", "READING_COMP"))
        self.assertEqual(first["marks"], 10)


class TestDefaultQuestionCounts(unittest.TestCase):

    def test_counts(self):
        cases = [
            ("Mathematics", 38),
            ("English",     11),
            ("Hindi",       16),
            ("Telugu",      18),
            ("Science",     39),
            ("Social Science", 38),
        ]
        for subject, expected in cases:
            with self.subTest(subject=subject):
                self.assertEqual(
                    _router["default_cbse_question_count"](subject, 10),
                    expected,
                )


class TestLegacyTypeMapping(unittest.TestCase):

    def test_mapping(self):
        cases = [
            ("READING_COMP",     "CASE_STUDY"),
            ("GRAMMAR",          "SHORT"),
            ("LETTER",           "LONG"),
            ("MCQ",              "MCQ"),
            ("ASSERTION_REASON", "ASSERTION_REASON"),
            ("LONG_ANSWER",      "LONG"),
            ("SHORT_ANSWER",     "SHORT"),
        ]
        for qtype, expected in cases:
            with self.subTest(qtype=qtype):
                self.assertEqual(_router["_legacy_question_type"](qtype), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
