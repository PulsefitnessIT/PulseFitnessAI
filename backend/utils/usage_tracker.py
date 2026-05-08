"""Per-tenant usage meter (iter 215c0).

Lightweight counters for usage-based billing & soft-cap warnings. Tracks
the four metrics that scale linearly with cost:

    • members        — gym members on the platform (counted live from the
                       memberships collection, not incremented here).
    • ai_tokens      — Claude / Gemini / GPT token consumption (write-in
                       from `record_ai_usage`).
    • sms            — outbound SMS (currently mocked Twilio; counter is
                       still incremented so dashboards reflect future bills).
    • api_calls      — total /api/* hits per org (cheap counter, used for
                       rate-limit upsell prompts).
    • emails         — outbound transactional + marketing emails (Resend).

Storage model: one document per (org_id, period_yyyymm) in
`usage_counters`. We use atomic `$inc` so concurrent writes stay accurate.

Limits live in `PLAN_LIMITS` and gate dashboard warnings — not enforcement.
Hard enforcement should remain at the Stripe billing layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from utils.database import db


# Soft limits per plan — drives the warning banner, not enforcement.
PLAN_LIMITS: dict[str, dict[str, int]] = {
    # Trial: generous enough to demo every feature
    "trial": {"members": 200, "ai_tokens": 500_000, "sms": 100, "api_calls": 50_000, "emails": 1_000},
    "starter": {"members": 250, "ai_tokens": 1_000_000, "sms": 250, "api_calls": 100_000, "emails": 5_000},
    "pro": {"members": 1_500, "ai_tokens": 5_000_000, "sms": 1_500, "api_calls": 500_000, "emails": 50_000},
    "enterprise": {"members": 100_000, "ai_tokens": 50_000_000, "sms": 50_000, "api_calls": 5_000_000, "emails": 500_000},
}

# Single-module trial / paid licences resolve here. We pick the higher of
# the two to be friendly when a customer has multiple modules.
MODULE_LIMITS: dict[str, dict[str, int]] = {
    "memberships": {"members": 500, "ai_tokens": 250_000, "sms": 250, "api_calls": 100_000, "emails": 5_000},
    "crm":         {"members": 50,  "ai_tokens": 1_500_000, "sms": 50, "api_calls": 200_000, "emails": 10_000},
    "marketing":   {"members": 50,  "ai_tokens": 2_000_000, "sms": 1_000, "api_calls": 200_000, "emails": 25_000},
    "operations":  {"members": 50,  "ai_tokens": 250_000, "sms": 50, "api_calls": 100_000, "emails": 2_500},
}


def _period_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}{now.month:02d}"


async def record_usage(organization_id: str, metric: str, qty: int = 1) -> None:
    """Increment a usage metric for the current month. Safe to no-op."""
    if not organization_id or qty <= 0 or metric not in {"ai_tokens", "sms", "api_calls", "emails"}:
        return
    period = _period_key()
    await db.usage_counters.update_one(
        {"organization_id": organization_id, "period": period},
        {
            "$inc": {f"counts.{metric}": int(qty)},
            "$setOnInsert": {
                "organization_id": organization_id,
                "period": period,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
        upsert=True,
    )


async def get_usage_summary(organization_id: str) -> dict:
    """Return the current period's counters, plus live member count + plan limits."""
    period = _period_key()
    doc = await db.usage_counters.find_one(
        {"organization_id": organization_id, "period": period}, {"_id": 0}
    ) or {}
    counts = dict(doc.get("counts") or {})

    # Live member count — the source of truth is the `members` collection,
    # not a counter, so a bulk delete shows up immediately.
    members = await db.members.count_documents(
        {"organization_id": organization_id, "status": {"$ne": "deleted"}}
    )
    counts["members"] = members

    # Resolve limits from the org's plan.
    org = await db.organizations.find_one(
        {"id": organization_id},
        {"_id": 0, "subscription_tier": 1, "is_trial": 1, "enabled_modules": 1, "account_type": 1},
    ) or {}

    if org.get("is_trial"):
        limits = dict(PLAN_LIMITS["trial"])
    else:
        tier = (org.get("subscription_tier") or "starter").lower()
        # Map common tier aliases.
        if tier in ("none", "free"):
            tier = "starter"
        if tier in PLAN_LIMITS:
            limits = dict(PLAN_LIMITS[tier])
        else:
            # Sum module-level limits when on a multi-module plan.
            modules = org.get("enabled_modules") or []
            if modules:
                limits = {k: 0 for k in PLAN_LIMITS["starter"]}
                for m in modules:
                    for k, v in MODULE_LIMITS.get(m, {}).items():
                        limits[k] = max(limits.get(k, 0), v)
            else:
                limits = dict(PLAN_LIMITS["starter"])

    metrics = []
    for key in ("members", "ai_tokens", "sms", "api_calls", "emails"):
        used = int(counts.get(key, 0) or 0)
        limit = int(limits.get(key, 0) or 0)
        pct = round((used / limit) * 100, 1) if limit else 0.0
        if pct >= 100:
            level = "exceeded"
        elif pct >= 90:
            level = "critical"
        elif pct >= 75:
            level = "warning"
        else:
            level = "ok"
        metrics.append({
            "metric": key,
            "used": used,
            "limit": limit,
            "pct": pct,
            "level": level,
        })

    has_warning = any(m["level"] in ("warning", "critical", "exceeded") for m in metrics)
    return {
        "organization_id": organization_id,
        "period": period,
        "metrics": metrics,
        "has_warning": has_warning,
        "plan": (org.get("subscription_tier") or "starter").lower(),
        "is_trial": bool(org.get("is_trial")),
    }
