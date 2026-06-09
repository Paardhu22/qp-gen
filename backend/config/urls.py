from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
