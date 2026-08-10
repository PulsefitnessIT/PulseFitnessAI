"""Dealer Warranty Parts — Phase 1 foundation.

Global dealer spare-parts ecosystem that lives under Service Desk → Parts.
This module EXTENDS the existing platform and never duplicates core records:

  • Parts       → reuses the `svc_parts` catalogue (read-only lookups here).
  • Companies   → a dealer links to an existing CRM company via `company_id`.
  • Stock       → its own dealer-side ledger (`dealer_stock_movements`) that
                  mirrors the internal `svc_part_movements` pattern but tracks
                  parts held at remote *dealer* stores, not Pulse warehouses.

Collections owned here (all org-scoped by the Pulse Fitness service org):
  • dealer_parts_dealers          — dealer profile (links CRM company)
  • dealer_parts_settings         — allowance % config (global default)
  • dealer_parts_orders           — imported dealer orders/invoices + allowance
  • dealer_parts_allocations      — warranty parts packs (items embedded)
  • dealer_remote_stores          — dealer stores (main / van / warehouse)
  • dealer_remote_store_stock     — per-part stock in a remote store
  • dealer_stock_movements        — immutable stock ledger
  • dealer_parts_audit_events     — immutable audit trail

Phase 1 scope: dealers, order/invoice import + allowance calc, allocation
workflow (recommend → approve → dispatch → receive), remote stores + stock
ledger, dashboard rollups, settings, audit.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.security_plus import safe_regex, safe_regex_exact

async def require_staff(user=Depends(get_current_user)):
    """Reject dealer-portal sub-users from Pulse admin endpoints (defense-in-depth)."""
    if (user.get("role") or "").lower() == "dealer_user":
        raise HTTPException(403, "Dealer accounts cannot access this area")
    return user


router = APIRouter(prefix="/dealer-parts", tags=["Dealer Warranty Parts"], dependencies=[Depends(require_staff)])

DEALERS = "dealer_parts_dealers"
SETTINGS = "dealer_parts_settings"
ORDERS = "dealer_parts_orders"
ALLOCATIONS = "dealer_parts_allocations"
STORES = "dealer_remote_stores"
STORE_STOCK = "dealer_remote_store_stock"
MOVEMENTS = "dealer_stock_movements"
AUDIT = "dealer_parts_audit_events"

DEFAULT_PERCENTAGE = 2.5


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _can_manage(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    return bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or role in ("owner", "manager", "master_admin", "pulse_master_admin")
    )


def _strip(doc):
    if isinstance(doc, dict):
        doc.pop("_id", None)
    return doc


async def _audit(org: str, user: dict, action: str, **fields) -> None:
    await db[AUDIT].insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "action": action,
        "user_id": user.get("id"),
        "user_name": user.get("full_name") or user.get("email"),
        "at": _now(),
        **fields,
    })


async def _get_settings(org: str) -> dict:
    s = await db[SETTINGS].find_one({"organization_id": org}, {"_id": 0})
    if not s:
        s = {
            "organization_id": org,
            "enabled": True,
            "default_percentage": DEFAULT_PERCENTAGE,
            "approval_threshold": 5000.0,
            "over_allowance_approval_required": True,
            "require_receipt_confirmation": True,
            "ai_recommendations_enabled": True,
            "multi_currency_enabled": True,
            "enable_monitoring_agent": True,
            "failure_alert_threshold": 5,
            "usage_spike_factor": 2.0,
            "monitoring_window_days": 90,
            "updated_at": _now(),
        }
        await db[SETTINGS].insert_one(dict(s))
    return _strip(s)


async def _resolve_percentage(org: str, dealer: dict | None, override) -> float:
    if override is not None:
        try:
            return float(override)
        except (TypeError, ValueError):
            pass
    if dealer and dealer.get("default_percentage") is not None:
        return float(dealer["default_percentage"])
    s = await _get_settings(org)
    return float(s.get("default_percentage") or DEFAULT_PERCENTAGE)


# ─────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    return await _get_settings(_of(user))


@router.put("/settings")
async def update_settings(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    if not _can_manage(user):
        raise HTTPException(403, "Manager access required")
    await _get_settings(org)
    allowed = {
        "enabled", "default_percentage", "approval_threshold",
        "over_allowance_approval_required", "require_receipt_confirmation",
        "ai_recommendations_enabled", "multi_currency_enabled",
        "allow_dealer_portal_usage", "allow_engineer_app_usage",
        "require_photo_evidence", "enable_monitoring_agent",
        "failure_alert_threshold", "usage_spike_factor", "monitoring_window_days",
    }
    patch = {k: v for k, v in data.items() if k in allowed}
    patch["updated_at"] = _now()
    await db[SETTINGS].update_one({"organization_id": org}, {"$set": patch})
    await _audit(org, user, "settings_updated", changes=list(patch.keys()))
    return await _get_settings(org)


# ─────────────────────────────────────────────────────────────────
# Dealers
# ─────────────────────────────────────────────────────────────────

@router.get("/dealers")
async def list_dealers(
    search: str = Query(""),
    country: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
):
    org = _of(user)
    q: dict = {"organization_id": org}
    if country:
        q["country"] = country
    if search:
        q["$or"] = [{"name": safe_regex(search)}, {"country": safe_regex(search)}]
    rows = await db[DEALERS].find(q, {"_id": 0}).sort([("name", 1)]).limit(limit).to_list(limit)
    return {"dealers": rows, "count": len(rows)}


@router.post("/dealers")
async def create_dealer(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    company_id = data.get("company_id") or None
    # Anti-duplication: link to existing dealer if same company or same name.
    existing = None
    if company_id:
        existing = await db[DEALERS].find_one({"organization_id": org, "company_id": company_id})
    if not existing:
        existing = await db[DEALERS].find_one(
            {"organization_id": org, "name": safe_regex_exact(name)}
        )
    if existing:
        return _strip(existing)
    dealer = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "company_id": company_id,
        "name": name,
        "country": (data.get("country") or "").strip(),
        "region": (data.get("region") or "").strip(),
        "currency": (data.get("currency") or "GBP").strip().upper(),
        "account_manager": (data.get("account_manager") or "").strip(),
        "default_percentage": data.get("default_percentage"),
        "agreement": (data.get("agreement") or "").strip(),
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[DEALERS].insert_one(dict(dealer))
    await _audit(org, user, "dealer_created", dealer_id=dealer["id"], dealer_name=name)
    return _strip(dealer)


async def _dealer_or_404(org: str, dealer_id: str) -> dict:
    d = await db[DEALERS].find_one({"organization_id": org, "id": dealer_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dealer not found")
    return d


@router.get("/dealers/{dealer_id}")
async def get_dealer(dealer_id: str, user=Depends(get_current_user)):
    org = _of(user)
    dealer = await _dealer_or_404(org, dealer_id)
    orders = await db[ORDERS].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
    allocs = await db[ALLOCATIONS].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
    stores = await db[STORES].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).to_list(100)
    stock = await db[STORE_STOCK].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).to_list(2000)
    stock_value = sum((s.get("qty_on_hand") or 0) * (s.get("unit_value") or 0) for s in stock)
    allowance_total = sum(o.get("allowance") or 0 for o in orders)
    approved_value = sum(a.get("approved_value") or 0 for a in allocs if a.get("status") not in ("draft", "cancelled"))
    # Iter 282 — invoice allocation log: every invoice this dealer has had
    # parts allocated against (deduped by invoice number, newest first).
    invoices = []
    seen_inv = set()
    for a in allocs:
        ref = (a.get("invoice_reference") or "").strip()
        if not ref or a.get("status") == "cancelled":
            continue
        key = ref.upper().replace(" ", "")
        if key in seen_inv:
            continue
        seen_inv.add(key)
        invoices.append({
            "invoice_reference": ref,
            "allocation_id": a.get("id"),
            "status": a.get("status"),
            "value": a.get("recommended_value") or a.get("approved_value") or 0,
            "parts_count": len(a.get("items") or []),
            "allocated_at": a.get("created_at"),
        })
    return {
        "dealer": dealer,
        "orders": orders,
        "allocations": allocs,
        "invoices": invoices,
        "stores": stores,
        "stock": stock,
        "rollup": {
            "orders_count": len(orders),
            "allocations_count": len(allocs),
            "invoices_count": len(invoices),
            "stores_count": len(stores),
            "stock_lines": len(stock),
            "stock_value": round(stock_value, 2),
            "allowance_total": round(allowance_total, 2),
            "approved_value": round(approved_value, 2),
            "allowance_remaining": round(allowance_total - approved_value, 2),
        },
    }


@router.patch("/dealers/{dealer_id}")
async def update_dealer(dealer_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    await _dealer_or_404(org, dealer_id)
    allowed = {"name", "country", "region", "currency", "account_manager",
               "default_percentage", "agreement", "active", "company_id"}
    patch = {k: v for k, v in data.items() if k in allowed}
    patch["updated_at"] = _now()
    await db[DEALERS].update_one({"organization_id": org, "id": dealer_id}, {"$set": patch})
    await _audit(org, user, "dealer_updated", dealer_id=dealer_id, changes=list(patch.keys()))
    return await _dealer_or_404(org, dealer_id)


# ─────────────────────────────────────────────────────────────────
# Dealer-setup lookups — CRM companies + internal staff (main JWT).
# Mirrors the CRM/staff APIs but on the dealer-parts (Service Desk) token
# so the "Set up a dealer" form can populate dropdowns without a separate
# CRM login.
# ─────────────────────────────────────────────────────────────────

@router.get("/crm-companies")
async def list_crm_companies_for_dealers(search: str = "", limit: int = Query(200), user=Depends(get_current_user)):
    org = _of(user)
    q = {"organization_id": org}
    if search:
        q["name"] = safe_regex(search)
    rows = await db.crm_companies.find(q, {"_id": 0, "id": 1, "name": 1, "country": 1, "industry": 1}).sort("name", 1).limit(limit).to_list(limit)
    return {"companies": rows, "count": len(rows)}


@router.post("/crm-companies")
async def create_crm_company_for_dealer(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    existing = await db.crm_companies.find_one({"organization_id": org, "name": safe_regex_exact(name)}, {"_id": 0})
    if existing:
        return {"id": existing["id"], "name": existing["name"]}
    company = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "name": name,
        "industry": "Fitness Equipment Dealer",
        "country": (data.get("country") or "").strip(),
        "created_by": user.get("id"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm_companies.insert_one(dict(company))
    await _audit(org, user, "crm_company_created_from_dealer", company_id=company["id"], name=name)
    return {"id": company["id"], "name": company["name"]}


@router.get("/staff")
async def list_internal_staff(user=Depends(get_current_user)):
    """Internal Pulse Fitness Ltd staff — used for the Account Manager dropdown."""
    org = _of(user)
    rows = await db.users.find(
        {"organization_id": org, "disabled": {"$ne": True}, "role": {"$ne": "dealer_user"}},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1},
    ).sort("full_name", 1).to_list(500)
    return {"staff": rows, "count": len(rows)}



# ─────────────────────────────────────────────────────────────────
# Orders / Invoices + allowance calculation
# ─────────────────────────────────────────────────────────────────

@router.get("/orders")
async def list_orders(
    dealer_id: str = Query(""),
    limit: int = Query(200, ge=1, le=500),
    user=Depends(get_current_user),
):
    org = _of(user)
    q: dict = {"organization_id": org}
    if dealer_id:
        q["dealer_id"] = dealer_id
    rows = await db[ORDERS].find(q, {"_id": 0}).sort([("created_at", -1)]).limit(limit).to_list(limit)
    return {"orders": rows, "count": len(rows)}


@router.post("/orders")
async def create_order(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    dealer_id = data.get("dealer_id")
    if not dealer_id:
        raise HTTPException(400, "dealer_id required")
    dealer = await _dealer_or_404(org, dealer_id)
    order_ref = (data.get("order_reference") or "").strip()
    # Anti-duplication: same dealer + order_reference already imported.
    if order_ref:
        dup = await db[ORDERS].find_one({"organization_id": org, "dealer_id": dealer_id, "order_reference": order_ref})
        if dup:
            return _strip(dup)
    lines = []
    total = 0.0
    for ln in (data.get("lines") or []):
        qty = float(ln.get("quantity") or 0)
        unit = float(ln.get("unit_value") or 0)
        line_total = round(qty * unit, 2)
        total += line_total
        lines.append({
            "id": str(uuid.uuid4()),
            "machine_model": (ln.get("machine_model") or "").strip(),
            "machine_category": (ln.get("machine_category") or "").strip(),
            "quantity": qty,
            "unit_value": unit,
            "line_total": line_total,
        })
    order_value = float(data.get("order_value") or total or 0)
    percentage = await _resolve_percentage(org, dealer, data.get("spare_parts_percentage"))
    allowance = round(order_value * percentage / 100.0, 2)
    order = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "dealer_id": dealer_id,
        "dealer_name": dealer["name"],
        "order_reference": order_ref,
        "invoice_reference": (data.get("invoice_reference") or "").strip(),
        "order_date": data.get("order_date") or "",
        "invoice_date": data.get("invoice_date") or "",
        "currency": (data.get("currency") or dealer.get("currency") or "GBP").upper(),
        "order_value": round(order_value, 2),
        "spare_parts_percentage": percentage,
        "allowance": allowance,
        "exchange_rate": data.get("exchange_rate"),
        "lines": lines,
        "notes": (data.get("notes") or "").strip(),
        "source_document_url": data.get("source_document_url") or "",
        "status": "imported",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[ORDERS].insert_one(dict(order))
    await _audit(org, user, "order_imported", dealer_id=dealer_id, order_id=order["id"],
                 order_value=order_value, allowance=allowance)
    return _strip(order)


@router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    org = _of(user)
    o = await db[ORDERS].find_one({"organization_id": org, "id": order_id}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Order not found")
    return o


# ─────────────────────────────────────────────────────────────────
# Allocations (warranty parts packs)
# ─────────────────────────────────────────────────────────────────

ALLOC_STATUSES = [
    "draft", "awaiting_approval", "approved", "dispatched",
    "received", "partially_received", "completed", "cancelled",
]


def _alloc_value(items: list) -> float:
    return round(sum(float(i.get("quantity") or 0) * float(i.get("unit_value") or 0) for i in items), 2)


@router.get("/allocations")
async def list_allocations(
    dealer_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(200, ge=1, le=500),
    user=Depends(get_current_user),
):
    org = _of(user)
    q: dict = {"organization_id": org}
    if dealer_id:
        q["dealer_id"] = dealer_id
    if status:
        q["status"] = status
    rows = await db[ALLOCATIONS].find(q, {"_id": 0}).sort([("created_at", -1)]).limit(limit).to_list(limit)
    return {"allocations": rows, "count": len(rows)}


@router.post("/allocations")
async def create_allocation(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    dealer_id = data.get("dealer_id")
    order_id = data.get("order_id")
    if not dealer_id:
        raise HTTPException(400, "dealer_id required")
    dealer = await _dealer_or_404(org, dealer_id)
    order = None
    if order_id:
        order = await db[ORDERS].find_one({"organization_id": org, "id": order_id}, {"_id": 0})
    # Iter 282 — capture the source invoice number so Pulse Fitness has a log
    # of which invoices have had parts allocated, and HARD-BLOCK re-using an
    # invoice already allocated anywhere in the org (avoids double allocation).
    invoice_reference = (data.get("invoice_reference") or (order or {}).get("invoice_reference") or "").strip()
    invoice_norm = invoice_reference.upper().replace(" ", "")
    if invoice_norm:
        dup = await db[ALLOCATIONS].find_one(
            {"organization_id": org, "invoice_reference_norm": invoice_norm,
             "status": {"$ne": "cancelled"}},
            {"_id": 0, "dealer_name": 1, "created_at": 1},
        )
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Invoice {invoice_reference} has already been allocated to {dup.get('dealer_name') or 'another dealer'}. Each invoice can only be used once.",
            )
    items = []
    for it in (data.get("items") or []):
        items.append({
            "id": str(uuid.uuid4()),
            "part_sku": (it.get("part_sku") or "").strip().upper(),
            "part_name": (it.get("part_name") or "").strip(),
            "machine_model": (it.get("machine_model") or "").strip(),
            "quantity": float(it.get("quantity") or 0),
            "unit_value": float(it.get("unit_value") or 0),
            "reason": (it.get("reason") or "").strip(),
            "status": "recommended",
        })
    value = _alloc_value(items)
    allowance = float(order.get("allowance") or 0) if order else 0.0
    alloc = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "dealer_id": dealer_id,
        "dealer_name": dealer["name"],
        "order_id": order_id,
        "order_reference": order.get("order_reference") if order else "",
        "invoice_reference": invoice_reference,
        "invoice_reference_norm": invoice_norm,
        "items": items,
        "recommended_value": value,
        "approved_value": 0.0,
        "allowance": allowance,
        "allowance_remaining": round(allowance - value, 2),
        "over_allowance": value > allowance if allowance else False,
        "status": "draft",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[ALLOCATIONS].insert_one(dict(alloc))
    await _audit(org, user, "allocation_created", dealer_id=dealer_id, allocation_id=alloc["id"], value=value)
    return _strip(alloc)


async def _alloc_or_404(org: str, alloc_id: str) -> dict:
    a = await db[ALLOCATIONS].find_one({"organization_id": org, "id": alloc_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Allocation not found")
    return a


@router.get("/allocations/{alloc_id}")
async def get_allocation(alloc_id: str, user=Depends(get_current_user)):
    return await _alloc_or_404(_of(user), alloc_id)


@router.patch("/allocations/{alloc_id}")
async def update_allocation(alloc_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    alloc = await _alloc_or_404(org, alloc_id)
    if alloc["status"] not in ("draft", "awaiting_approval"):
        raise HTTPException(400, "Only draft/awaiting allocations can be edited")
    patch: dict = {"updated_at": _now()}
    if "items" in data:
        items = []
        for it in data["items"]:
            items.append({
                "id": it.get("id") or str(uuid.uuid4()),
                "part_sku": (it.get("part_sku") or "").strip().upper(),
                "part_name": (it.get("part_name") or "").strip(),
                "machine_model": (it.get("machine_model") or "").strip(),
                "quantity": float(it.get("quantity") or 0),
                "unit_value": float(it.get("unit_value") or 0),
                "reason": (it.get("reason") or "").strip(),
                "status": it.get("status") or "recommended",
            })
        value = _alloc_value(items)
        patch["items"] = items
        patch["recommended_value"] = value
        patch["allowance_remaining"] = round((alloc.get("allowance") or 0) - value, 2)
        patch["over_allowance"] = value > (alloc.get("allowance") or 0) if alloc.get("allowance") else False
    await db[ALLOCATIONS].update_one({"organization_id": org, "id": alloc_id}, {"$set": patch})
    await _audit(org, user, "allocation_updated", allocation_id=alloc_id, changes=list(patch.keys()))
    return await _alloc_or_404(org, alloc_id)


@router.post("/allocations/{alloc_id}/submit")
async def submit_allocation(alloc_id: str, user=Depends(get_current_user)):
    org = _of(user)
    alloc = await _alloc_or_404(org, alloc_id)
    if alloc["status"] != "draft":
        raise HTTPException(400, "Only draft allocations can be submitted")
    await db[ALLOCATIONS].update_one({"organization_id": org, "id": alloc_id},
                                     {"$set": {"status": "awaiting_approval", "updated_at": _now()}})
    await _audit(org, user, "allocation_submitted", allocation_id=alloc_id)
    return await _alloc_or_404(org, alloc_id)


@router.post("/allocations/{alloc_id}/approve")
async def approve_allocation(alloc_id: str, data: dict = None, user=Depends(get_current_user)):
    org = _of(user)
    alloc = await _alloc_or_404(org, alloc_id)
    if alloc["status"] not in ("draft", "awaiting_approval"):
        raise HTTPException(400, "Allocation is not awaiting approval")
    settings = await _get_settings(org)
    value = _alloc_value(alloc.get("items") or [])
    over = bool(alloc.get("over_allowance"))
    threshold = float(settings.get("approval_threshold") or 0)
    needs_manager = (over and settings.get("over_allowance_approval_required")) or (value > threshold and threshold > 0)
    if needs_manager and not _can_manage(user):
        raise HTTPException(403, "Manager approval required (over allowance / above threshold)")
    reason = (data or {}).get("reason", "")
    await db[ALLOCATIONS].update_one(
        {"organization_id": org, "id": alloc_id},
        {"$set": {"status": "approved", "approved_value": value,
                  "approved_by": user.get("full_name") or user.get("email"),
                  "approval_reason": reason, "approved_at": _now(), "updated_at": _now()}},
    )
    await _audit(org, user, "allocation_approved", allocation_id=alloc_id, value=value,
                 over_allowance=over, reason=reason)
    # Central financial telemetry — parts allocation approval releases spend.
    try:
        from utils.security_events import log_security_event, SEV_WARNING
        await log_security_event(
            "parts_allocation_approved", user=user, severity=SEV_WARNING,
            resource_type="parts_allocation", resource_id=alloc_id, action="approve",
            result="allowed", tenant_id=org,
            detail=f"value={value} over_allowance={over}",
        )
    except Exception:
        pass
    return await _alloc_or_404(org, alloc_id)


async def _upsert_store_stock(org: str, store: dict, item: dict, *, in_transit_delta=0.0, on_hand_delta=0.0):
    key = {"organization_id": org, "store_id": store["id"], "part_sku": item["part_sku"]}
    existing = await db[STORE_STOCK].find_one(key)
    if not existing:
        doc = {
            "id": str(uuid.uuid4()),
            "organization_id": org,
            "dealer_id": store["dealer_id"],
            "store_id": store["id"],
            "store_name": store["name"],
            "part_sku": item["part_sku"],
            "part_name": item.get("part_name") or "",
            "qty_on_hand": max(0.0, on_hand_delta),
            "qty_in_transit": max(0.0, in_transit_delta),
            "unit_value": item.get("unit_value") or 0,
            "min_stock": 0,
            "recommended_stock": 0,
            "last_received": _now() if on_hand_delta else None,
            "updated_at": _now(),
        }
        await db[STORE_STOCK].insert_one(doc)
    else:
        inc = {}
        if in_transit_delta:
            inc["qty_in_transit"] = in_transit_delta
        if on_hand_delta:
            inc["qty_on_hand"] = on_hand_delta
        upd = {"$set": {"updated_at": _now(), "part_name": item.get("part_name") or existing.get("part_name")}}
        if inc:
            upd["$inc"] = inc
        if on_hand_delta:
            upd["$set"]["last_received"] = _now()
        await db[STORE_STOCK].update_one(key, upd)


async def _movement(org: str, user: dict, *, dealer_id, store_id, store_name, mtype, part_sku,
                    part_name, qty, from_loc="", to_loc="", ref="", reason="", allocation_id=""):
    mv = {
        "id": str(uuid.uuid4()),
        "reference": ref or f"MV-{uuid.uuid4().hex[:8].upper()}",
        "organization_id": org,
        "dealer_id": dealer_id,
        "store_id": store_id,
        "store_name": store_name,
        "movement_type": mtype,
        "part_sku": part_sku,
        "part_name": part_name,
        "quantity": qty,
        "from_location": from_loc,
        "to_location": to_loc,
        "allocation_id": allocation_id,
        "reason": reason,
        "user_id": user.get("id"),
        "user_name": user.get("full_name") or user.get("email"),
        "at": _now(),
    }
    await db[MOVEMENTS].insert_one(dict(mv))
    return _strip(mv)


@router.post("/allocations/{alloc_id}/dispatch")
async def dispatch_allocation(alloc_id: str, data: dict = None, user=Depends(get_current_user)):
    org = _of(user)
    alloc = await _alloc_or_404(org, alloc_id)
    if alloc["status"] != "approved":
        raise HTTPException(400, "Allocation must be approved before dispatch")
    data = data or {}
    store_id = data.get("store_id")
    # Resolve destination remote store (create a default 'Main Dealer Store' if none).
    store = None
    if store_id:
        store = await db[STORES].find_one({"organization_id": org, "id": store_id}, {"_id": 0})
    if not store:
        store = await db[STORES].find_one({"organization_id": org, "dealer_id": alloc["dealer_id"]}, {"_id": 0})
    if not store:
        store = {
            "id": str(uuid.uuid4()),
            "organization_id": org,
            "dealer_id": alloc["dealer_id"],
            "dealer_name": alloc.get("dealer_name"),
            "name": "Main Dealer Store",
            "store_type": "main",
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db[STORES].insert_one(dict(store))
    for it in (alloc.get("items") or []):
        if it.get("status") == "removed" or not it.get("part_sku"):
            continue
        qty = float(it.get("quantity") or 0)
        if qty <= 0:
            continue
        await _upsert_store_stock(org, store, it, in_transit_delta=qty)
        await _movement(org, user, dealer_id=alloc["dealer_id"], store_id=store["id"],
                        store_name=store["name"], mtype="dispatched_to_dealer",
                        part_sku=it["part_sku"], part_name=it.get("part_name") or "",
                        qty=qty, from_loc="pulse_warehouse", to_loc=store["name"],
                        allocation_id=alloc_id)
    await db[ALLOCATIONS].update_one(
        {"organization_id": org, "id": alloc_id},
        {"$set": {"status": "dispatched", "store_id": store["id"],
                  "dispatched_at": _now(), "updated_at": _now()}},
    )
    await _audit(org, user, "allocation_dispatched", allocation_id=alloc_id, store_id=store["id"])
    return await _alloc_or_404(org, alloc_id)


@router.post("/allocations/{alloc_id}/receive")
async def receive_allocation(alloc_id: str, data: dict = None, user=Depends(get_current_user)):
    org = _of(user)
    alloc = await _alloc_or_404(org, alloc_id)
    if alloc["status"] not in ("dispatched", "partially_received"):
        raise HTTPException(400, "Allocation must be dispatched before receipt")
    store = await db[STORES].find_one({"organization_id": org, "id": alloc.get("store_id")}, {"_id": 0})
    if not store:
        raise HTTPException(400, "Destination store missing")
    for it in (alloc.get("items") or []):
        if it.get("status") == "removed" or not it.get("part_sku"):
            continue
        qty = float(it.get("quantity") or 0)
        if qty <= 0:
            continue
        await _upsert_store_stock(org, store, it, in_transit_delta=-qty, on_hand_delta=qty)
        await _movement(org, user, dealer_id=alloc["dealer_id"], store_id=store["id"],
                        store_name=store["name"], mtype="received_by_dealer",
                        part_sku=it["part_sku"], part_name=it.get("part_name") or "",
                        qty=qty, from_loc="in_transit", to_loc=store["name"],
                        allocation_id=alloc_id)
    await db[ALLOCATIONS].update_one(
        {"organization_id": org, "id": alloc_id},
        {"$set": {"status": "completed", "received_at": _now(), "updated_at": _now()}},
    )
    await _audit(org, user, "allocation_received", allocation_id=alloc_id)
    return await _alloc_or_404(org, alloc_id)


# ─────────────────────────────────────────────────────────────────
# Remote stores + stock
# ─────────────────────────────────────────────────────────────────

@router.get("/stores")
async def list_stores(dealer_id: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    q: dict = {"organization_id": org}
    if dealer_id:
        q["dealer_id"] = dealer_id
    rows = await db[STORES].find(q, {"_id": 0}).sort([("name", 1)]).to_list(500)
    return {"stores": rows, "count": len(rows)}


@router.post("/stores")
async def create_store(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    dealer_id = data.get("dealer_id")
    name = (data.get("name") or "").strip()
    if not dealer_id or not name:
        raise HTTPException(400, "dealer_id and name required")
    dealer = await _dealer_or_404(org, dealer_id)
    existing = await db[STORES].find_one({"organization_id": org, "dealer_id": dealer_id, "name": safe_regex_exact(name)})
    if existing:
        return _strip(existing)
    store = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "dealer_id": dealer_id,
        "dealer_name": dealer["name"],
        "name": name,
        "store_type": (data.get("store_type") or "main").strip(),
        "country": (data.get("country") or dealer.get("country") or "").strip(),
        "region": (data.get("region") or dealer.get("region") or "").strip(),
        "address": (data.get("address") or "").strip(),
        "contact": (data.get("contact") or "").strip(),
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[STORES].insert_one(dict(store))
    await _audit(org, user, "store_created", dealer_id=dealer_id, store_id=store["id"])
    return _strip(store)


@router.get("/stores/{store_id}/stock")
async def get_store_stock(store_id: str, user=Depends(get_current_user)):
    org = _of(user)
    store = await db[STORES].find_one({"organization_id": org, "id": store_id}, {"_id": 0})
    if not store:
        raise HTTPException(404, "Store not found")
    stock = await db[STORE_STOCK].find({"organization_id": org, "store_id": store_id}, {"_id": 0}).to_list(2000)
    for s in stock:
        on_hand = s.get("qty_on_hand") or 0
        mn = s.get("min_stock") or 0
        if on_hand <= 0:
            s["stock_status"] = "out_of_stock"
        elif mn and on_hand <= mn:
            s["stock_status"] = "low_stock"
        else:
            s["stock_status"] = "in_stock"
    return {"store": store, "stock": stock}


# ─────────────────────────────────────────────────────────────────
# Stock movement ledger
# ─────────────────────────────────────────────────────────────────

@router.get("/movements")
async def list_movements(
    dealer_id: str = Query(""),
    store_id: str = Query(""),
    part_sku: str = Query(""),
    limit: int = Query(200, ge=1, le=1000),
    user=Depends(get_current_user),
):
    org = _of(user)
    q: dict = {"organization_id": org}
    if dealer_id:
        q["dealer_id"] = dealer_id
    if store_id:
        q["store_id"] = store_id
    if part_sku:
        q["part_sku"] = part_sku.strip().upper()
    rows = await db[MOVEMENTS].find(q, {"_id": 0}).sort([("at", -1)]).limit(limit).to_list(limit)
    return {"movements": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

@router.get("/audit")
async def list_audit(limit: int = Query(200, ge=1, le=1000), user=Depends(get_current_user)):
    org = _of(user)
    rows = await db[AUDIT].find({"organization_id": org}, {"_id": 0}).sort([("at", -1)]).limit(limit).to_list(limit)
    return {"events": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# Dashboard rollups
# ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    org = _of(user)
    dealers = await db[DEALERS].count_documents({"organization_id": org})
    stores = await db[STORES].count_documents({"organization_id": org})
    orders = await db[ORDERS].find({"organization_id": org}, {"_id": 0}).to_list(2000)
    allocs = await db[ALLOCATIONS].find({"organization_id": org}, {"_id": 0}).to_list(2000)
    stock = await db[STORE_STOCK].find({"organization_id": org}, {"_id": 0}).to_list(5000)

    stock_value = round(sum((s.get("qty_on_hand") or 0) * (s.get("unit_value") or 0) for s in stock), 2)
    allowance_total = round(sum(o.get("allowance") or 0 for o in orders), 2)
    approved_value = round(sum(a.get("approved_value") or 0 for a in allocs
                               if a.get("status") not in ("draft", "cancelled")), 2)
    awaiting_approval = sum(1 for a in allocs if a.get("status") == "awaiting_approval")
    awaiting_receipt = sum(1 for a in allocs if a.get("status") in ("dispatched", "partially_received"))
    low_stock = sum(1 for s in stock if (s.get("min_stock") or 0) and (s.get("qty_on_hand") or 0) <= (s.get("min_stock") or 0))

    # Usage by country (allowance basis) for a simple chart.
    by_country: dict = {}
    dealer_country = {}
    for d in await db[DEALERS].find({"organization_id": org}, {"_id": 0}).to_list(2000):
        dealer_country[d["id"]] = d.get("country") or "Unknown"
    for o in orders:
        c = dealer_country.get(o.get("dealer_id"), "Unknown")
        by_country[c] = round(by_country.get(c, 0) + (o.get("allowance") or 0), 2)

    return {
        "cards": {
            "dealers": dealers,
            "stores": stores,
            "stock_value": stock_value,
            "orders_count": len(orders),
            "allowance_total": allowance_total,
            "approved_value": approved_value,
            "allowance_remaining": round(allowance_total - approved_value, 2),
            "awaiting_approval": awaiting_approval,
            "awaiting_receipt": awaiting_receipt,
            "low_stock": low_stock,
        },
        "allowance_by_country": [{"country": k, "allowance": v} for k, v in sorted(by_country.items(), key=lambda x: -x[1])],
        "recent_allocations": sorted(allocs, key=lambda a: a.get("created_at", ""), reverse=True)[:8],
    }
