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

from django.test import TestCase

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
