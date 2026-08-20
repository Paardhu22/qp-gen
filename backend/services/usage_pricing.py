"""What the tokens actually cost, in rupees.

Every panel in this product reports spend as a token count, which is the one
unit a school administrator has no intuition for. "4.2 million tokens" answers
nothing; "₹1,840 this month" is the number that decides whether a limit gets
raised. This module is the single place that turns one into the other.

Two deliberate choices:

*   **Prices are a table, not a lookup.** OpenAI publishes per-model rates and
    changes them; a deployment must be able to correct a stale rate without a
    code change, so `MODEL_PRICING_USD_JSON` overrides any entry. The built-in
    table is the sensible default, not the authority.
*   **The result is an estimate and is named like one.** Token accounting on
    our side cannot see cached-input discounts, batch pricing, or the separate
    image-token tiers `gpt-image-1` bills on. Reporting this as "cost" invites
    someone to reconcile it against an invoice; it is a working figure for
    deciding limits, and every consumer should label it as approximate.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Iterable, Mapping, Tuple

from django.conf import settings
from django.db.models import Sum

logger = logging.getLogger("[USAGE_PRICING]")

#: USD per one million tokens, as ``(prompt, completion)``.
#:
#: Keys are matched exactly first, then by longest prefix, so a dated snapshot
#: id such as ``gpt-4.1-mini-2025-04-14`` bills at the ``gpt-4.1-mini`` rate
#: rather than silently falling through to the default.
DEFAULT_PRICING_USD_PER_MTOK: Dict[str, Tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o4-mini": (1.10, 4.40),
    "o3-mini": (1.10, 4.40),
    "text-embedding-3-small": (0.02, 0.00),
    "text-embedding-3-large": (0.13, 0.00),
    # Image generation bills text input, image input and image output at three
    # different rates and we record only a flat token count, so this is the
    # coarsest entry in the table. Priced at the image-output rate because that
    # is what dominates a figure-drawing call — an under-estimate here would be
    # the one that matters, since images are the expensive stage.
    "gpt-image-1": (5.00, 40.00),
}

#: Used when a model is not in the table at all. Deliberately the rate of the
#: model this product actually runs on, so an unrecognised name reports a
#: plausible figure rather than ₹0 — a zero would read as "this stage is free".
FALLBACK_USD_PER_MTOK: Tuple[float, float] = (0.40, 1.60)

#: Kept out of the price table because it moves for an entirely different
#: reason. Overridable per deployment: a school's finance team reconciling
#: against a card statement wants the rate their bank used.
DEFAULT_USD_TO_INR = 88.0


def _overrides() -> Mapping[str, Tuple[float, float]]:
    """Per-deployment price corrections from `MODEL_PRICING_USD_JSON`.

    Shape is ``{"model": [prompt_usd_per_mtok, completion_usd_per_mtok]}``. A
    malformed value is logged and ignored rather than raised: a typo in an env
    var must not take the analytics dashboard down.
    """
    raw = getattr(settings, "MODEL_PRICING_USD_JSON", "") or ""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        out: Dict[str, Tuple[float, float]] = {}
        for model, pair in (parsed or {}).items():
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                out[str(model)] = (float(pair[0]), float(pair[1]))
            elif isinstance(pair, (int, float)):
                # A single number means "same rate both ways", which is how
                # embedding models are usually quoted.
                out[str(model)] = (float(pair), float(pair))
        return out
    except Exception as exc:
        logger.warning("MODEL_PRICING_USD_JSON is not usable, ignoring it: %s", exc)
        return {}


def usd_to_inr_rate() -> float:
    try:
        rate = float(getattr(settings, "USD_TO_INR", DEFAULT_USD_TO_INR))
    except (TypeError, ValueError):
        return DEFAULT_USD_TO_INR
    return rate if rate > 0 else DEFAULT_USD_TO_INR


def rate_for(model: str) -> Tuple[float, float]:
    """USD per million (prompt, completion) tokens for `model`."""
    name = (model or "").strip()
    table = {**DEFAULT_PRICING_USD_PER_MTOK, **_overrides()}
    if name in table:
        return table[name]
    # Longest prefix wins, so "gpt-4.1-mini-2025-04-14" does not match "gpt-4.1".
    best: Tuple[str, Tuple[float, float]] | None = None
    for key, pair in table.items():
        if name.startswith(key) and (best is None or len(key) > len(best[0])):
            best = (key, pair)
    return best[1] if best else FALLBACK_USD_PER_MTOK


def usd_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_rate, completion_rate = rate_for(model)
    return (
        (prompt_tokens or 0) * prompt_rate + (completion_tokens or 0) * completion_rate
    ) / 1_000_000.0


def inr_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    return round(usd_cost(model, prompt_tokens, completion_tokens) * usd_to_inr_rate(), 2)


def inr_cost_of_rows(rows: Iterable[Mapping]) -> float:
    """Total rupee cost of pre-grouped rows.

    Each row needs ``model``, ``prompt`` and ``completion``. Grouping by model
    before calling this is what keeps the whole report a fixed number of
    queries no matter how many organizations exist.
    """
    total_usd = sum(
        usd_cost(row.get("model") or "", row.get("prompt") or 0, row.get("completion") or 0)
        for row in rows
    )
    return round(total_usd * usd_to_inr_rate(), 2)


def inr_cost_of_usage(queryset) -> float:
    """Rupee cost of an `ApiUsage` queryset, in exactly one grouped query."""
    rows = (
        queryset.values("model")
        .annotate(prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens"))
        .order_by()
    )
    return inr_cost_of_rows(rows)


def inr_cost_by_group(queryset, group_field: str) -> Dict[object, float]:
    """Rupee cost per value of `group_field`, in one grouped query.

    The grouping is ``(group_field, model)`` because the price depends on the
    model — summing tokens per group first and pricing the total would bill a
    school's image generation at the chat rate.
    """
    buckets: Dict[object, list] = {}
    rows = (
        queryset.values(group_field, "model")
        .annotate(prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens"))
        .order_by()
    )
    for row in rows:
        buckets.setdefault(row[group_field], []).append(row)
    return {key: inr_cost_of_rows(rows) for key, rows in buckets.items()}


def format_inr(amount: float) -> str:
    """`1840.5` → `"₹1,840.50"`. For logs and emails, not for the API."""
    return f"₹{amount:,.2f}"
