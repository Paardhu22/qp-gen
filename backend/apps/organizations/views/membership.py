"""Who belongs to an organization: joining, switching, approving, rejecting, roles, removal."""

import logging
from django.db.models import Count
from django.http import Http404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.common.permissions import IsOrgAdminOrSuperAdmin, IsSuperAdmin
from apps.accounts.models import User
from apps.projects.models import Paper, Project, Question
from services.auth.emails import (
    send_join_request_email,
    send_membership_approved_email,
    send_membership_moved_email,
    send_membership_rejected_email,
    send_membership_removed_email,
    send_role_changed_email,
)
from ..models import Membership
from ..serializers import MembershipSerializer
from services.auth import cognito
from apps.accounts import views as accounts_views
from apps.organizations.views.common import _approved_elsewhere, _frontend, _get_organization_or_404, _org_admin_emails, _resettle_after_losing
from apps.organizations.views.directory import OrganizationDetailView

logger = logging.getLogger("[ORGANIZATIONS_VIEWS]")


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
        # A paper row only exists once someone saves one. Generating without
        # saving still leaves questions behind, and reporting a bare "0 papers"
        # for someone with a six-figure token count reads as a broken screen
        # rather than as the distinction it actually is — so the bank is
        # counted too, and the empty state can say which of the two happened.
        projects = Project.objects.filter(user_id=user_id)
        return Response(
            {
                "user": {
                    "id": membership.user.id,
                    "name": membership.user.name,
                    "email": membership.user.email,
                },
                "question_bank": {
                    "projects": projects.count(),
                    "questions": Question.objects.filter(project__user_id=user_id).count(),
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
        cognito_username = accounts_views.get_cognito_username(member)
        try:
            cognito.add_user_to_group(cognito_username, "approved")
            cognito.remove_user_from_group(cognito_username, "pending")
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

        # Rejecting the sole admin locks the school out just as surely as
        # removing them does.
        if self._is_last_admin(membership):
            return Response({"error": self.LAST_ADMIN_ERROR}, status=400)

        member = membership.user
        # Cognito groups are an account-wide fact, so they only change when the
        # account loses its LAST approved school. Demoting someone who still
        # teaches elsewhere would lock them out of a school that never rejected
        # them.
        if not _approved_elsewhere(member, membership.organization_id):
            cognito_username = accounts_views.get_cognito_username(member)
            try:
                cognito.remove_user_from_group(cognito_username, "approved")
                cognito.add_user_to_group(cognito_username, "pending")
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
        organization_id = membership.organization_id
        organization_name = membership.organization.name
        # Same rule as rejection: an account-wide demotion only when this was
        # the last approved school. Fail-closed on a Cognito error is kept —
        # deleting the row while the group sync failed would leave someone
        # approved in Cognito and a stranger in the database.
        if not _approved_elsewhere(member, organization_id):
            cognito_username = accounts_views.get_cognito_username(member)
            try:
                cognito.remove_user_from_group(cognito_username, "approved")
                cognito.add_user_to_group(cognito_username, "pending")
            except Exception as e:
                logger.error("Failed to sync Cognito groups for %s: %s", member.email, e)
                return Response({"error": f"Failed to sync with Cognito: {str(e)}"}, status=500)

        membership.delete()
        _resettle_after_losing(member, organization_id, fallback_status="pending")

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

        # Memberships are per school, so "already there" means any membership at
        # the target, not just the active one — moving the active row onto a
        # school they already have a row at would break (user, organization)
        # uniqueness.
        at_target = user.membership_for(target.id)
        if at_target:
            if at_target.role == role:
                # Caller and database already agree — let a stale table re-sync
                # rather than reporting an error for a no-op.
                return Response(MembershipSerializer(at_target).data)
            return Response(
                {
                    "error": "They are already at this school. Use the role "
                    "picker to change what they can do there."
                },
                status=400,
            )

        membership = user.active_membership
        source = membership.organization if membership else None

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
            if user.active_organization_id == source.id:
                user.active_organization = target
                user.save(update_fields=["active_organization"])
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
