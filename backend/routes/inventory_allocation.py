"""
Inventory & Distribution — PHASE 5 · Customer Allocation, Installation & Warranty.

Dealer allocates dealer-held machines (Phase-4 dealer_inventory_holdings) to THEIR customers
with duplicate-safe customer matching (reuses the CRM crm2_companies register — no second
customer database).  Allocation creates the ACTIVE ASSET in the EXISTING equipment register
(db.equipment) — the provisional/dealer unit becomes that one asset (unit.asset_id links it,
never a duplicate).  The Customer Operations Portal view is a customer-scoped read over
db.equipment.  Installation/commissioning (the Engineer App calls the same endpoint) activates
the asset and starts warranty per the configured rule.
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.inventory_distribution import _of, _now, _uid, _next_ref, _audit, _require_ops_role, _get_settings

router = APIRouter(prefix="/inventory/alloc", tags=["Inventory & Distribution · Customer Allocation"])
logger = logging.getLogger(__name__)

ALLOCATION_STATUSES = ["allocated", "awaiting_delivery", "awaiting_installation", "installation_in_progress", "installed", "active", "cancelled"]

WARRANTY_MONTHS_DEFAULT = 24


async def _touch_unit(user, unit_id, status, extra=None):
    payload = {"status": status, "updated_at": _now()}
    if extra:
        payload.update(extra)
    await db.inv_equipment_units.update_one(
        {**_of(user), "id": unit_id},
        {"$set": payload, "$push": {"history": {"status": status, "at": _now(), "by": user.get("email")}}},
    )


# ──────────────────────────── Available dealer stock ────────────────────────────
@router.get("/available")
async def available_stock(dealer_id: Optional[str] = None, user=Depends(get_current_user)):
    flt = {**_of(user), "status": "available"}
    if dealer_id:
        flt["dealer_id"] = dealer_id
    rows = await db.dealer_inventory_holdings.find(flt, {"_id": 0}).sort("received_date", -1).limit(500).to_list(500)
    return {"available": rows}


# ──────────────────────────── Customer duplicate prevention ────────────────────────────
@router.get("/customers/search")
async def search_customers(q: str, user=Depends(get_current_user)):
    """Search the EXISTING CRM company register to prevent duplicate customers."""
    if not q or len(q) < 2:
        return {"matches": []}
    of = _of(user)
    rx = {"$regex": re.escape(q), "$options": "i"}
    rows = await db.crm2_companies.find(
        {**of, "$or": [{"name": rx}, {"trading_name": rx}, {"domain": rx}, {"postcode": rx}]},
        {"_id": 0, "id": 1, "name": 1, "country": 1, "company_type": 1, "postcode": 1, "domain": 1},
    ).limit(15).to_list(15)
    return {"matches": rows}


class NewCustomerIn(BaseModel):
    name: str
    country: str = "GB"
    postcode: Optional[str] = None
    domain: Optional[str] = None
    dealer_id: Optional[str] = None
    force: bool = False  # confirm-create despite possible duplicates


@router.post("/customers")
async def create_customer(body: NewCustomerIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    of = _of(user)
    # duplicate scan
    rx = {"$regex": f"^{re.escape(body.name.strip())}$", "$options": "i"}
    dupes = await db.crm2_companies.find({**of, "name": rx}, {"_id": 0, "id": 1, "name": 1, "country": 1}).limit(10).to_list(10)
    if dupes and not body.force:
        return {"created": False, "duplicates": dupes, "message": "Possible existing customer(s) found — confirm to create anyway or use the existing record."}
    company_id = _uid()
    doc = {
        "id": company_id, "organization_id": user.get("organization_id"), "name": body.name.strip(),
        "country": body.country, "postcode": body.postcode, "domain": body.domain,
        "company_type": "dealer_customer", "status": "pending_validation",
        "created_by_dealer": body.dealer_id, "created_at": _now(),
    }
    await db.crm2_companies.insert_one({**doc})
    await _audit(user, "dealer_customer_created", "company", company_id, {"name": body.name, "status": "pending_validation"})
    doc.pop("_id", None)
    return {"created": True, "company": doc}


# ──────────────────────────── Allocate machines to a customer ────────────────────────────
class AllocateIn(BaseModel):
    unit_ids: List[str]
    customer_company_id: str
    customer_site: Optional[str] = None
    planned_delivery_date: Optional[str] = None
    planned_install_date: Optional[str] = None
    service_responsibility: str = "dealer"  # dealer | pulse | third_party


@router.post("/allocate")
async def allocate(body: AllocateIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    of = _of(user)
    company = await db.crm2_companies.find_one({**of, "id": body.customer_company_id}, {"_id": 0, "id": 1, "name": 1})
    if not company:
        raise HTTPException(404, "Customer company not found")
    results = []
    for unit_id in body.unit_ids:
        holding = await db.dealer_inventory_holdings.find_one({**of, "unit_id": unit_id, "status": "available"})
        if not holding:
            results.append({"unit_id": unit_id, "ok": False, "reason": "not available for allocation"})
            continue
        unit = await db.inv_equipment_units.find_one({**of, "id": unit_id}, {"_id": 0})
        # 1) create the ACTIVE ASSET in the existing equipment register (single record; unit becomes asset)
        asset_id = _uid()
        await db.equipment.insert_one({
            "id": asset_id, "user_id": user.get("id"), "organization_id": user.get("organization_id"),
            "name": f"{unit.get('model') or unit.get('product_code')} — {unit.get('serial_number')}",
            "equipment_type": "Fitness Machine", "model": unit.get("model"),
            "serial_number": unit.get("serial_number"), "manuals": [],
            "status": "awaiting_installation",
            "asset_source": "dealer_distribution", "source_unit_id": unit_id,
            "customer_company_id": company["id"], "customer_company_name": company["name"],
            "customer_site": body.customer_site, "dealer_id": holding.get("dealer_id"),
            "distribution_order_id": unit.get("order_id"),
            "created_at": _now(), "updated_at": _now(),
        })
        # 2) allocation record
        alloc_id = _uid()
        ref = await _next_ref(user, "ALL", db.dealer_customer_allocations)
        await db.dealer_customer_allocations.insert_one({
            "id": alloc_id, "organization_id": user.get("organization_id"), "reference": ref,
            "unit_id": unit_id, "asset_id": asset_id, "dealer_id": holding.get("dealer_id"),
            "customer_company_id": company["id"], "customer_company_name": company["name"],
            "customer_site": body.customer_site, "serial_number": unit.get("serial_number"),
            "model": unit.get("model"), "product_code": unit.get("product_code"),
            "planned_delivery_date": body.planned_delivery_date, "planned_install_date": body.planned_install_date,
            "service_responsibility": body.service_responsibility, "status": "awaiting_installation",
            "created_by": user.get("email"), "created_at": _now(),
        })
        # 3) mark holding + unit (unit becomes the asset — asset_id set, not duplicated)
        await db.dealer_inventory_holdings.update_one({"id": holding["id"]}, {"$set": {"status": "customer_allocated", "intended_customer_id": company["id"], "updated_at": _now()}})
        await _touch_unit(user, unit_id, "customer_allocated", extra={"asset_id": asset_id, "customer_company_id": company["id"]})
        results.append({"unit_id": unit_id, "ok": True, "allocation_id": alloc_id, "asset_id": asset_id, "reference": ref})
    ok = [r for r in results if r["ok"]]
    await _audit(user, "customer_allocation", "company", company["id"], {"allocated": len(ok)})
    return {"results": results, "allocated": len(ok), "customer": company["name"]}


@router.get("/allocations")
async def list_allocations(status: Optional[str] = None, user=Depends(get_current_user)):
    flt = _of(user)
    if status and status != "all":
        flt["status"] = status
    rows = await db.dealer_customer_allocations.find(flt, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return {"allocations": rows}


@router.get("/allocations/{alloc_id}")
async def get_allocation(alloc_id: str, user=Depends(get_current_user)):
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Allocation not found")
    install = await db.installation_commissioning_records.find_one({**of, "allocation_id": alloc_id}, {"_id": 0})
    warranty = await db.warranty_activation_events.find_one({**of, "unit_id": a["unit_id"]}, {"_id": 0})
    asset = await db.equipment.find_one({**of, "id": a.get("asset_id")}, {"_id": 0})
    return {"allocation": a, "installation": install, "warranty": warranty, "asset": asset}


# ──────────────────────────── Installation & commissioning (Engineer App calls this) ────────────────────────────
INSTALL_CHECKS = [
    {"key": "positioned", "label": "Machine positioned & levelled"},
    {"key": "power", "label": "Power / network connected"},
    {"key": "safety", "label": "Safety checks completed"},
    {"key": "test_run", "label": "Test run passed"},
    {"key": "customer_walkthrough", "label": "Customer walkthrough done"},
]


class InstallIn(BaseModel):
    engineer_name: str
    checklist: dict = {}
    software_version: Optional[str] = None
    condition: Optional[str] = None
    customer_acceptance: bool = False
    notes: Optional[str] = None


async def _warranty_dates(user, event: str):
    settings = await _get_settings(user)
    rule = settings.get("warranty_activation_rule", "installation_date")
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=WARRANTY_MONTHS_DEFAULT * 30)
    return rule, start.isoformat(), end.isoformat()


@router.post("/allocations/{alloc_id}/install")
async def install_commission(alloc_id: str, body: InstallIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id})
    if not a:
        raise HTTPException(404, "Allocation not found")
    if not body.customer_acceptance:
        raise HTTPException(400, "Customer acceptance is required to commission the asset")
    # installation record
    rec_id = _uid()
    await db.installation_commissioning_records.insert_one({
        "id": rec_id, "organization_id": user.get("organization_id"), "allocation_id": alloc_id,
        "unit_id": a["unit_id"], "asset_id": a.get("asset_id"), "engineer_name": body.engineer_name,
        "checklist": body.checklist, "software_version": body.software_version, "condition": body.condition,
        "customer_acceptance": body.customer_acceptance, "notes": body.notes,
        "commissioned_at": _now(), "recorded_by": user.get("email"),
    })
    # warranty activation
    rule, w_start, w_end = await _warranty_dates(user, "installation_date")
    await db.warranty_activation_events.insert_one({
        "id": _uid(), "organization_id": user.get("organization_id"), "unit_id": a["unit_id"],
        "asset_id": a.get("asset_id"), "warranty_start": w_start, "warranty_end": w_end,
        "warranty_source": rule, "triggering_event": "commissioning", "created_at": _now(),
    })
    # activate the ASSET in the existing register + mark unit active
    await db.equipment.update_one({**of, "id": a.get("asset_id")}, {"$set": {
        "status": "active", "warranty_expiry": w_end, "commissioned_at": _now(),
        "software_version": body.software_version, "updated_at": _now(),
    }})
    await _touch_unit(user, a["unit_id"], "active_asset")
    await db.dealer_customer_allocations.update_one({"id": alloc_id}, {"$set": {"status": "active", "installed_at": _now(), "updated_at": _now()}})
    await db.dealer_inventory_holdings.update_one({**of, "unit_id": a["unit_id"]}, {"$set": {"status": "installed", "updated_at": _now()}})
    await _audit(user, "installation_commissioned", "allocation", alloc_id, {"warranty_end": w_end})
    return {"ok": True, "asset_status": "active", "warranty_start": w_start, "warranty_end": w_end, "warranty_rule": rule}


# ──────────────────────────── Customer Operations Portal view (over the single asset register) ────────────────────────────
@router.get("/customer-portal/{company_id}/equipment")
async def customer_portal_equipment(company_id: str, user=Depends(get_current_user)):
    of = _of(user)
    company = await db.crm2_companies.find_one({**of, "id": company_id}, {"_id": 0, "id": 1, "name": 1})
    rows = await db.equipment.find(
        {**of, "customer_company_id": company_id, "asset_source": "dealer_distribution"},
        {"_id": 0, "id": 1, "name": 1, "model": 1, "serial_number": 1, "status": 1, "warranty_expiry": 1,
         "customer_site": 1, "commissioned_at": 1, "software_version": 1},
    ).sort("created_at", -1).to_list(500)
    return {"company": company, "equipment": rows}


@router.get("/summary")
async def alloc_summary(user=Depends(get_current_user)):
    of = _of(user)
    return {
        "available_to_allocate": await db.dealer_inventory_holdings.count_documents({**of, "status": "available"}),
        "awaiting_installation": await db.dealer_customer_allocations.count_documents({**of, "status": "awaiting_installation"}),
        "active_assets": await db.dealer_customer_allocations.count_documents({**of, "status": "active"}),
    }
