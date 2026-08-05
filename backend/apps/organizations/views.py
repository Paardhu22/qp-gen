import logging
import secrets
from datetime import timedelta

from django.conf import settings as django_settings
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.accounts.views import get_cognito_username
from apps.common.permissions import IsOrgAdminOrSuperAdmin, IsSuperAdmin
from apps.generation.models import ApiUsage
from services.cognito_service import add_user_to_group, remove_user_from_group
from services.email_service import send_organization_invite_email

from .models import Membership, Organization, OrganizationInvite
from .serializers import (
    MembershipSerializer,
    OrganizationDetailSerializer,
    OrganizationInviteSerializer,
    OrganizationListSerializer,
    PublicOrganizationSerializer,
)

logger = logging.getLogger("[ORGANIZATIONS_VIEWS]")

INVITE_EXPIRY_DAYS = 7


def _get_organization_or_404(org_id: str) -> Organization:
    try:
        return Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        raise Http404("Organization not found")


class PublicOrganizationListView(APIView):
    """Unauthenticated list of active organizations, for the signup dropdown."""
    permission_classes = [AllowAny]

    def get(self, request):
        orgs = Organization.objects.filter(is_active=True).order_by("name")
        return Response(PublicOrganizationSerializer(orgs, many=True).data)


class OrganizationInviteCreateView(APIView):
    """Superadmin invites an email address to create + administer a new org."""
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email is required"}, status=400)

        invite = OrganizationInvite.objects.create(
            email=email,
            token=secrets.token_urlsafe(32),
            invited_by=request.user,
            expires_at=timezone.now() + timedelta(days=INVITE_EXPIRY_DAYS),
        )

        base = (django_settings.FRONTEND_URL or "").rstrip("/")
        invite_link = f"{base}/onboard?token={invite.token}"

        send_organization_invite_email(to_email=email, invite_link=invite_link)

        logger.info("Superadmin %s invited %s to create an organization", request.user.email, email)
        return Response(OrganizationInviteSerializer(invite).data, status=201)


class OrganizationInviteAcceptView(APIView):
    """
    Invited user (already signed up + authenticated via Cognito) accepts the
    invite and creates their organization. IsAuthenticated only — the caller
    is still `status="pending"` at this point and would otherwise be blocked
    by the default IsApprovedOrAdmin permission.
    """

    def get_permissions(self):
        # GET (token lookup, used to pre-fill/lock the signup email) is public
        # — the token itself is the secret, same trust boundary as the POST.
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response({"error": "token is required"}, status=400)
        try:
            invite = OrganizationInvite.objects.get(token=token)
        except OrganizationInvite.DoesNotExist:
            return Response({"error": "Invalid invite token"}, status=404)

        if invite.status != "pending":
            return Response({"error": "This invite has already been used or revoked"}, status=400)
        if invite.expires_at < timezone.now():
            return Response({"error": "This invite has expired"}, status=400)

        return Response({"email": invite.email})

    def post(self, request):
        token = request.data.get("token")
        organization_name = (request.data.get("organization_name") or "").strip()
        if not token or not organization_name:
            return Response({"error": "token and organization_name are required"}, status=400)

        try:
            invite = OrganizationInvite.objects.get(token=token)
        except OrganizationInvite.DoesNotExist:
            return Response({"error": "Invalid invite token"}, status=404)

        if invite.status != "pending":
            return Response({"error": "This invite has already been used or revoked"}, status=400)
        if invite.expires_at < timezone.now():
            invite.status = "expired"
            invite.save(update_fields=["status"])
            return Response({"error": "This invite has expired"}, status=400)
        if invite.email.lower() != request.user.email.lower():
            return Response({"error": "This invite was sent to a different email address"}, status=403)
        if getattr(request.user, "membership", None):
            return Response({"error": "Your account already belongs to an organization"}, status=400)

        org = Organization.objects.create(name=organization_name, created_by=request.user)
        Membership.objects.create(
            user=request.user,
            organization=org,
            role="org_admin",
            status="approved",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

        invite.status = "accepted"
        invite.organization = org
        invite.save(update_fields=["status", "organization"])

        cognito_username = get_cognito_username(request.user)
        try:
            add_user_to_group(cognito_username, "approved")
            remove_user_from_group(cognito_username, "pending")
        except Exception as e:
            logger.error("Failed to sync Cognito groups for new org admin %s: %s", request.user.email, e)

        request.user.status = "approved"
        request.user.save(update_fields=["status"])

        logger.info("%s accepted invite %s and created organization %s", request.user.email, invite.id, org.id)
        return Response(OrganizationDetailSerializer(org).data, status=201)


class OrganizationJoinView(APIView):
    """
    Authenticated user (just finished Cognito signup) picks an org to join
    as a teacher. Membership starts pending until the org admin approves.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        organization_id = request.data.get("organization_id")
        if not organization_id:
            return Response({"error": "organization_id is required"}, status=400)

        if getattr(request.user, "membership", None):
            return Response({"error": "Your account already belongs to an organization"}, status=400)

        org = _get_organization_or_404(organization_id)
        Membership.objects.create(user=request.user, organization=org, role="teacher", status="pending")

        logger.info("%s requested to join organization %s", request.user.email, org.id)
        return Response(UserSerializer(request.user).data, status=201)


class OrganizationListView(APIView):
    """Superadmin: list every organization with member count + token usage."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        orgs = Organization.objects.all().order_by("name")
        return Response(OrganizationListSerializer(orgs, many=True).data)


class OrganizationUsageSummaryView(APIView):
    """Superadmin: flat token-usage rollup across all organizations."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        total_tokens = ApiUsage.objects.aggregate(total=Sum("total_tokens"))["total"] or 0
        unassigned_tokens = (
            ApiUsage.objects.filter(organization__isnull=True).aggregate(total=Sum("total_tokens"))["total"] or 0
        )
        return Response({
            "total_tokens": total_tokens,
            "unassigned_tokens": unassigned_tokens,
            "organizations": OrganizationListSerializer(
                Organization.objects.all().order_by("name"), many=True
            ).data,
        })


class OrganizationDetailView(APIView):
    """Org admin (own org) or superadmin: organization detail + members."""
    permission_classes = [IsOrgAdminOrSuperAdmin]

    def get(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not request.user.is_superadmin and not self._is_admin_of(request.user, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)
        return Response(OrganizationDetailSerializer(org).data)

    @staticmethod
    def _is_admin_of(user, org_id):
        membership = getattr(user, "membership", None)
        return bool(
            membership
            and membership.role == "org_admin"
            and membership.status == "approved"
            and membership.organization_id == org_id
        )


class OrganizationMembersListView(APIView):
    """Org admin (own org) or superadmin: list members with usage."""
    permission_classes = [IsOrgAdminOrSuperAdmin]

    def get(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not request.user.is_superadmin and not OrganizationDetailView._is_admin_of(request.user, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)
        members = org.members.select_related("user").order_by("-created_at")
        return Response(MembershipSerializer(members, many=True).data)


class _OrganizationMemberActionView(APIView):
    permission_classes = [IsOrgAdminOrSuperAdmin]

    def _get_membership(self, request, org_id, user_id):
        if not request.user.is_superadmin and not OrganizationDetailView._is_admin_of(request.user, org_id):
            return None, Response({"error": "You do not manage this organization"}, status=403)
        try:
            membership = Membership.objects.select_related("user").get(
                organization_id=org_id, user_id=user_id
            )
        except Membership.DoesNotExist:
            return None, Response({"error": "Member not found"}, status=404)
        return membership, None


class OrganizationMemberApproveView(_OrganizationMemberActionView):
    def post(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        member = membership.user
        cognito_username = get_cognito_username(member)
        try:
            add_user_to_group(cognito_username, "approved")
            remove_user_from_group(cognito_username, "pending")
        except Exception as e:
            logger.error("Failed to sync Cognito groups for %s: %s", member.email, e)
            return Response({"error": f"Failed to sync with Cognito: {str(e)}"}, status=500)

        membership.status = "approved"
        membership.reviewed_by = request.user
        membership.reviewed_at = timezone.now()
        membership.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        member.status = "approved"
        member.save(update_fields=["status"])

        logger.info("%s approved member %s in organization %s", request.user.email, member.email, org_id)
        return Response(MembershipSerializer(membership).data)


class OrganizationMemberRejectView(_OrganizationMemberActionView):
    def post(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        member = membership.user
        cognito_username = get_cognito_username(member)
        try:
            remove_user_from_group(cognito_username, "approved")
            add_user_to_group(cognito_username, "pending")
        except Exception as e:
            logger.error("Failed to sync Cognito groups for %s: %s", member.email, e)
            return Response({"error": f"Failed to sync with Cognito: {str(e)}"}, status=500)

        membership.status = "rejected"
        membership.reviewed_by = request.user
        membership.reviewed_at = timezone.now()
        membership.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        member.status = "rejected"
        member.save(update_fields=["status"])

        logger.info("%s rejected member %s in organization %s", request.user.email, member.email, org_id)
        return Response(MembershipSerializer(membership).data)


class OrganizationMemberRemoveView(_OrganizationMemberActionView):
    def delete(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        member = membership.user
        cognito_username = get_cognito_username(member)
        try:
            remove_user_from_group(cognito_username, "approved")
            add_user_to_group(cognito_username, "pending")
        except Exception as e:
            logger.error("Failed to sync Cognito groups for %s: %s", member.email, e)

        membership.delete()

        member.status = "pending"
        member.save(update_fields=["status"])

        logger.info("%s removed member %s from organization %s", request.user.email, member.email, org_id)
        return Response(status=204)
