import logging
import secrets
from datetime import timedelta

from django.conf import settings as django_settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import Http404
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.accounts.views import get_cognito_username
from apps.common.permissions import IsOrgAdminOrSuperAdmin, IsSuperAdmin
from apps.generation.models import ApiUsage
from apps.projects.models import Paper
from services.cognito_service import add_user_to_group, remove_user_from_group
from apps.accounts.models import User
from services.email_service import (
    send_join_request_email,
    send_membership_approved_email,
    send_membership_moved_email,
    send_membership_rejected_email,
    send_membership_removed_email,
    send_organization_invite_email,
    send_role_changed_email,
)
from services.organization_logo import (
    remove_organization_logo,
    store_organization_logo,
)

from .models import Membership, Organization, OrganizationInvite
from .serializers import (
    PROFILE_FIELDS,
    MembershipSerializer,
    OrganizationDetailSerializer,
    OrganizationInviteSerializer,
    OrganizationListSerializer,
    OrganizationProfileSerializer,
    PublicOrganizationSerializer,
)

logger = logging.getLogger("[ORGANIZATIONS_VIEWS]")

INVITE_EXPIRY_DAYS = 7


def _get_organization_or_404(org_id: str) -> Organization:
    try:
        return Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        raise Http404("Organization not found")


def _org_admin_emails(org: Organization) -> list[str]:
    """Every approved admin of `org` — the people a request should reach.

    A school can have more than one admin (that is the point of the role
    endpoint below), and mailing only the first would leave the request
    invisible to whoever is actually at their desk.
    """
    return list(
        org.members.filter(role="org_admin", status="approved")
        .select_related("user")
        .values_list("user__email", flat=True)
    )


def _first_error(errors) -> str:
    """Flatten DRF's {field: [msg]} into one sentence for the toast.

    The frontend shows a single line, so handing it the whole dict would
    surface `{'gstin': [ErrorDetail(...)]}` to a school administrator.
    """
    for value in errors.values():
        if isinstance(value, (list, tuple)) and value:
            return str(value[0])
        if value:
            return str(value)
    return "Those details could not be saved."


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


class OrganizationInviteRevokeView(APIView):
    """Expire a sent invite before its deadline, so its link stops working.

    The row is kept rather than deleted: "we invited this address on the 8th
    and pulled it on the 9th" is worth being able to answer, and the accept
    view already refuses any invite whose status is not "pending".
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, invite_id):
        invite = OrganizationInvite.objects.filter(id=invite_id).first()
        if not invite:
            return Response({"error": "Invite not found"}, status=404)
        if invite.status == "accepted":
            # Revoking it would say nothing about the account that already
            # exists, so refuse rather than imply the school lost access.
            return Response(
                {"error": "That invite has already been accepted."}, status=400
            )
        if invite.status != "pending":
            return Response({"error": "That invite is no longer active."}, status=400)

        invite.status = "revoked"
        # Expiring it too means anything reading `expires_at` (the dashboard's
        # "7d left") agrees with the status instead of contradicting it.
        invite.expires_at = timezone.now()
        invite.save(update_fields=["status", "expires_at", "updated_at"])

        logger.info(
            "Superadmin %s revoked the invite to %s", request.user.email, invite.email
        )
        return Response(OrganizationInviteSerializer(invite).data)


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

        # Institute details arrive in the same POST but are entirely optional —
        # onboarding step 2 has a Skip button, so an admin without their GSTIN
        # certificate to hand still finishes. Anything supplied is validated;
        # anything omitted keeps the model default.
        profile = OrganizationProfileSerializer(
            data={k: v for k, v in request.data.items() if k in PROFILE_FIELDS}
        )
        if not profile.is_valid():
            return Response({"error": _first_error(profile.errors)}, status=400)

        org = Organization.objects.create(
            name=organization_name,
            created_by=request.user,
            **profile.validated_data,
        )
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

        # The admins are the ones who have to act on this, and nothing else
        # tells them it happened.
        send_join_request_email(
            to_emails=_org_admin_emails(org),
            applicant_name=request.user.name,
            applicant_email=request.user.email,
            organization_name=org.name,
        )

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


class SuperAdminAnalyticsView(APIView):
    """Everything the superadmin dashboard draws, in one round trip.

    One endpoint rather than four because the four panels are read together on
    every load, and four requests would mean four Cognito token validations and
    four connection round trips to render one screen.

    `days` selects the trend window (1..365, default 30). The other sections are
    all-time: "which school is heaviest" and "where do tokens go" are questions
    about the account, not about the last fortnight.
    """

    permission_classes = [IsSuperAdmin]

    #: Guardrail for the trend query. A year of daily buckets is 365 rows —
    #: fine to serialize; an unbounded `days` is not.
    MAX_TREND_DAYS = 365

    def get(self, request):
        try:
            days = int(request.query_params.get("days", 30))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, self.MAX_TREND_DAYS))

        since = timezone.now() - timedelta(days=days)

        return Response({
            "days": days,
            "totals": self._totals(),
            "trend": self._trend(since, days),
            "by_organization": self._by_organization(),
            "by_operation": self._grouped("operation"),
            "by_model": self._grouped("model"),
            "roster": self._roster(),
        })

    def _totals(self) -> dict:
        agg = ApiUsage.objects.aggregate(
            total=Sum("total_tokens"),
            prompt=Sum("prompt_tokens"),
            completion=Sum("completion_tokens"),
        )
        unassigned = (
            ApiUsage.objects.filter(organization__isnull=True)
            .aggregate(total=Sum("total_tokens"))["total"]
            or 0
        )
        return {
            "total_tokens": agg["total"] or 0,
            "prompt_tokens": agg["prompt"] or 0,
            "completion_tokens": agg["completion"] or 0,
            # Usage recorded before an org existed, or by the superadmin. Shown
            # explicitly so the per-org bars visibly not summing to the headline
            # total is explained rather than mysterious.
            "unassigned_tokens": unassigned,
            "organization_count": Organization.objects.count(),
            "active_organization_count": Organization.objects.filter(is_active=True).count(),
            "member_count": Membership.objects.count(),
            "pending_member_count": Membership.objects.filter(status="pending").count(),
        }

    def _trend(self, since, days: int) -> list:
        """Daily token totals, zero-filled across the whole window.

        Zero-filling matters: a chart fed only the days that happen to have
        rows draws a continuous line across a quiet week, which reads as steady
        usage rather than none.
        """
        rows = (
            ApiUsage.objects.filter(created_at__gte=since)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(tokens=Sum("total_tokens"), calls=Count("id"))
            .order_by("day")
        )
        by_day = {r["day"]: r for r in rows if r["day"] is not None}

        today = timezone.now().date()
        series = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            row = by_day.get(day)
            series.append({
                "date": day.isoformat(),
                "tokens": (row or {}).get("tokens") or 0,
                "calls": (row or {}).get("calls") or 0,
            })
        return series

    def _by_organization(self) -> list:
        """Token totals per organization, heaviest first.

        Aggregated in one grouped query rather than per-org, so this stays a
        single round trip as the account grows.
        """
        totals = {
            row["organization"]: row
            for row in ApiUsage.objects.filter(organization__isnull=False)
            .values("organization")
            .annotate(tokens=Sum("total_tokens"), calls=Count("id"))
        }
        members = {
            row["organization"]: row["n"]
            for row in Membership.objects.values("organization").annotate(n=Count("id"))
        }

        out = []
        for org in Organization.objects.all():
            row = totals.get(org.id) or {}
            out.append({
                "id": org.id,
                "name": org.name,
                "city": org.city,
                "is_active": org.is_active,
                "tokens": row.get("tokens") or 0,
                "calls": row.get("calls") or 0,
                "member_count": members.get(org.id, 0),
            })
        out.sort(key=lambda r: r["tokens"], reverse=True)
        return out

    def _grouped(self, field: str) -> list:
        """Token totals grouped by `operation` or `model`, heaviest first."""
        rows = (
            ApiUsage.objects.values(field)
            .annotate(tokens=Sum("total_tokens"), calls=Count("id"))
            .order_by("-tokens")
        )
        return [
            {
                # `model` is blank on rows written before it was recorded;
                # labelling that "unknown" beats an unlabelled slice.
                "label": r[field] or "unknown",
                "tokens": r["tokens"] or 0,
                "calls": r["calls"] or 0,
            }
            for r in rows
        ]

    def _roster(self) -> dict:
        """Operational state: what is waiting on someone to act."""
        now = timezone.now()
        pending_invites = OrganizationInvite.objects.filter(
            status="pending", expires_at__gte=now
        ).order_by("-created_at")[:50]
        expired_invites = OrganizationInvite.objects.filter(
            status="pending", expires_at__lt=now
        ).count()
        pending_members = (
            Membership.objects.filter(status="pending")
            .select_related("user", "organization")
            .order_by("-created_at")[:50]
        )

        return {
            "pending_invites": OrganizationInviteSerializer(pending_invites, many=True).data,
            "expired_invite_count": expired_invites,
            "pending_members": [
                {
                    "id": m.id,
                    "user_id": m.user_id,
                    "name": m.user.name,
                    "email": m.user.email,
                    "organization_id": m.organization_id,
                    "organization_name": m.organization.name,
                    "created_at": m.created_at,
                }
                for m in pending_members
            ],
            # An organization nobody has joined beyond its admin, or that has
            # never spent a token, is the one to chase after an onboarding.
            "empty_organizations": [
                {"id": o.id, "name": o.name, "created_at": o.created_at}
                for o in Organization.objects.annotate(n=Count("members")).filter(n__lte=1)
            ],
        }


class OrganizationDetailView(APIView):
    """Org admin (own org) or superadmin: organization detail + members."""
    permission_classes = [IsOrgAdminOrSuperAdmin]

    def get(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not request.user.is_superadmin and not self._is_admin_of(request.user, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)
        return Response(OrganizationDetailSerializer(org).data)

    def patch(self, request, org_id):
        """Edit the institute profile after onboarding.

        This is what makes step 2 skippable: an admin who had no GSTIN on
        signup day fills it in here instead.
        """
        org = _get_organization_or_404(org_id)
        if not request.user.is_superadmin and not self._is_admin_of(request.user, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)

        serializer = OrganizationProfileSerializer(org, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({"error": _first_error(serializer.errors)}, status=400)
        serializer.save()

        logger.info("%s updated organization %s profile", request.user.email, org.id)
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


class OrganizationLogoView(APIView):
    """Upload or remove an organization's crest.

    Multipart rather than a presigned direct-to-S3 PUT, for the same reason
    BrandAssetListView is: a crest is a few hundred kilobytes, and the round
    trip through the API buys per-format validation and the dimension read that
    a browser uploading straight to a bucket cannot do.
    """

    permission_classes = [IsOrgAdminOrSuperAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def _authorized(self, request, org_id) -> bool:
        return request.user.is_superadmin or OrganizationDetailView._is_admin_of(
            request.user, org_id
        )

    def post(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not self._authorized(request, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": "Choose an image to upload."}, status=400)

        try:
            store_organization_logo(
                org,
                data=upload.read(),
                content_type=getattr(upload, "content_type", "") or "",
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        logger.info("%s uploaded a logo for organization %s", request.user.email, org.id)
        return Response(OrganizationDetailSerializer(org).data, status=201)

    def delete(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not self._authorized(request, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)

        remove_organization_logo(org)
        return Response(OrganizationDetailSerializer(org).data)


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

    #: Refused when the action would take away the school's last admin. Shared
    #: by demote, reject and remove — all three end with nobody able to approve
    #: a teacher, and all three are one click in a table.
    LAST_ADMIN_ERROR = (
        "This is the school's only admin. Promote someone else first, "
        "then change this member."
    )

    @staticmethod
    def _is_last_admin(membership) -> bool:
        if membership.role != "org_admin" or membership.status != "approved":
            return False
        return not (
            Membership.objects.filter(
                organization_id=membership.organization_id,
                role="org_admin",
                status="approved",
            )
            .exclude(id=membership.id)
            .exists()
        )

    def _get_membership(self, request, org_id, user_id):
        if not request.user.is_superadmin and not OrganizationDetailView._is_admin_of(request.user, org_id):
            return None, Response({"error": "You do not manage this organization"}, status=403)
        try:
            # `organization` is joined too: every action below names the school
            # in the notification email it sends.
            membership = Membership.objects.select_related("user", "organization").get(
                organization_id=org_id, user_id=user_id
            )
        except Membership.DoesNotExist:
            return None, Response({"error": "Member not found"}, status=404)
        return membership, None


class OrganizationMemberPapersView(_OrganizationMemberActionView):
    """The papers one member has generated, for the admin looking at their row.

    Inherits `_get_membership` for the same two guards as every other member
    action: the caller must manage this school, and the user must actually be
    in it — an admin cannot read a stranger's papers by guessing a user id.

    Content is deliberately not returned. This answers "what has this teacher
    been producing", which the titles and subjects already do; shipping the
    question text of every paper would be a much larger disclosure than the
    question it was asked.
    """

    def get(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        papers = (
            Paper.objects.filter(user_id=user_id)
            .annotate(set_count=Count("sets"))
            .order_by("-created_at")[:200]
        )
        return Response(
            {
                "user": {
                    "id": membership.user.id,
                    "name": membership.user.name,
                    "email": membership.user.email,
                },
                "papers": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "subject": p.subject,
                        "grade_class": p.grade_class,
                        "board": p.board,
                        "set_count": p.set_count,
                        "created_at": p.created_at,
                    }
                    for p in papers
                ],
            }
        )


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

        send_membership_approved_email(
            to_email=member.email,
            user_name=member.name,
            organization_name=membership.organization.name,
        )

        logger.info("%s approved member %s in organization %s", request.user.email, member.email, org_id)
        return Response(MembershipSerializer(membership).data)


class OrganizationMemberRejectView(_OrganizationMemberActionView):
    def post(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        # Rejecting the sole admin locks the school out just as surely as
        # removing them does.
        if self._is_last_admin(membership):
            return Response({"error": self.LAST_ADMIN_ERROR}, status=400)

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

        send_membership_rejected_email(
            to_email=member.email,
            user_name=member.name,
            organization_name=membership.organization.name,
        )

        logger.info("%s rejected member %s in organization %s", request.user.email, member.email, org_id)
        return Response(MembershipSerializer(membership).data)


class OrganizationMemberRoleView(_OrganizationMemberActionView):
    """Move a member between `teacher` and `org_admin`.

    The role lives entirely in `Membership` — deliberately no Cognito group is
    touched here. The pool's groups (pending/approved/admin/superadmin) encode
    whether an account may sign in at all and whether it is platform staff;
    which school someone administers is not a platform-wide fact, and pushing it
    into the `admin` group would hand a school's admin the platform endpoints
    guarded by `IsAdmin`. `IsOrgAdminOrSuperAdmin` reads the membership row, so
    the change takes effect on the member's next request either way.
    """

    def post(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        role = (request.data.get("role") or "").strip()
        valid_roles = {choice for choice, _ in Membership.ROLE_CHOICES}
        if role not in valid_roles:
            return Response(
                {"error": f"role must be one of: {', '.join(sorted(valid_roles))}"},
                status=400,
            )

        if role == membership.role:
            # Not an error — the caller and the database already agree. Answer
            # with the row so an out-of-date table just re-syncs.
            return Response(MembershipSerializer(membership).data)

        # An admin demoting themselves would lose the very permission needed to
        # undo it, from a dropdown, with no confirmation step.
        if membership.user_id == request.user.id:
            return Response(
                {"error": "You cannot change your own role. Ask another admin to do it."},
                status=400,
            )

        if role == "org_admin" and membership.status != "approved":
            return Response(
                {"error": "Approve this member before making them a school admin."},
                status=400,
            )

        # Demoting the last admin would leave the school with nobody able to
        # approve teachers — recoverable only by a superadmin.
        if role != "org_admin" and self._is_last_admin(membership):
            return Response({"error": self.LAST_ADMIN_ERROR}, status=400)

        membership.role = role
        membership.reviewed_by = request.user
        membership.reviewed_at = timezone.now()
        membership.save(update_fields=["role", "reviewed_by", "reviewed_at"])

        member = membership.user
        send_role_changed_email(
            to_email=member.email,
            user_name=member.name,
            organization_name=membership.organization.name,
            new_role=role,
            changed_by=request.user.email,
        )

        logger.info(
            "%s changed %s's role to %s in organization %s",
            request.user.email, member.email, role, org_id,
        )
        return Response(MembershipSerializer(membership).data)


class OrganizationMemberRemoveView(_OrganizationMemberActionView):
    def delete(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        # Same reasoning as the demotion guard: removing the last admin
        # strands the school.
        if self._is_last_admin(membership):
            return Response({"error": self.LAST_ADMIN_ERROR}, status=400)

        member = membership.user
        organization_name = membership.organization.name
        cognito_username = get_cognito_username(member)
        try:
            remove_user_from_group(cognito_username, "approved")
            add_user_to_group(cognito_username, "pending")
        except Exception as e:
            logger.error("Failed to sync Cognito groups for %s: %s", member.email, e)

        membership.delete()

        member.status = "pending"
        member.save(update_fields=["status"])

        send_membership_removed_email(
            to_email=member.email,
            user_name=member.name,
            organization_name=organization_name,
        )

        logger.info("%s removed member %s from organization %s", request.user.email, member.email, org_id)
        return Response(status=204)


class OrganizationMemberAssignView(APIView):
    """Put a user in a school — either their first one, or a different one.

    Platform-level rather than nested under an organization, because the most
    common case has no source org to nest under: an account that signed up and
    never joined anywhere. One endpoint covers both, since "assign" and "move"
    differ only in whether a membership row already exists.

    Superadmin only. An org admin must not be able to push a user into a school
    they do not manage, nor pull one out of another admin's school — both are
    reachable from this endpoint, so the whole thing sits above them.
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        organization_id = (request.data.get("organization_id") or "").strip()
        if not organization_id:
            return Response({"error": "organization_id is required"}, status=400)
        target = _get_organization_or_404(organization_id)

        # Defaults to teacher, and deliberately so: administering school A says
        # nothing about school B, and silently carrying org_admin across would
        # hand someone a new school's member list as a side effect of a move.
        role = (request.data.get("role") or "teacher").strip()
        valid_roles = {choice for choice, _ in Membership.ROLE_CHOICES}
        if role not in valid_roles:
            return Response(
                {"error": f"role must be one of: {', '.join(sorted(valid_roles))}"},
                status=400,
            )

        membership = getattr(user, "membership", None)
        source = membership.organization if membership else None

        if membership and membership.organization_id == target.id:
            if membership.role == role:
                # Caller and database already agree — let a stale table re-sync
                # rather than reporting an error for a no-op.
                return Response(MembershipSerializer(membership).data)
            return Response(
                {
                    "error": "They are already at this school. Use the role "
                    "picker to change what they can do there."
                },
                status=400,
            )

        if membership and _OrganizationMemberActionView._is_last_admin(membership):
            return Response(
                {
                    "error": f"They are the only admin of {source.name}. Promote "
                    "someone else there first, then move them."
                },
                status=400,
            )

        if membership:
            # Status rides along: a teacher already approved at their old school
            # was approved as a person, and making a superadmin's correction of
            # a mis-joined school cost them a second approval round would be
            # friction for no safety gained.
            membership.organization = target
            membership.role = role
            membership.reviewed_by = request.user
            membership.reviewed_at = timezone.now()
            membership.save(
                update_fields=["organization", "role", "reviewed_by", "reviewed_at"]
            )
        else:
            # A first placement starts pending, exactly as joining does, so the
            # receiving school's admin still gets their say — and so approval
            # runs through the one path that syncs Cognito.
            membership = Membership.objects.create(
                user=user, organization=target, role=role, status="pending"
            )

        # Past ApiUsage rows keep pointing at the organization that actually
        # spent the tokens. Reassigning history to the new school would silently
        # rewrite another school's bill.
        send_membership_moved_email(
            to_email=user.email,
            user_name=user.name,
            from_organization=source.name if source else None,
            to_organization=target.name,
            new_role=role,
            pending_approval=membership.status != "approved",
        )

        logger.info(
            "%s assigned %s to organization %s (from %s) as %s",
            request.user.email,
            user.email,
            target.id,
            source.id if source else "none",
            role,
        )
        return Response(MembershipSerializer(membership).data)
