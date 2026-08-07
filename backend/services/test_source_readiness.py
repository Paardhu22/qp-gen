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
        cls.user = User.objects.create(id="u1", name="U1", email="u1@t.local")
        cls.other = User.objects.create(id="u2", name="U2", email="u2@t.local")

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
        cls.user = User.objects.create(id="pu", name="PU", email="pu@t.local")

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
