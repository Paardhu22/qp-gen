import traceback

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from services.document_service import process_pdf_upload, process_pdf_from_storage

from apps.documents.serializers import DocumentUploadSerializer


class DocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            pdf_source = process_pdf_upload(
                file=serializer.validated_data["file"],
                user=request.user,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except Exception as exc:
            with open("upload_error.log", "a") as f:
                f.write(f"Error: {exc}\n{traceback.format_exc()}\n")
            return Response({"error": f"Internal server error: {exc}"}, status=500)

        # Return "pdfSourceId" to match the new architecture.
        # `warnings` surfaces non-fatal degradations (e.g. PyMuPDF missing →
        # text-only extraction) so the UI can show them instead of failing
        # silently.
        warnings = getattr(pdf_source, "warnings", []) or []
        return Response({"pdfSourceId": pdf_source.id, "warnings": warnings})


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
            with open("upload_error.log", "a") as f:
                f.write(f"Confirm error: {exc}\n{traceback.format_exc()}\n")
            return Response({"error": f"Internal server error: {exc}"}, status=500)

        warnings = getattr(pdf_source, "warnings", []) or []
        return Response({"pdfSourceId": pdf_source.id, "warnings": warnings})
