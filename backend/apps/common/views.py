import logging
import posixpath

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.views.static import serve as static_serve
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from services.storage.media_urls import fresh_signed_media_url, is_remote_storage

logger = logging.getLogger(__name__)

#: What `?inline=1` will stream: raster images only. SVG is left out on purpose
#: (it can carry script), and so is every other file type.
INLINE_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
#: A logo or a figure for an export, not a general file proxy.
INLINE_MAX_BYTES = 15 * 1024 * 1024
_CHUNK = 64 * 1024


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


def _stream_inline_image(request, path: str):
    """The image's bytes, straight from storage, instead of a redirect.

    Exports (PDF, Word) have to read an image's pixels in the browser, which
    needs a CORS-clean response. A redirect to a presigned S3 URL is not one:
    after a cross-origin redirect the browser asks S3 with ``Origin: null``,
    and a bucket whose CORS rule names the app's origin answers with no CORS
    headers, so the download is blocked and the image is left out of the file.
    Streaming the bytes from here puts them behind django-cors-headers, which
    already allows the frontend, whatever the bucket's own rule says.

    Returns None when the request is not one this handles (not an image, or
    unknown extension), so the caller falls through to the normal redirect.
    """
    extension = posixpath.splitext(path)[1].lower()
    content_type = INLINE_IMAGE_TYPES.get(extension)
    if content_type is None:
        return None
    try:
        size = default_storage.size(path)
        if size > INLINE_MAX_BYTES:
            return HttpResponse(status=413)
        stored = default_storage.open(path, "rb")
    except Exception as exc:  # a missing key surfaces as botocore's ClientError
        logger.warning("Inline media read failed for %s: %s", path, exc)
        raise Http404("Object cannot be resolved.") from exc

    def chunks():
        try:
            while True:
                block = stored.read(_CHUNK)
                if not block:
                    return
                yield block
        finally:
            stored.close()

    response = StreamingHttpResponse(chunks(), content_type=content_type)
    response["Content-Length"] = str(size)
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    # Short, and public: the path is the same one the redirect already exposes.
    response["Cache-Control"] = "public, max-age=300"
    return response


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
        # `?inline=1`: the bytes themselves, for the exporters (see above).
        if request.GET.get("inline") == "1":
            streamed = _stream_inline_image(request, path)
            if streamed is not None:
                return streamed
        signed = fresh_signed_media_url(path)
        if not signed:
            raise Http404("Object cannot be resolved.")
        # A "signed" URL that is this same path would loop the browser until
        # it gives up — what every image did after the Django 5.2 upgrade. If
        # it ever happens again, serve the bytes instead of the redirect.
        if signed.split("?", 1)[0] != request.path:
            return HttpResponseRedirect(signed)
    return static_serve(request, path, document_root=settings.MEDIA_ROOT)
