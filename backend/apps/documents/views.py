from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAppUserAuthenticated
from apps.documents.serializers import DocumentUploadSerializer
from services.document_service import process_document_upload


class DocumentUploadView(APIView):
    permission_classes = [IsAppUserAuthenticated]

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            document = process_document_upload(
                file=serializer.validated_data["file"],
                user=request.user,
                project_id=serializer.validated_data.get("projectId") or None,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except Exception as exc:
            import traceback
            error_log = f"Error: {str(exc)}\n{traceback.format_exc()}\n"
            with open("upload_error.log", "a") as f:
                f.write(error_log)
            return Response({"error": f"Internal server error: {str(exc)}"}, status=500)

        return Response({"documentId": document.id})
