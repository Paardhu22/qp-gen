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
from email.mime.image import MIMEImage
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger("[EMAIL_SERVICE]")


# ── The template ────────────────────────────────────────────────────────────
# Every message in this module is the same shape — a heading, a greeting, some
# paragraphs, at most one call to action — so there is one layout rather than a
# hand-written body per notification. Senders describe their content and the
# renderers below produce both halves of the multipart message from it, which
# is what keeps the plain-text alternative from drifting out of date.
#
# The HTML is deliberately dated: tables for structure, inline styles, no CSS
# file. Mail clients discard <style> blocks and ignore flexbox; anything more
# modern renders as an unstyled column in Outlook.

#: The product, and the company whose logo tops every message.
BRAND = "QP Gen"
COMPANY = "HSAT Edu Solutions"

#: Pulled from the logo itself, so the template and the crest agree.
_NAVY = "#242a52"
_ORANGE = "#f26a21"
_INK = "#1f2430"
_MUTED = "#6b7280"
_BORDER = "#e6e8ee"
_CANVAS = "#f4f5f8"

#: The logo travels with the message as an inline attachment rather than a URL.
#: A hosted image would depend on the frontend being reachable and on the
#: client not blocking remote content; `cid:` needs neither.
_LOGO_PATH = Path(settings.BASE_DIR) / "assets" / "email" / "hsat-logo.png"
_LOGO_CID = "hsat-logo"


@lru_cache(maxsize=1)
def _logo_bytes() -> Optional[bytes]:
    """Read the logo once per process; None if it isn't deployed alongside us."""
    try:
        return _LOGO_PATH.read_bytes()
    except OSError as exc:
        logger.warning("Email logo missing at %s (%s) — sending without it", _LOGO_PATH, exc)
        return None


def _render_text(
    *,
    greeting: str,
    paragraphs: Sequence[str],
    button: Optional[tuple[str, str]],
    closing: Optional[str],
) -> str:
    blocks = [greeting, *paragraphs]
    if button:
        # The label is dropped: in plain text the surrounding paragraph already
        # says what the link is for, and "Sign in: https://…" reads as noise.
        blocks.append(button[1])
    if closing:
        blocks.append(closing)
    blocks.append(f"— {BRAND}")
    return "\n\n".join(blocks) + "\n"


def _render_html(
    *,
    heading: str,
    greeting: str,
    paragraphs: Sequence[str],
    button: Optional[tuple[str, str]],
    closing: Optional[str],
) -> str:
    body_html = "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:{_INK};">'
        f"{escape(text)}</p>"
        for text in paragraphs
    )

    button_html = ""
    if button:
        label, url = button
        # Wrapped in its own table: Outlook ignores padding on a bare <a>, and
        # the cell is what actually gives the button its shape there.
        button_html = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin:4px 0 26px;"><tr>'
            f'<td align="center" bgcolor="{_ORANGE}" style="border-radius:8px;">'
            f'<a href="{escape(url, quote=True)}" '
            f'style="display:inline-block;padding:12px 26px;font-size:15px;'
            f'font-weight:600;color:#ffffff;text-decoration:none;'
            f'border-radius:8px;">{escape(label)}</a></td></tr></table>'
        )

    closing_html = ""
    if closing:
        closing_html = (
            f'<p style="margin:24px 0 0;padding-top:18px;'
            f'border-top:1px solid {_BORDER};font-size:13px;line-height:1.6;'
            f'color:{_MUTED};">{escape(closing)}</p>'
        )

    # Falls back to the wordmark when the asset is missing, so a bad deploy
    # costs the logo rather than the whole header.
    if _logo_bytes():
        logo_html = (
            f'<img src="cid:{_LOGO_CID}" alt="{escape(COMPANY, quote=True)}" '
            f'width="180" height="72" '
            f'style="display:block;width:180px;height:auto;border:0;outline:none;'
            f'text-decoration:none;" />'
        )
    else:
        logo_html = (
            f'<span style="font-size:20px;font-weight:700;color:{_NAVY};'
            f'letter-spacing:-0.01em;">{escape(COMPANY)}</span>'
        )

    return f"""\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta name="color-scheme" content="light only" />
    <meta name="supported-color-schemes" content="light only" />
    <title>{escape(heading)}</title>
  </head>
  <body style="margin:0;padding:0;background:{_CANVAS};-webkit-font-smoothing:antialiased;">
    <!-- Shown in the inbox list beside the subject, then hidden in the body. -->
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
      {escape(heading)} — {escape(BRAND)} by {escape(COMPANY)}
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:{_CANVAS};padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="max-width:600px;background:#ffffff;border:1px solid {_BORDER};
                        border-radius:16px;overflow:hidden;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                                    Roboto,Helvetica,Arial,sans-serif;">
            <tr>
              <td style="padding:28px 36px 22px;">
                {logo_html}
              </td>
            </tr>
            <!-- The crest's own palette, as a rule under the header. -->
            <tr>
              <td style="height:3px;line-height:3px;font-size:0;
                         background:{_ORANGE};">&nbsp;</td>
            </tr>
            <tr>
              <td style="padding:32px 36px 30px;">
                <h1 style="margin:0 0 18px;font-size:21px;line-height:1.35;
                           font-weight:700;color:{_NAVY};">{escape(heading)}</h1>
                <p style="margin:0 0 16px;font-size:15px;line-height:1.65;
                          color:{_INK};">{escape(greeting)}</p>
                {body_html}
                {button_html}
                {closing_html}
              </td>
            </tr>
            <tr>
              <td style="padding:20px 36px 26px;background:#fafbfc;
                         border-top:1px solid {_BORDER};font-size:12px;
                         line-height:1.6;color:{_MUTED};">
                <strong style="color:{_NAVY};">{escape(BRAND)}</strong>
                &nbsp;·&nbsp; a {escape(COMPANY)} product<br />
                You're receiving this because you have a {escape(BRAND)} account.
                If this message wasn't meant for you, please ignore it.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def _send(
    *,
    recipients: list[str],
    subject: str,
    heading: str,
    greeting: str,
    paragraphs: Sequence[str],
    button: Optional[tuple[str, str]] = None,
    closing: Optional[str] = None,
    fail_silently: bool = True,
) -> bool:
    """Render one notification into both formats and hand it to `_safe_send`."""
    return _safe_send(
        subject=subject,
        fail_silently=fail_silently,
        body=_render_text(
            greeting=greeting, paragraphs=paragraphs, button=button, closing=closing
        ),
        html_body=_render_html(
            heading=heading,
            greeting=greeting,
            paragraphs=paragraphs,
            button=button,
            closing=closing,
        ),
        recipients=recipients,
    )


def _app_url() -> str:
    return (settings.FRONTEND_URL or "").rstrip("/")


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
    return _send(
        recipients=[to_email],
        subject="Reset your QP Gen password",
        heading="Reset your password",
        greeting=_greeting(user_name),
        paragraphs=[
            "We received a request to reset the password for your QP Gen account.",
            f"Choose a new password using the button below. The link is valid for "
            f"{minutes} minutes.",
        ],
        button=("Choose a new password", reset_url),
        closing=(
            "If you did not request a password reset you can safely ignore this "
            "email — your existing password remains active."
        ),
    )


def send_welcome_email(*, to_email: str, user_name: Optional[str] = None) -> bool:
    """Send the post-signup welcome email. Best-effort — never blocks signup."""
    return _send(
        recipients=[to_email],
        subject="Welcome to QP Gen",
        heading=f"Welcome, {user_name}!" if user_name else "Welcome!",
        greeting=_greeting(user_name),
        paragraphs=[
            "Your QP Gen account is ready. Sign in to upload a source PDF and "
            "generate your first paper.",
        ],
        button=("Open QP Gen", _app_url()),
        closing=(
            "If you did not create this account, please reply to this email so "
            "we can investigate."
        ),
    )


def send_organization_invite_email(*, to_email: str, invite_link: str) -> bool:
    """Email a superadmin's organization-creation invite link.

    Same console-log fallback as `send_password_reset_email`: while
    EMAIL_BACKEND is the dev console backend, log the link at WARNING so it's
    usable without real SMTP/SES credentials.
    """
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
    return _send(
        recipients=[to_email],
        subject="You're invited to set up your school on QP Gen",
        heading="Set up your school on QP Gen",
        greeting="Hello,",
        paragraphs=[
            "You've been invited to create your school's organization on QP Gen.",
            "Use the button below to set up your account and your school.",
        ],
        button=("Set up my school", invite_link),
        closing="If you weren't expecting this invite, you can safely ignore this email.",
    )


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
    return _send(
        recipients=[to_email],
        subject="Your QP Gen account has been approved",
        heading="Your account is approved",
        greeting=_greeting(user_name),
        paragraphs=[
            f"Your QP Gen account{_at(organization_name)} has been approved. You "
            "can sign in now and start generating papers.",
        ],
        button=("Sign in to QP Gen", _app_url()),
    )


def send_membership_rejected_email(
    *, to_email: str, user_name: Optional[str] = None, organization_name: Optional[str] = None
) -> bool:
    return _send(
        recipients=[to_email],
        subject="Your QP Gen account request was declined",
        heading="Your request was declined",
        greeting=_greeting(user_name),
        paragraphs=[
            f"Your request to join QP Gen{_at(organization_name)} was not "
            "approved, so you won't be able to sign in for now.",
        ],
        closing=(
            "If you think this is a mistake, reply to this email or contact your "
            "school's administrator."
        ),
    )


def send_membership_removed_email(
    *, to_email: str, user_name: Optional[str] = None, organization_name: Optional[str] = None
) -> bool:
    return _send(
        recipients=[to_email],
        subject="You have been removed from your QP Gen school",
        heading="You've been removed from your school",
        greeting=_greeting(user_name),
        paragraphs=[
            # Not `_at`: that renders " at X", and "removed from at X" is wrong.
            f"Your account has been removed from {organization_name or 'your school'} "
            "on QP Gen. Your papers "
            "are untouched, but you'll need to be added back before you can sign "
            "in again.",
        ],
        closing="If you think this is a mistake, contact your school's administrator.",
    )


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

    return _send(
        recipients=[to_email],
        subject=f"Your QP Gen role is now {label}",
        heading=f"You're now a {label}",
        greeting=_greeting(user_name),
        paragraphs=[
            f"Your role{_at(organization_name)} was changed{by} to {label}.",
            consequence,
        ],
        button=("Open QP Gen", _app_url()),
    )


def send_membership_moved_email(
    *,
    to_email: str,
    user_name: Optional[str] = None,
    from_organization: Optional[str] = None,
    to_organization: str,
    new_role: str,
    pending_approval: bool = False,
) -> bool:
    """Tell a user their account was placed in, or moved to, a school.

    `from_organization` is None when they had no school at all, which is a
    different event to a transfer and reads wrongly if phrased as a move.

    `pending_approval` matters more than it looks: a newly placed member starts
    pending, so telling them "you're now at X" without saying they still cannot
    sign in would send them straight into a rejection screen.
    """
    label = ROLE_LABELS.get(new_role, new_role)
    subject = (
        f"You've been moved to {to_organization} on QP Gen"
        if from_organization
        else f"You've been added to {to_organization} on QP Gen"
    )
    opening = (
        f"Your account has been moved from {from_organization} to "
        f"{to_organization} on QP Gen, as a {label}."
        if from_organization
        else f"Your account has been added to {to_organization} on QP Gen, as a {label}."
    )
    tail = (
        "An administrator at your new school still needs to approve you before "
        "you can sign in. We'll email you when that happens."
        if pending_approval
        else "You can sign in and carry on as usual."
    )
    return _send(
        recipients=[to_email],
        subject=subject,
        heading=(
            f"You've moved to {to_organization}"
            if from_organization
            else f"You've been added to {to_organization}"
        ),
        greeting=_greeting(user_name),
        paragraphs=[opening, tail],
        # Nothing to open while they still cannot sign in.
        button=None if pending_approval else ("Sign in to QP Gen", _app_url()),
        closing="If this looks wrong, contact your school's administrator.",
    )


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
    return _send(
        recipients=to_emails,
        subject=f"{who} wants to join {organization_name}",
        heading="Someone is waiting for approval",
        greeting="Hello,",
        paragraphs=[
            f"{who} has asked to join {organization_name} on QP Gen and is "
            "waiting for approval.",
        ],
        button=("Review the request", f"{_app_url()}/admin"),
    )


def send_test_email(*, to_email: str, fail_silently: bool = True) -> bool:
    """The `verify_email` command's probe message, rendered like a real one."""
    return _send(
        recipients=[to_email],
        subject="QP Gen mail check",
        heading="Your mail configuration works",
        greeting="Hello,",
        paragraphs=[
            "This is a test message from QP Gen.",
            "If you are reading it, invites, approvals, rejections and role "
            "changes will reach their recipients too.",
        ],
        fail_silently=fail_silently,
    )


def _attach_logo(message: EmailMultiAlternatives) -> None:
    """Attach the crest as an inline part the HTML can reach at `cid:`.

    `mixed_subtype = "related"` is the load-bearing line: it makes the message
    multipart/related, which is what tells a client the image belongs to the
    HTML rather than being a file the reader is meant to download. Without it
    the logo shows up as a paperclip and the header renders broken.
    """
    data = _logo_bytes()
    if not data:
        return
    message.mixed_subtype = "related"
    image = MIMEImage(data, "png")
    image.add_header("Content-ID", f"<{_LOGO_CID}>")
    image.add_header("Content-Disposition", "inline", filename="hsat-logo.png")
    message.attach(image)


def _safe_send(
    *,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    recipients: list[str],
    fail_silently: bool = True,
) -> bool:
    """Deliver one message, logging rather than raising if the provider refuses.

    Sent as multipart/alternative: `body` is the plain-text part every client
    can read, `html_body` the styled one most will show instead. The text part
    is not optional — a message with only HTML scores as spam and is unreadable
    in clients with images and markup disabled.

    `fail_silently=False` is for the `verify_email` command alone, which exists
    to surface the provider's own error text. Notifications must never raise:
    an SMTP outage cannot be allowed to roll back a membership change that has
    already been applied elsewhere.
    """
    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")
            _attach_logo(message)
        message.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error(
            "Email send failed (backend=%s, subject=%r, to=%s): %s",
            settings.EMAIL_BACKEND,
            subject,
            ", ".join(recipients),
            exc,
        )
        if not fail_silently:
            raise
        return False
