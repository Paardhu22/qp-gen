from rest_framework.permissions import BasePermission


class IsAppUserAuthenticated(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and getattr(user, "is_authenticated", False))


class IsApprovedOrAdmin(BasePermission):
    """
    Allows access only to authenticated users who have been approved or are admins.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_superadmin", False)) or getattr(
            user, "status", "pending"
        ) in ["approved", "admin"]


class IsAdmin(BasePermission):
    """
    Allows access only to authenticated admin users.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_superadmin", False)) or getattr(
            user, "status", "pending"
        ) == "admin"


class IsSuperAdmin(BasePermission):
    """
    Allows access only to the platform-wide superadmin.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_superadmin", False))


def is_org_admin_anywhere(user) -> bool:
    """True when this account administers at least one school.

    Checks EVERY membership, not the active one. A teacher who administers
    school B while currently working as school A is still school B's
    administrator, and gating the endpoint on the active membership would make
    managing their other school impossible without switching first — for a
    check that the per-organization test below re-does properly anyway.
    """
    memberships = getattr(user, "memberships", None)
    if memberships is None:
        return False
    return any(
        m.role == "org_admin" and m.status == "approved" for m in memberships.all()
    )


def has_org_admin_membership(user, organization_id: str) -> bool:
    """True when this account holds an approved org_admin membership HERE.

    Purely about membership — the platform superadmin is not one, and is not
    treated as one here. Callers that want "may this person manage this
    school?" want `is_org_admin_of` below; this one answers "do they belong to
    it as an admin?", which is the question the invite and member screens ask
    before they decide whose school they are looking at.
    """
    membership = (
        user.membership_for(organization_id) if hasattr(user, "membership_for") else None
    )
    return bool(
        membership
        and membership.role == "org_admin"
        and membership.status == "approved"
    )


def is_org_admin_of(user, organization_id: str) -> bool:
    """May this account manage THIS school? The authorization check."""
    if getattr(user, "is_superadmin", False):
        return True
    return has_org_admin_membership(user, organization_id)


class IsOrgAdminOrSuperAdmin(BasePermission):
    """
    Allows the platform superadmin (any organization), or a user who
    administers at least one organization.

    This is the coarse gate — it answers "could this person be an admin of
    something?". Every view behind it must still check the specific
    organization with `is_org_admin_of`, because administering one school
    grants nothing at another.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superadmin", False):
            return True
        return is_org_admin_anywhere(user)

    def is_org_admin_of(self, user, organization_id: str) -> bool:
        return is_org_admin_of(user, organization_id)
