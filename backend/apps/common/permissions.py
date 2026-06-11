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
