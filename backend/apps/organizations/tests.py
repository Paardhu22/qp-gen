import secrets
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.generation.models import ApiUsage
from services.usage_limits import UsageLimitExceeded, check_monthly_token_limit
from services.usage_pricing import usd_to_inr_rate

from .domains import domain_of_email, normalize_domains
from .models import Membership, Organization, OrganizationInvite


class OrganizationPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="North School")
        self.other_org = Organization.objects.create(name="South School")
        self.pending = User.objects.create(
            id="11111111111111111111111111111111",
            name="Pending",
            email="pending@example.com",
            status="pending",
        )
        self.approved = User.objects.create(
            id="22222222222222222222222222222222",
            name="Approved",
            email="approved@example.com",
            status="approved",
        )
        Membership.objects.create(
            user=self.approved,
            organization=self.org,
            role="teacher",
            status="approved",
        )
        self.org_admin = User.objects.create(
            id="33333333333333333333333333333333",
            name="Org Admin",
            email="admin@example.com",
            status="approved",
        )
        Membership.objects.create(
            user=self.org_admin,
            organization=self.org,
            role="org_admin",
            status="approved",
        )

    def test_pending_user_is_refused_by_product_endpoint(self):
        self.client.force_authenticate(user=self.pending)
        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, 403)

    def test_approved_user_is_allowed_by_product_endpoint(self):
        self.client.force_authenticate(user=self.approved)
        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, 200)

    def test_org_admin_cannot_manage_another_org(self):
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.get(f"/api/organizations/{self.other_org.id}")
        self.assertEqual(response.status_code, 403)

    def test_rejected_member_can_request_again(self):
        rejected = User.objects.create(
            id="44444444444444444444444444444444",
            name="Rejected",
            email="rejected@example.com",
            status="rejected",
        )
        Membership.objects.create(
            user=rejected,
            organization=self.other_org,
            role="teacher",
            status="rejected",
            reviewed_by=self.org_admin,
            reviewed_at=timezone.now(),
        )

        self.client.force_authenticate(user=rejected)
        response = self.client.post(
            "/api/organizations/join",
            {"organization_id": self.org.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        # Multi-org: the rejection at the other school is history and stays as
        # history. What matters is that the new request exists and is waiting.
        membership = Membership.objects.get(user=rejected, organization=self.org)
        self.assertEqual(membership.status, "pending")
        self.assertIsNone(membership.reviewed_by)
        self.assertEqual(
            Membership.objects.get(user=rejected, organization=self.other_org).status,
            "rejected",
        )

    def test_user_organization_requires_approved_membership(self):
        Membership.objects.create(
            user=self.pending,
            organization=self.org,
            role="teacher",
            status="pending",
        )

        self.assertIsNone(self.pending.organization)
        self.assertEqual(self.approved.organization, self.org)

    def test_monthly_token_limit_blocks_generation_stream(self):
        self.org.monthly_token_limit = 10
        self.org.save(update_fields=["monthly_token_limit"])
        ApiUsage.objects.create(
            user=self.approved,
            organization=self.org,
            operation="test",
            model="test",
            total_tokens=10,
        )

        from services.pool.pipeline import stream_pool_questions

        stream = stream_pool_questions(
            user=self.approved,
            pdf_source_ids=["source"],
            topic="Light",
            count=1,
            difficulty="medium",
        )
        first = next(iter(stream))
        self.assertIn("ORG_TOKEN_LIMIT_EXCEEDED", first)


class EmailDomainTests(TestCase):
    """A school's email domain, used to pre-select the right school at signup."""

    def test_a_domain_is_read_out_of_an_address(self):
        self.assertEqual(domain_of_email("R.Menon@DPSBangalore.edu.in "), "dpsbangalore.edu.in")
        self.assertEqual(domain_of_email("not-an-address"), "")

    def test_what_people_actually_type_is_accepted(self):
        self.assertEqual(
            normalize_domains(" @School.EDU , https://www.second.org/ "),
            "school.edu,second.org",
        )

    def test_duplicates_collapse(self):
        self.assertEqual(normalize_domains("school.edu, School.edu"), "school.edu")

    def test_a_public_provider_is_refused(self):
        # Claiming gmail.com would silently match every consumer address on the
        # platform, which is the opposite of identifying one school.
        with self.assertRaises(ValueError):
            normalize_domains("gmail.com")

    def test_something_that_is_not_a_domain_is_refused(self):
        with self.assertRaises(ValueError):
            normalize_domains("school")

    def test_the_public_list_flags_and_promotes_the_matching_school(self):
        Organization.objects.create(name="Zeta School", email_domains="zeta.edu.in")
        Organization.objects.create(name="Alpha School")

        response = APIClient().get("/api/organizations/public?email=teacher@zeta.edu.in")

        self.assertEqual(response.status_code, 200)
        # Matched school first, even though it sorts last alphabetically.
        self.assertEqual(response.data[0]["name"], "Zeta School")
        self.assertTrue(response.data[0]["matches_email_domain"])
        self.assertFalse(response.data[1]["matches_email_domain"])

    def test_without_an_email_nothing_is_flagged(self):
        Organization.objects.create(name="Zeta School", email_domains="zeta.edu.in")
        response = APIClient().get("/api/organizations/public")
        self.assertFalse(response.data[0]["matches_email_domain"])

    def test_an_admin_can_save_domains_through_the_profile_patch(self):
        org = Organization.objects.create(name="North School")
        admin = User.objects.create(
            id="aa111111111111111111111111111111",
            name="Admin",
            email="a@north.edu",
            status="approved",
        )
        Membership.objects.create(
            user=admin, organization=org, role="org_admin", status="approved"
        )
        client = APIClient()
        client.force_authenticate(user=admin)

        response = client.patch(
            f"/api/organizations/{org.id}",
            {"email_domains": "@North.edu"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email_domains"], ["north.edu"])


class TeacherInviteTests(TestCase):
    """An org admin's invite link, which skips the approval queue."""

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="North School")
        self.other_org = Organization.objects.create(name="South School")
        self.admin = User.objects.create(
            id="bb111111111111111111111111111111",
            name="Admin",
            email="admin@north.edu",
            status="approved",
        )
        Membership.objects.create(
            user=self.admin, organization=self.org, role="org_admin", status="approved"
        )
        self.teacher = User.objects.create(
            id="bb222222222222222222222222222222",
            name="New Teacher",
            email="teacher@north.edu",
            status="pending",
        )
        self.superadmin = User.objects.create(
            id="bb999999999999999999999999999999",
            name="Super",
            email="super@example.com",
            status="admin",
            is_superadmin=True,
        )

    def _invite(self, email="teacher@north.edu", org=None):
        self.client.force_authenticate(user=self.admin)
        return self.client.post(
            f"/api/organizations/{(org or self.org).id}/invites",
            {"email": email},
            format="json",
        )

    def test_an_admin_invites_a_teacher_to_their_own_school(self):
        response = self._invite()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["role"], "teacher")
        self.assertEqual(response.data["organization"], self.org.id)

    def test_an_admin_cannot_invite_into_another_school(self):
        response = self._invite(org=self.other_org)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.other_org.invites.count(), 0)

    def test_accepting_joins_the_school_already_approved(self):
        self._invite()
        token = OrganizationInvite.objects.get(email="teacher@north.edu").token

        self.client.force_authenticate(user=self.teacher)
        response = self.client.post(
            "/api/organizations/invites/accept", {"token": token}, format="json"
        )

        self.assertEqual(response.status_code, 201)
        membership = Membership.objects.get(user=self.teacher)
        self.assertEqual(membership.organization_id, self.org.id)
        self.assertEqual(membership.status, "approved")
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, "approved")

    def test_accepting_never_reveals_the_member_roster(self):
        # A teacher who has just joined is not an admin — the detail serializer
        # carries every colleague's token spend on it.
        self._invite()
        token = OrganizationInvite.objects.get(email="teacher@north.edu").token
        self.client.force_authenticate(user=self.teacher)

        response = self.client.post(
            "/api/organizations/invites/accept", {"token": token}, format="json"
        )

        self.assertNotIn("members", response.data)

    def test_the_organization_comes_off_the_invite_not_the_request(self):
        # Otherwise any valid teacher invite is membership of any school.
        self._invite()
        token = OrganizationInvite.objects.get(email="teacher@north.edu").token
        self.client.force_authenticate(user=self.teacher)

        self.client.post(
            "/api/organizations/invites/accept",
            {"token": token, "organization_id": self.other_org.id,
             "organization_name": "Somewhere Else"},
            format="json",
        )

        self.assertEqual(Membership.objects.get(user=self.teacher).organization_id, self.org.id)

    def test_someone_elses_invite_is_refused(self):
        self._invite(email="intended@north.edu")
        token = OrganizationInvite.objects.get(email="intended@north.edu").token

        self.client.force_authenticate(user=self.teacher)
        response = self.client.post(
            "/api/organizations/invites/accept", {"token": token}, format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Membership.objects.filter(user=self.teacher).exists())

    def test_an_expired_invite_is_refused(self):
        self._invite()
        invite = OrganizationInvite.objects.get(email="teacher@north.edu")
        invite.expires_at = timezone.now() - timedelta(days=1)
        invite.save(update_fields=["expires_at"])

        self.client.force_authenticate(user=self.teacher)
        response = self.client.post(
            "/api/organizations/invites/accept", {"token": invite.token}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        invite.refresh_from_db()
        self.assertEqual(invite.status, "expired")

    def test_re_inviting_retires_the_previous_link(self):
        # A resend must not leave a second working credential in an inbox.
        self._invite()
        first = OrganizationInvite.objects.get(email="teacher@north.edu")
        self._invite()

        first.refresh_from_db()
        self.assertEqual(first.status, "revoked")
        self.assertEqual(
            OrganizationInvite.objects.filter(
                email="teacher@north.edu", status="pending"
            ).count(),
            1,
        )

    def test_inviting_someone_who_already_belongs_somewhere_is_refused(self):
        response = self._invite(email=self.admin.email)
        self.assertEqual(response.status_code, 400)


class InviteRevocationTests(TestCase):
    """Withdrawing an invite that is still live in somebody's inbox."""

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="North School")
        self.other_org = Organization.objects.create(name="South School")
        self.superadmin = User.objects.create(
            id="cc999999999999999999999999999999",
            name="Super",
            email="super@example.com",
            status="admin",
            is_superadmin=True,
        )
        self.admin = User.objects.create(
            id="cc111111111111111111111111111111",
            name="Admin",
            email="admin@north.edu",
            status="approved",
        )
        Membership.objects.create(
            user=self.admin, organization=self.org, role="org_admin", status="approved"
        )

    def _invite(self, *, org, role="teacher", email="x@north.edu"):
        return OrganizationInvite.objects.create(
            email=email,
            token=secrets.token_urlsafe(16),
            role=role,
            organization=org,
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_an_admin_revokes_an_invite_for_their_own_school(self):
        invite = self._invite(org=self.org)
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(f"/api/organizations/invites/{invite.id}")

        self.assertEqual(response.status_code, 200)
        invite.refresh_from_db()
        self.assertEqual(invite.status, "revoked")

    def test_an_admin_cannot_revoke_another_schools_invite(self):
        invite = self._invite(org=self.other_org)
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(f"/api/organizations/invites/{invite.id}")

        self.assertEqual(response.status_code, 403)
        invite.refresh_from_db()
        self.assertEqual(invite.status, "pending")

    def test_an_admin_cannot_revoke_an_org_creation_invite(self):
        # It belongs to no organization yet, so it has no owner but the superadmin.
        invite = self._invite(org=None, role="org_admin")
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(f"/api/organizations/invites/{invite.id}")

        self.assertEqual(response.status_code, 403)

    def test_the_superadmin_can_revoke_anything(self):
        invite = self._invite(org=None, role="org_admin")
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.delete(f"/api/organizations/invites/{invite.id}")

        self.assertEqual(response.status_code, 200)
        invite.refresh_from_db()
        self.assertEqual(invite.status, "revoked")

    def test_revoking_twice_is_not_an_error(self):
        invite = self._invite(org=self.org)
        self.client.force_authenticate(user=self.admin)

        self.client.delete(f"/api/organizations/invites/{invite.id}")
        response = self.client.delete(f"/api/organizations/invites/{invite.id}")

        self.assertEqual(response.status_code, 200)

    def test_an_accepted_invite_cannot_be_revoked(self):
        invite = self._invite(org=self.org)
        invite.status = "accepted"
        invite.save(update_fields=["status"])
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(f"/api/organizations/invites/{invite.id}")

        self.assertEqual(response.status_code, 400)

    def test_a_revoked_invite_can_no_longer_be_accepted(self):
        invite = self._invite(org=self.org, email="teacher@north.edu")
        joiner = User.objects.create(
            id="cc222222222222222222222222222222",
            name="Teacher",
            email="teacher@north.edu",
            status="pending",
        )
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f"/api/organizations/invites/{invite.id}")

        self.client.force_authenticate(user=joiner)
        response = self.client.post(
            "/api/organizations/invites/accept", {"token": invite.token}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Membership.objects.filter(user=joiner).exists())

    def test_the_listing_settles_expired_invites(self):
        invite = self._invite(org=None, role="org_admin")
        invite.expires_at = timezone.now() - timedelta(days=1)
        invite.save(update_fields=["expires_at"])
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get("/api/organizations/invites")

        self.assertEqual(response.status_code, 200)
        invite.refresh_from_db()
        self.assertEqual(invite.status, "expired")

    def test_the_token_is_never_serialized(self):
        self._invite(org=None, role="org_admin")
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get("/api/organizations/invites")

        self.assertNotIn("token", response.data[0])


class OrganizationUsageReportingTests(TestCase):
    """Batched aggregation (no N+1) and rupee conversion on the admin panels."""

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="North School")
        self.superadmin = User.objects.create(
            id="dd999999999999999999999999999999",
            name="Super",
            email="super@example.com",
            status="admin",
            is_superadmin=True,
        )
        self.teacher = User.objects.create(
            id="dd111111111111111111111111111111",
            name="Teacher",
            email="t@north.edu",
            status="approved",
        )
        Membership.objects.create(
            user=self.teacher, organization=self.org, role="teacher", status="approved"
        )
        ApiUsage.objects.create(
            user=self.teacher,
            organization=self.org,
            operation="pool",
            model="gpt-4.1-mini",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            total_tokens=2_000_000,
        )

    def test_the_list_reports_tokens_and_rupees(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get("/api/organizations/")

        row = response.data[0]
        self.assertEqual(row["total_tokens"], 2_000_000)
        self.assertEqual(row["member_count"], 1)
        self.assertEqual(row["admin_email"], None)
        # 1M prompt at $0.40 + 1M completion at $1.60 = $2.00, at the default rate.
        self.assertAlmostEqual(row["total_cost_inr"], 2.00 * usd_to_inr_rate(), places=2)

    def test_the_list_does_not_scale_its_queries_with_the_number_of_schools(self):
        for i in range(6):
            Organization.objects.create(name=f"School {i}")
        self.client.force_authenticate(user=self.superadmin)

        # One query for the organizations, four batched aggregates for the four
        # numbers on every row. The count is not the point — that it does not
        # move when the number of schools triples is.
        with self.assertNumQueries(5):
            self.client.get("/api/organizations/")

        for i in range(6, 20):
            Organization.objects.create(name=f"School {i}")
        with self.assertNumQueries(5):
            self.client.get("/api/organizations/")

    def test_the_member_roster_prices_each_member(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get(f"/api/organizations/{self.org.id}")

        member = response.data["members"][0]
        self.assertEqual(member["tokens_consumed"], 2_000_000)
        self.assertGreater(member["cost_inr"], 0)

    def test_only_the_superadmin_may_set_the_spend_cap(self):
        admin = User.objects.create(
            id="dd222222222222222222222222222222",
            name="Admin",
            email="a@north.edu",
            status="approved",
        )
        Membership.objects.create(
            user=admin, organization=self.org, role="org_admin", status="approved"
        )
        self.client.force_authenticate(user=admin)

        response = self.client.patch(
            f"/api/organizations/{self.org.id}",
            {"monthly_token_limit": 999_999_999},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.monthly_token_limit, 0)

    def test_the_superadmin_sets_the_spend_cap(self):
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.patch(
            f"/api/organizations/{self.org.id}",
            {"monthly_token_limit": 5000},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.monthly_token_limit, 5000)


class UnapprovedMemberBillingTests(TestCase):
    """A member's spend belongs to their school whether or not they are approved."""

    def setUp(self):
        self.org = Organization.objects.create(name="North School", monthly_token_limit=100)
        self.pending = User.objects.create(
            id="ee111111111111111111111111111111",
            name="Pending",
            email="p@north.edu",
            status="pending",
        )
        Membership.objects.create(
            user=self.pending, organization=self.org, role="teacher", status="pending"
        )

    def test_authorisation_still_says_no_organization(self):
        self.assertIsNone(self.pending.organization)

    def test_billing_still_says_the_school_pays(self):
        self.assertEqual(self.pending.billing_organization, self.org)

    def test_an_unapproved_members_spend_counts_against_the_cap(self):
        ApiUsage.objects.create(
            user=self.pending,
            organization=self.pending.billing_organization,
            operation="pool",
            model="gpt-4.1-mini",
            total_tokens=500,
        )
        with self.assertRaises(UsageLimitExceeded):
            check_monthly_token_limit(self.pending)


class MultiOrganizationMembershipTests(TestCase):
    """A teacher who works at more than one school. See User.active_membership."""

    def setUp(self):
        self.client = APIClient()
        self.north = Organization.objects.create(name="North School")
        self.south = Organization.objects.create(name="South School")
        self.teacher = User.objects.create(
            id="ba111111111111111111111111111111",
            name="Two Schools",
            email="both@example.com",
            status="approved",
        )
        self.north_admin = User.objects.create(
            id="ba222222222222222222222222222222",
            name="North Admin",
            email="north-admin@example.com",
            status="approved",
        )
        Membership.objects.create(
            user=self.north_admin, organization=self.north, role="org_admin", status="approved"
        )

    def _join(self, org, status="approved"):
        return Membership.objects.create(
            user=self.teacher, organization=org, role="teacher", status=status
        )

    # ── resolution ────────────────────────────────────────────────────────
    def test_one_school_needs_no_choosing(self):
        self._join(self.north)
        self.assertEqual(self.teacher.organization, self.north)

    def test_the_chosen_school_wins_over_the_fallback(self):
        self._join(self.north)
        self._join(self.south)
        self.teacher.active_organization = self.south
        self.teacher.save(update_fields=["active_organization"])

        self.assertEqual(self.teacher.organization, self.south)

    def test_a_pending_only_account_still_has_a_membership_to_show(self):
        # It is what tells the teacher they are waiting on someone.
        self._join(self.north, status="pending")
        self.assertIsNotNone(self.teacher.membership)
        # …but it authorises nothing.
        self.assertIsNone(self.teacher.organization)

    def test_no_memberships_resolves_to_nothing_rather_than_raising(self):
        self.assertIsNone(self.teacher.membership)
        self.assertIsNone(self.teacher.organization)
        self.assertIsNone(self.teacher.billing_organization)

    # ── joining ───────────────────────────────────────────────────────────
    def test_a_teacher_can_request_a_second_school(self):
        self._join(self.north)
        self.client.force_authenticate(user=self.teacher)

        response = self.client.post(
            "/api/organizations/join", {"organization_id": self.south.id}, format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.teacher.memberships.count(), 2)

    def test_joining_a_second_school_does_not_disturb_the_first(self):
        # Losing access to school A because you asked to join school B would be
        # an obvious bug.
        self._join(self.north)
        self.client.force_authenticate(user=self.teacher)

        self.client.post(
            "/api/organizations/join", {"organization_id": self.south.id}, format="json"
        )

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, "approved")
        self.assertEqual(
            self.teacher.memberships.get(organization=self.north).status, "approved"
        )

    def test_asking_twice_at_the_same_school_is_refused(self):
        self._join(self.north, status="pending")
        self.client.force_authenticate(user=self.teacher)

        response = self.client.post(
            "/api/organizations/join", {"organization_id": self.north.id}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.teacher.memberships.count(), 1)

    # ── switching ─────────────────────────────────────────────────────────
    def test_switching_changes_which_school_is_in_effect(self):
        self._join(self.north)
        self._join(self.south)
        self.client.force_authenticate(user=self.teacher)

        response = self.client.post(
            "/api/organizations/switch", {"organization_id": self.south.id}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.organization, self.south)

    def test_you_cannot_switch_to_a_school_you_do_not_belong_to(self):
        self._join(self.north)
        self.client.force_authenticate(user=self.teacher)

        response = self.client.post(
            "/api/organizations/switch", {"organization_id": self.south.id}, format="json"
        )

        self.assertEqual(response.status_code, 404)

    def test_you_cannot_switch_to_a_school_that_has_not_approved_you(self):
        self._join(self.north)
        self._join(self.south, status="pending")
        self.client.force_authenticate(user=self.teacher)

        response = self.client.post(
            "/api/organizations/switch", {"organization_id": self.south.id}, format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.organization, self.north)

    def test_the_listing_names_every_school_and_which_is_active(self):
        self._join(self.north)
        self._join(self.south, status="pending")
        self.client.force_authenticate(user=self.teacher)

        response = self.client.get("/api/organizations/switch")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["memberships"]), 2)
        self.assertEqual(response.data["active_organization_id"], self.north.id)

    # ── losing one school ─────────────────────────────────────────────────
    def test_removal_from_one_school_leaves_the_other_intact(self):
        self._join(self.north)
        self._join(self.south)
        self.client.force_authenticate(user=self.north_admin)

        self.client.delete(
            f"/api/organizations/{self.north.id}/members/{self.teacher.id}"
        )

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, "approved")
        self.assertEqual(self.teacher.organization, self.south)

    def test_removal_from_the_last_school_demotes_the_account(self):
        self._join(self.north)
        self.client.force_authenticate(user=self.north_admin)

        # Cognito is stubbed because losing the last school is the one path
        # that DOES touch the group sync, and that sync fails closed (D6) —
        # against a real pool with no such user it 500s and the membership
        # survives, which would hide what this test is about.
        with patch("apps.organizations.views.add_user_to_group"), patch(
            "apps.organizations.views.remove_user_from_group"
        ):
            self.client.delete(
                f"/api/organizations/{self.north.id}/members/{self.teacher.id}"
            )

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, "pending")
        self.assertIsNone(self.teacher.organization)

    def test_only_losing_the_last_school_touches_the_cognito_groups(self):
        # An account still teaching elsewhere must not be demoted account-wide:
        # that would lock them out of a school that never removed them.
        self._join(self.north)
        self._join(self.south)
        self.client.force_authenticate(user=self.north_admin)

        with patch("apps.organizations.views.add_user_to_group") as add, patch(
            "apps.organizations.views.remove_user_from_group"
        ) as remove:
            self.client.delete(
                f"/api/organizations/{self.north.id}/members/{self.teacher.id}"
            )

        add.assert_not_called()
        remove.assert_not_called()

    def test_removal_moves_the_active_school_off_the_one_they_left(self):
        self._join(self.north)
        self._join(self.south)
        self.teacher.active_organization = self.north
        self.teacher.save(update_fields=["active_organization"])
        self.client.force_authenticate(user=self.north_admin)

        self.client.delete(
            f"/api/organizations/{self.north.id}/members/{self.teacher.id}"
        )

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.active_organization_id, self.south.id)

    def test_rejection_at_one_school_does_not_reject_the_account(self):
        self._join(self.north)
        self._join(self.south, status="pending")
        self.client.force_authenticate(user=self.north_admin)

        self.client.post(
            f"/api/organizations/{self.north.id}/members/{self.teacher.id}/reject"
        )

        self.teacher.refresh_from_db()
        # Still approved, because South still has them — the account-wide flag
        # only drops when the LAST approved school goes.
        self.assertEqual(self.teacher.status, "approved")

    # ── administering more than one school ────────────────────────────────
    def test_an_admin_of_two_schools_manages_both_without_switching(self):
        Membership.objects.create(
            user=self.north_admin, organization=self.south, role="org_admin", status="approved"
        )
        self.north_admin.active_organization = self.north
        self.north_admin.save(update_fields=["active_organization"])
        self.client.force_authenticate(user=self.north_admin)

        self.assertEqual(
            self.client.get(f"/api/organizations/{self.north.id}").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/organizations/{self.south.id}").status_code, 200
        )

    def test_administering_one_school_grants_nothing_at_another(self):
        self.client.force_authenticate(user=self.north_admin)
        response = self.client.get(f"/api/organizations/{self.south.id}")
        self.assertEqual(response.status_code, 403)

    def test_a_teacher_at_two_schools_administers_neither(self):
        self._join(self.north)
        self._join(self.south)
        self.client.force_authenticate(user=self.teacher)

        self.assertEqual(
            self.client.get(f"/api/organizations/{self.north.id}").status_code, 403
        )

    # ── billing ───────────────────────────────────────────────────────────
    def test_spend_is_billed_to_the_school_currently_in_effect(self):
        self._join(self.north)
        self._join(self.south)
        self.teacher.active_organization = self.south
        self.teacher.save(update_fields=["active_organization"])
        self.teacher.refresh_from_db()

        self.assertEqual(self.teacher.billing_organization, self.south)

    # ── invites ───────────────────────────────────────────────────────────
    def test_a_teacher_invite_adds_a_school_rather_than_replacing_one(self):
        self._join(self.north)
        south_admin = User.objects.create(
            id="ba333333333333333333333333333333",
            name="South Admin",
            email="south-admin@example.com",
            status="approved",
        )
        Membership.objects.create(
            user=south_admin, organization=self.south, role="org_admin", status="approved"
        )
        self.client.force_authenticate(user=south_admin)
        self.client.post(
            f"/api/organizations/{self.south.id}/invites",
            {"email": self.teacher.email},
            format="json",
        )
        token = OrganizationInvite.objects.get(email=self.teacher.email).token

        self.client.force_authenticate(user=self.teacher)
        response = self.client.post(
            "/api/organizations/invites/accept", {"token": token}, format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.teacher.memberships.count(), 2)
        self.assertEqual(
            self.teacher.memberships.get(organization=self.north).status, "approved"
        )

    def test_the_same_person_cannot_hold_two_memberships_at_one_school(self):
        from django.db.utils import IntegrityError

        self._join(self.north)
        with self.assertRaises(IntegrityError):
            Membership.objects.create(
                user=self.teacher, organization=self.north, role="teacher", status="pending"
            )
