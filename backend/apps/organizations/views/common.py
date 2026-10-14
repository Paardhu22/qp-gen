"""Shared helpers for the organization views: invite creation, membership reconciliation, lookups."""

import logging
import secrets
from datetime import timedelta
from django.conf import settings as django_settings
from django.http import Http404
from django.utils import timezone

from ..models import Organization, OrganizationInvite
from services.auth import cognito
from apps.accounts import views as accounts_views

logger = logging.getLogger("[ORGANIZATIONS_VIEWS]")


INVITE_EXPIRY_DAYS = 7


def _frontend(path: str) -> str:
    """An absolute link into the app. Never `localhost` in production.

    Every emailed link is built through here for the same reason the
    password-reset link is: one place gets `FRONTEND_URL` right, and a link
    composed ad hoc in a view is the one that ships with a dev host baked in.
    """
    base = (django_settings.FRONTEND_URL or "").rstrip("/")
    return f"{base}{path if path.startswith('/') else '/' + path}"


def _new_invite(*, email: str, role: str, organization, invited_by) -> OrganizationInvite:
    return OrganizationInvite.objects.create(
        email=email,
        token=secrets.token_urlsafe(32),
        role=role,
        organization=organization,
        invited_by=invited_by,
        expires_at=timezone.now() + timedelta(days=INVITE_EXPIRY_DAYS),
    )


def _reconcile_expired(invites) -> None:
    """Write `expired` onto invites whose date has passed.

    Expiry is a date comparison, so an invite is *effectively* expired the
    moment the clock passes it — but the stored status still says "pending",
    and every screen that filters on the column shows it as outstanding. This
    settles the column whenever a list is read, which is the only moment
    anybody cares.
    """
    stale = [i.id for i in invites if i.status == "pending" and i.is_expired]
    if stale:
        OrganizationInvite.objects.filter(id__in=stale).update(status="expired")


def _approved_elsewhere(user, excluding_organization_id) -> bool:
    """True when the account still has an approved school other than this one."""
    return any(
        m.status == "approved" and m.organization_id != excluding_organization_id
        for m in user.memberships.all()
    )


def _resettle_after_losing(user, organization_id, *, fallback_status: str) -> None:
    """Fix up an account that has just lost its membership at one school.

    Two things can be stale afterwards, and both are user-visible:

    *   `active_organization` may point at the school they were just removed
        from, which would leave them working as a school they no longer belong
        to. It moves to another approved membership, or to nothing.
    *   The account-wide `status` may say "approved" on the strength of a
        membership that no longer exists — but must NOT be demoted while
        another approved school remains, or a removal at one school locks them
        out of another that never removed them.
    """
    remaining = [
        m
        for m in user.memberships.all()
        if m.status == "approved" and m.organization_id != organization_id
    ]
    updates = []

    if user.active_organization_id == organization_id:
        user.active_organization = remaining[0].organization if remaining else None
        updates.append("active_organization")

    if not remaining and user.status != fallback_status:
        user.status = fallback_status
        updates.append("status")

    if updates:
        user.save(update_fields=updates)


def _promote_to_approved(user) -> None:
    """Move a user into Cognito's `approved` group, best effort.

    Best effort on purpose: the database is already the authority on approval
    status (see `_status_rank` in apps/common/authentication.py), so a Cognito
    hiccup must not undo a membership that was just committed in a
    transaction. It is logged loudly because the two stores drifting is a real
    problem — just not one worth failing an accepted invite over.
    """
    username = accounts_views.get_cognito_username(user)
    try:
        cognito.add_user_to_group(username, "approved")
        cognito.remove_user_from_group(username, "pending")
    except Exception as exc:
        logger.error("Failed to sync Cognito groups for %s: %s", user.email, exc)


def _get_organization_or_404(org_id: str) -> Organization:
    try:
        return Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        raise Http404("Organization not found")


def _org_admin_emails(org: Organization) -> list[str]:
    """Every approved admin of `org` — the people a request should reach.

    A school can have more than one admin (that is the point of the role
    endpoint below), and mailing only the first would leave the request
    invisible to whoever is actually at their desk.
    """
    return list(
        org.members.filter(role="org_admin", status="approved")
        .select_related("user")
        .values_list("user__email", flat=True)
    )


def _first_error(errors) -> str:
    """Flatten DRF's {field: [msg]} into one sentence for the toast.

    The frontend shows a single line, so handing it the whole dict would
    surface `{'gstin': [ErrorDetail(...)]}` to a school administrator.
    """
    for value in errors.values():
        if isinstance(value, (list, tuple)) and value:
            return str(value[0])
        if value:
            return str(value)
    return "Those details could not be saved."
