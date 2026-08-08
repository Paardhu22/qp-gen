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
    """Email the password-reset link. Returns True on success, False on failure.

    Issue 5 — when `EMAIL_BACKEND` is the dev/console backend (i.e. no real
    SMTP is configured), `send_mail` "delivers" the message to stdout. The
    user never receives anything in their inbox. We log the reset URL at
    WARNING level so it shows up in `manage.py runserver` output without
    having to scroll through the full RFC-822 dump — that closes the loop
    on the "no email arrives" complaint in local development. In prod
    with a real SMTP backend the WARNING is harmless extra context.
    """
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
    backend = (settings.EMAIL_BACKEND or "").lower()
    is_console_or_dummy = (
        "console" in backend or "dummy" in backend or "locmem" in backend
    )
    if is_console_or_dummy:
        logger.warning(
            "Password-reset email going through the %s backend (no actual SMTP). "
            "Reset link for %s (expires in %dm): %s",
            settings.EMAIL_BACKEND,
            to_email,
            minutes,
            reset_url,
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


def send_organization_invite_email(*, to_email: str, invite_link: str) -> bool:
    """Email a superadmin's organization-creation invite link.

    Same console-log fallback as `send_password_reset_email`: while
    EMAIL_BACKEND is the dev console backend, log the link at WARNING so it's
    usable without real SMTP/SES credentials.
    """
    subject = "You're invited to set up your school on qp-gen"
    body = (
        "Hello,\n\n"
        "You've been invited to create your school's organization on qp-gen.\n\n"
        f"Click this link to set up your account and organization:\n{invite_link}\n\n"
        "If you weren't expecting this invite, you can safely ignore this email.\n\n"
        "— qp-gen\n"
    )
    backend = (settings.EMAIL_BACKEND or "").lower()
    is_console_or_dummy = (
        "console" in backend or "dummy" in backend or "locmem" in backend
    )
    if is_console_or_dummy:
        logger.warning(
            "Organization invite email going through the %s backend (no actual SMTP). "
            "Invite link for %s: %s",
            settings.EMAIL_BACKEND,
            to_email,
            invite_link,
        )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


# ── Membership notifications ────────────────────────────────────────────────
# Every admin decision that changes what a user can do sends one of these. The
# rule is deliberate: a teacher whose account is approved, rejected, removed or
# re-roled has no other way to find out — the app simply behaves differently the
# next time they sign in, which reads as a bug rather than a decision.
#
# All of them are best-effort, exactly like the welcome email. `_safe_send`
# swallows and logs delivery failures, and no caller checks the return value:
# an SMTP outage must never leave a membership half-updated, with the database
# rolled back and the Cognito group already changed.

#: What the role slugs are called in prose. The stored values ("org_admin")
#: are not something to put in front of a school administrator.
ROLE_LABELS = {
    "org_admin": "school admin",
    "teacher": "teacher",
}


def _greeting(user_name: Optional[str]) -> str:
    return f"Hi {user_name}," if user_name else "Hello,"


def _at(organization_name: Optional[str]) -> str:
    """Render " at <school>" or nothing — org-less accounts share these bodies."""
    return f" at {organization_name}" if organization_name else ""


def send_membership_approved_email(
    *, to_email: str, user_name: Optional[str] = None, organization_name: Optional[str] = None
) -> bool:
    subject = "Your qp-gen account has been approved"
    body = (
        f"{_greeting(user_name)}\n\n"
        f"Your qp-gen account{_at(organization_name)} has been approved. You can "
        "sign in now and start generating papers.\n\n"
        f"{settings.FRONTEND_URL}\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def send_membership_rejected_email(
    *, to_email: str, user_name: Optional[str] = None, organization_name: Optional[str] = None
) -> bool:
    subject = "Your qp-gen account request was declined"
    body = (
        f"{_greeting(user_name)}\n\n"
        f"Your request to join qp-gen{_at(organization_name)} was not approved, "
        "so you won't be able to sign in for now.\n\n"
        "If you think this is a mistake, reply to this email or contact your "
        "school's administrator.\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def send_membership_removed_email(
    *, to_email: str, user_name: Optional[str] = None, organization_name: Optional[str] = None
) -> bool:
    subject = "You have been removed from your qp-gen school"
    body = (
        f"{_greeting(user_name)}\n\n"
        f"Your account has been removed from{_at(organization_name) or ' your school'} "
        "on qp-gen. Your papers are untouched, but you'll need to be added back "
        "before you can sign in again.\n\n"
        "If you think this is a mistake, contact your school's administrator.\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def send_role_changed_email(
    *,
    to_email: str,
    user_name: Optional[str] = None,
    organization_name: Optional[str] = None,
    new_role: str,
    changed_by: Optional[str] = None,
) -> bool:
    """Tell a member their role changed, and what that now lets them do.

    The "what changed for you" line matters more than the role name: "school
    admin" means nothing until you know it's the person who approves teachers.
    """
    label = ROLE_LABELS.get(new_role, new_role)
    if new_role == "org_admin":
        consequence = (
            "As a school admin you can now approve or remove teachers"
            f"{_at(organization_name)} and manage the school's details."
        )
    else:
        consequence = (
            "As a teacher you can generate and edit papers. Managing the "
            "school's members is no longer part of your account."
        )
    by = f" by {changed_by}" if changed_by else ""

    subject = f"Your qp-gen role is now {label}"
    body = (
        f"{_greeting(user_name)}\n\n"
        f"Your role{_at(organization_name)} was changed{by} to {label}.\n\n"
        f"{consequence}\n\n"
        f"{settings.FRONTEND_URL}\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def send_join_request_email(
    *,
    to_emails: list[str],
    applicant_name: str,
    applicant_email: str,
    organization_name: str,
) -> bool:
    """Tell a school's admins that someone is waiting on their approval.

    Without this, a pending teacher's request sits invisible until an admin
    happens to open the members page.
    """
    if not to_emails:
        return False
    who = f"{applicant_name} ({applicant_email})" if applicant_name else applicant_email
    subject = f"{who} wants to join {organization_name}"
    body = (
        "Hello,\n\n"
        f"{who} has asked to join {organization_name} on qp-gen and is waiting "
        "for approval.\n\n"
        f"Review the request here:\n{(settings.FRONTEND_URL or '').rstrip('/')}/admin\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=to_emails)


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
