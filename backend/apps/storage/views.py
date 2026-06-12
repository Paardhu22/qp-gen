"""Storage endpoints: upload exports to S3 and retrieve fresh presigned URLs.

POST /api/storage/upload-export/
    Upload a generated PDF/DOCX export; backend stores it in S3 and records
    the key on the relevant model row.

GET  /api/storage/export-url/?key=<s3_key>
    Validate ownership and return a fresh presigned GET URL (900 s).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils.text import slugify
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import ExportRecord, Paper
from services.s3_client import (
    S3NotConfigured,
    generate_presigned_get_url,
    is_configured,
    upload_bytes,
)

logger = logging.getLogger("[STORAGE]")

ALLOWED_EXPORT_TYPES = {"question_paper", "answer_script", "question_bank"}
ALLOWED_FILE_FORMATS = {"pdf", "docx"}
CONTENT_TYPE_MAP = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _build_s3_key(
    export_type: str,
    file_format: str,
    user_id: str,
    paper: Paper | None,
) -> str:
    ext = file_format  # 'pdf' or 'docx'
    if export_type == "question_paper":
        assert paper is not None
        slug = slugify(paper.title) or "paper"
        return f"question-papers/{user_id}/{paper.id}/{slug}.{ext}"
    if export_type == "answer_script":
        assert paper is not None
        slug = slugify(paper.title) or "answer-key"
        return f"answer-scripts/{user_id}/{paper.id}/{slug}-answer-key.{ext}"
    # question_bank — no persistent paper object; use UTC timestamp
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"question_bank/{user_id}/{ts}.{ext}"


class UploadExportView(APIView):
    """Accept a generated PDF/DOCX from the browser, store in S3, record key."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_configured():
            return Response(
                {"error": "S3 is not configured on this server."},
                status=503,
            )

        # --- validate inputs ---
        export_type = request.data.get("export_type", "")
        file_format = request.data.get("file_format", "")
        paper_id = request.data.get("paper_id") or None
        uploaded_file = request.FILES.get("file")

        if export_type not in ALLOWED_EXPORT_TYPES:
            return Response(
                {"error": f"export_type must be one of {sorted(ALLOWED_EXPORT_TYPES)}"},
                status=400,
            )
        if file_format not in ALLOWED_FILE_FORMATS:
            return Response(
                {"error": f"file_format must be one of {sorted(ALLOWED_FILE_FORMATS)}"},
                status=400,
            )
        if uploaded_file is None:
            return Response({"error": "Missing file."}, status=400)

        max_bytes = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(100 * 1024 * 1024)))
        if uploaded_file.size > max_bytes:
            return Response(
                {"error": f"File exceeds maximum size of {max_bytes} bytes."},
                status=400,
            )

        # --- ownership check ---
        paper: Paper | None = None
        if export_type in {"question_paper", "answer_script"}:
            if not paper_id:
                return Response(
                    {"error": "paper_id is required for question_paper and answer_script exports."},
                    status=400,
                )
            try:
                paper = Paper.objects.get(id=paper_id, user=request.user)
            except Paper.DoesNotExist:
                return Response(
                    {"error": "Paper not found or access denied."},
                    status=404,
                )

        # --- build key and upload ---
        s3_key = _build_s3_key(export_type, file_format, request.user.id, paper)
        content_type = CONTENT_TYPE_MAP[file_format]

        try:
            data = uploaded_file.read()
            upload_bytes(s3_key, data, content_type=content_type)
        except S3NotConfigured as exc:
            logger.error("S3 not configured: %s", exc)
            return Response({"error": "S3 storage is not available."}, status=503)
        except (ClientError, BotoCoreError) as exc:
            logger.error("S3 upload failed for key=%s: %s", s3_key, exc)
            return Response({"error": "Upload to storage failed. Please try again."}, status=502)

        # --- persist key on the right model ---
        if paper is not None:
            if file_format == "pdf":
                Paper.objects.filter(pk=paper.pk).update(s3_pdf_key=s3_key)
            else:
                Paper.objects.filter(pk=paper.pk).update(s3_docx_key=s3_key)
        else:
            # question_bank — create a standalone record
            ExportRecord.objects.create(
                user=request.user,
                s3_key=s3_key,
                file_format=file_format,
            )

        logger.info(
            "Export uploaded: type=%s format=%s key=%s user=%s",
            export_type,
            file_format,
            s3_key,
            request.user.id,
        )
        return Response({"s3_key": s3_key}, status=201)


class ExportUrlView(APIView):
    """Return a fresh presigned GET URL for a previously-uploaded export key."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_configured():
            return Response(
                {"error": "S3 is not configured on this server."},
                status=503,
            )

        s3_key = request.query_params.get("key", "").strip()
        if not s3_key:
            return Response({"error": "Missing key parameter."}, status=400)

        # Verify the requesting user owns this key.
        user = request.user
        owns = (
            Paper.objects.filter(user=user, s3_pdf_key=s3_key).exists()
            or Paper.objects.filter(user=user, s3_docx_key=s3_key).exists()
            or ExportRecord.objects.filter(user=user, s3_key=s3_key).exists()
        )
        if not owns:
            return Response({"error": "Not found or access denied."}, status=404)

        try:
            url = generate_presigned_get_url(s3_key, expire=900)
        except (ClientError, BotoCoreError, S3NotConfigured) as exc:
            logger.error("Presigned URL generation failed for key=%s: %s", s3_key, exc)
            return Response({"error": "Could not generate download URL."}, status=502)

        return Response({"url": url, "expires_in": 900})
