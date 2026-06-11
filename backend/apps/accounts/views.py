import logging

from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.common.permissions import IsAdmin
from services.cognito_service import add_user_to_group, remove_user_from_group

logger = logging.getLogger("[ACCOUNTS_VIEWS]")


def get_cognito_username(user: User) -> str:
    """
    Cognito admin APIs require the canonical 36-character sub UUID.
    Restore hyphens to our local 32-character ID to get the original sub.
    """
    uid = user.id
    if len(uid) == 32:
        return f"{uid[:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}"
    return uid


class ProfileView(APIView):
    """
    Retrieve the current user's profile.
    This view only requires IsAuthenticated, allowing pending or rejected users
    to retrieve their status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class AdminUsersListView(APIView):
    """
    List all local users. Accessible only to administrators.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        status_filter = request.query_params.get("status")
        users = User.objects.all().order_by("-created_at")

        if status_filter:
            users = users.filter(status=status_filter)

        # Basic pagination
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
        total = users.count()
        users = users[offset : offset + limit]

        return Response({
            "total": total,
            "limit": limit,
            "offset": offset,
            "users": UserSerializer(users, many=True).data,
        })


class AdminUserApproveView(APIView):
    """
    Approve a pending user.
    """
    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise Http404("User not found")

        cognito_username = get_cognito_username(user)

        try:
            # Add user to Cognito group 'approved'
            add_user_to_group(cognito_username, "approved")
            # Remove user from Cognito group 'pending'
            remove_user_from_group(cognito_username, "pending")
        except Exception as e:
            logger.error("Failed to update Cognito groups for user %s: %s", user.email, e)
            return Response({"error": f"Failed to sync with Cognito: {str(e)}"}, status=500)

        # Update local status
        user.status = "approved"
        user.save(update_fields=["status"])

        logger.info("Admin %s approved user %s", request.user.email, user.email)
        return Response(UserSerializer(user).data)


class AdminUserRejectView(APIView):
    """
    Reject or block a user.
    """
    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise Http404("User not found")

        cognito_username = get_cognito_username(user)

        try:
            # Remove from approved and admin groups in Cognito
            remove_user_from_group(cognito_username, "approved")
            remove_user_from_group(cognito_username, "admin")
            # Add back to pending (so they are unapproved in Cognito)
            add_user_to_group(cognito_username, "pending")
        except Exception as e:
            logger.error("Failed to update Cognito groups for user %s: %s", user.email, e)
            return Response({"error": f"Failed to sync with Cognito: {str(e)}"}, status=500)

        # Update local status to rejected
        user.status = "rejected"
        user.save(update_fields=["status"])

        logger.info("Admin %s rejected user %s", request.user.email, user.email)
        return Response(UserSerializer(user).data)
