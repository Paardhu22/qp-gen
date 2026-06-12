from django.contrib import admin
from django.urls import include, path, re_path

from apps.common.views import serve_media
from config.debug_views import science_engine_health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("debug/science-engine-health", science_engine_health),
    path("api/", include("apps.common.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/documents/", include("apps.documents.urls")),
    path("api/hsat/", include("apps.documents.hsat_urls")),
    path("api/generation/", include("apps.generation.urls")),
    path("api/projects/", include("apps.projects.urls")),
    path("api/storage/", include("apps.storage.urls")),
    # Stable media resolver: redirects to a fresh presigned URL on S3,
    # streams from MEDIA_ROOT locally. Replaces the DEBUG-only static()
    # route, which 404'd every /media/pdf_images/... request when files
    # lived in S3 (or whenever DEBUG was off).
    re_path(r"^media/(?P<path>.+)$", serve_media, name="serve-media"),
]
