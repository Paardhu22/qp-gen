import logging

from django.http import Http404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import BrandAsset, User
from apps.accounts.serializers import UserSerializer
from apps.common.permissions import IsAdmin
from services.brand_kit import (
    delete_logo,
    get_or_create_kit,
    serialize_asset,
    serialize_kit,
    store_logo,
    valid_accent_color,
)
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
