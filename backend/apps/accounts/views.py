import logging

from django.db.models import Q
from django.http import Http404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import BrandAsset, User
from apps.accounts.serializers import UserSerializer
from apps.common.permissions import IsAdmin, IsAdminOrSuperAdmin
from services.brand_kit import (
    delete_logo,
    get_or_create_kit,
    serialize_asset,
    serialize_kit,
    store_logo,
    valid_accent_color,
)
from services.cognito_service import add_user_to_group, remove_user_from_group
from services.email_service import (
    send_membership_approved_email,
    send_membership_rejected_email,
)

logger = logging.getLogger("[ACCOUNTS_VIEWS]")


def get_cognito_username(user: User) -> str:
    """
    Return the identifier to pass as `Username` to Cognito admin APIs.

    Their `Username` parameter takes the pool Username OR any alias attribute,
    and this pool aliases on email — so the email works for every user.

    It must NOT be the sub. That only ever worked while Cognito generated the
    Username itself and the two happened to be equal; users created through
    admin_create_user get an independent Username, and passing their sub fails
    with UserNotFoundException (which is exactly what AdminAddUserToGroup did
    to the seeded superadmin). Rebuilding the sub from User.id is therefore
    wrong here, even though User.id is genuinely derived from the sub.
    """
    return user.email


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
    List all local users. Accessible to platform admins and the superadmin.

    `?q=` filters on name or email; `?status=` on the account status. Both are
    applied before pagination, so `total` counts the filtered set rather than
    the whole table — otherwise a search would report a page count for results
    it isn't showing.
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        status_filter = request.query_params.get("status")
        query = (request.query_params.get("q") or "").strip()
        # The membership join feeds UserSerializer.get_membership, which the
        # admin table reads for every row — without it this is N+1.
        users = User.objects.select_related(
            "membership", "membership__organization"
        ).order_by("-created_at")

        if status_filter:
            users = users.filter(status=status_filter)

        if query:
            users = users.filter(
                Q(name__icontains=query) | Q(email__icontains=query)
            )

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

        membership = getattr(user, "membership", None)
        send_membership_approved_email(
            to_email=user.email,
            user_name=user.name,
            organization_name=membership.organization.name if membership else None,
        )

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

        membership = getattr(user, "membership", None)
        send_membership_rejected_email(
            to_email=user.email,
            user_name=user.name,
            organization_name=membership.organization.name if membership else None,
        )

        logger.info("Admin %s rejected user %s", request.user.email, user.email)
        return Response(UserSerializer(user).data)


class BrandKitView(APIView):
    """The school's identity: read it, or change part of it.

    GET creates the kit on first touch, so the client never has to distinguish
    "no kit yet" from "an empty kit" — both are a blank form.

    PATCH touches only the keys the body names. Every field is independently
    optional and independently clearable, which is why each is tested with
    `in request.data` rather than for truthiness: a teacher removing their
    address must be able to send an empty string and have it stick.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        kit = get_or_create_kit(request.user)
        return Response({"brandKit": serialize_kit(kit)})

    def patch(self, request):
        kit = get_or_create_kit(request.user)
        payload = request.data or {}
        changed = []

        if "instituteName" in payload:
            kit.institute_name = str(payload.get("instituteName") or "").strip()[:200]
            changed.append("institute_name")

        if "instituteAddress" in payload:
            kit.institute_address = str(payload.get("instituteAddress") or "").strip()
            changed.append("institute_address")

        if "accentColor" in payload:
            accent = str(payload.get("accentColor") or "").strip()
            if not valid_accent_color(accent):
                return Response(
                    {"error": "That is not a colour we recognise. Use a hex value like #2f5fdd."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            kit.accent_color = accent
            changed.append("accent_color")

        if "fontFamily" in payload:
            kit.font_family = str(payload.get("fontFamily") or "").strip()[:120]
            changed.append("font_family")

        if "headerLayout" in payload:
            layout = payload.get("headerLayout")
            kit.header_layout = layout if isinstance(layout, dict) else {}
            changed.append("header_layout")

        if not changed:
            return Response(
                {"error": "Nothing to update."}, status=status.HTTP_400_BAD_REQUEST
            )

        kit.save(update_fields=[*changed, "updated_at"])
        return Response({"brandKit": serialize_kit(kit)})


class BrandAssetListView(APIView):
    """Upload a logo.

    Multipart rather than a presigned direct-to-S3 PUT (which is how chapter
    PDFs go up): a logo is a few hundred kilobytes and the round trip through
    the API buys per-format validation and the dimension read, which a browser
    uploading straight to a bucket cannot do.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"error": "Choose an image to upload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        kit = get_or_create_kit(request.user)
        try:
            asset = store_logo(
                kit,
                data=upload.read(),
                content_type=getattr(upload, "content_type", "") or "",
                name=request.data.get("name") or getattr(upload, "name", ""),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"asset": serialize_asset(asset)}, status=status.HTTP_201_CREATED
        )


class BrandAssetDetailView(APIView):
    """Rename or delete one logo."""

    permission_classes = [IsAuthenticated]

    def _get(self, request, asset_id):
        # Scoped through the kit's owner, so another account's asset id is a
        # 404 rather than a way to delete their crest.
        return BrandAsset.objects.filter(
            kit__user=request.user, id=asset_id
        ).first()

    def patch(self, request, asset_id):
        asset = self._get(request, asset_id)
        if asset is None:
            return Response(
                {"error": "That logo is no longer there."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if "name" not in (request.data or {}):
            return Response(
                {"error": "Nothing to update."}, status=status.HTTP_400_BAD_REQUEST
            )
        asset.name = str(request.data.get("name") or "").strip()[:120]
        asset.save(update_fields=["name", "updated_at"])
        return Response({"asset": serialize_asset(asset)})

    def delete(self, request, asset_id):
        asset = self._get(request, asset_id)
        if asset is None:
            return Response(
                {"error": "That logo is no longer there."},
                status=status.HTTP_404_NOT_FOUND,
            )
        delete_logo(asset)
        return Response(status=status.HTTP_204_NO_CONTENT)
