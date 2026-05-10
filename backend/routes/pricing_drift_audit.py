"""Pricing drift audit (Iter 216g · Plan D).

Compares the master-admin pricing engine (`pricing_plans`) against legacy /
parallel pricing surfaces and returns a list of drift items so the operator
can spot stale numbers before they reach a customer screen.

Surfaces compared:
  1. ``pricing_plans`` (the editable source of truth) → Marketing module
  2. ``marketing_plans`` (legacy 3-tier) → flagged because it duplicates #1
  3. ``PricingPage.js`` static `PLANS` array values → checked via known
     hard-coded copy (Starter £29 / Pro £79 / Bundle £199 / Enterprise £249).
     Those four numbers are encoded here as ``HOMEPAGE_PRICES``. If any of
     them are touched in the future, just update this file and the audit
     will catch the next drift event.

Endpoint
--------
* ``GET /api/master-admin/pricing/audit-drift``  → ``{ items: [...] }``
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routes.auth import get_current_user
from routes.master_admin import require_master_admin
from utils.database import db


router = APIRouter(tags=["pricing-drift"])


# Hard-coded marketing-page prices (kept in sync manually with PricingPage.js
# `PLANS` array). When you edit those, edit here too — the audit will then
# flag any further drift between the homepage and the pricing engine.
HOMEPAGE_PRICES = {
    "starter":    29,
    "pro":        79,
    "bundle":    199,
    "enterprise": 249,
}


@router.get("/master-admin/pricing/audit-drift")
async def audit_drift(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    items: list[dict] = []

    # 1) Marketing module in pricing_plans vs marketing_plans collection.
    mkt_engine = await db.pricing_plans.find_one(
        {"brand": "gymaxis", "module_id": "marketing"}, {"_id": 0},
    )
    legacy_plans = await db.marketing_plans.find({}, {"_id": 0}).to_list(length=20)
    if mkt_engine and legacy_plans:
        engine_monthly = (mkt_engine.get("prices") or {}).get("GBP", {}).get("monthly", 0)
        for lp in legacy_plans:
            legacy_pence = int(lp.get("monthly_price_gbp", 0)) * 100
            if legacy_pence and legacy_pence != engine_monthly:
                items.append({
                    "severity": "warning",
                    "surface": "marketing_plans (legacy)",
                    "field": f"{lp.get('id')} · monthly £",
                    "engine_value": f"£{engine_monthly / 100:.2f}",
                    "drift_value": f"£{lp.get('monthly_price_gbp', 0):.2f}",
                    "fix": "Sunset legacy `marketing_plans` once add-on packs are live in production.",
                })

    # 2) Homepage hard-coded numbers vs engine. The engine has per-module
    #    plans, so we compare what the homepage IMPLIES against the closest
    #    engine equivalent. If you update PricingPage.js, mirror the value
    #    in HOMEPAGE_PRICES so this audit stays accurate.
    plans_by_module = {
        p["module_id"]: p
        async for p in db.pricing_plans.find({"brand": "gymaxis"}, {"_id": 0})
    }
    bundle = plans_by_module.get("bundle_all")
    ops = plans_by_module.get("operations")
    if bundle:
        bundle_monthly_p = (bundle.get("prices") or {}).get("GBP", {}).get("monthly", 0)
        bundle_monthly = bundle_monthly_p / 100
        if abs(bundle_monthly - HOMEPAGE_PRICES["bundle"]) > 0.5:
            items.append({
                "severity": "warning",
                "surface": "PricingPage.js (homepage)",
                "field": "Bundle · monthly £",
                "engine_value": f"£{bundle_monthly:.2f}",
                "drift_value": f"£{HOMEPAGE_PRICES['bundle']:.2f}",
                "fix": "Update the static PLANS array in PricingPage.js (or migrate it to /api/pricing/public).",
            })
    if ops:
        ops_monthly_p = (ops.get("prices") or {}).get("GBP", {}).get("monthly", 0)
        ops_monthly = ops_monthly_p / 100
        if abs(ops_monthly - HOMEPAGE_PRICES["pro"]) > 0.5:
            items.append({
                "severity": "info",
                "surface": "PricingPage.js (homepage)",
                "field": "Pro / Operations · monthly £",
                "engine_value": f"£{ops_monthly:.2f}",
                "drift_value": f"£{HOMEPAGE_PRICES['pro']:.2f}",
                "fix": "Operations module £49 in engine, homepage shows Pro £79 — confirm whether these refer to the same SKU.",
            })

    # 3) Memberships still flagged Lite/Pro? Surface anything in DB.
    pro_orgs = await db.organizations.count_documents(
        {"memberships_tier": "pro"},
    )
    if pro_orgs:
        items.append({
            "severity": "info",
            "surface": "organizations.memberships_tier (legacy field)",
            "field": "memberships_tier == 'pro'",
            "engine_value": "single-tier (no Lite/Pro)",
            "drift_value": f"{pro_orgs} orgs still flagged Pro",
            "fix": "Field is preserved for forward-compat but no longer surfaced. Optional: run a one-off update setting it to null on all orgs.",
        })

    return {
        "items": items,
        "count": len(items),
        "compared_surfaces": [
            "pricing_plans (engine)",
            "marketing_plans (legacy)",
            "PricingPage.js (homepage)",
            "organizations.memberships_tier (legacy field)",
        ],
    }


__all__ = ["router"]
