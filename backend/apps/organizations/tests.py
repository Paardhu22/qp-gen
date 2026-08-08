from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.organizations.models import Membership, Organization
from apps.organizations.views import (
    OrganizationMemberAssignView,
    OrganizationMemberRemoveView,
    OrganizationMemberRoleView,
)


class MemberRoleChangeTests(TestCase):
    """The role endpoint, exercised through the view.

    `force_authenticate` rather than a signed request: authentication is
    Cognito's, tested in apps.accounts, and mocking a JWT here would test the
    validator a third time instead of the rule this endpoint actually enforces.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.org = Organization.objects.create(name="Nalanda High")

        self.admin = self._member("admin@school.test", "org_admin", "approved")
        self.teacher = self._member("teacher@school.test", "teacher", "approved")
        mail.outbox = []

    def _member(self, email: str, role: str, status: str) -> User:
        user = User.objects.create(name=email.split("@")[0], email=email, status="approved")
        Membership.objects.create(
            user=user, organization=self.org, role=role, status=status
        )
        return user

    def _change_role(self, *, actor: User, target: User, role: str):
        request = self.factory.post(
            f"/api/organizations/{self.org.id}/members/{target.id}/role",
            {"role": role},
            format="json",
        )
        force_authenticate(request, user=actor)
        return OrganizationMemberRoleView.as_view()(
            request, org_id=self.org.id, user_id=target.id
        )

    def test_promoting_a_teacher_updates_the_membership_and_emails_them(self):
        response = self._change_role(actor=self.admin, target=self.teacher, role="org_admin")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "org_admin")
        self.teacher.membership.refresh_from_db()
        self.assertEqual(self.teacher.membership.role, "org_admin")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.teacher.email])
        self.assertIn("school admin", mail.outbox[0].subject)

    def test_demoting_is_allowed_once_a_second_admin_exists(self):
        self._change_role(actor=self.admin, target=self.teacher, role="org_admin")
        mail.outbox = []

        # Reload: the promotion wrote a new row, but `self.teacher` still holds
        # the membership cached from setUp, and the permission check reads it.
        # A real request builds the user from scratch every time.
        promoted = User.objects.get(pk=self.teacher.pk)
        response = self._change_role(actor=promoted, target=self.admin, role="teacher")

        self.assertEqual(response.status_code, 200)
        self.admin.membership.refresh_from_db()
        self.assertEqual(self.admin.membership.role, "teacher")
        self.assertEqual(len(mail.outbox), 1)

    def test_the_last_admin_cannot_be_demoted(self):
        # The superadmin does the demoting, so this fails on the last-admin
        # rule rather than on the "not your own role" one.
        superadmin = User.objects.create(
            name="Root", email="root@qp.test", status="approved", is_superadmin=True
        )
        response = self._change_role(actor=superadmin, target=self.admin, role="teacher")

        self.assertEqual(response.status_code, 400)
        self.assertIn("only admin", response.data["error"])
        self.admin.membership.refresh_from_db()
        self.assertEqual(self.admin.membership.role, "org_admin")
        self.assertEqual(mail.outbox, [])

    def test_an_admin_cannot_change_their_own_role(self):
        self._change_role(actor=self.admin, target=self.teacher, role="org_admin")
        mail.outbox = []

        response = self._change_role(actor=self.admin, target=self.admin, role="teacher")

        self.assertEqual(response.status_code, 400)
        self.assertIn("your own role", response.data["error"])
        self.assertEqual(mail.outbox, [])

    def test_a_pending_member_must_be_approved_before_being_promoted(self):
        applicant = self._member("new@school.test", "teacher", "pending")
        response = self._change_role(actor=self.admin, target=applicant, role="org_admin")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Approve this member", response.data["error"])
        self.assertEqual(mail.outbox, [])

    def test_an_unknown_role_is_rejected(self):
        response = self._change_role(actor=self.admin, target=self.teacher, role="principal")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_setting_the_role_it_already_has_is_a_no_op(self):
        """The caller and the database already agree — re-sync, don't error."""
        response = self._change_role(actor=self.admin, target=self.teacher, role="teacher")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "teacher")
        # No decision was made, so nothing to tell them about.
        self.assertEqual(mail.outbox, [])

    def test_a_teacher_cannot_change_anyone_role(self):
        other = self._member("other@school.test", "teacher", "approved")
        response = self._change_role(actor=self.teacher, target=other, role="org_admin")

        self.assertEqual(response.status_code, 403)

    @patch("apps.organizations.views.remove_user_from_group")
    @patch("apps.organizations.views.add_user_to_group")
    def test_removing_a_member_emails_them(self, _add, _remove):
        request = self.factory.delete(
            f"/api/organizations/{self.org.id}/members/{self.teacher.id}"
        )
        force_authenticate(request, user=self.admin)
        response = OrganizationMemberRemoveView.as_view()(
            request, org_id=self.org.id, user_id=self.teacher.id
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Membership.objects.filter(user=self.teacher).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.teacher.email])

    @patch("apps.organizations.views.remove_user_from_group")
    @patch("apps.organizations.views.add_user_to_group")
    def test_the_last_admin_cannot_be_removed(self, _add, _remove):
        superadmin = User.objects.create(
            name="Root", email="root@qp.test", status="approved", is_superadmin=True
        )
        request = self.factory.delete(
            f"/api/organizations/{self.org.id}/members/{self.admin.id}"
        )
        force_authenticate(request, user=superadmin)
        response = OrganizationMemberRemoveView.as_view()(
            request, org_id=self.org.id, user_id=self.admin.id
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Membership.objects.filter(user=self.admin).exists())


class MemberAssignTests(TestCase):
    """Placing a user in a school, and moving them between schools."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.source = Organization.objects.create(name="Nalanda High")
        self.target = Organization.objects.create(name="Takshashila School")
        self.superadmin = User.objects.create(
            name="Root", email="root@qp.test", status="approved", is_superadmin=True
        )
        mail.outbox = []

    def _user(self, email, org=None, role="teacher", status="approved"):
        user = User.objects.create(
            name=email.split("@")[0], email=email, status="approved"
        )
        if org:
            Membership.objects.create(
                user=user, organization=org, role=role, status=status
            )
        return user

    def _assign(self, *, actor, target_user, organization_id, role=None):
        body = {"organization_id": organization_id}
        if role:
            body["role"] = role
        request = self.factory.post(
            f"/api/organizations/members/{target_user.id}/assign", body, format="json"
        )
        force_authenticate(request, user=actor)
        return OrganizationMemberAssignView.as_view()(request, user_id=target_user.id)

    def test_a_user_with_no_school_is_placed_and_starts_pending(self):
        """The receiving school still gets its say — approval syncs Cognito."""
        user = self._user("nobody@school.test")
        response = self._assign(
            actor=self.superadmin, target_user=user, organization_id=self.target.id
        )

        self.assertEqual(response.status_code, 200)
        membership = Membership.objects.get(user=user)
        self.assertEqual(membership.organization_id, self.target.id)
        self.assertEqual(membership.status, "pending")
        self.assertEqual(membership.role, "teacher")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("added", mail.outbox[0].subject)

    def test_moving_keeps_an_approved_member_approved(self):
        user = self._user("teacher@school.test", org=self.source)
        response = self._assign(
            actor=self.superadmin, target_user=user, organization_id=self.target.id
        )

        self.assertEqual(response.status_code, 200)
        membership = Membership.objects.get(user=user)
        self.assertEqual(membership.organization_id, self.target.id)
        self.assertEqual(membership.status, "approved")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("moved", mail.outbox[0].subject)

    def test_an_admin_arrives_as_a_teacher_unless_asked_otherwise(self):
        """Administering one school says nothing about the next."""
        # A second admin so the move is not blocked by the last-admin rule.
        self._user("other@school.test", org=self.source, role="org_admin")
        user = self._user("head@school.test", org=self.source, role="org_admin")

        self._assign(
            actor=self.superadmin, target_user=user, organization_id=self.target.id
        )
        self.assertEqual(Membership.objects.get(user=user).role, "teacher")

    def test_an_explicit_role_is_honoured(self):
        user = self._user("teacher@school.test", org=self.source)
        self._assign(
            actor=self.superadmin,
            target_user=user,
            organization_id=self.target.id,
            role="org_admin",
        )
        self.assertEqual(Membership.objects.get(user=user).role, "org_admin")

    def test_the_source_school_cannot_be_stranded(self):
        user = self._user("head@school.test", org=self.source, role="org_admin")
        response = self._assign(
            actor=self.superadmin, target_user=user, organization_id=self.target.id
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("only admin", response.data["error"])
        self.assertEqual(Membership.objects.get(user=user).organization_id, self.source.id)
        self.assertEqual(mail.outbox, [])

    def test_assigning_to_the_school_they_are_already_at_is_a_no_op(self):
        user = self._user("teacher@school.test", org=self.source)
        response = self._assign(
            actor=self.superadmin, target_user=user, organization_id=self.source.id
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_an_unknown_organization_is_a_404(self):
        user = self._user("teacher@school.test")
        response = self._assign(
            actor=self.superadmin, target_user=user, organization_id="nope"
        )
        self.assertEqual(response.status_code, 404)

    def test_an_org_admin_cannot_move_anyone(self):
        """Otherwise they could pull members out of a school they don't manage."""
        admin = self._user("admin@school.test", org=self.source, role="org_admin")
        user = self._user("teacher@school.test", org=self.source)

        response = self._assign(
            actor=admin, target_user=user, organization_id=self.target.id
        )
        self.assertEqual(response.status_code, 403)
