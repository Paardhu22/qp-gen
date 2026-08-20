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


def send_teacher_invite_email(
    *, to_email: str, invite_link: str, organization_name: str, inviter_name: str = ""
) -> bool:
    """Email a school admin's invite link for a teacher to join their school.

    Distinct from `send_organization_invite_email` because the two links do
    genuinely different things — one creates a school, one joins an existing
    one already approved — and a teacher told to "set up your organization"
    would reasonably think they were being asked to register the school again.
    """
    who = f"{inviter_name} has" if inviter_name else "You have been"
    subject = f"Join {organization_name} on qp-gen"
    body = (
        "Hello,\n\n"
        f"{who} invited you to join {organization_name} on qp-gen.\n\n"
        "Use this link to sign up — you'll be added to the school straight "
        f"away, with no approval to wait for:\n{invite_link}\n\n"
        "If you weren't expecting this invite, you can safely ignore this email.\n\n"
        "— qp-gen\n"
    )
    _log_link_in_dev(to_email, invite_link, "Teacher invite")
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def send_join_request_email(
    *,
    to_emails: list[str],
    teacher_name: str,
    teacher_email: str,
    organization_name: str,
    review_link: str,
) -> bool:
    """Tell a school's admins that someone is waiting on their approval.

    Without this the approval queue is invisible: a teacher signs up, lands on
    a "waiting for approval" screen, and nobody is told there is anything to
    approve. The request then sits until the teacher thinks to chase it by
    other means, which is the single most common way an onboarding dies.
    """
    if not to_emails:
        return False
    who = teacher_name or teacher_email
    subject = f"{who} asked to join {organization_name}"
    body = (
        "Hello,\n\n"
        f"{who} ({teacher_email}) has asked to join {organization_name} on qp-gen.\n\n"
        "They cannot generate anything until someone approves them. Review the "
        f"request here:\n{review_link}\n\n"
        "— qp-gen\n"
    )
    _log_link_in_dev(", ".join(to_emails), review_link, "Join request")
    return _safe_send(subject=subject, body=body, recipients=list(to_emails))


def send_membership_approved_email(
    *, to_email: str, user_name: str = "", organization_name: str = ""
) -> bool:
    """Tell a teacher their access is live.

    The approval happens on someone else's screen, so without this the teacher
    finds out by trying again later and guessing.
    """
    greeting = f"Hi {user_name}," if user_name else "Hello,"
    where = f" as a member of {organization_name}" if organization_name else ""
    subject = "Your qp-gen account is approved"
    body = (
        f"{greeting}\n\n"
        f"Your qp-gen account has been approved{where}. You can sign in and "
        "start building papers now.\n\n"
        f"{settings.FRONTEND_URL}\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def send_membership_rejected_email(
    *, to_email: str, user_name: str = "", organization_name: str = ""
) -> bool:
    """Tell a teacher their request was declined, and what they can do next.

    Naming the next step matters: the usual cause is picking the wrong school
    from the dropdown, and a bare "declined" leaves the teacher stuck with no
    idea that choosing again is even possible.
    """
    greeting = f"Hi {user_name}," if user_name else "Hello,"
    where = f" to join {organization_name}" if organization_name else ""
    subject = "About your qp-gen access request"
    body = (
        f"{greeting}\n\n"
        f"Your request{where} on qp-gen was not approved.\n\n"
        "If you picked the wrong school, you can sign in and send a request to "
        "the right one. Otherwise, contact your school's qp-gen administrator.\n\n"
        f"{settings.FRONTEND_URL}\n\n"
        "— qp-gen\n"
    )
    return _safe_send(subject=subject, body=body, recipients=[to_email])


def _log_link_in_dev(to_email: str, link: str, label: str) -> None:
    """Surface a link at WARNING while no real SMTP backend is configured.

    Same reasoning as the password-reset path: with the console backend the
    message goes to stdout and never reaches an inbox, so without this a local
    invite flow is untestable.
    """
    backend = (settings.EMAIL_BACKEND or "").lower()
    if "console" in backend or "dummy" in backend or "locmem" in backend:
        logger.warning(
            "%s email going through the %s backend (no actual SMTP). Link for %s: %s",
            label,
            settings.EMAIL_BACKEND,
            to_email,
            link,
        )


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
