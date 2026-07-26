"""
Tests for the CBSE Class-10 language engine (English 184, Hindi 085, Telugu 089):
generation modes, RAG routing, per-subject grammar/composition builders, and the
hard validation gates.

These import the router + validators directly (no Django settings access at import
time), mirroring test_new_subjects.

Run with:  python -m unittest q_instructions.tests.test_language_logic -v
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.generation_router import (  # noqa: E402
    build_question_plan,
    build_retrieval_query,
    default_cbse_question_count,
    _GRAMMAR_TASK_PLAN,
    TELUGU_METRE_GANA,
)
from services import language_validation as lv  # noqa: E402


def _plan(subject):
    return build_question_plan("", "medium", -1, class_num=10, subject=subject)


def _slots_by_mode(plan, mode):
    return [s for s in plan if s.generation_mode == mode]


def _section_marks(plan):
    out = {}
    for s in plan:
        out[s.section_title] = out.get(s.section_title, 0) + s.marks
    return out


def _fake_slot(subject, mode, hint=""):
    return types.SimpleNamespace(subject=subject, generation_mode=mode, instruction_hint=hint)


# ---------------------------------------------------------------------------
# Marks / count integrity
# ---------------------------------------------------------------------------
class TestMarksAndCounts(unittest.TestCase):

    def test_all_subjects_sum_to_80(self):
        for subject in ("English", "Hindi", "Telugu", "Mathematics", "Science", "Social Science"):
            with self.subTest(subject=subject):
                self.assertEqual(sum(s.marks for s in _plan(subject)), 80)

    def test_question_counts(self):
        cases = {"English": 11, "Hindi": 16, "Telugu": 18, "Mathematics": 38, "Science": 39}
        for subject, expected in cases.items():
            with self.subTest(subject=subject):
                self.assertEqual(len(_plan(subject)), expected)

    def test_science_expected_count_matches_blueprint(self):
        # Regression guard for the documented "Science off-by-one" concern.
        science = _plan("Science")
        self.assertEqual(len(science), default_cbse_question_count("Science", 10))
        self.assertEqual(len(science), 39)
        self.assertEqual(sum(s.marks for s in science), 80)

    def test_english_section_marks(self):
        # Section titles follow the official paper's own headings.
        marks = _section_marks(_plan("English"))
        self.assertEqual(marks["Section A - Reading Skills"], 20)
        self.assertEqual(marks["Section B - Grammar and Writing Skills"], 20)
        self.assertEqual(marks["Section C - Literature Textbook"], 40)

    def test_hindi_section_marks(self):
        marks = _section_marks(_plan("Hindi"))
        self.assertEqual(marks["खण्ड क - अपठित बोध"], 14)
        self.assertEqual(marks["खण्ड ख - व्यावहारिक व्याकरण"], 16)
        self.assertEqual(marks["खण्ड ग - पाठ्यपुस्तक"], 28)
        self.assertEqual(marks["खण्ड घ - रचनात्मक लेखन"], 22)

    def test_telugu_section_marks(self):
        marks = _section_marks(_plan("Telugu"))
        self.assertEqual(marks["విభాగం ఎ"], 10)
        self.assertEqual(marks["విభాగం బి"], 11)
        self.assertEqual(marks["విభాగం సి"], 29)
        self.assertEqual(marks["విభాగం డి"], 30)


# ---------------------------------------------------------------------------
# RAG routing — the core bug
# ---------------------------------------------------------------------------
class TestRetrievalRouting(unittest.TestCase):

    def test_non_content_slots_have_empty_query(self):
        for subject in ("English", "Hindi", "Telugu"):
            for slot in _plan(subject):
                with self.subTest(subject=subject, idx=slot.index, mode=slot.generation_mode):
                    if slot.generation_mode in ("GRAMMAR", "COMPOSITION", "PASSAGE"):
                        self.assertEqual(slot.retrieval_query, "",
                                         f"{subject} slot {slot.index} ({slot.generation_mode}) must not retrieve")
                    else:
                        self.assertEqual(slot.generation_mode, "CONTENT")
                        self.assertTrue(slot.retrieval_query.strip(),
                                        f"{subject} CONTENT slot {slot.index} must have a query")

    def test_content_slots_retrieve(self):
        for slot in _plan("Science"):  # every Science slot is CONTENT
            self.assertEqual(slot.generation_mode, "CONTENT")
            self.assertTrue(slot.retrieval_query.strip())

    def test_build_retrieval_query_modes(self):
        common = dict(topic="t", subject="english", stream="X", qtype_name="GRAMMAR",
                      marks=10, difficulty="medium", class_num=10)
        for mode in ("GRAMMAR", "COMPOSITION", "PASSAGE"):
            self.assertEqual(build_retrieval_query(mode=mode, **common), "")
        self.assertTrue(build_retrieval_query(mode="CONTENT", **common).strip())

    def test_no_content_block_for_non_content(self):
        # Every non-CONTENT instruction must NOT instruct the model to use retrieved chunks.
        for subject in ("English", "Hindi", "Telugu"):
            for slot in _plan(subject):
                if slot.generation_mode != "CONTENT":
                    self.assertNotIn("retrieved textbook chunks", slot.exact_instruction)


# ---------------------------------------------------------------------------
# Grammar builders (per subject)
# ---------------------------------------------------------------------------
class TestGrammarBuilders(unittest.TestCase):

    def _english_q3(self):
        g = _slots_by_mode(_plan("English"), "GRAMMAR")
        self.assertEqual(len(g), 1)
        return g[0]

    def test_english_grammar_12_tasks_any_10(self):
        instr = self._english_q3().exact_instruction
        plan = _GRAMMAR_TASK_PLAN["english"]
        self.assertIn(str(plan["tasks"]), instr)          # 12
        self.assertIn(f"any {plan['attempt']}", instr)     # any 10 — derived from the plan constant
        self.assertEqual((plan["tasks"], plan["attempt"]), (12, 10))

    def test_english_grammar_reported_speech_3_error_correction_2(self):
        instr = self._english_q3().exact_instruction
        self.assertIn("EXACTLY 3 times", instr)            # reported speech ×3
        self.assertIn("EXACTLY twice", instr)              # error correction ×2

    def test_hindi_grammar_5_tasks_any_4_devanagari(self):
        g = _slots_by_mode(_plan("Hindi"), "GRAMMAR")
        self.assertEqual(len(g), 4)  # Q3–Q6
        plan = _GRAMMAR_TASK_PLAN["hindi"]
        self.assertEqual((plan["tasks"], plan["attempt"]), (5, 4))
        for slot in g:
            self.assertIn(str(plan["tasks"]), slot.exact_instruction)
            self.assertIn(str(plan["attempt"]), slot.exact_instruction)
            self.assertTrue(any('ऀ' <= ch <= 'ॿ' for ch in slot.exact_instruction))

    def test_telugu_grammar_clusters(self):
        plan = _plan("Telugu")
        grammar = _slots_by_mode(plan, "GRAMMAR")
        # Q4–Q11 are all grammar/vocab MCQ clusters.
        self.assertEqual(len(grammar), 8)
        for slot in grammar:
            self.assertIn("Telugu Unicode", slot.exact_instruction)

    def test_telugu_chandas_includes_gana_table(self):
        chandas = [s for s in _plan("Telugu")
                   if s.generation_mode == "GRAMMAR" and "ఛందస" in (s.instruction_hint or "")]
        self.assertEqual(len(chandas), 1)
        instr = chandas[0].exact_instruction
        for metre, gana in TELUGU_METRE_GANA.items():
            self.assertIn(metre, instr)
            self.assertIn(gana, instr)


# ---------------------------------------------------------------------------
# Composition builders
# ---------------------------------------------------------------------------
class TestCompositionBuilders(unittest.TestCase):

    def test_hindi_anuched_demands_exactly_3_hints(self):
        comp = [s for s in _plan("Hindi")
                if s.generation_mode == "COMPOSITION" and "अनुच्छेद" in (s.instruction_hint or "")]
        self.assertEqual(len(comp), 1)
        self.assertIn("EXACTLY 3 संकेत-बिन्दु", comp[0].exact_instruction)

    def test_english_analytical_is_stimulus_based(self):
        # Selected on the slot's declared asset type, not on wording in the
        # hint — that is what the prompt builder now keys off too.
        comp = [s for s in _plan("English") if s.asset_type == "analytical_paragraph"]
        self.assertEqual(len(comp), 1)
        self.assertEqual(comp[0].generation_mode, "COMPOSITION")
        self.assertIn("STIMULUS-BASED", comp[0].exact_instruction)

    def test_composition_carries_cardinal_rule(self):
        for subject in ("English", "Hindi", "Telugu"):
            for slot in _slots_by_mode(_plan(subject), "COMPOSITION"):
                self.assertIn("never write the student's answer", slot.exact_instruction.lower())


# ---------------------------------------------------------------------------
# Hard validation gates
# ---------------------------------------------------------------------------
class TestValidation(unittest.TestCase):

    def test_script_guard_rejects_roman_telugu(self):
        slot = _fake_slot("Telugu", "GRAMMAR", hint="సంధి")
        bad = {"content": "Identify the correct sandhi for the given example.", "answer": "Option A"}
        ok, _ = lv.validate_language_question(slot, bad)
        self.assertFalse(ok)

    def test_script_guard_accepts_telugu(self):
        slot = _fake_slot("Telugu", "GRAMMAR", hint="సంధి")
        good = {"content": "కింది వాటిలో సరైన సంధిని గుర్తించండి. (అ) ... (ఆ) ... (ఇ) ... (ఈ) ...",
                "answer": "(అ) సరైనది."}
        ok, reason = lv.validate_language_question(slot, good)
        self.assertTrue(ok, reason)

    def test_hindi_anuched_rejects_topic_with_2_hints(self):
        slot = _fake_slot("Hindi", "COMPOSITION", hint="Q12 अनुच्छेद लेखन")
        content = (
            "किसी एक विषय पर लगभग 120 शब्द में अनुच्छेद लिखिए।\n"
            "1. डिजिटल भारत — संकेत-बिन्दु: परिभाषा, महत्त्व, भूमिका\n"
            "2. पर्यावरण प्रदूषण — संकेत-बिन्दु: अर्थ, आवश्यकता, प्रभाव\n"
            "3. युवा और खेल — संकेत-बिन्दु: परिचय, लाभ\n"
        )
        ok, reason = lv.validate_language_question(slot, {"content": content, "answer": ""})
        self.assertFalse(ok)
        self.assertIn("3", reason)

    def test_hindi_anuched_accepts_3_hints_each(self):
        slot = _fake_slot("Hindi", "COMPOSITION", hint="Q12 अनुच्छेद लेखन")
        content = (
            "किसी एक विषय पर लगभग 120 शब्द में अनुच्छेद लिखिए।\n"
            "1. डिजिटल भारत — संकेत-बिन्दु: परिभाषा, महत्त्व, भूमिका\n"
            "2. पर्यावरण प्रदूषण — संकेत-बिन्दु: अर्थ, आवश्यकता, प्रभाव\n"
            "3. युवा और खेल — संकेत-बिन्दु: परिचय, लाभ, प्रभाव\n"
        )
        ok, reason = lv.validate_language_question(slot, {"content": content, "answer": ""})
        self.assertTrue(ok, reason)

    def test_english_analytical_rejects_single_option(self):
        slot = _fake_slot("English", "COMPOSITION", hint="Q5 Analytical Paragraph")
        content = "Analyse the following stimulus in 120-150 words and justify. (A) A ten-year veteran who is relevant and engaging."
        ok, _ = lv.validate_language_question(slot, {"content": content, "answer": ""})
        self.assertFalse(ok)

    def test_english_analytical_accepts_two_options(self):
        slot = _fake_slot("English", "COMPOSITION", hint="Q5 Analytical Paragraph")
        content = ("Analyse the following in 120-150 words and justify your choice. "
                   "(A) Speaker A: 10 yrs experience, relevant, engaging. "
                   "(B) Speaker B: younger, niche expertise, interactive.")
        ok, reason = lv.validate_language_question(slot, {"content": content, "answer": ""})
        self.assertTrue(ok, reason)

    def test_scenario_missing_word_limit_rejected(self):
        slot = _fake_slot("English", "COMPOSITION", hint="Q4 formal letter")
        content = "Write a formal letter to the Municipal Commissioner about waterlogging."
        ok, reason = lv.validate_language_question(slot, {"content": content, "answer": ""})
        self.assertFalse(ok)
        self.assertIn("word limit", reason.lower())

    def test_scenario_with_word_limit_accepted(self):
        slot = _fake_slot("English", "COMPOSITION", hint="Q4 formal letter")
        content = ("Write a formal letter (about 120 words) to the Municipal Commissioner, "
                   "Pune, about waterlogging. You are Rohan, a resident.")
        ok, reason = lv.validate_language_question(slot, {"content": content, "answer": ""})
        self.assertTrue(ok, reason)

    def test_telugu_chandas_rejects_gana_mismatch(self):
        # Names చంపకమాల but lists ఉత్పలమాల's gaṇa and not the correct one.
        text = f"ఈ పద్యం చంపకమాల వృత్తం. గణాలు: {TELUGU_METRE_GANA['ఉత్పలమాల']}"
        ok, _ = lv.validate_telugu_chandas(text)
        self.assertFalse(ok)

    def test_telugu_chandas_accepts_correct_gana(self):
        text = f"ఈ పద్యం చంపకమాల వృత్తం. గణాలు: {TELUGU_METRE_GANA['చంపకమాల']}"
        ok, reason = lv.validate_telugu_chandas(text)
        self.assertTrue(ok, reason)

    def test_content_slot_validation_is_noop(self):
        slot = _fake_slot("Science", "CONTENT", hint="")
        ok, _ = lv.validate_language_question(slot, {"content": "What is Ohm's law?", "answer": "V=IR"})
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
