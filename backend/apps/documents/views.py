import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from services.document_service import process_pdf_upload, process_pdf_from_storage

from apps.documents.serializers import DocumentUploadSerializer

logger = logging.getLogger(__name__)


class DocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # background=True returns as soon as the row + raw file are saved;
            # extraction / captioning / embedding run on a worker thread and the
            # client polls DocumentStatusView until status flips to ready/error.
            pdf_source = process_pdf_upload(
                file=serializer.validated_data["file"],
                user=request.user,
                background=True,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except Exception as exc:
            # Stateless box: errors go to the app logger (stdout/stderr →
            # CloudWatch), never to a local file the instance loses on
            # recycle. logger.exception carries the traceback.
            logger.exception("PDF upload failed")
            return Response({"error": f"Internal server error: {exc}"}, status=500)

        # Return "pdfSourceId" to match the new architecture.
        # `status` is "ready" for a deduped/cached source, otherwise "processing"
        # — the client polls the status endpoint. `warnings` surfaces non-fatal
        # degradations (e.g. PyMuPDF missing → text-only extraction).
        warnings = getattr(pdf_source, "warnings", []) or []
        return Response(
            {
                "pdfSourceId": pdf_source.id,
                "status": pdf_source.status,
                "warnings": warnings,
            }
        )


class DocumentStatusView(APIView):
    """Poll target for the async upload flow: report a PdfSource's ingest state.

    Returns {status, chunk_count, error}. Scoped to the requesting user so one
    user can't probe another's sources.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, source_id):
        from apps.documents.models import DocumentChunk, PdfSource

        source = PdfSource.objects.filter(id=source_id, user=request.user).first()
        if source is None:
            return Response({"error": "Not found"}, status=404)

        # PdfSource has no chunk_count column (only HsatSource does); count the
        # chunks written so far so the UI can show live ingest progress.
        chunk_count = DocumentChunk.objects.filter(pdf_source=source).count()

        return Response(
            {
                "id": source.id,
                "status": source.status,
                "chunk_count": chunk_count,
                "error": source.error or None,
            }
        )


# Presigned upload flow: generate a presigned POST for direct-to-S3 uploads
# and a confirm endpoint to notify the backend to process the stored object.
import boto3
from uuid import uuid4
from django.conf import settings
from django.http import JsonResponse
from django.core.files.storage import default_storage


class PresignUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Request body: { name, content_type, size }
        Returns presigned POST data or `{ enabled: false }` if S3 not configured.
        """
        if not getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
            return Response({"enabled": False}, status=400)

        name = request.data.get("name") or "upload.pdf"
        content_type = request.data.get("content_type") or "application/pdf"
        size = int(request.data.get("size") or 0)

        # Create a unique key
        key = f"uploads/{request.user.id}/{uuid4().hex}_{name}"

        client = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
            endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None) or None,
        )

        import os
        max_size = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(100 * 1024 * 1024)))
        conditions = [["content-length-range", 1, max_size], {"Content-Type": content_type}]

        try:
            post = client.generate_presigned_post(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=key,
                Fields={"Content-Type": content_type},
                Conditions=conditions,
                ExpiresIn=getattr(settings, "AWS_QUERYSTRING_EXPIRE", 3600),
            )
        except Exception as exc:
            return Response({"error": str(exc)}, status=500)

        return JsonResponse({"url": post["url"], "fields": post["fields"], "key": key})


class ConfirmUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Request body: { key, name?, content_type? }

        Verifies the object exists in storage and triggers processing
        via process_pdf_from_storage, which avoids the double-save that
        would occur if we re-uploaded the file. Returns `pdfSourceId`.
        """
        key = request.data.get("key")
        if not key:
            return Response({"error": "Missing key"}, status=400)

        try:
            pdf_source = process_pdf_from_storage(
                key=key,
                user=request.user,
                name=request.data.get("name") or "upload.pdf",
                content_type=request.data.get("content_type") or "application/pdf",
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except Exception as exc:
            logger.exception("Presigned-upload confirm failed for key=%s", key)
            return Response({"error": f"Internal server error: {exc}"}, status=500)

        warnings = getattr(pdf_source, "warnings", []) or []
        return Response({"pdfSourceId": pdf_source.id, "warnings": warnings})
