from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.views.static import serve as static_serve
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from services.media_urls import fresh_signed_media_url, is_remote_storage


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


def serve_media(request, path: str):
    """Resolve a stable /media/<storage_path> URL to actual bytes.

    Persisted documents (chunk metadata, question payloads, TipTap docs)
    reference media by this stable URL only. With S3/MinIO storage we
    redirect to a presigned URL minted fresh per request, so nothing
    long-lived ever leaves the backend; with local storage we stream the
    file from MEDIA_ROOT (covers dev and non-S3 deployments where the
    frontend was 404ing on /media/pdf_images/... paths).
    """
    if ".." in path.split("/"):
        raise Http404("Invalid media path.")
    if is_remote_storage():
        signed = fresh_signed_media_url(path)
        if not signed:
            raise Http404("Object cannot be resolved.")
        return HttpResponseRedirect(signed)
    return static_serve(request, path, document_root=settings.MEDIA_ROOT)
