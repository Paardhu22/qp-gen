from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.generation.models import ApiUsage

from .models import Membership, Organization


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
        membership = Membership.objects.get(user=rejected)
        self.assertEqual(membership.organization_id, self.org.id)
        self.assertEqual(membership.status, "pending")
        self.assertIsNone(membership.reviewed_by)

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
