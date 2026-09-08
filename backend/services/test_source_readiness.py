"""Tests for the authoritative source-readiness gate (services.source_readiness)
and its wiring into the pool pipeline. Regression cover for the async-upload
race that surfaced as the generic "No questions could be generated" error."""
import json
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.documents.models import DocumentChunk, HsatSource, PdfSource
from services.source_readiness import (
    DOCUMENTS_NOT_READY,
    REASON_NO_CHUNKS,
    REASON_NO_TEXT,
    REASON_NOT_FOUND,
    REASON_NOT_READY,
    build_not_ready_payload,
    check_sources_ready,
)


def _pdf(user, *, status, sha, name="ch.pdf"):
    return PdfSource.objects.create(
        name=name, size=1, content_type="application/pdf",
        status=status, user=user, sha256=sha,
    )


def _chunk(*, pdf=None, hsat=None, idx=0):
    return DocumentChunk.objects.create(
        content="Photosynthesis is the process. " * 20,
        page=1, chunk_index=idx, embedding=[0.0] * 1536,
        pdf_source=pdf, hsat_source=hsat,
        metadata={"sourcePdf": "ch.pdf"},
    )


class CheckSourcesReadyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(id="u1", name="U1", email="u1@t.local", status="approved")
        cls.other = User.objects.create(id="u2", name="U2", email="u2@t.local", status="approved")

    def test_ready_pdf_with_chunks_passes(self):
        src = _pdf(self.user, status="ready", sha="a")
        _chunk(pdf=src)
        self.assertEqual(
            check_sources_ready(user=self.user, pdf_source_ids=[src.id]), []
        )

    def test_processing_pdf_is_not_ready(self):
        src = _pdf(self.user, status="processing", sha="b")
        pending = check_sources_ready(user=self.user, pdf_source_ids=[src.id])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].reason, REASON_NOT_READY)
        self.assertEqual(pending[0].status, "processing")
        self.assertEqual(pending[0].name, "ch.pdf")

    def test_ready_pdf_without_chunks_flagged_no_chunks(self):
        src = _pdf(self.user, status="ready", sha="c")  # ready but 0 chunks
        pending = check_sources_ready(user=self.user, pdf_source_ids=[src.id])
        self.assertEqual([p.reason for p in pending], [REASON_NO_CHUNKS])

    def test_other_users_source_is_not_found(self):
        src = _pdf(self.other, status="ready", sha="d")
        _chunk(pdf=src)
        pending = check_sources_ready(user=self.user, pdf_source_ids=[src.id])
        self.assertEqual([p.reason for p in pending], [REASON_NOT_FOUND])
        self.assertIsNone(pending[0].name)  # do not leak another user's data

    def test_unknown_id_is_not_found(self):
        pending = check_sources_ready(
            user=self.user, pdf_source_ids=["does-not-exist"]
        )
        self.assertEqual([p.reason for p in pending], [REASON_NOT_FOUND])

    def test_hsat_readiness_checked_without_ownership(self):
        book = HsatSource.objects.create(
            id="h1", grade="10", subject="Science", book="NCERT",
            status="processing", chunk_count=0,
        )
        pending = check_sources_ready(
            user=self.user, hsat_source_ids=[book.id]
        )
        self.assertEqual([p.reason for p in pending], [REASON_NOT_READY])
        self.assertEqual(pending[0].name, "NCERT")

    def test_ready_hsat_without_chunks_flagged_no_chunks(self):
        book = HsatSource.objects.create(
            id="h2", grade="10", subject="Science", book="NCERT",
            status="ready", chunk_count=0,
        )
        pending = check_sources_ready(user=self.user, hsat_source_ids=[book.id])
        self.assertEqual([p.reason for p in pending], [REASON_NO_CHUNKS])

    def test_ready_hsat_with_chunks_passes(self):
        # HSAT chunks store a NULL pdfSourceId, which the SQLite test schema
        # forbids (migration 0006 only drops that NOT NULL on Postgres). Patch
        # the chunk-presence lookup to exercise the ready+has-chunks branch.
        book = HsatSource.objects.create(
            id="h3", grade="10", subject="Science", book="NCERT",
            status="ready", chunk_count=5,
        )
        with patch(
            "services.source_readiness._ids_with_chunks",
            return_value={book.id},
        ):
            self.assertEqual(
                check_sources_ready(user=self.user, hsat_source_ids=[book.id]),
                [],
            )

    def test_mixed_pass_and_fail(self):
        good = _pdf(self.user, status="ready", sha="e", name="good.pdf")
        _chunk(pdf=good)
        bad = _pdf(self.user, status="processing", sha="f", name="bad.pdf")
        pending = check_sources_ready(
            user=self.user, pdf_source_ids=[good.id, bad.id]
        )
        self.assertEqual([p.name for p in pending], ["bad.pdf"])

    def test_payload_shape(self):
        src = _pdf(self.user, status="processing", sha="g", name="ch1.pdf")
        pending = check_sources_ready(user=self.user, pdf_source_ids=[src.id])
        payload = build_not_ready_payload(pending)
        self.assertEqual(payload["code"], DOCUMENTS_NOT_READY)
        self.assertIn("ch1.pdf", payload["error"])
        self.assertEqual(payload["pendingDocuments"][0]["reason"], REASON_NOT_READY)
        self.assertEqual(payload["pendingDocuments"][0]["kind"], "pdf")


class PipelineGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(id="pu", name="PU", email="pu@t.local", status="approved")

    def test_no_sources_at_all_is_a_hard_error_before_the_readiness_gate(self):
        # `QuestionGenerationSerializer.validate` already rejects this at the
        # API boundary; this is the pipeline's own copy of that precondition,
        # for the callers that reach `stream_pool_questions` directly (tests,
        # `paper-from-bank`'s sibling entry points, any future caller). It
        # must fire before `check_sources_ready` — an empty id list is
        # vacuously "nothing pending", so without this check the gate would
        # wave a sourceless request straight through.
        from services.pool.pipeline import stream_pool_questions

        events = list(
            stream_pool_questions(
                user=self.user,
                pdf_source_ids=[],
                topic="",
                count=-1,
                difficulty="medium",
                payload={"subject": "Science", "class": "10"},
            )
        )
        self.assertEqual(len(events), 1)
        self.assertIn("event: error", events[0])
        self.assertNotIn(DOCUMENTS_NOT_READY, events[0])

    def test_pipeline_emits_documents_not_ready_and_stops(self):
        from services.pool.pipeline import stream_pool_questions

        src = _pdf(self.user, status="processing", sha="p1", name="chem.pdf")
        events = list(
            stream_pool_questions(
                user=self.user,
                pdf_source_ids=[src.id],
                topic="",
                count=-1,
                difficulty="medium",
                payload={"subject": "Science", "class": "10"},
            )
        )
        # The gate fires first and generation stops immediately.
        self.assertEqual(len(events), 1)
        raw = events[0]
        self.assertIn("event: error", raw)
        self.assertIn(DOCUMENTS_NOT_READY, raw)
        # Parse the SSE data line to confirm the structured payload.
        data_line = [l for l in raw.splitlines() if l.startswith("data:")][0]
        payload = json.loads(data_line[len("data:"):].strip())
        self.assertEqual(payload["code"], DOCUMENTS_NOT_READY)
        self.assertEqual(payload["pendingDocuments"][0]["name"], "chem.pdf")

    def test_pipeline_proceeds_past_gate_when_ready(self):
        # A ready source with chunks must NOT be rejected by the gate. We only
        # assert the gate did not short-circuit — i.e. the first event is not the
        # readiness error (downstream may still fail without OpenAI, which is
        # fine; this test only guards the gate).
        from services.pool.pipeline import stream_pool_questions

        src = _pdf(self.user, status="ready", sha="p2", name="ok.pdf")
        _chunk(pdf=src)
        gen = stream_pool_questions(
            user=self.user,
            pdf_source_ids=[src.id],
            topic="",
            count=-1,
            difficulty="medium",
            payload={"subject": "Science", "class": "10"},
        )
        first = next(gen)
        self.assertNotIn(DOCUMENTS_NOT_READY, first)
        gen.close()


def _image_chunk(*, pdf=None, hsat=None, idx=0, page=1):
    """A figure chunk exactly as ingestion stored them for a scanned PDF:
    no caption, no nearby text (there was no text layer to be near)."""
    return DocumentChunk.objects.create(
        content=f"# Visual Source\nPage: {page}\nNearby textbook text:",
        page=page, chunk_index=idx, embedding=[0.0] * 1536,
        pdf_source=pdf, hsat_source=hsat,
        metadata={
            "sourcePdf": "scan.pdf",
            "chunkType": "image",
            "image_url": "https://example.test/p.jpg",
            "image_caption": "",
        },
    )


class ScannedSourceGateTests(TestCase):
    """A scanned PDF ingested before OCR existed has chunks — one per page
    image, all uncaptioned — and used to sail through the readiness gate. The
    chapter it produced was nothing but a figure inventory, so the generator
    wrote a paper asking which figure sat on page 7."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(
            id="u3", name="U3", email="u3@t.local", status="approved"
        )

    def test_pdf_with_only_image_chunks_is_flagged_no_text(self):
        src = _pdf(self.user, status="ready", sha="s1", name="scan.pdf")
        for i in range(11):
            _image_chunk(pdf=src, idx=i, page=i + 1)
        pending = check_sources_ready(user=self.user, pdf_source_ids=[src.id])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].reason, REASON_NO_TEXT)
        self.assertEqual(pending[0].name, "scan.pdf")

    def test_text_chunks_alongside_images_still_pass(self):
        src = _pdf(self.user, status="ready", sha="s2", name="mixed.pdf")
        _chunk(pdf=src, idx=0)
        _image_chunk(pdf=src, idx=1)
        self.assertEqual(
            check_sources_ready(user=self.user, pdf_source_ids=[src.id]), []
        )

    def test_hsat_with_only_image_chunks_is_flagged_no_text(self):
        book = HsatSource.objects.create(book="Scanned Book", status="ready")
        _image_chunk(hsat=book)
        pending = check_sources_ready(user=self.user, hsat_source_ids=[book.id])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].reason, REASON_NO_TEXT)

    def test_payload_says_reupload_not_wait(self):
        src = _pdf(self.user, status="ready", sha="s3", name="scan.pdf")
        _image_chunk(pdf=src)
        pending = check_sources_ready(user=self.user, pdf_source_ids=[src.id])
        payload = build_not_ready_payload(pending)
        self.assertEqual(payload["code"], DOCUMENTS_NOT_READY)
        self.assertIn("scan.pdf", payload["error"])
        self.assertIn("Re-upload", payload["error"])
        # Telling a teacher to wait for a scan to finish processing is advice
        # that can never come true.
        self.assertNotIn("Wait for", payload["error"])


class UnreadableDuplicateTests(TestCase):
    """The repair path. The scanned-PDF gate tells a teacher to re-upload, and
    dedupe on `(user, sha256, status="ready")` handed back the same unusable
    source every time — so the advice the error message gives could never
    work, and no fix to ingestion could reach the file."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(
            id="u4", name="U4", email="u4@t.local", status="approved"
        )

    def test_unreadable_duplicate_is_discarded(self):
        from services.document_service import _reusable_duplicate

        stale = _pdf(self.user, status="ready", sha="dup1", name="scan.pdf")
        _image_chunk(pdf=stale)

        self.assertIsNone(
            _reusable_duplicate(self.user, "dup1", file_name="scan.pdf")
        )
        # Dropped, so the re-upload falls through to a real ingest.
        self.assertFalse(PdfSource.objects.filter(id=stale.id).exists())
        self.assertFalse(DocumentChunk.objects.filter(pdf_source_id=stale.id).exists())

    def test_readable_duplicate_is_still_reused(self):
        from services.document_service import _reusable_duplicate

        good = _pdf(self.user, status="ready", sha="dup2", name="ch.pdf")
        _chunk(pdf=good)

        self.assertEqual(
            _reusable_duplicate(self.user, "dup2", file_name="ch.pdf"), good
        )
        self.assertTrue(PdfSource.objects.filter(id=good.id).exists())

    def test_another_users_copy_is_untouched(self):
        from services.document_service import _reusable_duplicate

        other = User.objects.create(
            id="u5", name="U5", email="u5@t.local", status="approved"
        )
        theirs = _pdf(other, status="ready", sha="dup3", name="scan.pdf")
        _image_chunk(pdf=theirs)

        self.assertIsNone(
            _reusable_duplicate(self.user, "dup3", file_name="scan.pdf")
        )
        self.assertTrue(PdfSource.objects.filter(id=theirs.id).exists())
