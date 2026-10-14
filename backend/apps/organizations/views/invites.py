"""Invitations: create, revoke, teacher invites, and accepting an invite."""

import logging
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.common.permissions import IsOrgAdminOrSuperAdmin, IsSuperAdmin
from services.auth.emails import send_organization_invite_email, send_teacher_invite_email
from ..models import Membership, Organization, OrganizationInvite
from ..serializers import (
    PROFILE_FIELDS,
    OrganizationDetailSerializer,
    OrganizationInviteSerializer,
    OrganizationProfileSerializer,
)
from apps.organizations.views.common import _first_error, _frontend, _get_organization_or_404, _new_invite, _promote_to_approved, _reconcile_expired
from apps.organizations.views.directory import OrganizationDetailView

logger = logging.getLogger("[ORGANIZATIONS_VIEWS]")


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
