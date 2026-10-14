"""Platform-wide (superadmin) views: analytics, superadmin grants, user deletion."""

import logging
from datetime import timedelta
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.common.permissions import IsSuperAdmin
from apps.generation.models import ApiUsage
from apps.accounts.models import User
from services.auth.emails import send_account_deleted_email, send_superadmin_changed_email
from services.organizations.usage_pricing import inr_cost_by_group, inr_cost_of_usage
from ..models import Membership, Organization, OrganizationInvite
from ..serializers import OrganizationInviteSerializer
from services.auth import cognito
from apps.accounts import views as accounts_views

logger = logging.getLogger("[ORGANIZATIONS_VIEWS]")


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
        unassigned_qs = ApiUsage.objects.filter(organization__isnull=True)
        unassigned = unassigned_qs.aggregate(total=Sum("total_tokens"))["total"] or 0
        return {
            "total_tokens": agg["total"] or 0,
            "prompt_tokens": agg["prompt"] or 0,
            "completion_tokens": agg["completion"] or 0,
            # The headline number a school administrator actually reads.
            "total_cost_inr": inr_cost_of_usage(ApiUsage.objects.all()),
            "unassigned_cost_inr": inr_cost_of_usage(unassigned_qs),
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
        assigned = ApiUsage.objects.filter(organization__isnull=False)
        totals = {
            row["organization"]: row
            for row in assigned.values("organization").annotate(
                tokens=Sum("total_tokens"), calls=Count("id")
            )
        }
        # Priced per (organization, model) — summing an org's tokens first and
        # pricing the total would bill its image generation at the chat rate.
        costs = inr_cost_by_group(assigned, "organization")
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
                "cost_inr": costs.get(org.id, 0.0),
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
        costs = inr_cost_by_group(ApiUsage.objects.all(), field)
        return [
            {
                # `model` is blank on rows written before it was recorded;
                # labelling that "unknown" beats an unlabelled slice.
                "label": r[field] or "unknown",
                "tokens": r["tokens"] or 0,
                "calls": r["calls"] or 0,
                "cost_inr": costs.get(r[field], 0.0),
            }
            for r in rows
        ]

    def _roster(self) -> dict:
        """Operational state: what is waiting on someone to act."""
        now = timezone.now()
        pending_invites = (
            OrganizationInvite.objects.filter(status="pending", expires_at__gte=now)
            .select_related("organization", "invited_by")
            .order_by("-created_at")[:50]
        )
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


class PlatformSuperadminView(APIView):
    """Promote a user to platform superadmin, or take it back.

    The Cognito group is the source of truth, not the column. `is_superadmin`
    is recomputed from the token's `cognito:groups` on every authenticated
    request (see common/authentication.py), so flipping only the local flag
    would be undone the next time they called anything. That is why a Cognito
    failure here is fatal rather than logged: a half-applied promotion is a
    user who looks like a superadmin in the table and isn't one in practice.

    Promotion also ends their school membership. A superadmin is platform
    staff — they see every school — and the admin screens already render them
    as belonging to none. Demotion therefore leaves an account with no school,
    which is exactly the state the School picker exists to resolve.
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        make = request.data.get("is_superadmin")
        if not isinstance(make, bool):
            return Response({"error": "is_superadmin must be true or false"}, status=400)

        if user.id == request.user.id:
            # Self-demotion is the one move that cannot be undone from this
            # screen: the moment it lands, the caller loses the permission
            # needed to reach the endpoint again. It is also what keeps the
            # platform from losing its last superadmin — demoting the last one
            # means demoting yourself, since anyone else is a second one.
            return Response(
                {"error": "You cannot change your own superadmin access."}, status=400
            )

        if user.is_superadmin == make:
            return Response(UserSerializer(user).data)

        cognito_username = accounts_views.get_cognito_username(user)
        try:
            if make:
                cognito.ensure_cognito_group("superadmin", description="Platform-wide superadmin")
                cognito.add_user_to_group(cognito_username, "superadmin")
                # Superadmins are approved by definition — without this a
                # promoted pending user still hits the approval wall.
                cognito.add_user_to_group(cognito_username, "approved")
                cognito.remove_user_from_group(cognito_username, "pending")
            else:
                cognito.remove_user_from_group(cognito_username, "superadmin")
        except Exception as e:
            logger.error("Failed to sync Cognito superadmin group for %s: %s", user.email, e)
            return Response({"error": f"Failed to sync with Cognito: {str(e)}"}, status=500)

        membership = user.active_membership
        organization_name = membership.organization.name if membership else None
        updates = ["is_superadmin", "status"]
        if make:
            user.memberships.all().delete()
            user.active_organization = None
            updates.append("active_organization")

        user.is_superadmin = make
        # "admin" is the status the seeded superadmin carries; a demoted user
        # keeps their access but is nobody's member until assigned a school.
        user.status = "admin" if make else "pending"
        user.save(update_fields=updates)

        send_superadmin_changed_email(
            to_email=user.email,
            user_name=user.name,
            granted=make,
            organization_name=organization_name,
            changed_by=request.user.name or request.user.email,
        )

        logger.info(
            "%s %s superadmin access for %s",
            request.user.email,
            "granted" if make else "revoked",
            user.email,
        )
        return Response(UserSerializer(user).data)


class PlatformUserDeleteView(APIView):
    """Delete an account outright — from Cognito, and from here.

    Distinct from removing someone from a school, which keeps the account and
    everything in it. This ends the account: Cognito loses the credentials, and
    the local row goes with its papers, projects and questions on cascade.

    Cognito is deleted first and a failure there aborts. The other order leaves
    the worst possible state — credentials that still authenticate against a
    user row that no longer exists, which `authentication.py` would helpfully
    recreate on the next request, undoing the deletion.

    Superadmin only, and never another superadmin: revoke their access first,
    so ending platform staff's account is always two deliberate steps.
    """

    permission_classes = [IsSuperAdmin]

    def delete(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        if user.id == request.user.id:
            return Response({"error": "You cannot delete your own account."}, status=400)

        if user.is_superadmin:
            return Response(
                {
                    "error": "They are a superadmin. Remove their superadmin "
                    "access first, then delete the account."
                },
                status=400,
            )

        email, name = user.email, user.name
        try:
            cognito.delete_cognito_user(accounts_views.get_cognito_username(user))
        except Exception as e:
            logger.error("Failed to delete Cognito user %s: %s", email, e)
            return Response({"error": f"Failed to delete from Cognito: {str(e)}"}, status=500)

        # Everything the user authored cascades. Their ApiUsage rows do not —
        # that FK is SET_NULL, because the tokens were spent against a school's
        # bill and deleting the person must not rewrite it.
        user.delete()

        # Told after the fact, not asked: the account is already gone, and this
        # is the only notice they will get that it happened.
        send_account_deleted_email(to_email=email, user_name=name)

        logger.info("Superadmin %s deleted the account %s", request.user.email, email)
        return Response(status=204)
