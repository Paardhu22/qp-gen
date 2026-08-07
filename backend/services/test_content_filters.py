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
        # The SSE layer is json.dumps parsed back by the browser; emulate the
        # full serialize→deserialize.
        from services.pool.pipeline import _sse

        passage = f"Q38 heights of tower: use √3 = 1.732 and {UNICODE_MATH}."
        event = _sse({"question": {"content": clean_question_text(passage)}})
        payload = event.split("data: ", 1)[1].strip()
        decoded = json.loads(payload)
        for symbol in UNICODE_MATH.split():
            self.assertIn(symbol, decoded["question"]["content"])

    def test_unicode_symbols_survive_printable_assembly(self):
        from services.pool.rendering import printable_content

        content = "Find √5 + π where θ = 45° and ∠A ≠ ∠B."
        printable = printable_content(
            content, or_alternative="Find √3 − π where ∆ABC is right-angled."
        )
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

    # The inline-SVG figure pipeline (_figure_to_data_url) went away with the
    # per-slot engine — the pool attaches figures as stored image URLs rather
    # than asking the model to draw SVG markup, so there is no SVG to validate.
    # is_label_only_caption above still guards the ingestion side, which is
    # where label-only residue actually originates.


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


class PoolNormalisationIntegrationTests(TestCase):
    """End-to-end through the pool normaliser: the exact s3b symptoms.

    Ported from the per-slot engine's _coerce_question tests when that engine
    was removed. The scrubbing choke point moved (Model 1 runs
    clean_question_text over every stem) but the symptoms these guard against
    are unchanged, so the coverage follows the behaviour rather than the
    function that used to host it.
    """

    def _normalise(self, raw_text, **kwargs):
        from services.pool.model1 import _normalise_batch
        from services.pool.recipes import Batch, TypeQuota

        batch = Batch("short", [TypeQuota("SHORT_ANSWER", 3, 1)])
        raw = {
            "type": "SHORT_ANSWER",
            "marks": 3,
            "topic": "Trigonometric identities",
            "blooms": "APPLY",
            "difficulty": "medium",
            "question": raw_text,
            "answer": "Standard identity proof.",
            "explanation": "Pythagorean identity.",
            **kwargs,
        }
        accepted, _invalid = _normalise_batch(
            [raw], batch=batch, subject="Mathematics",
            chapter_name="Trigonometry", pool_id="p1", difficulty="medium",
        )
        return accepted[0] if accepted else None

    def test_blueprint_leakage_is_scrubbed_from_the_stem(self):
        question = self._normalise(
            "Prove \\(\\sin^2\\theta + \\cos^2\\theta = 1\\).\n"
            "Internal choice — answer either (A) or (B) as given in the question content."
        )
        self.assertIsNotNone(question)
        self.assertNotIn("Internal choice", question.question)
        self.assertNotIn("answer either", question.question)

    def test_orphan_or_is_removed_from_the_stem(self):
        question = self._normalise(
            "OR\nProve \\(\\csc^2\\theta - \\cot^2\\theta = 1\\)."
        )
        self.assertIsNotNone(question)
        self.assertFalse(question.question.startswith("OR"))

    def test_vi_contamination_is_scrubbed_from_the_stem(self):
        question = self._normalise(ViLeakTests.VI_BLOCK + "\nProve the identity.")
        self.assertIsNotNone(question)
        self.assertNotIn("Visually Impaired", question.question)

    def test_content_hash_tracks_the_cleaned_stem_not_the_raw_one(self):
        # Otherwise a stem that only differs by leaked scaffolding would
        # dedup as a distinct question and both copies would reach the bank.
        from services.pool.schema import compute_content_hash

        dirty = self._normalise(
            "Prove \\(\\sin^2\\theta + \\cos^2\\theta = 1\\).\n"
            "Internal choice — answer either (A) or (B) as given in the question content."
        )
        clean = self._normalise("Prove \\(\\sin^2\\theta + \\cos^2\\theta = 1\\).")

        self.assertEqual(dirty.content_hash, clean.content_hash)
        self.assertEqual(
            dirty.content_hash,
            compute_content_hash("Mathematics", "Trigonometry", clean.question),
        )
