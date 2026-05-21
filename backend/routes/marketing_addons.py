"""Marketing email-volume bolt-on packs (Iter 216g).

Customers buy a base Marketing module (£39/mo). To send more than the
included 5,000 emails/month they attach one or more add-on packs:

  email_boost_25k     +£19/mo  +25,000 emails
  email_boost_100k    +£59/mo  +100,000 emails
  email_boost_500k    +£199/mo +500,000 emails
  sms_pack_1k         +£29/mo  +1,000 SMS

Effective email cap = base 5,000 + sum(active pack credits).

Two collections:
- ``marketing_addons``       — catalog (master admin curates SKUs)
- ``marketing_org_addons``   — per-org attached packs (master admin grants /
                               removes; later upgradeable to Stripe sub items)

Endpoints
---------
* ``GET    /api/master-admin/marketing/addons``                — list catalog
* ``POST   /api/master-admin/marketing/addons``                — add SKU
* ``PUT    /api/master-admin/marketing/addons/{id}``           — edit SKU
* ``DELETE /api/master-admin/marketing/addons/{id}``           — remove SKU

* ``GET    /api/master-admin/marketing/orgs/{org}/addons``     — admin view
* ``POST   /api/master-admin/marketing/orgs/{org}/addons``     — admin attach
* ``DELETE /api/master-admin/marketing/orgs/{org}/addons/{id}``— admin detach

* ``GET    /api/marketing/addons/catalog``                     — tenant SKUs
* ``GET    /api/marketing/addons/mine``                        — tenant: my packs + effective limits
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from routes.auth import get_current_user
from routes.master_admin import require_master_admin
from utils.database import db
from utils.module_access import has_module

router = APIRouter(tags=["marketing-addons"])


# Base entitlement that every Marketing module subscriber gets.
BASE_INCLUDED_EMAILS = 5_000
BASE_INCLUDED_SMS = 0


DEFAULT_ADDONS: list[dict[str, Any]] = [
    {
        "code": "email_boost_25k",
        "name": "Email Boost · 25,000",
        "kind": "email",
        "monthly_price_pence": 1_900,
        "included_emails": 25_000,
        "included_sms": 0,
        "active": True,
        "sort_order": 1,
    },
    {
        "code": "email_boost_100k",
        "name": "Email Boost · 100,000",
        "kind": "email",
        "monthly_price_pence": 5_900,
        "included_emails": 100_000,
        "included_sms": 0,
        "active": True,
        "sort_order": 2,
    },
    {
        "code": "email_boost_500k",
        "name": "Email Boost · 500,000",
        "kind": "email",
        "monthly_price_pence": 19_900,
        "included_emails": 500_000,
        "included_sms": 0,
        "active": True,
        "sort_order": 3,
    },
    {
        "code": "sms_pack_1k",
        "name": "SMS Pack · 1,000",
        "kind": "sms",
        "monthly_price_pence": 2_900,
        "included_emails": 0,
        "included_sms": 1_000,
        "active": True,
        "sort_order": 10,
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _seed_catalog_if_empty() -> int:
    """Seed the default Email + SMS bolt-on packs.

    Iter 216h275 — also re-seeds when every existing row has been
    deactivated. The previous "count > 0 → skip" check meant that
    after a master admin had deactivated all packs (or after a
    partial restore left only inactive rows behind), the tenant
    catalog endpoint kept returning an empty list AND the seeder
    wouldn't re-populate the defaults. Production "No packs
    available right now" repro path.
    """
    active_count = await db.marketing_addons.count_documents({"active": True})
    if active_count > 0:
        return 0
    # Only seed defaults that aren't already present (by code) — keeps
    # custom packs the master admin might have added intact.
    existing_codes = {
        r.get("code") async for r in db.marketing_addons.find({}, {"_id": 0, "code": 1})
    }
    docs = [
        {**a, "id": str(uuid.uuid4()), "created_at": _now()}
        for a in DEFAULT_ADDONS
        if a["code"] not in existing_codes
    ]
    if docs:
        await db.marketing_addons.insert_many(docs)
    return len(docs)


def _normalise_addon(body: dict) -> dict:
    code = (body.get("code") or "").strip().lower()[:60]
    if not code:
        raise HTTPException(400, "code is required")
    name = (body.get("name") or "").strip()[:120] or code
    kind = (body.get("kind") or "email").strip().lower()
    if kind not in ("email", "sms"):
        raise HTTPException(400, "kind must be 'email' or 'sms'")
    return {
        "code": code,
        "name": name,
        "kind": kind,
        "monthly_price_pence": max(0, int(body.get("monthly_price_pence") or 0)),
        "included_emails": max(0, int(body.get("included_emails") or 0)),
        "included_sms": max(0, int(body.get("included_sms") or 0)),
        "active": bool(body.get("active", True)),
        "sort_order": int(body.get("sort_order") or 0),
    }


# ── Master admin: catalogue CRUD ──────────────────────────────────────


@router.get("/master-admin/marketing/addons")
async def list_addons_admin(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    seeded = await _seed_catalog_if_empty()
    rows = (
        await db.marketing_addons.find({}, {"_id": 0})
        .sort([("sort_order", 1), ("monthly_price_pence", 1)])
        .to_list(length=200)
    )
    return {"rows": rows, "count": len(rows), "seeded": seeded}


@router.post("/master-admin/marketing/addons")
async def add_addon(body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    data = _normalise_addon(body)
    if await db.marketing_addons.find_one({"code": data["code"]}, {"_id": 1}):
        raise HTTPException(409, f"add-on with code '{data['code']}' already exists")
    row = {**data, "id": str(uuid.uuid4()), "created_at": _now()}
    await db.marketing_addons.insert_one(row.copy())
    row.pop("_id", None)
    return {"ok": True, "row": row}


@router.put("/master-admin/marketing/addons/{addon_id}")
async def update_addon(
    addon_id: str = Path(..., min_length=1),
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    existing = await db.marketing_addons.find_one({"id": addon_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Add-on not found")
    patch = _normalise_addon({**existing, **body})
    # code is immutable on update to keep entitlement references stable
    patch["code"] = existing["code"]
    await db.marketing_addons.update_one(
        {"id": addon_id}, {"$set": {**patch, "updated_at": _now()}},
    )
    row = await db.marketing_addons.find_one({"id": addon_id}, {"_id": 0})
    return {"ok": True, "row": row}


@router.delete("/master-admin/marketing/addons/{addon_id}")
async def delete_addon(
    addon_id: str = Path(..., min_length=1),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    res = await db.marketing_addons.delete_one({"id": addon_id})
    if not res.deleted_count:
        raise HTTPException(404, "Add-on not found")
    return {"ok": True}


# ── Master admin: per-org attach / detach ─────────────────────────────


async def _resolve_addon(addon_ref: str) -> dict:
    """Look up by id OR code."""
    addon = await db.marketing_addons.find_one(
        {"$or": [{"id": addon_ref}, {"code": addon_ref}]},
        {"_id": 0},
    )
    if not addon:
        raise HTTPException(404, f"Add-on '{addon_ref}' not found in catalog")
    if not addon.get("active"):
        raise HTTPException(400, f"Add-on '{addon['code']}' is disabled")
    return addon


async def _list_org_addons(org_id: str) -> list[dict]:
    rows = await db.marketing_org_addons.find(
        {"organization_id": org_id, "active": True}, {"_id": 0},
    ).sort("attached_at", 1).to_list(length=200)
    # decorate with current catalog data
    if rows:
        codes = list({r["code"] for r in rows})
        catalog = {
            a["code"]: a
            for a in await db.marketing_addons.find({"code": {"$in": codes}}, {"_id": 0}).to_list(200)
        }
        for r in rows:
            cat = catalog.get(r["code"], {})
            r["name"] = cat.get("name", r["code"])
            r["kind"] = cat.get("kind", "email")
            r["monthly_price_pence"] = cat.get("monthly_price_pence", 0)
            r["included_emails"] = cat.get("included_emails", 0)
            r["included_sms"] = cat.get("included_sms", 0)
    return rows


def _effective_limits(packs: list[dict]) -> dict:
    extra_emails = sum(int(p.get("included_emails") or 0) for p in packs)
    extra_sms = sum(int(p.get("included_sms") or 0) for p in packs)
    extra_cost = sum(int(p.get("monthly_price_pence") or 0) for p in packs)
    return {
        "base_included_emails": BASE_INCLUDED_EMAILS,
        "base_included_sms": BASE_INCLUDED_SMS,
        "addon_emails": extra_emails,
        "addon_sms": extra_sms,
        "monthly_emails": BASE_INCLUDED_EMAILS + extra_emails,
        "monthly_sms": BASE_INCLUDED_SMS + extra_sms,
        "addon_monthly_cost_pence": extra_cost,
    }


@router.get("/master-admin/marketing/orgs/{organization_id}/addons")
async def admin_list_org_addons(
    organization_id: str = Path(..., min_length=1),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    packs = await _list_org_addons(organization_id)
    return {"rows": packs, "limits": _effective_limits(packs)}


@router.post("/master-admin/marketing/orgs/{organization_id}/addons")
async def admin_attach_addon(
    organization_id: str = Path(..., min_length=1),
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    addon = await _resolve_addon((body.get("code") or body.get("addon_id") or "").strip())
    org = await db.organizations.find_one({"id": organization_id}, {"_id": 1})
    if not org:
        raise HTTPException(404, "Organisation not found")
    row = {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "code": addon["code"],
        "active": True,
        "attached_at": _now(),
        "attached_by": user.get("email") or user.get("id"),
        "notes": (body.get("notes") or "").strip()[:300],
    }
    await db.marketing_org_addons.insert_one(row.copy())
    row.pop("_id", None)
    return {"ok": True, "row": row}


@router.delete("/master-admin/marketing/orgs/{organization_id}/addons/{attachment_id}")
async def admin_detach_addon(
    organization_id: str = Path(..., min_length=1),
    attachment_id: str = Path(..., min_length=1),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    res = await db.marketing_org_addons.update_one(
        {"id": attachment_id, "organization_id": organization_id},
        {"$set": {"active": False, "detached_at": _now(), "detached_by": user.get("email") or user.get("id")}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Attachment not found")
    return {"ok": True}


# ── Tenant-facing reads ───────────────────────────────────────────────


@router.get("/marketing/addons/catalog")
async def tenant_catalog(user: dict = Depends(get_current_user)):
    """Read-only catalog of available packs.

    Master admins (no `organization_id`) get the catalog without the
    module-access gate so the Marketing module preview works correctly.
    """
    org_id = user.get("organization_id")
    if org_id:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        if org and not has_module(user, org, "marketing") and not user.get("is_master_admin"):
            raise HTTPException(403, "Marketing module not active for this organisation")
    await _seed_catalog_if_empty()
    rows = (
        await db.marketing_addons.find({"active": True}, {"_id": 0, "created_at": 0})
        .sort([("sort_order", 1), ("monthly_price_pence", 1)])
        .to_list(length=100)
    )
    return {"rows": rows, "count": len(rows), "base": {
        "included_emails": BASE_INCLUDED_EMAILS,
        "included_sms": BASE_INCLUDED_SMS,
    }}


@router.get("/marketing/addons/mine")
async def tenant_my_addons(user: dict = Depends(get_current_user)):
    """Show the operator their attached packs + effective email cap.

    Read-only by design — for now, attaching new packs is master-admin
    only (until the Stripe sub-line integration ships in a follow-up).
    Master admin preview returns base limits with no attached packs so
    the panel still renders cleanly.
    """
    org_id = user.get("organization_id")
    if not org_id:
        # Master-admin preview path — no tenant context.
        return {
            "rows": [],
            "limits": _effective_limits([]),
            "usage": {"emails_sent": 0, "sms_sent": 0, "ai_generations": 0, "contacts_count": 0},
        }
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organization not found")
    if not has_module(user, org, "marketing") and not user.get("is_master_admin"):
        raise HTTPException(403, "Marketing module not active for this organisation")
    packs = await _list_org_addons(org_id)
    limits = _effective_limits(packs)
    sub = await db.marketing_subscriptions.find_one({"organization_id": org_id}, {"_id": 0})
    usage = (sub or {}).get("usage_this_period") or {"emails_sent": 0, "sms_sent": 0}
    return {"rows": packs, "limits": limits, "usage": usage}


__all__ = ["router"]
