"""Tests for scanned-PDF OCR (services.ocr_service).

Regression cover for the bug where two phone-scanned Class 6 Maths chapters
(11 + 5 pages, zero text layer between them) ingested "successfully" as 16
uncaptioned figure chunks, and the generator — handed a chapter whose entire
body was a figure inventory — produced a paper of questions like "Which figure
is on page 7?" and "How many figures are mentioned in the chapter?".
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from services.ocr_service import has_usable_text, ocr_pdf_pages, page_needs_ocr


def _blank_pdf(page_count: int) -> bytes:
    """A PDF with no text layer at all — the shape of a phone scan."""
    from services.pdf_service import _import_pymupdf

    fitz = _import_pymupdf()
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page(width=595, height=842)
    buffer = doc.tobytes()
    doc.close()
    return buffer


def _pages(page_count: int, content: str = "") -> list:
    return [
        {"pageNumber": i + 1, "content": content} for i in range(page_count)
    ]


class TextThresholdTests(TestCase):
    def test_empty_page_needs_ocr(self):
        self.assertTrue(page_needs_ocr(""))
        self.assertTrue(page_needs_ocr("   \n\f "))

    def test_scanner_artefact_page_needs_ocr(self):
        # A stray header is not a page of text.
        self.assertTrue(page_needs_ocr("Chapter 3"))

    def test_real_page_does_not_need_ocr(self):
        self.assertFalse(page_needs_ocr("A prime triplet is a set of " * 20))

    def test_text_less_document_is_not_usable(self):
        # The exact input that produced the bad paper: 16 pages, ~0 characters.
        self.assertFalse(has_usable_text("\n" * 16, 16))

    def test_thin_document_is_not_usable_at_scale(self):
        # 400 characters is a plausible worksheet and a failed 20-page chapter.
        self.assertTrue(has_usable_text("x" * 400, 1))
        self.assertFalse(has_usable_text("x" * 400, 20))

    def test_real_chapter_is_usable(self):
        self.assertTrue(has_usable_text("Factors and multiples. " * 500, 5))


class OcrPdfPagesTests(TestCase):
    def test_transcribes_only_the_pages_that_need_it(self):
        buffer = _blank_pdf(3)
        pages = _pages(3)
        pages[1]["content"] = "This page already has plenty of real text. " * 10

        with patch(
            "services.ocr_service.ocr_page_image", return_value="# Prime Triplet"
        ) as ocr:
            result, stats = ocr_pdf_pages(buffer, pages)

        self.assertEqual(ocr.call_count, 2)          # not the page with text
        self.assertEqual(stats["succeeded"], 2)
        self.assertEqual(result[0]["content"], "# Prime Triplet")
        self.assertEqual(result[2]["content"], "# Prime Triplet")
        self.assertTrue(result[0]["ocr"])
        self.assertIn("already has plenty", result[1]["content"])
        self.assertNotIn("ocr", result[1])

    def test_digital_pdf_makes_no_vision_calls(self):
        buffer = _blank_pdf(2)
        pages = _pages(2, "Real extracted textbook prose, at length. " * 10)

        with patch("services.ocr_service.ocr_page_image") as ocr:
            _, stats = ocr_pdf_pages(buffer, pages)

        ocr.assert_not_called()
        self.assertEqual(stats["attempted"], 0)

    def test_one_failed_page_does_not_sink_the_document(self):
        buffer = _blank_pdf(2)

        def flaky(data_url, user=None):
            flaky.calls += 1
            if flaky.calls == 1:
                raise RuntimeError("429 forever")
            return "Sphenic numbers"

        flaky.calls = 0
        with patch("services.ocr_service.ocr_page_image", side_effect=flaky):
            result, stats = ocr_pdf_pages(buffer, _pages(2))

        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["succeeded"], 1)
        self.assertEqual(
            {str(p.get("content") or "") for p in result}, {"", "Sphenic numbers"}
        )

    def test_empty_transcription_counts_as_a_failure(self):
        buffer = _blank_pdf(1)
        with patch("services.ocr_service.ocr_page_image", return_value="   "):
            result, stats = ocr_pdf_pages(buffer, _pages(1))
        self.assertEqual(stats["succeeded"], 0)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(result[0]["content"], "")

    @override_settings(PDF_OCR_ENABLED=False)
    def test_kill_switch_skips_ocr_entirely(self):
        with patch("services.ocr_service.ocr_page_image") as ocr:
            _, stats = ocr_pdf_pages(_blank_pdf(2), _pages(2))
        ocr.assert_not_called()
        self.assertEqual(stats["skipped"], "disabled")

    @override_settings(PDF_OCR_MAX_PAGES=2)
    def test_page_cap_bounds_the_bill(self):
        with patch("services.ocr_service.ocr_page_image", return_value="text") as ocr:
            _, stats = ocr_pdf_pages(_blank_pdf(6), _pages(6))
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(stats["attempted"], 2)
