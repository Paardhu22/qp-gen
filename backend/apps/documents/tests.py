"""Regression tests for the PDF source upload pipeline.

Cluster B: PDF source upload was failing in production with
``NotNullViolation: null value in column "content_type"``. The fix:
``services.document_service.process_pdf_upload`` now captures
``file.content_type`` (defaulting to ``"application/pdf"``) and passes it
to ``PdfSource.objects.create``, and ``PdfSource`` carries a matching
field with a safe default so the column is always populated even when
the client omits the Content-Type header.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.documents.models import PdfSource


class _FakeUploadedFile:
    """Mimics the subset of Django's ``UploadedFile`` that the upload
    pipeline reads."""

    def __init__(self, *, name: str, content: bytes, content_type: str | None):
        self.name = name
        self.content_type = content_type
        self._content = content

    def read(self) -> bytes:
        return self._content


class PdfSourceContentTypeRegressionTests(TestCase):
    """Cluster B regression: every successful upload must populate
    ``pdf_source.content_type`` so the legacy NOT NULL column in
    production accepts the row."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create(
            id="test-user-content-type",
            name="Tester",
            email="content-type@test.local",
        )

    def _patch_pipeline(self):
        """Stub the heavy parts (PDF parse, embeddings, image-store) so
        the test exercises the wiring without external services."""
        patchers = [
            patch(
                "services.document_service.extract_text_from_pdf",
                return_value={
                    "text": "hello world",
                    "pages": [{"pageNumber": 1, "content": "hello world"}],
                    "images": [],
                    "metadata": {},
                },
            ),
            patch(
                "services.document_service.process_semantic_pipeline",
                return_value=[],
            ),
            patch(
                "services.document_service.chunk_text",
                return_value=[type("C", (), {"content": "hello", "page": 1, "chunk_index": 0, "metadata": {}})()],
            ),
            patch(
                "services.document_service.generate_embeddings",
                return_value=[[0.0] * 1536],
            ),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def test_upload_with_explicit_content_type_persists_it(self) -> None:
        self._patch_pipeline()
        from services.document_service import process_pdf_upload

        fake_file = _FakeUploadedFile(
            name="trignometry.pdf",
            content=b"fake-pdf-bytes",
            content_type="application/pdf",
        )
        pdf_source = process_pdf_upload(file=fake_file, user=self.user)

        pdf_source.refresh_from_db()
        self.assertEqual(pdf_source.content_type, "application/pdf")
        self.assertEqual(pdf_source.name, "trignometry.pdf")

    def test_upload_with_missing_content_type_falls_back_to_default(self) -> None:
        """If the client omits Content-Type (some test clients and curl
        invocations do), the upload must still succeed — the NOT NULL
        constraint is satisfied by the application/pdf default."""
        self._patch_pipeline()
        from services.document_service import process_pdf_upload

        fake_file = _FakeUploadedFile(
            name="surfaceareavol.pdf",
            content=b"fake-pdf-bytes",
            content_type=None,
        )
        pdf_source = process_pdf_upload(file=fake_file, user=self.user)

        pdf_source.refresh_from_db()
        self.assertEqual(pdf_source.content_type, "application/pdf")

    def test_model_default_satisfies_not_null(self) -> None:
        """Even a direct ``create()`` call that omits ``content_type``
        must succeed because the model carries a default; this guards
        against future call sites regressing the upload fix."""
        pdf_source = PdfSource.objects.create(
            name="legacy.pdf",
            size=42,
            user=self.user,
        )
        pdf_source.refresh_from_db()
        self.assertEqual(pdf_source.content_type, "application/pdf")


class UploadErrorLoggingTests(TestCase):
    """P0 statelessness pass: upload failures go to the app logger, never
    to a local upload_error.log file (ephemeral EC2 disk, multi-instance)."""

    LOG_FILE = "upload_error.log"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create(
            id="loguser000000000000000000000001a",
            name="Logger",
            email="logger@test.local",
        )

    def setUp(self) -> None:
        import os

        from rest_framework.test import APIClient

        # Defensive: a stale artifact from pre-fix code must not skew the
        # "no file created" assertion.
        if os.path.exists(self.LOG_FILE):
            os.remove(self.LOG_FILE)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _assert_no_log_file(self) -> None:
        import os

        self.assertFalse(
            os.path.exists(self.LOG_FILE),
            "upload error handling must not write a local log file",
        )

    def test_upload_failure_logs_and_writes_no_file(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        with patch(
            "apps.documents.views.process_pdf_upload",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs("apps.documents.views", level="ERROR") as logs:
                response = self.client.post(
                    "/api/documents/upload",
                    {"file": SimpleUploadedFile("t.pdf", b"%PDF", content_type="application/pdf")},
                    format="multipart",
                )

        self.assertEqual(response.status_code, 500)
        self.assertIn("PDF upload failed", logs.output[0])
        self._assert_no_log_file()

    def test_confirm_failure_logs_and_writes_no_file(self) -> None:
        with patch(
            "apps.documents.views.process_pdf_from_storage",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs("apps.documents.views", level="ERROR") as logs:
                response = self.client.post(
                    "/api/documents/confirm",
                    {"key": "uploads/u/x.pdf"},
                    format="json",
                )

        self.assertEqual(response.status_code, 500)
        self.assertIn("confirm failed", logs.output[0])
        self._assert_no_log_file()


@override_settings(HSAT_CHAPTER_CONCURRENCY=1)
class HsatReingestTests(TestCase):
    """Applying a book must never re-read chapters it has already read.

    Chapter concurrency is pinned to 1 because the test database is
    in-memory SQLite, which locks under the ThreadPoolExecutor the real
    ingest uses against Postgres. Nothing here is about concurrency.

    ``ingest_hsat_book_async`` flips the row to "processing" before it
    spawns its worker, which made every status-based skip inside
    ``ingest_hsat_book`` unreachable from the API: each apply re-downloaded
    and re-parsed every selected chapter and bulk_created a SECOND copy of
    its chunks. That is what made "apply this source" slow on an already
    indexed book, and it handed Model 1 the same chapter twice.

    The skip now keys off persisted chunks, so it holds no matter what the
    book's status says.
    """

    KEYS = [
        "input-pdfs/class 10/Science/Science/CH1 - Reactions.pdf",
        "input-pdfs/class 10/Science/Science/CH2 - Acids.pdf",
    ]

    def _fake_extract(self, **kwargs):
        from apps.documents.models import DocumentChunk

        DocumentChunk.objects.create(
            content="chapter text",
            chunk_index=0,
            hsat_source=kwargs["hsat_source"],
            metadata={"s3_key": kwargs["extra_metadata"]["s3_key"]},
        )
        return {"total_chunks": 1, "text_chunks": 1, "image_chunks": 0}

    def setUp(self) -> None:
        patchers = [
            patch("services.hsat_catalog.get_book_keys", return_value=self.KEYS),
            patch("services.hsat_service.is_configured", return_value=True),
            patch("services.hsat_service.download_to_buffer", return_value=b"pdf"),
            patch(
                "services.hsat_service.extract_and_persist_chunks",
                side_effect=self._fake_extract,
            ),
        ]
        started = [p.start() for p in patchers]
        for p in patchers:
            self.addCleanup(p.stop)
        #: The stubbed chapter reader — how many times it ran, and with what.
        self.extract = started[-1]

    def _own_and_ingest(self, chapter_keys):
        """Reproduce what the async helper does before spawning its worker."""
        from services.hsat_service import get_or_create_source, ingest_hsat_book

        source = get_or_create_source("10", "Science", "Science")
        if source.status != "processing":
            source.status = "processing"
            source.save(update_fields=["status"])
        return ingest_hsat_book(
            "10", "Science", "Science", chapter_keys=chapter_keys
        )

    def test_reapplying_the_same_chapters_writes_no_duplicate_chunks(self) -> None:
        from apps.documents.models import DocumentChunk

        self._own_and_ingest(self.KEYS)
        self.assertEqual(DocumentChunk.objects.count(), 2)
        first_calls = self.extract.call_count

        source = self._own_and_ingest(self.KEYS)

        self.assertEqual(self.extract.call_count, first_calls)
        self.assertEqual(DocumentChunk.objects.count(), 2)
        self.assertEqual(source.status, "ready")

    def test_a_newly_picked_chapter_is_topped_up_alone(self) -> None:
        from apps.documents.models import DocumentChunk

        self._own_and_ingest([self.KEYS[0]])
        self.assertEqual(DocumentChunk.objects.count(), 1)

        # Now the teacher also ticks chapter 2. Only chapter 2 is read.
        self._own_and_ingest(self.KEYS)

        keys_read = [
            c.kwargs["extra_metadata"]["s3_key"]
            for c in self.extract.call_args_list
        ]
        self.assertEqual(keys_read, [self.KEYS[0], self.KEYS[1]])
        self.assertEqual(DocumentChunk.objects.count(), 2)

    def test_async_helper_leaves_a_fully_ingested_book_ready(self) -> None:
        """A re-apply must not park a readable book in "processing" — that
        row is what blocks generation and shows "Preparing this book…"."""
        from services.hsat_service import ingest_hsat_book_async

        self._own_and_ingest(self.KEYS)
        source = ingest_hsat_book_async(
            "10", "Science", "Science", chapter_keys=self.KEYS
        )

        self.assertEqual(source.status, "ready")
