import logging
import secrets
from datetime import timedelta

from django.conf import settings as django_settings
from django.db import transaction
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
from apps.common.permissions import (
    IsOrgAdminOrSuperAdmin,
    IsSuperAdmin,
    has_org_admin_membership,
)
from apps.generation.models import ApiUsage
from services.cognito_service import add_user_to_group, remove_user_from_group
from services.email_service import (
    send_join_request_email,
    send_membership_approved_email,
    send_membership_rejected_email,
    send_organization_invite_email,
    send_teacher_invite_email,
)
from services.organization_logo import (
    remove_organization_logo,
    store_organization_logo,
)
from services.usage_pricing import inr_cost_by_group, inr_cost_of_usage

from .domains import domain_of_email
from .models import Membership, Organization, OrganizationInvite
from .selectors import with_usage
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


def _frontend(path: str) -> str:
    """An absolute link into the app. Never `localhost` in production.

    Every emailed link is built through here for the same reason the
    password-reset link is: one place gets `FRONTEND_URL` right, and a link
    composed ad hoc in a view is the one that ships with a dev host baked in.
    """
    base = (django_settings.FRONTEND_URL or "").rstrip("/")
    return f"{base}{path if path.startswith('/') else '/' + path}"


def _new_invite(*, email: str, role: str, organization, invited_by) -> OrganizationInvite:
    return OrganizationInvite.objects.create(
        email=email,
        token=secrets.token_urlsafe(32),
        role=role,
        organization=organization,
        invited_by=invited_by,
        expires_at=timezone.now() + timedelta(days=INVITE_EXPIRY_DAYS),
    )


def _reconcile_expired(invites) -> None:
    """Write `expired` onto invites whose date has passed.

    Expiry is a date comparison, so an invite is *effectively* expired the
    moment the clock passes it — but the stored status still says "pending",
    and every screen that filters on the column shows it as outstanding. This
    settles the column whenever a list is read, which is the only moment
    anybody cares.
    """
    stale = [i.id for i in invites if i.status == "pending" and i.is_expired]
    if stale:
        OrganizationInvite.objects.filter(id__in=stale).update(status="expired")


def _approved_elsewhere(user, excluding_organization_id) -> bool:
    """True when the account still has an approved school other than this one."""
    return any(
        m.status == "approved" and m.organization_id != excluding_organization_id
        for m in user.memberships.all()
    )


def _resettle_after_losing(user, organization_id, *, fallback_status: str) -> None:
    """Fix up an account that has just lost its membership at one school.

    Two things can be stale afterwards, and both are user-visible:

    *   `active_organization` may point at the school they were just removed
        from, which would leave them working as a school they no longer belong
        to. It moves to another approved membership, or to nothing.
    *   The account-wide `status` may say "approved" on the strength of a
        membership that no longer exists — but must NOT be demoted while
        another approved school remains, or a removal at one school locks them
        out of another that never removed them.
    """
    remaining = [
        m
        for m in user.memberships.all()
        if m.status == "approved" and m.organization_id != organization_id
    ]
    updates = []

    if user.active_organization_id == organization_id:
        user.active_organization = remaining[0].organization if remaining else None
        updates.append("active_organization")

    if not remaining and user.status != fallback_status:
        user.status = fallback_status
        updates.append("status")

    if updates:
        user.save(update_fields=updates)


def _promote_to_approved(user) -> None:
    """Move a user into Cognito's `approved` group, best effort.

    Best effort on purpose: the database is already the authority on approval
    status (see `_status_rank` in apps/common/authentication.py), so a Cognito
    hiccup must not undo a membership that was just committed in a
    transaction. It is logged loudly because the two stores drifting is a real
    problem — just not one worth failing an accepted invite over.
    """
    username = get_cognito_username(user)
    try:
        add_user_to_group(username, "approved")
        remove_user_from_group(username, "pending")
    except Exception as exc:
        logger.error("Failed to sync Cognito groups for %s: %s", user.email, exc)


def _org_admin_emails(organization) -> list:
    return list(
        Membership.objects.filter(
            organization=organization, role="org_admin", status="approved"
        )
        .select_related("user")
        .values_list("user__email", flat=True)
    )


def _get_organization_or_404(org_id: str) -> Organization:
    try:
        return Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        raise Http404("Organization not found")


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
    """Unauthenticated list of active organizations, for the signup dropdown.

    `?email=` is the difference between a usable dropdown and an alphabetical
    list of every school on the platform. When the signup form has already
    collected an address, the school claiming that email domain is flagged and
    sorted to the top so the teacher confirms a choice rather than hunting for
    one — picking the wrong "St. Mary's" strands them in a pending queue that
    nobody at that school will ever action.

    Matching is a hint and grants nothing: the membership still starts pending.
    Domains are spoofable at signup, so the only thing this may safely do is
    change the order of a list that was already public.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        email_domain = domain_of_email(request.query_params.get("email") or "")
        orgs = list(Organization.objects.filter(is_active=True).order_by("name"))
        data = PublicOrganizationSerializer(
            orgs, many=True, context={"email_domain": email_domain}
        ).data
        if email_domain:
            # Stable within each group: matches keep their alphabetical order,
            # and so does everything else.
            data = sorted(data, key=lambda row: not row["matches_email_domain"])
        return Response(data)


class OrganizationInviteCreateView(APIView):
    """Superadmin: invite an email to create + administer a new organization,
    or list every invite ever sent.

    GET exists because an invite is otherwise a write-only action: once sent,
    nobody can see whether it is outstanding, already used, or long expired,
    which makes "did we invite this school?" unanswerable and makes revocation
    impossible to offer.
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        invites = list(
            OrganizationInvite.objects.select_related("organization", "invited_by").all()
        )
        _reconcile_expired(invites)
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter == "open":
            invites = [i for i in invites if i.is_open]
        elif status_filter:
            invites = [i for i in invites if i.status == status_filter]
        return Response(OrganizationInviteSerializer(invites, many=True).data)

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email is required"}, status=400)

        # An address that already administers a school does not need a second
        # organization; sending the link anyway produces an invite that can
        # only ever fail at the last step, after the recipient has followed it.
        # Being a *teacher* somewhere is not a bar — a head of department at one
        # school setting up another is exactly who this link is for.
        existing = (
            Membership.objects.filter(
                user__email__iexact=email, role="org_admin", status="approved"
            )
            .select_related("organization")
            .first()
        )
        if existing:
            return Response(
                {"error": f"{email} already administers {existing.organization.name}."},
                status=400,
            )

        invite = _new_invite(
            email=email, role="org_admin", organization=None, invited_by=request.user
        )
        invite_link = _frontend(f"/onboard?token={invite.token}")
        send_organization_invite_email(to_email=email, invite_link=invite_link)

        logger.info("Superadmin %s invited %s to create an organization", request.user.email, email)
        return Response(OrganizationInviteSerializer(invite).data, status=201)


class OrganizationInviteRevokeView(APIView):
    """Withdraw an invite that has not been accepted yet.

    The reason this has to exist: an invite is a live credential for seven
    days, and the two cases that produce one — a typo'd address, and a person
    who has since left the school — are exactly the cases where the link is in
    somebody's inbox who should not have it. Until now the only remedy was to
    wait a week.

    Revoking is deliberately not a delete. The row is the record that the
    invite was sent and withdrawn, and an admin asking "what happened to that
    invite?" deserves an answer other than silence.
    """

    permission_classes = [IsOrgAdminOrSuperAdmin]

    def delete(self, request, invite_id):
        try:
            invite = OrganizationInvite.objects.select_related("organization").get(id=invite_id)
        except OrganizationInvite.DoesNotExist:
            raise Http404("Invite not found")

        # A school's admin may withdraw invites they issued for their own
        # school. Only the superadmin may touch an org-creation invite, which
        # belongs to no organization yet and so has no other owner.
        if not request.user.is_superadmin:
            if invite.organization_id is None or not OrganizationDetailView._is_admin_of(
                request.user, invite.organization_id
            ):
                return Response({"error": "You do not manage this invite"}, status=403)

        if invite.status == "accepted":
            return Response(
                {"error": "That invite has already been accepted. Remove the member instead."},
                status=400,
            )
        if invite.status == "revoked":
            # Idempotent: two admins clicking the same button is not an error.
            return Response(OrganizationInviteSerializer(invite).data)

        invite.status = "revoked"
        invite.save(update_fields=["status", "updated_at"])
        logger.info("%s revoked invite %s for %s", request.user.email, invite.id, invite.email)
        return Response(OrganizationInviteSerializer(invite).data)


class OrganizationTeacherInviteView(APIView):
    """A school admin invites a teacher straight into their own school.

    This is the shortcut around the approval queue, and it is safe precisely
    because the person issuing it is the person who would otherwise approve the
    request. A teacher following the link signs up and is a member — no
    dropdown to search, no pending state, nobody to chase.

    Scoped to one organization: an org admin may only invite into the school
    they administer, and the accept path re-checks that the address on the
    invite is the address that signed up.
    """

    permission_classes = [IsOrgAdminOrSuperAdmin]

    def _authorized(self, request, org_id) -> bool:
        return request.user.is_superadmin or OrganizationDetailView._is_admin_of(
            request.user, org_id
        )

    def get(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not self._authorized(request, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)
        invites = list(org.invites.select_related("organization", "invited_by").all())
        _reconcile_expired(invites)
        return Response(OrganizationInviteSerializer(invites, many=True).data)

    def post(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not self._authorized(request, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)

        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email is required"}, status=400)

        # Only a membership at THIS school is a bar. Teaching elsewhere is not
        # — inviting a teacher who also works at another school is the case
        # multi-org membership exists for.
        existing = Membership.objects.filter(
            user__email__iexact=email, organization=org
        ).first()
        if existing and existing.status != "rejected":
            return Response({"error": f"{email} already belongs to this school."}, status=400)

        # Re-inviting the same address is the normal way to resend a link the
        # recipient lost, so the old one is retired rather than left live —
        # otherwise every resend leaves another working credential behind.
        org.invites.filter(email__iexact=email, status="pending").update(status="revoked")

        invite = _new_invite(
            email=email, role="teacher", organization=org, invited_by=request.user
        )
        invite_link = _frontend(f"/register?invite={invite.token}")
        send_teacher_invite_email(
            to_email=email,
            invite_link=invite_link,
            organization_name=org.name,
            inviter_name=request.user.name or "",
        )
        logger.info("%s invited teacher %s to organization %s", request.user.email, email, org.id)
        return Response(OrganizationInviteSerializer(invite).data, status=201)


class OrganizationInviteAcceptView(APIView):
    """Accept an invite: create a school, or join one.

    Which of the two happens is `invite.role`, and the split is the whole
    reason teacher invites are worth having:

    *   `org_admin` — creates the organization named in the request and makes
        the caller its administrator.
    *   `teacher` — joins the organization the invite was issued for, already
        approved. No organization name is required or accepted; the school
        already exists and the caller does not get to name it.

    IsAuthenticated only — the caller is still `status="pending"` at this point
    and would otherwise be blocked by the default IsApprovedOrAdmin permission.
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
            invite = OrganizationInvite.objects.select_related("organization").get(token=token)
        except OrganizationInvite.DoesNotExist:
            return Response({"error": "Invalid invite token"}, status=404)

        if invite.status != "pending":
            return Response({"error": "This invite has already been used or revoked"}, status=400)
        if invite.expires_at < timezone.now():
            return Response({"error": "This invite has expired"}, status=400)

        # The role and school name let the signup screen say what accepting
        # actually does — "join Delhi Public School" rather than a generic
        # "you have been invited", which a teacher reasonably reads as being
        # asked to register their school a second time.
        return Response({
            "email": invite.email,
            "role": invite.role,
            "organization_id": invite.organization_id,
            "organization_name": invite.organization.name if invite.organization else None,
        })

    def post(self, request):
        token = request.data.get("token")
        organization_name = (request.data.get("organization_name") or "").strip()
        if not token:
            return Response({"error": "token is required"}, status=400)

        try:
            invite = OrganizationInvite.objects.select_related("organization").get(token=token)
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
        if invite.role == "teacher":
            return self._accept_teacher_invite(request, invite)

        # Creating a school is barred only for someone who already administers
        # one. Belonging to schools as a teacher is not a bar — an account can
        # hold several memberships, and setting up a new school is a normal
        # thing for a head of department elsewhere to do.
        if any(
            m.role == "org_admin" and m.status == "approved"
            for m in request.user.memberships.all()
        ):
            return Response(
                {"error": "Your account already administers an organization"}, status=400
            )

        if not organization_name:
            return Response({"error": "organization_name is required"}, status=400)

        # Institute details arrive in the same POST but are entirely optional —
        # onboarding step 2 has a Skip button, so an admin without their GSTIN
        # certificate to hand still finishes. Anything supplied is validated;
        # anything omitted keeps the model default.
        profile = OrganizationProfileSerializer(
            data={k: v for k, v in request.data.items() if k in PROFILE_FIELDS}
        )
        if not profile.is_valid():
            return Response({"error": _first_error(profile.errors)}, status=400)

        with transaction.atomic():
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

            request.user.status = "approved"
            request.user.save(update_fields=["status"])

        _promote_to_approved(request.user)

        logger.info("%s accepted invite %s and created organization %s", request.user.email, invite.id, org.id)
        return Response(OrganizationDetailSerializer(org).data, status=201)

    def _accept_teacher_invite(self, request, invite):
        """Join the school the invite names, already approved.

        The organization is read off the invite, never off the request: a
        client that could name its own organization here would turn any valid
        teacher invite into membership of any school on the platform.

        Additive. Accepting adds this school to whatever the account already
        has rather than replacing it — a teacher invited to a second branch
        must not lose the first, and everything they made there with it.
        """
        org = invite.organization
        if org is None or not org.is_active:
            return Response(
                {"error": "That school is no longer accepting members."}, status=400
            )

        with transaction.atomic():
            existing = request.user.membership_for(org.id)
            if existing:
                existing.role = "teacher"
                existing.status = "approved"
                existing.reviewed_by = invite.invited_by
                existing.reviewed_at = timezone.now()
                existing.save(
                    update_fields=[
                        "role",
                        "status",
                        "reviewed_by",
                        "reviewed_at",
                        "updated_at",
                    ]
                )
            else:
                Membership.objects.create(
                    user=request.user,
                    organization=org,
                    role="teacher",
                    status="approved",
                    reviewed_by=invite.invited_by,
                    reviewed_at=timezone.now(),
                )

            invite.status = "accepted"
            invite.save(update_fields=["status", "updated_at"])

            updates = ["status"]
            request.user.status = "approved"
            # The school they just joined becomes the one they are working as,
            # but only if they were not already working somewhere — accepting
            # an invite to a second school should not silently move a teacher
            # out of the one they are mid-paper in.
            if request.user.active_organization_id is None:
                request.user.active_organization = org
                updates.append("active_organization")
            request.user.save(update_fields=updates)

        _promote_to_approved(request.user)

        logger.info("%s accepted teacher invite %s to organization %s", request.user.email, invite.id, org.id)
        # The user, not the organization detail: a teacher who has just joined
        # is not an admin, and the detail serializer carries the full member
        # roster with every colleague's token spend on it.
        return Response(UserSerializer(request.user).data, status=201)


class OrganizationJoinView(APIView):
    """
    Authenticated user picks an org to join as a teacher. Membership starts
    pending until that org's admin approves.

    Callable more than once, deliberately. A teacher can work at more than one
    school — a subject specialist covering two branches, someone mid-move
    between jobs — and each school is its own request to that school's own
    admin. What is refused is a *second* request to a school they already have
    a live membership at; a rejected one may be re-sent, which is what makes a
    wrong choice at signup recoverable.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        organization_id = request.data.get("organization_id")
        if not organization_id:
            return Response({"error": "organization_id is required"}, status=400)

        org = _get_organization_or_404(organization_id)
        if not org.is_active:
            return Response({"error": "That school is not accepting members."}, status=400)

        existing = request.user.membership_for(org.id)
        if existing and existing.status == "approved":
            return Response({"error": "You are already a member of that school."}, status=400)
        if existing and existing.status == "pending":
            return Response(
                {"error": "Your request to join that school is already waiting for approval."},
                status=400,
            )

        if existing:
            # A rejected membership at this school. Re-opening the same row
            # rather than creating a second keeps one history per school —
            # and the unique constraint would refuse a duplicate anyway.
            existing.role = "teacher"
            existing.status = "pending"
            existing.reviewed_by = None
            existing.reviewed_at = None
            existing.save(
                update_fields=["role", "status", "reviewed_by", "reviewed_at", "updated_at"]
            )
        else:
            Membership.objects.create(
                user=request.user, organization=org, role="teacher", status="pending"
            )

        # The account's own status only drops to pending when this request is
        # the ONLY thing standing between them and access. A teacher already
        # approved at another school keeps working there while this one is
        # reviewed — losing access to school A because you asked to join
        # school B would be an obvious bug.
        if not request.user.approved_memberships() and request.user.status != "pending":
            request.user.status = "pending"
            request.user.save(update_fields=["status"])

        # Tell somebody. Without this the request lands in a queue nobody is
        # watching: the teacher sees "waiting for approval" and the admins see
        # nothing at all until they happen to open the members page.
        admin_emails = _org_admin_emails(org)
        if admin_emails:
            send_join_request_email(
                to_emails=admin_emails,
                teacher_name=request.user.name or "",
                teacher_email=request.user.email,
                organization_name=org.name,
                review_link=_frontend(f"/admin/organizations/{org.id}"),
            )
        else:
            # A school with no approved admin cannot action this at all, which
            # is worth saying out loud rather than leaving as a silent stall.
            logger.warning(
                "Join request for organization %s has no approved admin to notify", org.id
            )

        logger.info("%s requested to join organization %s", request.user.email, org.id)
        return Response(UserSerializer(request.user).data, status=201)


class OrganizationSwitchView(APIView):
    """Choose which of your schools you are currently working as.

    A teacher with two memberships is, at any moment, working as one of them:
    one masthead on the paper, one budget the tokens come out of, one set of
    colleagues in the admin screens. This is where that choice is made, and it
    is the only thing that changes — nothing is moved, copied or re-scoped.
    Papers stay with the account that made them.

    IsAuthenticated rather than the approved gate: switching is how a teacher
    gets *out* of a school that has gone wrong, and needing to be approved
    somewhere to change which school you are in would be a trap for exactly the
    person who most needs the door.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Every school this account belongs to, and which one is in effect."""
        memberships = request.user.memberships.select_related("organization").all()
        active = request.user.active_membership
        return Response({
            "active_organization_id": active.organization_id if active else None,
            "memberships": [
                {
                    "organization_id": m.organization_id,
                    "organization_name": m.organization.name,
                    "role": m.role,
                    "status": m.status,
                    "is_active": bool(active and m.id == active.id),
                }
                for m in memberships
            ],
        })

    def post(self, request):
        organization_id = request.data.get("organization_id")
        if not organization_id:
            return Response({"error": "organization_id is required"}, status=400)

        membership = request.user.membership_for(organization_id)
        if membership is None:
            # 404 rather than 403: whether a given organization exists is not
            # something a non-member should be able to probe from here.
            raise Http404("You do not belong to that organization")
        if membership.status != "approved":
            return Response(
                {"error": "You are not approved at that school yet."}, status=403
            )

        request.user.active_organization = membership.organization
        request.user.save(update_fields=["active_organization"])
        logger.info(
            "%s switched to organization %s", request.user.email, organization_id
        )
        return Response(UserSerializer(request.user).data)


class OrganizationListView(APIView):
    """Superadmin: list every organization with member count + token usage.

    `with_usage` computes all four per-row numbers for the whole page in a
    fixed five queries. Read straight off the queryset, the serializer fired
    one query per number per organization — forty-odd queries for a dozen
    schools, growing linearly with the account.
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        orgs = with_usage(Organization.objects.all().order_by("name"))
        return Response(OrganizationListSerializer(orgs, many=True).data)


class OrganizationUsageSummaryView(APIView):
    """Superadmin: flat token-usage rollup across all organizations."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        total_tokens = ApiUsage.objects.aggregate(total=Sum("total_tokens"))["total"] or 0
        unassigned = ApiUsage.objects.filter(organization__isnull=True)
        unassigned_tokens = unassigned.aggregate(total=Sum("total_tokens"))["total"] or 0
        orgs = with_usage(Organization.objects.all().order_by("name"))
        return Response({
            "total_tokens": total_tokens,
            "unassigned_tokens": unassigned_tokens,
            # Rupees alongside tokens throughout — see services/usage_pricing.py
            # for why this is an estimate and must be labelled as one.
            "total_cost_inr": inr_cost_of_usage(ApiUsage.objects.all()),
            "unassigned_cost_inr": inr_cost_of_usage(unassigned),
            "organizations": OrganizationListSerializer(orgs, many=True).data,
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

        # Two fields a school's own admin must not be able to set on themselves:
        # the spend cap they are capped by, and whether the school is switched
        # on at all. Superadmin only, and handled outside the profile serializer
        # so they can never be reached by a stray key in an ordinary profile
        # PATCH from the Settings page.
        if request.user.is_superadmin:
            changed = []
            if "monthly_token_limit" in request.data:
                try:
                    limit = int(request.data.get("monthly_token_limit") or 0)
                except (TypeError, ValueError):
                    return Response(
                        {"error": "The monthly token limit must be a whole number."},
                        status=400,
                    )
                if limit < 0:
                    return Response(
                        {"error": "The monthly token limit cannot be negative. Use 0 for no cap."},
                        status=400,
                    )
                org.monthly_token_limit = limit
                changed.append("monthly_token_limit")
            if "is_active" in request.data:
                org.is_active = bool(request.data.get("is_active"))
                changed.append("is_active")
            if changed:
                org.save(update_fields=[*changed, "updated_at"])
                logger.info(
                    "Superadmin %s changed %s on organization %s",
                    request.user.email,
                    ", ".join(changed),
                    org.id,
                )

        logger.info("%s updated organization %s profile", request.user.email, org.id)
        return Response(OrganizationDetailSerializer(org).data)

    @staticmethod
    def _is_admin_of(user, org_id):
        # Asks about THIS school specifically, via the user's membership there
        # — not via whichever school happens to be active. An admin of two
        # schools manages both without switching, and an admin of one still
        # gets a 403 at the other.
        #
        # Membership only: every caller pairs this with its own superadmin
        # check, so folding the superadmin in here would make those reads say
        # something they do not mean.
        return has_org_admin_membership(user, org_id)


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

    def _get_membership(self, request, org_id, user_id):
        if not request.user.is_superadmin and not OrganizationDetailView._is_admin_of(request.user, org_id):
            return None, Response({"error": "You do not manage this organization"}, status=403)
        try:
            membership = Membership.objects.select_related("user", "organization").get(
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

        updates = ["status"]
        member.status = "approved"
        # Give them somewhere to be if they have nowhere yet. A member approved
        # at their second school keeps working as their first.
        if member.active_organization_id is None:
            member.active_organization = membership.organization
            updates.append("active_organization")
        member.save(update_fields=updates)

        send_membership_approved_email(
            to_email=member.email,
            user_name=member.name or "",
            organization_name=membership.organization.name,
        )

        logger.info("%s approved member %s in organization %s", request.user.email, member.email, org_id)
        return Response(MembershipSerializer(membership).data)


class OrganizationMemberRejectView(_OrganizationMemberActionView):
    def post(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        member = membership.user
        # Cognito groups are an account-wide fact, so they only change when the
        # account loses its LAST approved school. Demoting someone who still
        # teaches elsewhere would lock them out of a school that never rejected
        # them.
        if not _approved_elsewhere(member, membership.organization_id):
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

        _resettle_after_losing(member, membership.organization_id, fallback_status="rejected")

        send_membership_rejected_email(
            to_email=member.email,
            user_name=member.name or "",
            organization_name=membership.organization.name,
        )

        logger.info("%s rejected member %s in organization %s", request.user.email, member.email, org_id)
        return Response(MembershipSerializer(membership).data)


class OrganizationMemberRemoveView(_OrganizationMemberActionView):
    def delete(self, request, org_id, user_id):
        membership, error = self._get_membership(request, org_id, user_id)
        if error:
            return error

        member = membership.user
        organization_id = membership.organization_id
        # Same rule as rejection: an account-wide demotion only when this was
        # the last approved school. Fail-closed on a Cognito error is kept —
        # deleting the row while the group sync failed would leave someone
        # approved in Cognito and a stranger in the database.
        if not _approved_elsewhere(member, organization_id):
            cognito_username = get_cognito_username(member)
            try:
                remove_user_from_group(cognito_username, "approved")
                add_user_to_group(cognito_username, "pending")
            except Exception as e:
                logger.error("Failed to sync Cognito groups for %s: %s", member.email, e)
                return Response({"error": f"Failed to sync with Cognito: {str(e)}"}, status=500)

        membership.delete()
        _resettle_after_losing(member, organization_id, fallback_status="pending")

        logger.info("%s removed member %s from organization %s", request.user.email, member.email, org_id)
        return Response(status=204)
