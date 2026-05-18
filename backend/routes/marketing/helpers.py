"""Shared helpers for the marketing package.

Imports + plan-defaults + entitlement / feature-gate helpers used by
every submodule. Importing from `.helpers` avoids cross-module deps.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from utils.database import db

logger = logging.getLogger("marketing")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


async def _org_id(user: dict) -> str:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(status_code=400, detail="User has no organization context")
    return org


# ───────────────────────── Plans (defaults) ─────────────────────────

DEFAULT_PLANS = [
    {
        "id": "basic",
        "name": "Basic Marketing",
        "monthly_price_gbp": 49,
        "annual_price_gbp": 490,
        "limits": {"contacts": 5_000, "monthly_emails": 25_000, "monthly_sms": 0,
                   "ai_generations": 0, "journey_count": 3, "social_accounts": 1},
        "features": {"audiences": True, "campaigns": True,
                     "ai_creative_studio": False, "journeys": True,
                     "social_scheduling": False, "advanced_attribution": False},
        "active": True, "sort_order": 1,
    },
    {
        "id": "pro",
        "name": "Pro Marketing",
        "monthly_price_gbp": 149,
        "annual_price_gbp": 1_490,
        "limits": {"contacts": 25_000, "monthly_emails": 250_000, "monthly_sms": 2_500,
                   "ai_generations": 500, "journey_count": 25, "social_accounts": 5},
        "features": {"audiences": True, "campaigns": True,
                     "ai_creative_studio": True, "journeys": True,
                     "social_scheduling": True, "advanced_attribution": True},
        "active": True, "sort_order": 2,
    },
    {
        "id": "enterprise",
        "name": "Enterprise Marketing",
        "monthly_price_gbp": 399,
        "annual_price_gbp": 3_990,
        "limits": {"contacts": 999_999, "monthly_emails": 9_999_999,
                   "monthly_sms": 9_999, "ai_generations": 5_000,
                   "journey_count": 999, "social_accounts": 999},
        "features": {"audiences": True, "campaigns": True,
                     "ai_creative_studio": True, "journeys": True,
                     "social_scheduling": True, "advanced_attribution": True,
                     "white_label_social": True, "dedicated_csm": True},
        "active": True, "sort_order": 3,
    },
]


async def _seed_default_plans_once() -> None:
    """Idempotent — seed only when the collection is empty."""
    existing = await db.marketing_plans.count_documents({})
    if existing == 0:
        await db.marketing_plans.insert_many([{**p, "created_at": _now_iso()} for p in DEFAULT_PLANS])


async def _get_plan(plan_id: str) -> Optional[dict]:
    return await db.marketing_plans.find_one({"id": plan_id}, {"_id": 0})


async def _get_org_subscription(organization_id: str) -> dict:
    """Return the org's marketing subscription, defaulting to a 14-day free
    Pro trial on first call so the user can immediately try premium features.

    Iter 216h192 — Orgs that already pay for a Pulse Pro / GymAxis Full / Lite
    platform plan get Marketing bundled. Seeding them as a 14-day "trial"
    surfaced a misleading "Free trial" pill in the Marketing header even
    after they had been customers for months. For those orgs we seed an
    ``active`` subscription instead so the entitlement reflects reality.
    """
    sub = await db.marketing_subscriptions.find_one({"organization_id": organization_id}, {"_id": 0})
    if sub:
        # Iter 216h192 — Heal stale 'trial' subs for orgs that have since
        # been switched onto a paid platform plan. Without this they keep
        # showing the misleading "Free trial" pill forever.
        if sub.get("status") == "trial":
            org = await db.organizations.find_one(
                {"id": organization_id}, {"_id": 0, "account_type": 1}
            ) or {}
            if (org.get("account_type") or "").lower() in {"pulse_pro", "full", "lite"}:
                await db.marketing_subscriptions.update_one(
                    {"organization_id": organization_id},
                    {"$set": {"status": "active", "comp_seats": True, "trial_ends_at": None,
                              "healed_at": _now_iso(), "healed_reason": "bundled_with_platform_plan"}},
                )
                sub["status"] = "active"
                sub["comp_seats"] = True
                sub["trial_ends_at"] = None
        return sub
    org = await db.organizations.find_one(
        {"id": organization_id}, {"_id": 0, "account_type": 1}
    ) or {}
    paid_platform_plan = (org.get("account_type") or "").lower() in {"pulse_pro", "full", "lite"}
    if paid_platform_plan:
        seed = {
            "organization_id": organization_id, "plan_id": "pro",
            "status": "active",
            "trial_ends_at": None,
            "current_period_end": None, "stripe_subscription_id": None,
            "usage_this_period": {"emails_sent": 0, "sms_sent": 0, "ai_generations": 0, "contacts_count": 0},
            "comp_seats": True,
            "created_at": _now_iso(),
        }
    else:
        seed = {
            "organization_id": organization_id, "plan_id": "pro",
            "status": "trial",
            "trial_ends_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "current_period_end": None, "stripe_subscription_id": None,
            "usage_this_period": {"emails_sent": 0, "sms_sent": 0, "ai_generations": 0, "contacts_count": 0},
            "comp_seats": False,
            "created_at": _now_iso(),
        }
    await db.marketing_subscriptions.insert_one(seed)
    return await db.marketing_subscriptions.find_one(
        {"organization_id": organization_id}, {"_id": 0},
    )


async def _get_entitlement(user: dict) -> dict:
    org_id = await _org_id(user)
    await _seed_default_plans_once()
    sub = await _get_org_subscription(org_id)
    plan = await _get_plan(sub["plan_id"]) or DEFAULT_PLANS[1]  # fallback Pro
    return {"subscription": sub, "plan": plan, "features": plan["features"], "limits": plan["limits"]}


def _require_feature(entitlement: dict, feature: str) -> None:
    if not entitlement["features"].get(feature):
        raise HTTPException(
            status_code=402,
            detail=f"This feature requires an upgrade ({feature}). Current plan: {entitlement['plan']['name']}",
        )


def _require_admin(user: dict) -> None:
    """Allow GymAxis Master + Pulse Master Admin to mutate plans + read
    analytics. Local import avoids a circular dep at module load."""
    from routes.master_admin import require_master_admin
    require_master_admin(user)
