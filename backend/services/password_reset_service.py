"""Password-reset token issuance and consumption (Cluster A.1).

Tokens are stored HASHED in the existing `verification` table (created by
the Prisma better-auth schema) so a database read does not yield a
working reset link. The plaintext token is sent in the email link; the
endpoint that consumes the link rehashes the input and looks up the row.

`identifier` is fixed to `password-reset:<user-id>` so:
* Each user can only have one valid reset token at a time (issuing a
  fresh token deletes prior tokens for the same identifier — this
  invalidates any previously emailed link if the user requests another).
* We never store a raw email/identifier in a way that ties leaked rows
  back to user-supplied addresses beyond what the FK already implies.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Account, User, Verification

logger = logging.getLogger("[PASSWORD_RESET]")

TOKEN_BYTES = 32  # → 64-character hex token in the URL
IDENTIFIER_PREFIX = "password-reset:"


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _identifier_for(user: User) -> str:
    return f"{IDENTIFIER_PREFIX}{user.id}"


def issue_reset_token(user: User) -> str:
    """Issue a fresh reset token, invalidating any prior outstanding tokens
    for this user. Returns the plaintext token to embed in the email link."""
    plaintext = secrets.token_hex(TOKEN_BYTES)
    expires_at = timezone.now() + timedelta(
        seconds=int(settings.PASSWORD_RESET_TIMEOUT)
    )
    identifier = _identifier_for(user)
    with transaction.atomic():
        # Invalidate every prior token for this user so the most recently
        # emailed link is the only one that works.
        Verification.objects.filter(identifier=identifier).delete()
        Verification.objects.create(
            identifier=identifier,
            value=_hash_token(plaintext),
            expires_at=expires_at,
        )
    return plaintext


def consume_reset_token(token: str, new_password: str) -> bool:
    """Validate the token and rotate the user's password atomically.

    Returns True on success. False covers all failure paths (unknown
    token, expired token, no matching local Account, etc.) so the caller
    can return a single generic error without leaking which step failed.
    """
    if not token or not new_password:
        return False

    hashed = _hash_token(token)
    now = timezone.now()
    with transaction.atomic():
        verification = (
            Verification.objects.select_for_update()
            .filter(value=hashed, identifier__startswith=IDENTIFIER_PREFIX)
            .first()
        )
        if verification is None:
            return False
        if verification.expires_at <= now:
            verification.delete()
            return False

        user_id = verification.identifier[len(IDENTIFIER_PREFIX):]
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            verification.delete()
            return False

        account = Account.objects.filter(
            user=user, provider_id="email"
        ).first()
        if account is None:
            verification.delete()
            return False

        account.set_password(new_password)
        account.save(update_fields=["password"])
        # One-shot consumption: the token is destroyed regardless of what
        # the user does next, so a successful link cannot be replayed.
        verification.delete()
    logger.info("Password reset for user %s", user.id)
    return True
