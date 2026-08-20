"""Read-side helpers for the organization panels.

The superadmin list, the usage rollup and the org detail page all draw the
same three numbers next to every school: how many members, how many tokens,
how much that came to in rupees. Computed inside serializer methods, each of
those was a query per organization per number — a twelve-school account issued
around forty queries to paint one table, and the shape got worse linearly.

Everything here answers the same question for a *whole set* of rows in a fixed
number of queries, then hands the answers back attached to the model instances.
Serializers read the attached values and fall back to computing their own when
they are absent, so a serializer used on a bare object still works — the
attachment is an optimisation, never a precondition.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from django.db.models import Count, Sum

from apps.generation.models import ApiUsage
from services.usage_pricing import inr_cost_by_group, inr_cost_of_usage

#: Attribute names stamped onto the model instances. Prefixed because they are
#: cached answers, not fields — nothing should mistake them for columns.
MEMBER_COUNT_ATTR = "_member_count"
TOTAL_TOKENS_ATTR = "_total_tokens"
COST_INR_ATTR = "_total_cost_inr"
ADMIN_EMAIL_ATTR = "_admin_email"


def with_usage(organizations: Iterable) -> List:
    """Attach member count, token total, rupee cost and admin email to each org.

    Five queries total, independent of how many organizations there are.
    """
    orgs = list(organizations)
    if not orgs:
        return orgs

    ids = [org.id for org in orgs]

    member_counts: Dict[str, int] = {
        row["organization"]: row["n"] for row in _membership_counts(ids)
    }
    token_totals: Dict[str, int] = {
        row["organization"]: row["tokens"] or 0
        for row in ApiUsage.objects.filter(organization_id__in=ids)
        .values("organization")
        .annotate(tokens=Sum("total_tokens"))
        .order_by()
    }
    costs = inr_cost_by_group(
        ApiUsage.objects.filter(organization_id__in=ids), "organization"
    )
    admin_emails = _admin_email_map(ids)

    for org in orgs:
        setattr(org, MEMBER_COUNT_ATTR, member_counts.get(org.id, 0))
        setattr(org, TOTAL_TOKENS_ATTR, token_totals.get(org.id, 0))
        setattr(org, COST_INR_ATTR, costs.get(org.id, 0.0))
        setattr(org, ADMIN_EMAIL_ATTR, admin_emails.get(org.id))
    return orgs


def _membership_counts(ids):
    # Imported lazily so this module can be imported from serializers without
    # participating in the app-loading import cycle.
    from .models import Membership

    return (
        Membership.objects.filter(organization_id__in=ids)
        .values("organization")
        .annotate(n=Count("id"))
        .order_by()
    )


def _admin_email_map(ids) -> Dict[str, str]:
    """One `org_id -> admin email` map in a single query.

    Where a school has more than one admin this picks the earliest, which is in
    practice the person who accepted the invite and set the school up — the
    right one to show as the contact.
    """
    from .models import Membership

    out: Dict[str, str] = {}
    rows = (
        Membership.objects.filter(organization_id__in=ids, role="org_admin")
        .select_related("user")
        .order_by("created_at")
    )
    for membership in rows:
        out.setdefault(membership.organization_id, membership.user.email)
    return out


def member_usage_map(organization) -> Dict[str, dict]:
    """Per-member tokens and rupee cost for one organization, in two queries.

    Keyed by user id. The detail page lists every member with their spend
    beside them, which was previously one aggregate per member.
    """
    usage = ApiUsage.objects.filter(organization=organization)
    tokens = {
        row["user"]: row["tokens"] or 0
        for row in usage.values("user").annotate(tokens=Sum("total_tokens")).order_by()
    }
    costs = inr_cost_by_group(usage, "user")
    return {
        user_id: {"tokens": total, "cost_inr": costs.get(user_id, 0.0)}
        for user_id, total in tokens.items()
    }


def organization_totals(organization) -> dict:
    """Tokens and rupee cost for a single organization, for the detail view."""
    usage = ApiUsage.objects.filter(organization=organization)
    return {
        "tokens": usage.aggregate(total=Sum("total_tokens"))["total"] or 0,
        "cost_inr": inr_cost_of_usage(usage),
    }
