import traceback

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from services.document_service import process_pdf_upload

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

        # Return "documentId" for API compatibility with the frontend.
        return Response({"documentId": pdf_source.id})
