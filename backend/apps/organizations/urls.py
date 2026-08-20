from django.urls import path

from .views import (
    OrganizationDetailView,
    OrganizationInviteAcceptView,
    OrganizationInviteCreateView,
    OrganizationInviteRevokeView,
    OrganizationJoinView,
    OrganizationListView,
    OrganizationLogoView,
    OrganizationMemberApproveView,
    OrganizationMemberRejectView,
    OrganizationMemberRemoveView,
    OrganizationMembersListView,
    OrganizationSwitchView,
    OrganizationTeacherInviteView,
    OrganizationUsageSummaryView,
    PublicOrganizationListView,
    SuperAdminAnalyticsView,
)

urlpatterns = [
    # Literal routes first — Django tries patterns in order and <str:org_id>
    # would otherwise swallow these single-segment paths.
    path("public", PublicOrganizationListView.as_view(), name="organizations-public"),
    path("invites", OrganizationInviteCreateView.as_view(), name="organizations-invite-create"),
    path("invites/accept", OrganizationInviteAcceptView.as_view(), name="organizations-invite-accept"),
    path(
        "invites/<str:invite_id>",
        OrganizationInviteRevokeView.as_view(),
        name="organizations-invite-revoke",
    ),
    path("join", OrganizationJoinView.as_view(), name="organizations-join"),
    path("switch", OrganizationSwitchView.as_view(), name="organizations-switch"),
    path("usage", OrganizationUsageSummaryView.as_view(), name="organizations-usage"),
    path("analytics", SuperAdminAnalyticsView.as_view(), name="organizations-analytics"),
    path("", OrganizationListView.as_view(), name="organizations-list"),

    path("<str:org_id>", OrganizationDetailView.as_view(), name="organizations-detail"),
    path("<str:org_id>/logo", OrganizationLogoView.as_view(), name="organizations-logo"),
    path("<str:org_id>/members", OrganizationMembersListView.as_view(), name="organizations-members"),
    path(
        "<str:org_id>/invites",
        OrganizationTeacherInviteView.as_view(),
        name="organizations-teacher-invites",
    ),
    path(
        "<str:org_id>/members/<str:user_id>/approve",
        OrganizationMemberApproveView.as_view(),
        name="organizations-member-approve",
    ),
    path(
        "<str:org_id>/members/<str:user_id>/reject",
        OrganizationMemberRejectView.as_view(),
        name="organizations-member-reject",
    ),
    path(
        "<str:org_id>/members/<str:user_id>",
        OrganizationMemberRemoveView.as_view(),
        name="organizations-member-remove",
    ),
]
