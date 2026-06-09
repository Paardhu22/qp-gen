from django.urls import path

from .hsat_views import (
    HsatApplyView,
    HsatCatalogView,
    HsatChaptersView,
    HsatIngestView,
    HsatPaperSourcesView,
)

urlpatterns = [
    path("catalog/", HsatCatalogView.as_view(), name="hsat-catalog"),
    path("chapters/", HsatChaptersView.as_view(), name="hsat-chapters"),
    path("ingest/", HsatIngestView.as_view(), name="hsat-ingest"),
    path("apply/", HsatApplyView.as_view(), name="hsat-apply"),
    path(
        "papers/<str:paper_id>/sources/",
        HsatPaperSourcesView.as_view(),
        name="hsat-paper-sources",
    ),
]
