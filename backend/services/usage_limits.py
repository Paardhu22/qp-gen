from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Sum
from django.utils import timezone

from apps.generation.models import ApiUsage


@dataclass(frozen=True)
class UsageLimitExceeded(RuntimeError):
    organization_id: str
    organization_name: str
    limit: int
    used: int

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
        }


def current_month_token_usage(organization) -> int:
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = (
        ApiUsage.objects.filter(
            organization=organization,
            created_at__gte=month_start,
        ).aggregate(total=Sum("total_tokens"))
    )
    return result["total"] or 0


def check_monthly_token_limit(user) -> None:
    organization = getattr(user, "organization", None)
    if organization is None:
        return

    limit = int(getattr(organization, "monthly_token_limit", 0) or 0)
    if limit <= 0:
        return

    used = current_month_token_usage(organization)
    if used >= limit:
        raise UsageLimitExceeded(
            organization_id=organization.id,
            organization_name=organization.name,
            limit=limit,
            used=used,
        )
