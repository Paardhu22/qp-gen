from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models import User
from apps.common.permissions import IsAdmin, IsApprovedOrAdmin
from apps.common.authentication import CognitoJWTAuthentication


class CognitoAuthAndPermissionsTests(TestCase):

    def setUp(self):
        self.pending_user = User.objects.create(
            id="11111111111111111111111111111111",
            name="Pending User",
            email="pending@example.com",
            status="pending",
        )
        self.approved_user = User.objects.create(
            id="22222222222222222222222222222222",
            name="Approved User",
            email="approved@example.com",
            status="approved",
        )
        self.admin_user = User.objects.create(
            id="33333333333333333333333333333333",
            name="Admin User",
            email="admin@example.com",
            status="admin",
        )
        self.rejected_user = User.objects.create(
            id="44444444444444444444444444444444",
            name="Rejected User",
            email="rejected@example.com",
            status="rejected",
        )

    def test_is_approved_or_admin_permission(self):
        permission = IsApprovedOrAdmin()
        mock_request = MagicMock()

        # Anonymous / Unauthenticated user
        mock_request.user = AnonymousUser()
        self.assertFalse(permission.has_permission(mock_request, None))

        # Pending user
        mock_request.user = self.pending_user
        self.assertFalse(permission.has_permission(mock_request, None))

        # Rejected user
        mock_request.user = self.rejected_user
        self.assertFalse(permission.has_permission(mock_request, None))

        # Approved user
        mock_request.user = self.approved_user
        self.assertTrue(permission.has_permission(mock_request, None))

        # Admin user
        mock_request.user = self.admin_user
        self.assertTrue(permission.has_permission(mock_request, None))

        # Superadmin implies approval even if the local status is stale.
        self.pending_user.is_superadmin = True
        mock_request.user = self.pending_user
        self.assertTrue(permission.has_permission(mock_request, None))

    def test_is_admin_permission(self):
        permission = IsAdmin()
        mock_request = MagicMock()

        # Anonymous / Unauthenticated user
        mock_request.user = AnonymousUser()
        self.assertFalse(permission.has_permission(mock_request, None))

        # Approved user
        mock_request.user = self.approved_user
        self.assertFalse(permission.has_permission(mock_request, None))

        # Admin user
        mock_request.user = self.admin_user
        self.assertTrue(permission.has_permission(mock_request, None))

    @patch("apps.common.authentication.CognitoTokenValidator")
    def test_cognito_authentication_success_id_token(self, mock_validator_cls):
        # Setup mock validator
        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator

        # Cognito sub with hyphens (36 chars)
        cognito_sub = "12345678-abcd-1234-abcd-123456789012"
        # Stripped ID (32 chars)
        expected_user_id = "12345678abcd1234abcd123456789012"

        mock_payload = {
            "sub": cognito_sub,
            "email": "newuser@example.com",
            "name": "New Cognito User",
            "token_use": "id",
            "cognito:groups": ["approved"],
        }
        mock_validator.validate_token.return_value = mock_payload

        # Setup authentication class
        authenticator = CognitoJWTAuthentication()

        # Create mock request with header
        mock_request = MagicMock()
        mock_request.META = {
            "HTTP_AUTHORIZATION": "Bearer valid_mock_token"
        }

        # Authenticate
        user, auth_detail = authenticator.authenticate(mock_request)

        # Asserts
        self.assertIsNotNone(user)
        self.assertIsNone(auth_detail)
        self.assertEqual(user.id, expected_user_id)
        self.assertEqual(user.email, "newuser@example.com")
        self.assertEqual(user.name, "New Cognito User")
        self.assertEqual(user.status, "approved")

        # Verify database record exists
        db_user = User.objects.get(id=expected_user_id)
        self.assertEqual(db_user.email, "newuser@example.com")
        self.assertEqual(db_user.status, "approved")

    @patch("apps.common.authentication.CognitoTokenValidator")
    def test_cognito_authentication_user_sync(self, mock_validator_cls):
        # Setup mock validator
        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator

        # Use the ID of the existing approved user (without hyphens)
        # Reconstruct Cognito sub (with hyphens)
        cognito_sub = "22222222-2222-2222-2222-222222222222"

        # Change status to admin, update name
        mock_payload = {
            "sub": cognito_sub,
            "email": "approved@example.com",
            "name": "Approved User Updated Name",
            "token_use": "id",
            "cognito:groups": ["admin"],  # Promote to admin
        }
        mock_validator.validate_token.return_value = mock_payload

        authenticator = CognitoJWTAuthentication()
        mock_request = MagicMock()
        mock_request.META = {
            "HTTP_AUTHORIZATION": "Bearer valid_mock_token"
        }

        user, _ = authenticator.authenticate(mock_request)

        self.assertEqual(user.name, "Approved User Updated Name")
        self.assertEqual(user.status, "admin")

        # Verify database synchronized the updates
        db_user = User.objects.get(id=self.approved_user.id)
        self.assertEqual(db_user.name, "Approved User Updated Name")
        self.assertEqual(db_user.status, "admin")

    @patch("apps.common.authentication.CognitoTokenValidator")
    def test_cognito_authentication_does_not_downgrade_from_stale_token(self, mock_validator_cls):
        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator
        mock_validator.validate_token.return_value = {
            "sub": "22222222-2222-2222-2222-222222222222",
            "email": "approved@example.com",
            "name": "Approved User",
            "token_use": "id",
            "cognito:groups": ["pending"],
        }

        authenticator = CognitoJWTAuthentication()
        mock_request = MagicMock()
        mock_request.META = {"HTTP_AUTHORIZATION": "Bearer valid_mock_token"}

        user, _ = authenticator.authenticate(mock_request)

        self.assertEqual(user.status, "approved")
        self.assertEqual(User.objects.get(id=self.approved_user.id).status, "approved")

    @patch("apps.common.authentication.CognitoTokenValidator")
    def test_cognito_authentication_does_not_reapprove_rejected_user(self, mock_validator_cls):
        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator
        mock_validator.validate_token.return_value = {
            "sub": "44444444-4444-4444-4444-444444444444",
            "email": "rejected@example.com",
            "name": "Rejected User",
            "token_use": "id",
            "cognito:groups": ["approved"],
        }

        authenticator = CognitoJWTAuthentication()
        mock_request = MagicMock()
        mock_request.META = {"HTTP_AUTHORIZATION": "Bearer valid_mock_token"}

        user, _ = authenticator.authenticate(mock_request)

        self.assertEqual(user.status, "rejected")
        self.assertEqual(User.objects.get(id=self.rejected_user.id).status, "rejected")

    @patch("apps.common.authentication.CognitoTokenValidator")
    def test_cognito_authentication_superadmin_implies_admin_status(self, mock_validator_cls):
        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator
        mock_validator.validate_token.return_value = {
            "sub": "55555555-5555-5555-5555-555555555555",
            "email": "super@example.com",
            "name": "Super Admin",
            "token_use": "id",
            "cognito:groups": ["superadmin"],
        }

        authenticator = CognitoJWTAuthentication()
        mock_request = MagicMock()
        mock_request.META = {"HTTP_AUTHORIZATION": "Bearer valid_mock_token"}

        user, _ = authenticator.authenticate(mock_request)

        self.assertTrue(user.is_superadmin)
        self.assertEqual(user.status, "admin")

    def test_cognito_authentication_missing_header(self):
        authenticator = CognitoJWTAuthentication()
        mock_request = MagicMock()
        mock_request.META = {}

        result = authenticator.authenticate(mock_request)
        self.assertIsNone(result)

    def test_cognito_authentication_malformed_header(self):
        authenticator = CognitoJWTAuthentication()
        mock_request = MagicMock()
        mock_request.META = {
            "HTTP_AUTHORIZATION": "InvalidFormat"
        }

        result = authenticator.authenticate(mock_request)
        self.assertIsNone(result)

    def test_cognito_authentication_invalid_bearer_format(self):
        authenticator = CognitoJWTAuthentication()
        mock_request = MagicMock()
        mock_request.META = {
            "HTTP_AUTHORIZATION": "Bearer token1 token2"
        }

        with self.assertRaises(AuthenticationFailed):
            authenticator.authenticate(mock_request)
