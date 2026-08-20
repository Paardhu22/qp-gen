from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Sum
from django.utils import timezone

from apps.generation.models import ApiUsage
from services.usage_pricing import inr_cost_of_usage


@dataclass(frozen=True)
class UsageLimitExceeded(RuntimeError):
    organization_id: str
    organization_name: str
    limit: int
    used: int
    #: Estimated rupee spend for the month so far. Carried on the error because
    #: the person who has to decide whether to raise the cap reads rupees, not
    #: tokens — "you have spent ₹1,840 of your allowance" is actionable in a way
    #: that a seven-digit token count is not. See services/usage_pricing.py.
    cost_inr: float = 0.0

    @property
    def payload(self) -> dict:
        return {
            "code": "ORG_TOKEN_LIMIT_EXCEEDED",
            "error": (
                f"{self.organization_name} has reached its monthly token limit."
            ),
            "organizationId": self.organization_id,
            "organizationName": self.organization_name,
            "monthlyTokenLimit": self.limit,
            "monthlyTokensUsed": self.used,
            "monthlyCostInr": self.cost_inr,
        }


def month_start(now=None):
    now = now or timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def current_month_usage_queryset(organization):
    return ApiUsage.objects.filter(
        organization=organization,
        created_at__gte=month_start(),
    )


def current_month_token_usage(organization) -> int:
    result = current_month_usage_queryset(organization).aggregate(
        total=Sum("total_tokens")
    )
    return result["total"] or 0


def current_month_cost_inr(organization) -> float:
    """Estimated rupee spend this calendar month. One grouped query."""
    return inr_cost_of_usage(current_month_usage_queryset(organization))


def check_monthly_token_limit(user) -> None:
    # `billing_organization` rather than `organization`: the latter resolves to
    # None while a membership is pending or rejected, and this function returns
    # early on None — so an unapproved member's spend used to bypass the cap
    # entirely. Whether the school's budget applies is a question about who
    # pays, not about who is authorised.
    organization = getattr(user, "billing_organization", None)
    if organization is None:
        return

    limit = int(getattr(organization, "monthly_token_limit", 0) or 0)
    if limit <= 0:
        return

    used = current_month_token_usage(organization)
    if used >= limit:
        # Priced only on the way out. The happy path runs on every billable
        # call and must stay one aggregate query.
        raise UsageLimitExceeded(
            organization_id=organization.id,
            organization_name=organization.name,
            limit=limit,
            used=used,
            cost_inr=current_month_cost_inr(organization),
        )
