"""Outbound email plumbing for auth flows.

All email sending must go through these helpers so the address rendering
and the FRONTEND_URL host stay consistent (otherwise reset links bake
`localhost:3000` into production messages). The functions are tolerant
of `send_mail` failures: a server-side exception is logged and the API
caller still receives the "we sent a link if you have an account" reply.
Refusing to leak whether an email exists is the standard
password-reset response — it prevents account enumeration attacks.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("[EMAIL_SERVICE]")


def _reset_link(token: str) -> str:
    """Compose the FE-hosted reset URL from configured env, never localhost."""
    base = (settings.FRONTEND_URL or "").rstrip("/")
    path = settings.PASSWORD_RESET_URL_PATH or "/reset-password"
    if not path.startswith("/"):
        path = "/" + path
    # `urljoin` collapses redundant slashes if either string ends/starts with one.
    return urljoin(base + "/", path.lstrip("/")) + f"?token={token}"


def send_password_reset_email(
    *, to_email: str, token: str, user_name: Optional[str] = None
) -> bool:
    """Email the password-reset link. Returns True on success, False on failure."""
    reset_url = _reset_link(token)
    minutes = max(1, int(settings.PASSWORD_RESET_TIMEOUT // 60))
    greeting = f"Hi {user_name}," if user_name else "Hello,"
    subject = "Reset your qp-gen password"
    body = (
        f"{greeting}\n\n"
        "We received a request to reset the password for your qp-gen account.\n\n"
        f"Click this link to choose a new password (valid for {minutes} minutes):\n"
        f"{reset_url}\n\n"
        "If you did not request a password reset you can safely ignore this "
        "email — your existing password remains active.\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def send_welcome_email(*, to_email: str, user_name: Optional[str] = None) -> bool:
    """Send the post-signup welcome email. Best-effort — never blocks signup."""
    greeting = f"Welcome, {user_name}!" if user_name else "Welcome!"
    subject = "Welcome to qp-gen"
    body = (
        f"{greeting}\n\n"
        "Your qp-gen account is ready. Sign in to upload a source PDF and "
        "generate your first paper.\n\n"
        f"{settings.FRONTEND_URL}\n\n"
        "If you did not create this account, please reply to this email so "
        "we can investigate.\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def _safe_send(*, subject: str, body: str, recipients: list[str]) -> bool:
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.error(
            "Email send failed (backend=%s, subject=%r, to=%s): %s",
            settings.EMAIL_BACKEND,
            subject,
            ", ".join(recipients),
            exc,
        )
        return False
