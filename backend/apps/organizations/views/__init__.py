"""Organization views, grouped by what they manage. URL config imports from here."""

from .invites import (
    OrganizationInviteAcceptView,
    OrganizationInviteCreateView,
    OrganizationInviteRevokeView,
    OrganizationTeacherInviteView,
)
from .directory import (
    OrganizationDetailView,
    OrganizationListView,
    OrganizationLogoView,
    OrganizationUsageSummaryView,
    PublicOrganizationListView,
)
from .membership import (
    OrganizationJoinView,
    OrganizationMemberApproveView,
    OrganizationMemberAssignView,
    OrganizationMemberPapersView,
    OrganizationMemberRejectView,
    OrganizationMemberRemoveView,
    OrganizationMemberRoleView,
    OrganizationMembersListView,
    OrganizationSwitchView,
)
from .platform import (
    PlatformSuperadminView,
    PlatformUserDeleteView,
    SuperAdminAnalyticsView,
)

__all__ = [
    "OrganizationDetailView",
    "OrganizationInviteAcceptView",
    "OrganizationInviteCreateView",
    "OrganizationInviteRevokeView",
    "OrganizationJoinView",
    "OrganizationListView",
    "OrganizationLogoView",
    "OrganizationMemberApproveView",
    "OrganizationMemberAssignView",
    "OrganizationMemberPapersView",
    "OrganizationMemberRejectView",
    "OrganizationMemberRemoveView",
    "OrganizationMemberRoleView",
    "OrganizationMembersListView",
    "OrganizationSwitchView",
    "OrganizationTeacherInviteView",
    "OrganizationUsageSummaryView",
    "PlatformSuperadminView",
    "PlatformUserDeleteView",
    "PublicOrganizationListView",
    "SuperAdminAnalyticsView",
]
