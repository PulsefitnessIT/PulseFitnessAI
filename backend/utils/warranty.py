"""Warranty tiers for Equipment Sales.

The seller can sell different levels of warranty against each piece of
equipment on a CPQ quote. A tier is captured on the equipment sale line at
quote time, flows through the PO/GRN so the created ``equipment`` record is
stamped with the sold cover, and is printed on the customer Handover Pack.

Kept deliberately small and code-defined (no new collection) — the price a
customer pays is set on the quote line itself; the tier only defines the
coverage label + duration used for the warranty expiry and the pack wording.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Ordered least → most cover. `code` is the stored value; `months` drives the
# warranty-expiry calculation; `summary` is the one-line customer wording.
WARRANTY_TIERS: list[dict] = [
    {
        "code": "standard",
        "label": "Standard — 1 year",
        "months": 12,
        "summary": "12 months parts & labour (manufacturer standard).",
    },
    {
        "code": "extended_3yr",
        "label": "Extended — 3 years",
        "months": 36,
        "summary": "3 years parts & labour, priority booking.",
    },
    {
        "code": "premium_5yr",
        "label": "Premium — 5 years",
        "months": 60,
        "summary": "5 years parts & labour, priority response & annual service.",
    },
]

_BY_CODE = {t["code"]: t for t in WARRANTY_TIERS}
DEFAULT_TIER = "standard"


def get_tier(code: str | None) -> dict:
    """Resolve a tier dict, falling back to the standard tier."""
    return _BY_CODE.get((code or "").strip().lower(), _BY_CODE[DEFAULT_TIER])


def tier_months(code: str | None) -> int:
    return int(get_tier(code)["months"])


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        return datetime.fromisoformat(v)
    except Exception:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def compute_expiry(start: str | None, months: int) -> str | None:
    """Return an ISO date (YYYY-MM-DD) `months` after `start` (approx via
    30.44-day months so we never depend on dateutil). Returns None if the
    start date can't be parsed."""
    dt = _parse_iso(start)
    if not dt:
        return None
    end = dt + timedelta(days=round(months * 30.44))
    return end.strftime("%Y-%m-%d")


__all__ = [
    "WARRANTY_TIERS", "DEFAULT_TIER", "get_tier", "tier_months", "compute_expiry",
]
