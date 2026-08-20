from django.test import TestCase

from apps.accounts.models import User
from apps.documents.models import DocumentChunk, PdfSource
from services.pool.chapters import build_chapters, split_chapter


def _user():
    return User.objects.create(
        id="chuser000000000000000000000001a",
        name="Ch",
        email="chapters@test.local",
        status="approved",
    )


def _source(user, name="book.pdf"):
    return PdfSource.objects.create(name=name, size=1000, status="ready", user=user)


def _chunk(source, index, content, metadata=None, page=1):
    return DocumentChunk.objects.create(
        content=content,
        page=page,
        chunk_index=index,
        metadata=metadata or {},
        pdf_source=source,
    )


class ChapterDetectionTests(TestCase):
    def test_reuses_semantic_chapter_metadata_as_source_of_truth(self):
        user = _user()
        source = _source(user)
        _chunk(
            source,
            0,
            "# Chapter 1 Electricity\n## Current\n\nCurrent flows in a circuit.",
            {
                "chapter": "Chapter 1 Electricity",
                "heading": "Current",
                "sourcePdf": "book.pdf",
            },
            page=4,
        )
        _chunk(
            source,
            1,
            "# Chapter 2 Magnetism\n## Fields\n\nMagnets have poles.",
            {
                "chapter": "Chapter 2 Magnetism",
                "heading": "Fields",
                "sourcePdf": "book.pdf",
            },
            page=18,
        )

        chapters = build_chapters(pdf_source_ids=[source.id])

        self.assertEqual([chapter.number for chapter in chapters], [1, 2])
        self.assertEqual(
            [chapter.title for chapter in chapters],
            ["Chapter 1 Electricity", "Chapter 2 Magnetism"],
        )
        self.assertEqual(chapters[0].question_metadata()["sourcePages"], [4, 4])

    def test_fallback_detects_lesson_heading_when_metadata_is_missing(self):
        user = _user()
        source = _source(user, "lessons.pdf")
        _chunk(source, 0, "Lesson 5: Light\n\nReflection happens at a surface.")
        _chunk(source, 1, "Lesson 6: Sound\n\nSound needs a medium.")

        chapters = build_chapters(pdf_source_ids=[source.id])

        self.assertEqual([chapter.number for chapter in chapters], [5, 6])
        self.assertEqual(
            [chapter.title for chapter in chapters],
            ["Lesson 5: Light", "Lesson 6: Sound"],
        )

    def test_plain_single_chapter_upload_falls_back_to_source_name(self):
        user = _user()
        source = _source(user, "worksheet.docx")
        _chunk(source, 0, "Some notes without an explicit chapter heading.")

        chapters = build_chapters(pdf_source_ids=[source.id])

        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "worksheet")

    def test_oversized_chapter_splits_without_changing_bank_chapter_metadata(self):
        user = _user()
        source = _source(user, "large.pdf")
        for index in range(8):
            _chunk(
                source,
                index,
                f"# Chapter 4 Tissues\n## Section {index}\n\n{'cell ' * 80}",
                {
                    "chapter": "Chapter 4 Tissues",
                    "heading": f"Section {index}",
                    "sourcePdf": "large.pdf",
                },
                page=index + 1,
            )

        original = build_chapters(pdf_source_ids=[source.id])[0]
        parts = split_chapter(original, max_chars=700)

        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[0].metadata["bankChapterTitle"], "Chapter 4 Tissues")
        self.assertEqual(parts[0].number, 4)

    def test_oversized_unstructured_text_is_hard_capped(self):
        user = _user()
        source = _source(user, "dense.pdf")
        _chunk(
            source,
            0,
            "# Chapter 9 Dense Text\n## Body\n\n" + ("x" * 2500),
            {
                "chapter": "Chapter 9 Dense Text",
                "heading": "Body",
                "sourcePdf": "dense.pdf",
            },
        )

        original = build_chapters(pdf_source_ids=[source.id])[0]
        parts = split_chapter(original, max_chars=700)

        self.assertGreater(len(parts), 1)
        self.assertTrue(all(part.char_count <= 700 for part in parts))
