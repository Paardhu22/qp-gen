from django.urls import path

from .views import (
    AdminUserApproveView,
    AdminUserRejectView,
    AdminUsersListView,
    ProfileView,
)

urlpatterns = [
    path("profile", ProfileView.as_view(), name="profile"),
    path("dashboard", ProfileView.as_view(), name="dashboard"),
    
    # Admin User management routes
    path("users", AdminUsersListView.as_view(), name="admin-users-list"),
    path("users/<str:user_id>/approve", AdminUserApproveView.as_view(), name="admin-user-approve"),
    path("users/<str:user_id>/reject", AdminUserRejectView.as_view(), name="admin-user-reject"),
]
