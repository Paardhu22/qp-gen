"""
Tests for the ISSUE A / ISSUE C fixes:

  - build_realized_general_instructions derives the printable header from the
    realized question list, not from blueprint constants. A 12-question body
    must never carry a 38-question header.
  - The PyMuPDF import shim in services.pdf_service falls back gracefully when
    PyMuPDF is missing and labels its output as `degraded`.

Run:  python -m unittest q_instructions.tests.test_content_scope -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def _load_router():
    """Load generation_router via exec, stubbing out Django (mirrors the
    pattern used by test_new_subjects)."""
    router_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'services', 'generation_router.py'
    )
    src = open(router_path).read()
    src = src.replace('from django.conf import settings', '')
    globs = {'__builtins__': __builtins__, 'logging': __import__('logging')}
    exec(compile(src, router_path, 'exec'), globs)
    return globs


_router = _load_router()


def _realized_paper(*sections):
    """Helper — sections is a list of (title, [(marks, question_type), ...])."""
    return {
        "generalInstructions": [],
        "sections": [
            {
                "title": title,
                "questions": [
                    {"marks": marks, "type": qtype, "content": "x"}
                    for marks, qtype in items
                ],
            }
            for title, items in sections
        ],
    }


class TestRealizedHeader(unittest.TestCase):
    """ISSUE A2 — the printable header must be a pure function of the
    realized paper, not the blueprint."""

    def test_truncated_paper_header_matches_body(self):
        """12 realized questions ⇒ header says 12, not 38."""
        result = _realized_paper(
            ("Section A - MCQ", [(1, "MCQ")] * 12),
        )
        lines = _router["build_realized_general_instructions"](
            result, "Mathematics", 10,
            scope_policy="source_only",
            fallback_count=0,
            requested_count=38,
        )
        joined = "\n".join(lines)
        # Header reflects the real 12-question body
        self.assertIn("12 questions", joined)
        # And it explicitly surfaces the gap so the user knows it's not 38
        self.assertIn("12", joined)
        self.assertIn("38", joined)
        # Crucially: never claim the blueprint count over a smaller body
        self.assertNotIn("38 questions. All questions are compulsory.", joined)

    def test_section_label_uses_realized_split(self):
        """The Section A "(n × m = T Marks)" label must reflect realized
        questions, not blueprint constants."""
        result = _realized_paper(
            ("Section A - MCQ", [(1, "MCQ")] * 12),
        )
        lines = _router["build_realized_general_instructions"](
            result, "Mathematics", 10, scope_policy="source_only",
            fallback_count=0, requested_count=38,
        )
        joined = "\n".join(lines)
        self.assertIn("12 × 1 = 12 Marks", joined)

    def test_strict_full_blueprint_header_says_38(self):
        """In strict mode with a complete realized paper, the header reads 38."""
        sections = (
            ("Section A - MCQ",                  [(1, "MCQ")] * 20),
            ("Section B - Very Short Answer",    [(2, "SHORT")] * 5),
            ("Section C - Short Answer",         [(3, "SHORT")] * 6),
            ("Section D - Long Answer",          [(5, "LONG")] * 4),
            ("Section E - Case-Based Questions", [(4, "CASE_STUDY")] * 3),
        )
        result = _realized_paper(*sections)
        lines = _router["build_realized_general_instructions"](
            result, "Mathematics", 10, scope_policy="strict",
            fallback_count=0, requested_count=38,
        )
        joined = "\n".join(lines)
        self.assertIn("38 question", joined)
        self.assertIn("20 × 1 = 20 Marks", joined)
        self.assertIn("5 × 2 = 10 Marks", joined)
        self.assertIn("6 × 3 = 18 Marks", joined)
        self.assertIn("4 × 5 = 20 Marks", joined)
        self.assertIn("3 × 4 = 12 Marks", joined)
        # Total marks line
        self.assertIn("80", joined)

    def test_strict_with_curriculum_fallback_surfaces_notice(self):
        """When some slots used curriculum fallback, the header still totals
        the realized count but adds a transparent notice."""
        result = _realized_paper(
            ("Section A - MCQ", [(1, "MCQ")] * 20),
        )
        lines = _router["build_realized_general_instructions"](
            result, "Mathematics", 10, scope_policy="strict",
            fallback_count=7, requested_count=20,
        )
        joined = "\n".join(lines)
        self.assertIn("20 question", joined)
        self.assertIn("CBSE curriculum", joined)
        self.assertIn("7", joined)

    def test_empty_paper_returns_explicit_message(self):
        result = _realized_paper()
        lines = _router["build_realized_general_instructions"](
            result, "Mathematics", 10,
        )
        self.assertEqual(lines, ["No questions could be generated."])


class TestSourceTypeStamping(unittest.TestCase):
    """ISSUE 2 — every emitted question must carry a `sourceType` flag so
    the frontend review tray can show a "From sources" vs "Curriculum
    fallback" badge. Without this, teachers can't tell the two apart and
    can't be selective about ungrounded questions."""

    def test_generation_service_stamps_source_type(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'services',
            'generation_service.py',
        )
        with open(path) as f:
            src = f.read()
        # Top-level field on the question
        self.assertIn('question["sourceType"] = source_type', src)
        # Mirrored on metadata so existing metadata-consumers also see it
        self.assertIn('question["metadata"]["sourceType"] = source_type', src)
        # Both values appear
        self.assertIn('"curriculum_fallback" if curriculum_fallback else "rag"', src)
        # The streamed event payload also carries it for the frontend
        self.assertIn('"sourceType": source_type', src)


class TestPdfServiceImportShim(unittest.TestCase):
    """ISSUE C — pdf_service must define a robust pymupdf→fitz import shim
    and degrade loudly (not silently) when PyMuPDF is unavailable."""

    def test_pdf_service_has_import_shim(self):
        pdf_service_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'services', 'pdf_service.py'
        )
        src = open(pdf_service_path).read()
        # Robust import: pymupdf first (newer name), fall back to fitz (older).
        self.assertIn("import pymupdf", src)
        self.assertIn("import fitz", src)
        # The fallback path must mark itself degraded so the API layer can
        # surface a warning instead of silently producing a worse paper.
        self.assertIn("degraded", src)
        self.assertIn("pymupdf_not_installed", src)


if __name__ == "__main__":
    unittest.main()
