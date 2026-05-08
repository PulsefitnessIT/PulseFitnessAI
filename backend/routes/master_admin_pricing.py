"""Master Admin — pricing engine.

Single source of truth for the prices shown on both brand homepages and
charged to organisations on monthly invoices. Master admin edits the
plans here; the public homepage fetches them via `GET /api/pricing/public`
without auth.

Why module-based?
=================
The product is sold à la carte: an org may take only Memberships, or
Operations + CRM, etc. Each module has its own price; a Bundle is a
discounted "everything" plan. Master admin can mark plans active /
inactive without deleting them, which keeps the audit trail clean.

Why per-currency hand-typed prices?
===================================
Auto-FX'd prices drift unpredictably and surprise customers. Operators
type the GBP / EUR / USD price independently and we never convert at
runtime.

Why per-site discount tiers?
============================
Big chains expect volume pricing. The discount is applied as a
percentage off the base monthly price, scaling with site count. Stripe
checkout receives the **post-discount** unit_amount as a one-off Price
so we never have to maintain N×M Stripe products for every site-count
combination.

Schema (`pricing_plans`)
========================
::

    {
        "id":            uuid,
        "brand":         "gymaxis" | "pulse",
        "module_id":     "operations" | "memberships" | "crm" |
                         "marketing" | "bundle_all",
        "name":          str,
        "description":   str,
        "features":      [str, …],
        "display_order": int,
        "active":        bool,
        "is_bundle":     bool,
        "prices": {                     # Hand-typed per-currency in MINOR units
            "GBP": {"monthly": 4900, "annual": 49000},
            "EUR": {"monthly": 5900, "annual": 59000},
            "USD": {"monthly": 6900, "annual": 69000}
        },
        "site_tiers": [                 # Volume discount, sorted by min_sites asc
            {"min_sites": 1, "max_sites": 1,    "discount_pct": 0},
            {"min_sites": 2, "max_sites": 5,    "discount_pct": 10},
            {"min_sites": 6, "max_sites": 20,   "discount_pct": 20},
            {"min_sites": 21, "max_sites": null,"discount_pct": 30}
        ],
        "vat_rate":      0.20,
        "vat_inclusive": true,
        "updated_by":    user_id,
        "updated_at":    iso,
        "created_at":    iso
    }

Schema (`pricing_audit_log`)
============================
Append-only — every PUT writes a row capturing before/after for the
plan that changed. Master admin uses this to answer "who changed the
Pulse Memberships price last week?" without spelunking git.
"""
from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────

SUPPORTED_CURRENCIES = ("GBP", "EUR", "USD")
SUPPORTED_BRANDS = ("gymaxis", "pulse")
MODULE_IDS = ("operations", "memberships", "crm", "marketing")
BUNDLE_ID = "bundle_all"
ALL_MODULE_IDS = (*MODULE_IDS, BUNDLE_ID)
DEFAULT_VAT_RATE = 0.20


# ── Default seed (used by /seed-defaults so a brand-new install has
#     something sensible on the public homepage immediately) ──────────

def _seed_plans() -> list[dict[str, Any]]:
    """Out-of-the-box plans for both brands.

    Numbers are placeholders the master admin will tune — but they map
    to the historic GymAxis price points (Pro = £79/m) so the public
    homepage doesn't show £0 the moment we deploy the engine.
    """
    base_tiers = [
        {"min_sites": 1, "max_sites": 1, "discount_pct": 0},
        {"min_sites": 2, "max_sites": 5, "discount_pct": 10},
        {"min_sites": 6, "max_sites": 20, "discount_pct": 20},
        {"min_sites": 21, "max_sites": None, "discount_pct": 30},
    ]
    # Module → (gbp_monthly, description, features)
    catalogue = {
        "operations": (4900, "Equipment, faults, PPM, suppliers, compliance.", [
            "Unlimited equipment records",
            "AI fault triage + audits",
            "PPM engine + compliance %",
            "Supplier collaboration portal",
            "Reports + weekly digest",
        ]),
        "memberships": (5900, "Member portal, class booking, plans, kiosk.", [
            "Unlimited members + family accounts",
            "Class booking + waitlist",
            "Stripe-powered recurring plans",
            "QR kiosk check-in",
            "Mobile App Builder",
        ]),
        "crm": (4900, "Pipeline, leads, tenders, deal-flow.", [
            "Lead + deal pipeline",
            "Email + activity tracking",
            "AI assistant for follow-ups",
            "Reports & forecasting",
        ]),
        "marketing": (3900, "Campaigns, templates, branded comms.", [
            "Email + SMS campaigns",
            "Branded templates & assets",
            "Audience segmentation",
            "Funnel & attribution analytics",
        ]),
    }
    seeds: list[dict[str, Any]] = []
    for brand in SUPPORTED_BRANDS:
        order = 0
        for mod_id, (gbp, desc, features) in catalogue.items():
            seeds.append({
                "id": str(uuid.uuid4()),
                "brand": brand,
                "module_id": mod_id,
                "name": mod_id.title(),
                "description": desc,
                "features": features,
                "display_order": order,
                "active": True,
                "is_bundle": False,
                "prices": {
                    "GBP": {"monthly": gbp,           "annual": gbp * 10},
                    "EUR": {"monthly": int(gbp * 1.18), "annual": int(gbp * 10 * 1.18)},
                    "USD": {"monthly": int(gbp * 1.27), "annual": int(gbp * 10 * 1.27)},
                },
                "site_tiers": deepcopy(base_tiers),
                "vat_rate": DEFAULT_VAT_RATE,
                "vat_inclusive": True,
            })
            order += 1
        # Bundle = sum of modules - 20%
        bundle_gbp = int(sum(g for g, *_ in catalogue.values()) * 0.80)
        seeds.append({
            "id": str(uuid.uuid4()),
            "brand": brand,
            "module_id": BUNDLE_ID,
            "name": "All-in-one Bundle",
            "description": "Operations + Memberships + CRM + Marketing — save 20%.",
            "features": [
                "Everything in all four modules",
                "Single sign-on across modules",
                "Consolidated dashboards & KPIs",
                "Priority engineer escalation",
                "Dedicated onboarding",
            ],
            "display_order": order,
            "active": True,
            "is_bundle": True,
            "prices": {
                "GBP": {"monthly": bundle_gbp,           "annual": bundle_gbp * 10},
                "EUR": {"monthly": int(bundle_gbp * 1.18), "annual": int(bundle_gbp * 10 * 1.18)},
                "USD": {"monthly": int(bundle_gbp * 1.27), "annual": int(bundle_gbp * 10 * 1.27)},
            },
            "site_tiers": deepcopy(base_tiers),
            "vat_rate": DEFAULT_VAT_RATE,
            "vat_inclusive": True,
        })
    return seeds


# ── Helpers ─────────────────────────────────────────────────────────

def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_brand(brand: str) -> str:
    b = (brand or "").lower()
    if b not in SUPPORTED_BRANDS:
        raise HTTPException(400, f"brand must be one of {SUPPORTED_BRANDS}")
    return b


def _validate_module(module_id: str) -> str:
    m = (module_id or "").lower()
    if m not in ALL_MODULE_IDS:
        raise HTTPException(400, f"module_id must be one of {ALL_MODULE_IDS}")
    return m


def _validate_prices(prices: dict) -> dict:
    if not isinstance(prices, dict):
        raise HTTPException(400, "prices must be an object")
    out: dict[str, dict[str, int]] = {}
    for ccy, pair in prices.items():
        ccy_u = ccy.upper()
        if ccy_u not in SUPPORTED_CURRENCIES:
            raise HTTPException(400, f"unsupported currency {ccy}")
        if not isinstance(pair, dict):
            raise HTTPException(400, f"prices.{ccy} must be {{monthly, annual}}")
        try:
            monthly = int(pair.get("monthly", 0))
            annual = int(pair.get("annual", 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"prices.{ccy} must be integers (minor units)") from exc
        if monthly < 0 or annual < 0:
            raise HTTPException(400, "prices must be non-negative")
        out[ccy_u] = {"monthly": monthly, "annual": annual}
    return out


def _validate_tiers(tiers: list) -> list[dict[str, Any]]:
    if not isinstance(tiers, list) or not tiers:
        # Empty tiers means "no volume discount" — replace with a single
        # 0%-off row so the rest of the engine can iterate uniformly.
        return [{"min_sites": 1, "max_sites": None, "discount_pct": 0}]
    out: list[dict[str, Any]] = []
    for t in tiers:
        if not isinstance(t, dict):
            raise HTTPException(400, "site_tiers entries must be objects")
        try:
            mn = int(t.get("min_sites", 1))
            mx = t.get("max_sites")
            mx_i = int(mx) if mx is not None else None
            pct = float(t.get("discount_pct", 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "site_tiers values must be numeric") from exc
        if mn < 1:
            raise HTTPException(400, "site_tiers.min_sites must be >= 1")
        if mx_i is not None and mx_i < mn:
            raise HTTPException(400, "site_tiers.max_sites must be >= min_sites")
        if pct < 0 or pct > 100:
            raise HTTPException(400, "site_tiers.discount_pct must be 0..100")
        out.append({"min_sites": mn, "max_sites": mx_i, "discount_pct": pct})
    out.sort(key=lambda r: r["min_sites"])
    return out


_FIELD_VALIDATORS: dict[str, Any] = {
    "brand":         lambda v: _validate_brand(v or ""),
    "module_id":     lambda v: _validate_module(v or ""),
    "description":   lambda v: (v or "").strip()[:500],
    "display_order": lambda v: _safe_int(v, 0, "display_order"),
    "active":        bool,
    "is_bundle":     bool,
    "prices":        lambda v: _validate_prices(v or {}),
    "site_tiers":    lambda v: _validate_tiers(v or []),
    "vat_rate":      lambda v: _validate_vat_rate(v),
    "vat_inclusive": lambda v: bool(v if v is not None else True),
}

# Fields that are required when ``partial=False`` (i.e. POST /pricing creates).
_REQUIRED_ON_CREATE = ("brand", "module_id", "is_bundle", "prices", "site_tiers")


def _safe_int(v: Any, default: int, name: str) -> int:
    try:
        return int(v if v is not None else default)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"{name} must be int") from exc


def _validate_vat_rate(v: Any) -> float:
    try:
        rate = float(v if v is not None else DEFAULT_VAT_RATE)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "vat_rate must be numeric") from exc
    if rate < 0 or rate > 1:
        raise HTTPException(400, "vat_rate must be between 0 and 1 (e.g. 0.20)")
    return rate


def _validate_features(v: Any) -> list[str]:
    if not isinstance(v, list):
        raise HTTPException(400, "features must be a list of strings")
    return [str(f).strip()[:200] for f in v if str(f).strip()][:30]


def _coerce_plan(payload: dict, *, partial: bool = False) -> dict[str, Any]:
    """Validate and normalise the operator-supplied plan body.

    Field-by-field via the ``_FIELD_VALIDATORS`` table so adding a new
    pricing column is a one-line registration rather than another
    ``if … in payload`` branch in this function.
    """
    out: dict[str, Any] = {}
    for field, validator in _FIELD_VALIDATORS.items():
        if field in payload or (not partial and field in _REQUIRED_ON_CREATE):
            out[field] = validator(payload.get(field))
    # `name` and `features` need cross-field context, kept inline.
    if "name" in payload or not partial:
        out["name"] = (payload.get("name") or "").strip()[:80] or out.get("module_id", "Plan").title()
    if "features" in payload:
        out["features"] = _validate_features(payload.get("features") or [])
    return out


def discount_for_sites(site_tiers: list[dict[str, Any]], sites: int) -> float:
    """Pure helper — return the discount_pct that applies for `sites`.

    Public so /api/pricing/public and the billing engine share one rule.
    """
    sites = max(1, int(sites or 1))
    for t in site_tiers:
        mn = int(t["min_sites"])
        mx = t.get("max_sites")
        if sites >= mn and (mx is None or sites <= int(mx)):
            return float(t.get("discount_pct", 0))
    return 0.0


def calculate_quote(plan: dict, *, currency: str, billing_cycle: str, sites: int) -> dict[str, Any]:
    """Return {gross, vat, total, currency, discount_pct, base_monthly, …}.

    `gross` and `total` are post-discount, post-VAT (since plans are
    VAT-inclusive by default — VAT is shown for transparency, not added
    on top).
    """
    ccy = currency.upper()
    if ccy not in SUPPORTED_CURRENCIES:
        ccy = "GBP"
    cycle = billing_cycle if billing_cycle in ("monthly", "annual") else "monthly"
    base = int((plan.get("prices") or {}).get(ccy, {}).get(cycle, 0))
    discount_pct = discount_for_sites(plan.get("site_tiers") or [], sites)
    discounted = int(round(base * (100 - discount_pct) / 100))
    vat_rate = float(plan.get("vat_rate", DEFAULT_VAT_RATE))
    vat_inclusive = bool(plan.get("vat_inclusive", True))
    if vat_inclusive:
        # VAT bundled inside the price; back out for transparency.
        vat = int(round(discounted - discounted / (1 + vat_rate)))
        gross = discounted - vat
        total = discounted
    else:
        vat = int(round(discounted * vat_rate))
        gross = discounted
        total = discounted + vat
    return {
        "currency": ccy,
        "billing_cycle": cycle,
        "base_amount": base,
        "discount_pct": discount_pct,
        "net_amount": gross,
        "vat_amount": vat,
        "total_amount": total,
        "vat_inclusive": vat_inclusive,
        "vat_rate": vat_rate,
        "sites": sites,
    }


# ── Endpoints — Master admin (write) ────────────────────────────────


@router.get("/master-admin/pricing")
async def list_plans(
    brand: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return every plan, optionally filtered by brand. Master admin only."""
    _require_master(user)
    query: dict[str, Any] = {}
    if brand:
        query["brand"] = _validate_brand(brand)
    cursor = db.pricing_plans.find(query, {"_id": 0}).sort("display_order", 1)
    plans = await cursor.to_list(length=200)
    return {"plans": plans}


@router.post("/master-admin/pricing/seed-defaults")
async def seed_defaults(user: dict = Depends(get_current_user)) -> dict:
    """Idempotent seeding — creates default plans only for missing
    (brand, module_id) pairs. Useful on a fresh install.
    """
    _require_master(user)
    created = 0
    for plan in _seed_plans():
        existing = await db.pricing_plans.find_one(
            {"brand": plan["brand"], "module_id": plan["module_id"]}, {"_id": 1}
        )
        if existing:
            continue
        plan["created_at"] = _now()
        plan["updated_at"] = _now()
        plan["updated_by"] = user.get("id")
        await db.pricing_plans.insert_one(plan)
        created += 1
    return {"created": created}


@router.post("/master-admin/pricing")
async def create_plan(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Create a new plan. Returns the inserted doc (no _id)."""
    _require_master(user)
    body = _coerce_plan(payload, partial=False)
    # On create, zero-fill missing currencies so the UI always sees all three.
    for ccy in SUPPORTED_CURRENCIES:
        body.setdefault("prices", {}).setdefault(ccy, {"monthly": 0, "annual": 0})
    # Reject duplicate (brand, module_id) — there's only ever one plan
    # per pair; updates use PUT.
    if await db.pricing_plans.find_one(
        {"brand": body["brand"], "module_id": body["module_id"]}, {"_id": 1}
    ):
        raise HTTPException(409, "A plan already exists for that brand+module")
    body["id"] = str(uuid.uuid4())
    body["created_at"] = _now()
    body["updated_at"] = _now()
    body["updated_by"] = user.get("id")
    await db.pricing_plans.insert_one(dict(body))
    saved = await db.pricing_plans.find_one({"id": body["id"]}, {"_id": 0})
    await _audit(plan_id=body["id"], before=None, after=saved, user_id=user.get("id"), action="create")
    return {"plan": saved}


@router.put("/master-admin/pricing/{plan_id}")
async def update_plan(
    plan_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Patch a plan. Logs before/after to `pricing_audit_log`."""
    _require_master(user)
    existing = await db.pricing_plans.find_one({"id": plan_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Plan not found")
    patch = _coerce_plan(payload, partial=True)
    # brand + module_id are immutable post-create (avoid breaking
    # FK-style references in audit log).
    patch.pop("brand", None)
    patch.pop("module_id", None)
    # Partial price updates merge into the existing prices dict so an
    # operator updating only GBP doesn't wipe EUR / USD to zero.
    if "prices" in patch:
        merged = dict(existing.get("prices") or {})
        for ccy, pair in patch["prices"].items():
            merged[ccy] = pair
        patch["prices"] = merged
    patch["updated_at"] = _now()
    patch["updated_by"] = user.get("id")
    await db.pricing_plans.update_one({"id": plan_id}, {"$set": patch})
    saved = await db.pricing_plans.find_one({"id": plan_id}, {"_id": 0})
    await _audit(plan_id=plan_id, before=existing, after=saved, user_id=user.get("id"), action="update")
    return {"plan": saved}


@router.delete("/master-admin/pricing/{plan_id}")
async def delete_plan(plan_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Hard delete — logged in audit log so the row history survives."""
    _require_master(user)
    existing = await db.pricing_plans.find_one({"id": plan_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Plan not found")
    await db.pricing_plans.delete_one({"id": plan_id})
    await _audit(plan_id=plan_id, before=existing, after=None, user_id=user.get("id"), action="delete")
    return {"deleted": True}


@router.get("/master-admin/pricing/audit")
async def get_audit(
    plan_id: str | None = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_master(user)
    query: dict[str, Any] = {}
    if plan_id:
        query["plan_id"] = plan_id
    cursor = db.pricing_audit_log.find(query, {"_id": 0}).sort("at", -1).limit(min(int(limit or 50), 200))
    rows = await cursor.to_list(length=200)
    return {"entries": rows}


# ── Public — homepage consumer ──────────────────────────────────────


@router.get("/pricing/public")
async def get_public_pricing(
    brand: str = "gymaxis",
    currency: str = "GBP",
    sites: int = 1,
) -> dict:
    """Anon-readable. Returns active plans with calculated prices.

    Example::

        GET /api/pricing/public?brand=pulse&currency=EUR&sites=4

    Each plan in the response has `quote_monthly` and `quote_annual`
    pre-computed for the requested currency + site count, so the
    homepage renders without touching the engine.
    """
    b = _validate_brand(brand)
    ccy = currency.upper() if currency.upper() in SUPPORTED_CURRENCIES else "GBP"
    sites_i = max(1, int(sites or 1))
    cursor = db.pricing_plans.find({"brand": b, "active": True}, {"_id": 0}).sort("display_order", 1)
    plans = await cursor.to_list(length=50)
    enriched = []
    for p in plans:
        enriched.append({
            **p,
            "quote_monthly": calculate_quote(p, currency=ccy, billing_cycle="monthly", sites=sites_i),
            "quote_annual":  calculate_quote(p, currency=ccy, billing_cycle="annual",  sites=sites_i),
        })
    return {
        "brand": b,
        "currency": ccy,
        "sites": sites_i,
        "supported_currencies": list(SUPPORTED_CURRENCIES),
        "plans": enriched,
    }


# ── Indexes (called on startup) ─────────────────────────────────────


async def ensure_pricing_indexes() -> None:
    """Idempotent — creates the pricing collection indexes."""
    try:
        await db.pricing_plans.create_index([("brand", 1), ("display_order", 1)])
        await db.pricing_plans.create_index([("brand", 1), ("module_id", 1)], unique=True)
        await db.pricing_plans.create_index([("active", 1)])
        await db.pricing_audit_log.create_index([("plan_id", 1), ("at", -1)])
        await db.pricing_audit_log.create_index([("at", -1)])
    except Exception:
        logger.exception("ensure_pricing_indexes failed (non-fatal)")


# ── Internal — audit ────────────────────────────────────────────────


async def _audit(*, plan_id: str, before: dict | None, after: dict | None,
                 user_id: str | None, action: str) -> None:
    try:
        await db.pricing_audit_log.insert_one({
            "id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "action": action,
            "before": before,
            "after": after,
            "by": user_id,
            "at": _now(),
        })
    except Exception:
        # Audit failure must never break the main request.
        logger.exception("pricing audit log insert failed")
