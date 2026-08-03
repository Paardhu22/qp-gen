from django.urls import path

from .views import (
    AdminUserApproveView,
    AdminUserRejectView,
    AdminUsersListView,
    BrandAssetDetailView,
    BrandAssetListView,
    BrandKitView,
    ProfileView,
)

urlpatterns = [
    path("profile", ProfileView.as_view(), name="profile"),
    path("dashboard", ProfileView.as_view(), name="dashboard"),
    
    # The school's identity — name, address, colours, and its logos. Read once
    # and applied to every paper header, instead of being retyped onto each.
    path("brand-kit", BrandKitView.as_view(), name="brand-kit"),
    path("brand-kit/assets", BrandAssetListView.as_view(), name="brand-assets"),
    path(
        "brand-kit/assets/<str:asset_id>",
        BrandAssetDetailView.as_view(),
        name="brand-asset-detail",
    ),

    # Admin User management routes
    path("users", AdminUsersListView.as_view(), name="admin-users-list"),
    path("users/<str:user_id>/approve", AdminUserApproveView.as_view(), name="admin-user-approve"),
    path("users/<str:user_id>/reject", AdminUserRejectView.as_view(), name="admin-user-reject"),
]
