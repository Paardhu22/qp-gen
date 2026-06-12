"""Tests for the storage upload-export and export-url endpoints."""

from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.projects.models import ExportRecord, Paper, Project


def _make_user(uid, email):
    return User.objects.create(id=uid, name="Test", email=email)


def _make_project(user):
    return Project.objects.create(name="Test Project", user=user)


def _make_paper(user, project, title="Math Paper"):
    return Paper.objects.create(
        title=title,
        content="{}",
        project=project,
        user=user,
    )


class UploadExportAuthTest(TestCase):
    """Unauthenticated requests must be rejected."""

    def test_unauthenticated_returns_401_or_403(self):
        client = APIClient()
        response = client.post("/api/storage/upload-export/", {})
        self.assertIn(response.status_code, (401, 403))


class UploadExportOwnershipTest(TestCase):
    """A paper belonging to a different user must return 404."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = _make_user("owner01234567890123456789012345", "owner@test.local")
        cls.other = _make_user("other01234567890123456789012345", "other@test.local")
        cls.project = _make_project(cls.owner)
        cls.paper = _make_paper(cls.owner, cls.project)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.other)

    @patch("apps.storage.views.is_configured", return_value=True)
    def test_wrong_user_paper_returns_404(self, _mock_cfg):
        pdf_bytes = b"%PDF-1.4 fake"
        response = self.client.post(
            "/api/storage/upload-export/",
            {
                "file": BytesIO(pdf_bytes),
                "export_type": "question_paper",
                "file_format": "pdf",
                "paper_id": self.paper.id,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)


class UploadExportKeyFormatTest(TestCase):
    """Verify the S3 key pattern matches the naming convention."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("keyuser234567890123456789012345", "keyuser@test.local")
        cls.project = _make_project(cls.user)
        cls.paper = _make_paper(cls.user, cls.project, title="Class 10 Math")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("apps.storage.views.upload_bytes")
    @patch("apps.storage.views.is_configured", return_value=True)
    def test_question_paper_pdf_key_format(self, _mock_cfg, mock_upload):
        response = self.client.post(
            "/api/storage/upload-export/",
            {
                "file": BytesIO(b"%PDF fake"),
                "export_type": "question_paper",
                "file_format": "pdf",
                "paper_id": self.paper.id,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        key = response.data["s3_key"]
        expected_prefix = f"question-papers/{self.user.id}/{self.paper.id}/"
        self.assertTrue(key.startswith(expected_prefix), f"Key {key!r} does not start with {expected_prefix!r}")
        self.assertTrue(key.endswith(".pdf"))
        mock_upload.assert_called_once()

    @patch("apps.storage.views.upload_bytes")
    @patch("apps.storage.views.is_configured", return_value=True)
    def test_answer_script_docx_key_format(self, _mock_cfg, mock_upload):
        response = self.client.post(
            "/api/storage/upload-export/",
            {
                "file": BytesIO(b"PK fake docx"),
                "export_type": "answer_script",
                "file_format": "docx",
                "paper_id": self.paper.id,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        key = response.data["s3_key"]
        self.assertTrue(key.startswith(f"answer-scripts/{self.user.id}/{self.paper.id}/"))
        self.assertTrue(key.endswith("-answer-key.docx"))

    @patch("apps.storage.views.upload_bytes")
    @patch("apps.storage.views.is_configured", return_value=True)
    def test_question_bank_key_format(self, _mock_cfg, mock_upload):
        response = self.client.post(
            "/api/storage/upload-export/",
            {
                "file": BytesIO(b"%PDF bank"),
                "export_type": "question_bank",
                "file_format": "pdf",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        key = response.data["s3_key"]
        self.assertTrue(key.startswith(f"question_bank/{self.user.id}/"))
        self.assertTrue(key.endswith(".pdf"))

    @patch("apps.storage.views.upload_bytes")
    @patch("apps.storage.views.is_configured", return_value=True)
    def test_paper_s3_key_persisted(self, _mock_cfg, mock_upload):
        response = self.client.post(
            "/api/storage/upload-export/",
            {
                "file": BytesIO(b"%PDF fake"),
                "export_type": "question_paper",
                "file_format": "pdf",
                "paper_id": self.paper.id,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.s3_pdf_key, response.data["s3_key"])

    @patch("apps.storage.views.upload_bytes")
    @patch("apps.storage.views.is_configured", return_value=True)
    def test_export_record_created_for_question_bank(self, _mock_cfg, mock_upload):
        before = ExportRecord.objects.filter(user=self.user).count()
        self.client.post(
            "/api/storage/upload-export/",
            {
                "file": BytesIO(b"%PDF bank"),
                "export_type": "question_bank",
                "file_format": "pdf",
            },
            format="multipart",
        )
        after = ExportRecord.objects.filter(user=self.user).count()
        self.assertEqual(after, before + 1)


class ExportUrlOwnershipTest(TestCase):
    """export-url must reject keys the user does not own."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = _make_user("urlown01234567890123456789012", "urlown@test.local")
        cls.other = _make_user("urloth01234567890123456789012", "urloth@test.local")
        cls.project = _make_project(cls.owner)
        cls.paper = _make_paper(cls.owner, cls.project)
        cls.paper.s3_pdf_key = "question-papers/urlown/fakeid/paper.pdf"
        cls.paper.save(update_fields=["s3_pdf_key"])

    def test_owner_can_get_url(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        with patch("apps.storage.views.is_configured", return_value=True), \
             patch("apps.storage.views.generate_presigned_get_url", return_value="https://s3.example.com/signed"):
            response = client.get(
                "/api/storage/export-url/",
                {"key": self.paper.s3_pdf_key},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("url", response.data)

    def test_other_user_gets_404(self):
        client = APIClient()
        client.force_authenticate(user=self.other)
        with patch("apps.storage.views.is_configured", return_value=True):
            response = client.get(
                "/api/storage/export-url/",
                {"key": self.paper.s3_pdf_key},
            )
        self.assertEqual(response.status_code, 404)
