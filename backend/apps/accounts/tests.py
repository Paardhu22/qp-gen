from django.test import TestCase

from apps.accounts.models import User


class AccountsTests(TestCase):
    def test_create_user_placeholder(self):
        user = User.objects.create(name="Test", email="test@example.com")
        self.assertEqual(user.email, "test@example.com")
