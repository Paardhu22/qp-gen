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
        # status must be 'approved' or 'admin'
        return getattr(user, "status", "pending") in ["approved", "admin"]


class IsAdmin(BasePermission):
    """
    Allows access only to authenticated admin users.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return getattr(user, "status", "pending") == "admin"


class IsAdminOrSuperAdmin(BasePermission):
    """A platform-staff admin, or the platform superadmin.

    `IsAdmin` alone is not enough for the platform user list: the superadmin is
    flagged by `is_superadmin` and keeps `status="approved"`, so a check on
    status would lock the one account that manages every school out of the
    screen that lists every user.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_superadmin", False)) or (
            getattr(user, "status", "pending") == "admin"
        )


class IsSuperAdmin(BasePermission):
    """
    Allows access only to the platform-wide superadmin.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_superadmin", False))


class IsOrgAdminOrSuperAdmin(BasePermission):
    """
    Allows the platform superadmin (any organization), or a user whose
    approved Membership has role="org_admin" (their own organization only).
    Object-level checks compare against the organization resolved by the view.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superadmin", False):
            return True
        membership = getattr(user, "membership", None)
        return bool(
            membership
            and membership.role == "org_admin"
            and membership.status == "approved"
        )

    def is_org_admin_of(self, user, organization_id: str) -> bool:
        if getattr(user, "is_superadmin", False):
            return True
        membership = getattr(user, "membership", None)
        return bool(
            membership
            and membership.role == "org_admin"
            and membership.status == "approved"
            and membership.organization_id == organization_id
        )
