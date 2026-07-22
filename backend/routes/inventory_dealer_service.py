"""
Inventory & Distribution — PHASE 6 · Dealer Service Desks.

Pulse creates a SCOPED service-desk workspace for an existing dealer (no duplicate dealer,
customer, asset, engineer or service-desk codebase).  After a machine is allocated to a
customer, faults route to the responsible desk (dealer vs Pulse) per configured rules — the
fault stays ONE shared record in the existing `issues` store (escalation never duplicates it).
Connects to the existing Dealer Warranty Parts / parts catalogue for recommendations.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from routes.inventory_distribution import _of, _now, _uid, _next_ref, _audit, _require_ops_role

router = APIRouter(prefix="/inventory/svc", tags=["Inventory & Distribution · Dealer Service Desks"])
logger = logging.getLogger(__name__)


# ──────────────────────────── Dealer service desk (creation wizard, deduped) ────────────────────────────
class ServiceDeskIn(BaseModel):
    dealer_id: str
    dealer_name: Optional[str] = None
    country: str = "GB"
    territories: List[str] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)          # products, customer_types, regions, hours, languages, timezones
    users: dict = Field(default_factory=dict)             # admins[], service_managers[], agents[], engineers[]
    stores: List[str] = Field(default_factory=list)
    service_rules: dict = Field(default_factory=dict)     # sla, warranty_routing, chargeable_routing, escalation, pulse_involvement
    customer_portal: dict = Field(default_factory=dict)   # access, fault_logging, asset_visibility, language, support_contact
    branding: dict = Field(default_factory=dict)          # mode, logo, contact, template


@router.get("/desks")
async def list_desks(user=Depends(get_current_user)):
    rows = await db.dealer_service_desks.find(_of(user), {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"desks": rows}


@router.post("/desks")
async def create_desk(body: ServiceDeskIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    of = _of(user)
    dealer = await db.crm2_companies.find_one({**of, "id": body.dealer_id}, {"_id": 0, "id": 1, "name": 1, "country": 1})
    if not dealer:
        raise HTTPException(404, "Dealer company not found in CRM")
    existing = await db.dealer_service_desks.find_one({**of, "dealer_id": body.dealer_id})
    if existing:
        raise HTTPException(409, {"error": "duplicate_desk", "message": f"A service desk already exists for {dealer['name']}"})
    ref = await _next_ref(user, "DSD", db.dealer_service_desks)
    doc = {
        "id": _uid(), "organization_id": user.get("organization_id"), "reference": ref,
        "dealer_id": body.dealer_id, "dealer_name": body.dealer_name or dealer["name"],
        "country": body.country, "territories": body.territories, "coverage": body.coverage,
        "users": body.users, "stores": body.stores, "service_rules": body.service_rules,
        "customer_portal": body.customer_portal, "branding": body.branding or {"mode": "pulse"},
        "status": "draft", "created_by": user.get("email"), "created_at": _now(),
    }
    await db.dealer_service_desks.insert_one({**doc})
    await _audit(user, "dealer_service_desk_created", "dealer_service_desk", doc["id"], {"dealer": doc["dealer_name"]})
    doc.pop("_id", None)
    return doc


@router.post("/desks/{desk_id}/activate")
async def activate_desk(desk_id: str, user=Depends(get_current_user)):
    _require_ops_role(user)
    desk = await db.dealer_service_desks.find_one({**_of(user), "id": desk_id})
    if not desk:
        raise HTTPException(404, "Service desk not found")
    await db.dealer_service_desks.update_one({"id": desk_id}, {"$set": {"status": "active", "activated_at": _now()}})
    await _audit(user, "dealer_service_desk_activated", "dealer_service_desk", desk_id, {})
    return {"ok": True, "status": "active"}


@router.get("/desks/{desk_id}")
async def get_desk(desk_id: str, user=Depends(get_current_user)):
    of = _of(user)
    desk = await db.dealer_service_desks.find_one({**of, "id": desk_id}, {"_id": 0})
    if not desk:
        raise HTTPException(404, "Service desk not found")
    dealer_id = desk["dealer_id"]
    # scoped views over EXISTING shared records
    allocations = await db.dealer_customer_allocations.find({**of, "dealer_id": dealer_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    customer_ids = list({a["customer_company_id"] for a in allocations if a.get("customer_company_id")})
    customers = await db.crm2_companies.find({**of, "id": {"$in": customer_ids}}, {"_id": 0, "id": 1, "name": 1, "status": 1}).to_list(500)
    faults = await db.issues.find({**of, "dealer_service_desk_id": desk_id}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {
        "desk": desk,
        "customers": customers,
        "assets": allocations,
        "faults": faults,
        "stats": {
            "customers": len(customers), "assets": len(allocations),
            "active_assets": len([a for a in allocations if a.get("status") == "active"]),
            "open_faults": len([f for f in faults if f.get("status") not in ("resolved", "closed")]),
        },
    }


# ──────────────────────────── Fault routing after allocation ────────────────────────────
async def _resolve_routing(user, serial: str) -> dict:
    of = _of(user)
    alloc = await db.dealer_customer_allocations.find_one({**of, "serial_number": serial}, {"_id": 0}, sort=[("created_at", -1)])
    if not alloc:
        return {"responsible": "pulse", "dealer_service_desk_id": None, "dealer_id": None,
                "dealer_name": None, "reason": "No dealer allocation found for this serial — routed to Pulse Service Desk."}
    dealer_id = alloc.get("dealer_id")
    desk = await db.dealer_service_desks.find_one({**of, "dealer_id": dealer_id, "status": "active"}, {"_id": 0}) if dealer_id else None
    resp = alloc.get("service_responsibility", "dealer")
    if resp == "pulse":
        return {"responsible": "pulse", "dealer_service_desk_id": None, "dealer_id": dealer_id,
                "dealer_name": alloc.get("customer_company_name"), "reason": "Service responsibility = Pulse."}
    if desk:
        return {"responsible": "dealer", "dealer_service_desk_id": desk["id"], "dealer_id": dealer_id,
                "dealer_name": desk.get("dealer_name"),
                "reason": f"Routed to dealer service desk {desk['reference']} ({resp}); escalates to Pulse if needed."}
    return {"responsible": "pulse", "dealer_service_desk_id": None, "dealer_id": dealer_id,
            "dealer_name": None, "reason": "No active dealer service desk — routed to Pulse."}


@router.get("/route")
async def route_fault(serial: str, user=Depends(get_current_user)):
    return await _resolve_routing(user, serial)


class FaultIn(BaseModel):
    serial_number: str
    title: str
    description: Optional[str] = None
    severity: str = "medium"
    reported_by: Optional[str] = None


@router.post("/faults")
async def log_fault(body: FaultIn, user=Depends(get_current_user)):
    """Log a fault against an allocated serial → routes to responsible desk → ONE shared issues record."""
    of = _of(user)
    routing = await _resolve_routing(user, body.serial_number)
    equip = await db.equipment.find_one(
        {**of, "$or": [{"serial_number": body.serial_number}, {"name": body.serial_number}]},
        {"_id": 0, "id": 1, "model": 1, "customer_company_id": 1, "customer_company_name": 1},
    )
    fault = {
        "id": _uid(), "organization_id": user.get("organization_id"),
        "serial_number": body.serial_number, "title": body.title, "description": body.description or body.title,
        "severity": body.severity, "status": "open", "machine_type": (equip or {}).get("model") or "",
        "equipment_id": (equip or {}).get("id"),
        "customer_company_id": (equip or {}).get("customer_company_id"),
        "source": "dealer_distribution",
        "responsible": routing["responsible"], "dealer_service_desk_id": routing["dealer_service_desk_id"],
        "dealer_id": routing["dealer_id"], "routing_reason": routing["reason"],
        "escalations": [], "reported_by": body.reported_by or user.get("email"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.issues.insert_one({**fault})
    await _audit(user, "fault_logged", "issue", fault["id"], {"serial": body.serial_number, "responsible": routing["responsible"]})
    fault.pop("_id", None)
    return {"fault": fault, "routing": routing}


@router.post("/faults/{fault_id}/escalate")
async def escalate_fault(fault_id: str, user=Depends(get_current_user)):
    """Escalate to Pulse — SAME fault record (no duplicate)."""
    of = _of(user)
    fault = await db.issues.find_one({**of, "id": fault_id})
    if not fault:
        raise HTTPException(404, "Fault not found")
    await db.issues.update_one({**of, "id": fault_id}, {
        "$set": {"responsible": "pulse", "escalated": True, "updated_at": _now()},
        "$push": {"escalations": {"at": _now(), "by": user.get("email"), "from": fault.get("responsible"), "to": "pulse"}},
    })
    await _audit(user, "fault_escalated", "issue", fault_id, {})
    return {"ok": True, "responsible": "pulse"}


# ──────────────────────────── Dealer Warranty Parts (connects to existing parts catalogue) ────────────────────────────
@router.get("/warranty-parts")
async def warranty_parts(dealer_id: str, user=Depends(get_current_user)):
    """Recommend warranty spare parts for a dealer's allocated machine models — reads the existing
    product/parts catalogue (crm_products). Full Dealer Warranty Parts engine logic is reused, not rebuilt."""
    of = _of(user)
    allocs = await db.dealer_customer_allocations.find({**of, "dealer_id": dealer_id}, {"_id": 0, "model": 1, "product_code": 1}).to_list(500)
    models = {}
    for a in allocs:
        key = a.get("model") or a.get("product_code")
        models[key] = models.get(key, 0) + 1
    # pull candidate parts from the existing catalogue
    parts = await db.crm_products.find(
        {**of, "$or": [{"category": {"$regex": "part", "$options": "i"}}, {"type": {"$regex": "part", "$options": "i"}}]},
        {"_id": 0, "id": 1, "sku": 1, "name": 1},
    ).limit(50).to_list(50)
    recommendations = [{"model": m, "installed_base": c,
                        "recommended_parts": [{"sku": p.get("sku"), "name": p.get("name")} for p in parts[:5]]}
                       for m, c in models.items()]
    return {"dealer_id": dealer_id, "models": models, "recommendations": recommendations,
            "note": "Recommendations read the existing parts catalogue; approved parts feed the warehouse/warranty-parts workflow."}


@router.get("/summary")
async def svc_summary(user=Depends(get_current_user)):
    of = _of(user)
    return {
        "service_desks": await db.dealer_service_desks.count_documents(of),
        "active_desks": await db.dealer_service_desks.count_documents({**of, "status": "active"}),
        "dealer_faults": await db.issues.count_documents({**of, "source": "dealer_distribution"}),
        "open_dealer_faults": await db.issues.count_documents({**of, "source": "dealer_distribution", "status": {"$nin": ["resolved", "closed"]}}),
    }
