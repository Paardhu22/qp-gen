from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from apps.accounts.models import Account, User


def register_user(name: str, email: str, password: str) -> User:
    if User.objects.filter(email=email).exists():
        raise ValidationError({"email": "Email already registered."})

    with transaction.atomic():
        user = User.objects.create(name=name, email=email)
        account = Account.objects.create(
            account_id=email,
            provider_id="email",
            user=user,
        )
        account.set_password(password)
        account.save(update_fields=["password"])

    return user


def authenticate_user(email: str, password: str) -> User:
    user = User.objects.filter(email=email).first()
    if not user:
        raise AuthenticationFailed("Invalid email or password")

    account = Account.objects.filter(user=user, provider_id="email", account_id=email).first()
    if not account or not account.check_password(password):
        raise AuthenticationFailed("Invalid email or password")

    return user
