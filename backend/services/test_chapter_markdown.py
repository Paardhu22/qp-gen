"""Tests for chapter Markdown reconstruction (Model 1's input).

The reconstruction has to be faithful: Model 1 writes ~80 questions off this
document, so duplicated paragraphs (overlap bleed) or dropped sections turn
straight into duplicated or missing questions.
"""

from django.test import TestCase

from apps.accounts.models import User
from apps.documents.models import DocumentChunk, PdfSource
from services.chapter_markdown import (
    ChapterMarkdown,
    build_chapter_markdown,
    infer_chapter_name,
)


def _make_user(email="md@test.local"):
    return User.objects.create(id="mduser00000000000000000000000001", name="MD", email=email)


def _make_source(user, name="electricity.pdf"):
    return PdfSource.objects.create(name=name, size=1000, status="ready", user=user)


def _chunk(source, index, content, metadata=None, page=1):
    return DocumentChunk.objects.create(
        content=content,
        page=page,
        chunk_index=index,
        metadata=metadata or {},
        pdf_source=source,
    )


class SemanticChunkReconstructionTests(TestCase):
    """PDFs go through process_semantic_pipeline — chunks carry chapter/heading
    metadata and embed a '# chapter / ## heading' prefix."""

    def setUp(self):
        self.user = _make_user()
        self.source = _make_source(self.user)

    def test_headings_emitted_once_not_per_chunk(self):
        for index in range(3):
            _chunk(
                self.source,
                index,
                f"# Electricity\n## Ohm's Law\n\nParagraph {index} about resistance.",
                {"chapter": "Electricity", "heading": "Ohm's Law", "sourcePdf": "electricity.pdf"},
            )

        result = build_chapter_markdown(
            pdf_source_ids=[self.source.id], use_cache=False
        )

        self.assertEqual(result.markdown.count("# Electricity"), 1)
        self.assertEqual(result.markdown.count("## Ohm's Law"), 1)
        for index in range(3):
            self.assertIn(f"Paragraph {index} about resistance.", result.markdown)

    def test_new_heading_starts_new_section(self):
        _chunk(
            self.source, 0,
            "# Electricity\n## Ohm's Law\n\nV equals I times R.",
            {"chapter": "Electricity", "heading": "Ohm's Law"},
        )
        _chunk(
            self.source, 1,
            "# Electricity\n## Heating Effect\n\nJoule's law of heating.",
            {"chapter": "Electricity", "heading": "Heating Effect"},
        )

        result = build_chapter_markdown(
            pdf_source_ids=[self.source.id], use_cache=False
        )

        self.assertIn("## Ohm's Law", result.markdown)
        self.assertIn("## Heating Effect", result.markdown)
        self.assertEqual(result.markdown.count("# Electricity"), 1)
        self.assertLess(
            result.markdown.index("Ohm's Law"),
            result.markdown.index("Heating Effect"),
            "Sections must keep document order (chunk_index).",
        )

    def test_chunks_are_read_in_document_order(self):
        # Insert out of order — ordering must come from chunk_index, not PK.
        _chunk(self.source, 2, "# C\n## H\n\nTHIRD", {"chapter": "C", "heading": "H"})
        _chunk(self.source, 0, "# C\n## H\n\nFIRST", {"chapter": "C", "heading": "H"})
        _chunk(self.source, 1, "# C\n## H\n\nSECOND", {"chapter": "C", "heading": "H"})

        markdown = build_chapter_markdown(
            pdf_source_ids=[self.source.id], use_cache=False
        ).markdown

        self.assertLess(markdown.index("FIRST"), markdown.index("SECOND"))
        self.assertLess(markdown.index("SECOND"), markdown.index("THIRD"))


class OverlapTrimmingTests(TestCase):
    """DOCX/txt go through chunk_text, which overlaps windows by 200 chars.
    Concatenating naively would duplicate a fifth of the chapter."""

    def setUp(self):
        self.user = _make_user("overlap@test.local")
        self.source = _make_source(self.user, "notes.docx")

    def test_overlapping_plain_chunks_are_deduplicated(self):
        shared = "The resistance of a conductor depends on its length and area. " * 2
        _chunk(self.source, 0, "Opening sentence about current. " + shared)
        _chunk(self.source, 1, shared + " Closing sentence about voltage.")

        markdown = build_chapter_markdown(
            pdf_source_ids=[self.source.id], use_cache=False
        ).markdown

        self.assertEqual(
            markdown.count("Opening sentence about current."), 1
        )
        self.assertEqual(
            markdown.count("Closing sentence about voltage."), 1
        )
        # The shared span appears once, not twice.
        self.assertEqual(
            markdown.count("The resistance of a conductor depends on its length and area."),
            2,
            "The shared text repeats twice within one chunk by construction, "
            "but must not be doubled to four by overlap bleed.",
        )

    def test_semantic_chunks_are_not_overlap_trimmed(self):
        """A semantic chunk that legitimately repeats a sentence must keep it —
        overlap trimming applies only to the plain chunk_text path."""
        repeated = "Ohm's law states that V = IR."
        _chunk(self.source, 0, f"# C\n## H\n\n{repeated}", {"chapter": "C", "heading": "H"})
        _chunk(self.source, 1, f"# C\n## H\n\n{repeated}", {"chapter": "C", "heading": "H"})

        markdown = build_chapter_markdown(
            pdf_source_ids=[self.source.id], use_cache=False
        ).markdown

        self.assertEqual(markdown.count(repeated), 2)


class FigureCollectionTests(TestCase):
    def setUp(self):
        self.user = _make_user("fig@test.local")
        self.source = _make_source(self.user)

    def test_image_chunks_become_figures_not_prose(self):
        _chunk(self.source, 0, "# C\n## H\n\nBody text.", {"chapter": "C", "heading": "H"})
        _chunk(
            self.source, 1,
            "# Visual Source\nPage: 4\nHidden caption: A series circuit.",
            {
                "chunkType": "image",
                "image_url": "/media/pdf_images/circuit.png",
                "image_caption": "A series circuit with three resistors.",
                "sourcePdf": "electricity.pdf",
            },
            page=4,
        )

        result = build_chapter_markdown(
            pdf_source_ids=[self.source.id], use_cache=False
        )

        self.assertEqual(len(result.figures), 1)
        figure = result.figures[0]
        self.assertEqual(figure.url, "/media/pdf_images/circuit.png")
        self.assertEqual(figure.page, 4)
        self.assertIn("A series circuit", figure.caption)

        # The raw "Hidden caption:" scaffolding must not leak into the prose.
        self.assertNotIn("Hidden caption:", result.markdown)
        # But the figure IS advertised in the inventory block.
        self.assertIn("Figures in this chapter", result.markdown)
        self.assertIn("A series circuit with three resistors.", result.markdown)

    def test_image_chunk_without_url_is_skipped(self):
        _chunk(self.source, 0, "# C\n## H\n\nBody.", {"chapter": "C", "heading": "H"})
        _chunk(self.source, 1, "orphan", {"chunkType": "image", "image_caption": "no url"})

        result = build_chapter_markdown(
            pdf_source_ids=[self.source.id], use_cache=False
        )
        self.assertEqual(result.figures, [])


class TruncationTests(TestCase):
    def setUp(self):
        self.user = _make_user("trunc@test.local")
        self.source = _make_source(self.user)

    def test_oversized_chapter_is_truncated_on_a_paragraph_boundary(self):
        for index in range(40):
            _chunk(
                self.source, index,
                f"# C\n## H\n\n{'word ' * 200}para{index}",
                {"chapter": "C", "heading": "H"},
            )

        result = build_chapter_markdown(
            pdf_source_ids=[self.source.id], max_chars=2000, use_cache=False
        )

        self.assertTrue(result.truncated)
        self.assertLessEqual(result.char_count, 2000)
        self.assertEqual(result.char_count, len(result.markdown))

    def test_within_limit_is_not_marked_truncated(self):
        _chunk(self.source, 0, "# C\n## H\n\nShort chapter.", {"chapter": "C", "heading": "H"})
        result = build_chapter_markdown(
            pdf_source_ids=[self.source.id], max_chars=100_000, use_cache=False
        )
        self.assertFalse(result.truncated)


class EmptyAndScopingTests(TestCase):
    def test_no_source_ids_returns_empty(self):
        result = build_chapter_markdown(pdf_source_ids=[], hsat_source_ids=[])
        self.assertTrue(result.is_empty)
        self.assertEqual(result.figures, [])

    def test_unknown_source_id_returns_empty(self):
        result = build_chapter_markdown(
            pdf_source_ids=["does-not-exist"], use_cache=False
        )
        self.assertTrue(result.is_empty)

    def test_only_requested_sources_are_included(self):
        user = _make_user("scope@test.local")
        wanted = _make_source(user, "wanted.pdf")
        other = PdfSource.objects.create(
            name="other.pdf", size=10, status="ready", user=user
        )
        _chunk(wanted, 0, "# C\n## H\n\nWANTED CONTENT", {"chapter": "C", "heading": "H"})
        _chunk(other, 0, "# C\n## H\n\nOTHER CONTENT", {"chapter": "C", "heading": "H"})

        markdown = build_chapter_markdown(
            pdf_source_ids=[wanted.id], use_cache=False
        ).markdown

        self.assertIn("WANTED CONTENT", markdown)
        self.assertNotIn("OTHER CONTENT", markdown)


class InferChapterNameTests(TestCase):
    def test_prefers_detected_chapter_heading(self):
        chapter = ChapterMarkdown(
            markdown="x", chapter_titles=["Chapter 12 Electricity"],
            source_names=["upload.pdf"],
        )
        self.assertEqual(infer_chapter_name(chapter), "Chapter 12 Electricity")

    def test_skips_pipeline_placeholder_headings(self):
        chapter = ChapterMarkdown(
            markdown="x",
            chapter_titles=["General Context", "Visual Source"],
            source_names=["light-reflection.pdf"],
        )
        self.assertEqual(infer_chapter_name(chapter), "light-reflection")

    def test_falls_back_to_topic_when_nothing_detected(self):
        chapter = ChapterMarkdown(markdown="x")
        self.assertEqual(infer_chapter_name(chapter, fallback="Acids and Bases"), "Acids and Bases")
