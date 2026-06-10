"""Round-4 regression tests — s3b paper review fixes.

Covers the content_filters module plus the integration points the s3b
review flagged: Unicode math survival (Q38), bare-LaTeX rescue (Q6/Q14),
figure label residue (Q23), VI leakage (Q31/Q37), orphan OR (Q29), and
blueprint metadata leakage (Q34).
"""

import json
from unittest.mock import patch

from django.test import TestCase

from services.content_filters import (
    clean_question_text,
    clean_vi_alternative_text,
    is_label_only_caption,
    remove_orphan_or_tokens,
    strip_blueprint_leakage,
    strip_vi_blocks,
    wrap_bare_latex_tokens,
)

UNICODE_MATH = "√ π θ ∠ ≠ ≤ ≥ ∆ α β ∞ × ÷ ² ³ °"


class UnicodeMathSurvivalTests(TestCase):
    """Issue 1 — no Unicode math symbol may be dropped anywhere between
    generation and render."""

    def test_unicode_symbols_survive_clean_pipeline(self):
        passage = (
            f"Use √5 : 3 ; take √5 and √5 = 1.732. Also π ≈ 22/7, θ = 30°, "
            f"∠ABC ≠ ∠DEF, x ≤ y ≥ z, ∆ABC, α + β, ∞. All: {UNICODE_MATH}"
        )
        cleaned = clean_question_text(passage)
        for symbol in UNICODE_MATH.split():
            self.assertIn(symbol, cleaned, f"{symbol!r} was stripped by cleaning")

    def test_unicode_symbols_survive_sse_json_round_trip(self):
        # The SSE layer is json.dumps (ensure_ascii=True → \uXXXX escapes)
        # parsed back by the browser; emulate the full serialize→deserialize.
        from services.generation_service import _sse_event

        passage = f"Q38 heights of tower: use √3 = 1.732 and {UNICODE_MATH}."
        event = _sse_event({"question": {"content": clean_question_text(passage)}})
        payload = event.split("data: ", 1)[1].strip()
        decoded = json.loads(payload)
        for symbol in UNICODE_MATH.split():
            self.assertIn(symbol, decoded["question"]["content"])

    def test_unicode_symbols_survive_printable_assembly(self):
        from services.generation_service import _printable_question_content

        content = "Find √5 + π where θ = 45° and ∠A ≠ ∠B."
        or_choice = {"content": "Find √3 − π where ∆ABC is right-angled."}
        printable = _printable_question_content(content, or_choice, None)
        for symbol in ("√", "π", "θ", "∠", "≠", "∆", "°"):
            self.assertIn(symbol, printable)


class WrapBareLatexTests(TestCase):
    """Issue 2 (upstream class) — bare LaTeX outside \\( \\) must be
    wrapped so the editor's inlineMath pass renders it."""

    def test_bare_frac_is_wrapped(self):
        out = wrap_bare_latex_tokens("The probability is \\frac{11}{36} exactly.")
        self.assertIn("\\(\\frac{11}{36}\\)", out)

    def test_bare_caret_is_wrapped(self):
        out = wrap_bare_latex_tokens("Solve x^2 - 5x + 6 = 0 for x.")
        self.assertIn("\\(x^2\\)", out)

    def test_existing_math_spans_untouched(self):
        text = "Solve \\(x^2 + 3x\\) and \\[\\frac{a}{b}\\] now."
        self.assertEqual(wrap_bare_latex_tokens(text), text)

    def test_unicode_math_not_wrapped(self):
        text = "Use √3 = 1.732 and π ≈ 3.14."
        self.assertEqual(wrap_bare_latex_tokens(text), text)

    def test_trailing_punctuation_stays_outside_wrap(self):
        out = wrap_bare_latex_tokens("the value is \\sqrt{3}.")
        self.assertIn("\\(\\sqrt{3}\\).", out)

    def test_spacing_artifact_backslash_colon(self):
        out = wrap_bare_latex_tokens("ratio 5\\:3 of sides")
        self.assertIn("5:3", out)
        self.assertNotIn("\\:", out)


class OrphanOrTests(TestCase):
    """Issue 5 — OR only ever BETWEEN alternatives."""

    def test_q29_shape_leading_or_before_first_choice_is_stripped(self):
        content = (
            "Prove one of the following identities:\n"
            "OR\n"
            "(A) Prove identity A holds.\n"
            "OR\n"
            "(B) Prove identity B holds."
        )
        out = remove_orphan_or_tokens(content)
        lines = [l.strip() for l in out.split("\n") if l.strip()]
        self.assertEqual(lines.count("OR"), 1)
        self.assertLess(lines.index("(A) Prove identity A holds."), lines.index("OR"))
        self.assertLess(lines.index("OR"), lines.index("(B) Prove identity B holds."))

    def test_legit_or_between_content_and_single_marker_alt_survives(self):
        # The printable assembly emits "<content>\nOR\n(B) …" — one marker
        # only; that OR is the real separator and must stay.
        printable = "Prove X for the given triangle.\nOR\n(B) Prove Y instead."
        self.assertEqual(remove_orphan_or_tokens(printable), printable)

    def test_leading_and_trailing_or_stripped(self):
        self.assertEqual(
            remove_orphan_or_tokens("OR\nReal question text."),
            "Real question text.",
        )
        self.assertEqual(
            remove_orphan_or_tokens("Real question text.\nOR"),
            "Real question text.",
        )

    def test_consecutive_or_lines_collapse(self):
        out = remove_orphan_or_tokens("Part A text.\nOR\nOR\nPart B text.")
        self.assertEqual(out.split("\n").count("OR"), 1)

    def test_hindi_or_label_handled(self):
        out = remove_orphan_or_tokens("अथवा\nवास्तविक प्रश्न।")
        self.assertEqual(out, "वास्तविक प्रश्न।")


class BlueprintLeakTests(TestCase):
    """Issue 6 — instruction echoes never reach question text."""

    def test_q34_trailing_metadata_sentence_removed(self):
        content = (
            "Solve the pair of equations graphically.\n"
            "OR\n"
            "Internal choice — answer either (A) or (B) as given in the question content."
        )
        out = clean_question_text(content)
        self.assertNotIn("Internal choice", out)
        self.assertNotIn("answer either", out)
        # The OR left dangling by the removal must go too (trailing orphan).
        self.assertFalse(out.strip().endswith("OR"))
        self.assertIn("Solve the pair of equations graphically.", out)

    def test_field_name_mentions_removed(self):
        out = strip_blueprint_leakage(
            "Find the roots.\nSet `question.or_choice` to null.\nShow your work."
        )
        self.assertNotIn("or_choice", out)
        self.assertIn("Find the roots.", out)
        self.assertIn("Show your work.", out)

    def test_mixed_line_keeps_legit_sentences(self):
        out = strip_blueprint_leakage(
            "Compute the mean. Internal choice — answer either (A) or (B) as given in the question content."
        )
        self.assertIn("Compute the mean.", out)
        self.assertNotIn("answer either", out)


class ViLeakTests(TestCase):
    """Issue 4 — VI alternate blocks never leak into content/chunks."""

    VI_BLOCK = (
        "A tower casts a shadow of 20 m.\n"
        "- - - - - - - - - - - - - - - - - - -\n"
        "Note: The following question is for Visually Impaired Students only in lieu of the visual question above.\n"
        "Describe the relation between angle and shadow length.\n"
        "- - - - - - - - - - - - - - - - - - -\n"
        "Find the height of the tower."
    )

    def test_vi_block_stripped_from_text(self):
        out = strip_vi_blocks(self.VI_BLOCK)
        self.assertNotIn("Visually Impaired", out)
        self.assertNotIn("- - -", out)
        self.assertNotIn("Describe the relation", out)
        self.assertIn("A tower casts a shadow of 20 m.", out)
        self.assertIn("Find the height of the tower.", out)

    def test_explicit_coordinates_block_stripped(self):
        text = (
            "Plot the triangle.\n"
            "Explicit coordinates (for visual-impaired alternative):\n"
            "A(0,0), B(4,0), C(0,3)\n"
            "\n"
            "Find its area."
        )
        out = strip_vi_blocks(text)
        self.assertNotIn("visual-impaired", out.lower())
        self.assertNotIn("A(0,0)", out)
        self.assertIn("Plot the triangle.", out)
        self.assertIn("Find its area.", out)

    def test_clean_question_text_removes_vi_contamination(self):
        out = clean_question_text(self.VI_BLOCK)
        self.assertNotIn("Visually Impaired", out)

    def test_vi_alternative_field_keeps_text_but_drops_framing(self):
        framed = (
            "- - - - - - - - - -\n"
            "Note: The following question is for Visually Impaired Students only in lieu of the visual question above.\n"
            "State Pythagoras' theorem in words.\n"
            "- - - - - - - - - -"
        )
        out = clean_vi_alternative_text(framed)
        self.assertEqual(out, "State Pythagoras' theorem in words.")


class LabelOnlyCaptionTests(TestCase):
    """Issue 3 — figure caption/SVG residue rejection."""

    def test_label_residue_rejected(self):
        for residue in ("A", "ΔB", "A ΔB", "∠ABC", "A B C Δ", "x y 3.5"):
            self.assertTrue(is_label_only_caption(residue), residue)

    def test_real_caption_accepted(self):
        self.assertFalse(
            is_label_only_caption(
                "Right triangle ABC with the right angle at B and hypotenuse AC."
            )
        )

    def test_text_only_svg_rejected_shape_svg_accepted(self):
        from services.generation_service import _figure_to_data_url

        text_only = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'>"
            "<text x='10' y='20'>A</text><text x='50' y='90'>ΔB</text></svg>"
        )
        self.assertEqual(_figure_to_data_url(text_only), "")

        with_shapes = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'>"
            "<line x1='0' y1='0' x2='100' y2='100'/>"
            "<text x='10' y='20'>A</text></svg>"
        )
        self.assertTrue(
            _figure_to_data_url(with_shapes).startswith("data:image/svg+xml;base64,")
        )


class ViIngestionTests(TestCase):
    """Issue 4 acceptance — no stored chunk may contain the VI pattern."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import User

        cls.user = User.objects.create(
            id="round4-vi-user", name="Round4", email="round4-vi@test.local"
        )

    def test_ingested_chunks_contain_no_vi_blocks(self):
        from apps.documents.models import DocumentChunk, PdfSource
        from services.document_service import extract_and_persist_chunks

        vi_text = ViLeakTests.VI_BLOCK
        source = PdfSource.objects.create(
            name="vi-test.txt", size=len(vi_text), user=self.user,
            content_type="text/plain", status="processing",
        )

        with patch(
            "services.document_service.generate_embeddings",
            side_effect=lambda texts, user=None: [[0.0] * 1536 for _ in texts],
        ):
            extract_and_persist_chunks(
                buffer=vi_text.encode("utf-8"),
                file_name="vi-test.txt",
                file_type="text/plain",
                pdf_source=source,
                user=self.user,
            )

        chunks = DocumentChunk.objects.filter(pdf_source=source)
        self.assertGreater(chunks.count(), 0)
        for chunk in chunks:
            self.assertNotIn("Visually Impaired", chunk.content)
            self.assertNotIn("in lieu of the visual", chunk.content)


class CoerceQuestionIntegrationTests(TestCase):
    """End-to-end through _coerce_question: the exact s3b symptoms."""

    def _slot(self, **overrides):
        class Slot:
            index = 29
            section_title = "Section C"
            question_type = "SHORT_ANSWER"
            legacy_type = "SHORT"
            marks = 3
            class_num = 10
            subject = "Mathematics"
            stream = "INTEGRATED"
            difficulty = "medium"
            choice_required = True
            vi_required = False
            requires_image = False
            requires_figure = False

        slot = Slot()
        for key, value in overrides.items():
            setattr(slot, key, value)
        return slot

    def test_orphan_or_and_blueprint_leak_scrubbed_from_payload(self):
        from services.generation_service import _coerce_question

        raw = {
            "question": {
                "content": (
                    "Prove one of the following identities:\n"
                    "OR\n"
                    "(A) Prove \\(\\sin^2\\theta + \\cos^2\\theta = 1\\).\n"
                    "OR\n"
                    "(B) Prove \\(\\sec^2\\theta - \\tan^2\\theta = 1\\).\n"
                    "Internal choice — answer either (A) or (B) as given in the question content."
                ),
                "or_choice": {"content": "OR\nProve \\(\\csc^2\\theta - \\cot^2\\theta = 1\\)."},
                "answer": "Standard identity proof.",
            }
        }
        question = _coerce_question(raw, self._slot(), [], is_retry=False)
        content = question["content"]
        self.assertNotIn("Internal choice", content)
        self.assertNotIn("answer either", content)
        # No OR before the (A) alternative.
        first_or = content.find("\nOR")
        self.assertGreater(first_or, content.find("(A)"))
        # The or_choice's leading orphan OR is gone.
        self.assertFalse(question["or_choice"]["content"].startswith("OR"))

    def test_vi_contamination_scrubbed_but_field_preserved(self):
        from services.generation_service import _coerce_question

        raw = {
            "question": {
                "content": ViLeakTests.VI_BLOCK,
                "or_choice": {"content": "Alternative question text here."},
                "answer": "42",
            }
        }
        question = _coerce_question(
            raw, self._slot(), [], is_retry=False, include_vi_alternatives=False
        )
        self.assertNotIn("Visually Impaired", question["content"])
        self.assertIsNone(question["vi_alternative"])
