"""
Inventory & Distribution — PHASE 4 · Dealer Distribution.

Shipment tracking → Dealer Receipt confirmation (scan serials, report shortage/damage)
→ Dealer Inventory (dealer-held stock) → Transfer Orders → International paperwork
(customs fields + versioned documents via inv_documents).

Builds on Phase-3 inv_shipments / inv_equipment_units. The dealer-receipt endpoint is
the SAME action the Dealer Portal will call — no separate stock or receipt record.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.inventory_distribution import _of, _now, _uid, _next_ref, _audit, _require_ops_role, _normalise_serial

router = APIRouter(prefix="/inventory/dist", tags=["Inventory & Distribution · Dealer Distribution"])
logger = logging.getLogger(__name__)

SHIPMENT_STATUSES = ["draft", "awaiting_booking", "booked", "collected", "in_transit", "customs_hold",
                     "customs_cleared", "out_for_delivery", "partially_delivered", "delivered",
                     "delivery_discrepancy", "returned", "lost", "cancelled"]
RECEIPT_STATUSES = ["awaiting_receipt", "receiving", "partially_received", "fully_received",
                    "discrepancy_reported", "damage_reported", "under_review", "closed"]


async def _movement(user, mtype, **kw):
    await db.inv_stock_movements.insert_one({
        "id": _uid(), "organization_id": user.get("organization_id"),
        "movement_ref": await _next_ref(user, "MOV", db.inv_stock_movements),
        "type": mtype, "user": user.get("email"), "sage_posting_status": "Operationally Completed",
        "created_at": _now(), **kw,
    })


async def _touch_unit(user, unit_id, status, extra=None):
    payload = {"status": status, "updated_at": _now()}
    if extra:
        payload.update(extra)
    await db.inv_equipment_units.update_one(
        {**_of(user), "id": unit_id},
        {"$set": payload, "$push": {"history": {"status": status, "at": _now(), "by": user.get("email")}}},
    )


# ──────────────────────────── Shipments ────────────────────────────
@router.get("/shipments")
async def list_shipments(status: Optional[str] = None, user=Depends(get_current_user)):
    flt = _of(user)
    if status and status != "all":
        flt["status"] = status
    rows = await db.inv_shipments.find(flt, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"shipments": rows}


@router.get("/shipments/{shipment_id}")
async def get_shipment(shipment_id: str, user=Depends(get_current_user)):
    of = _of(user)
    sh = await db.inv_shipments.find_one({**of, "id": shipment_id}, {"_id": 0})
    if not sh:
        raise HTTPException(404, "Shipment not found")
    packages = await db.inv_packages.find({**of, "id": {"$in": sh.get("package_ids", [])}}, {"_id": 0}).to_list(500)
    unit_ids = [u for p in packages for u in p.get("unit_ids", [])]
    units = await db.inv_equipment_units.find({**of, "id": {"$in": unit_ids}}, {"_id": 0}).to_list(2000)
    receipt = await db.dealer_receipts.find_one({**of, "shipment_id": shipment_id}, {"_id": 0})
    documents = await db.inv_documents.find({**of, "shipment_id": shipment_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"shipment": sh, "packages": packages, "units": units, "receipt": receipt, "documents": documents}


class ShipStatusIn(BaseModel):
    status: str
    tracking: Optional[str] = None


@router.post("/shipments/{shipment_id}/status")
async def set_shipment_status(shipment_id: str, body: ShipStatusIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    if body.status not in SHIPMENT_STATUSES:
        raise HTTPException(400, f"Unknown status '{body.status}'")
    sh = await db.inv_shipments.find_one({**_of(user), "id": shipment_id})
    if not sh:
        raise HTTPException(404, "Shipment not found")
    updates = {"status": body.status, "updated_at": _now()}
    if body.tracking is not None:
        updates["tracking"] = body.tracking
    await db.inv_shipments.update_one({"id": shipment_id}, {"$set": updates})
    await _audit(user, "shipment_status", "shipment", shipment_id, {"status": body.status})
    return {"ok": True, "status": body.status}


class CustomsIn(BaseModel):
    incoterm: Optional[str] = None
    country_of_origin: Optional[str] = None
    hs_code: Optional[str] = None
    export_reason: Optional[str] = None
    gross_weight: Optional[float] = None
    net_weight: Optional[float] = None
    declared_value: Optional[float] = None
    currency: Optional[str] = None
    eori: Optional[str] = None


@router.put("/shipments/{shipment_id}/customs")
async def set_customs(shipment_id: str, body: CustomsIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    sh = await db.inv_shipments.find_one({**_of(user), "id": shipment_id})
    if not sh:
        raise HTTPException(404, "Shipment not found")
    customs = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.inv_shipments.update_one({"id": shipment_id}, {"$set": {"customs": customs, "updated_at": _now()}})
    return {"ok": True, "customs": customs}


# ──────────────────────────── Documents (versioned) ────────────────────────────
DOC_TEMPLATES = {
    "packing_list": {"name": "Packing List", "version": "v1"},
    "delivery_note": {"name": "Delivery Note", "version": "v1"},
    "commercial_invoice_support": {"name": "Commercial Invoice Support", "version": "v1"},
    "export_packing_list": {"name": "Export Packing List", "version": "v1"},
}


class DocIn(BaseModel):
    type: str


@router.post("/shipments/{shipment_id}/documents")
async def generate_document(shipment_id: str, body: DocIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    tpl = DOC_TEMPLATES.get(body.type)
    if not tpl:
        raise HTTPException(400, f"Unknown document type. Options: {list(DOC_TEMPLATES)}")
    of = _of(user)
    sh = await db.inv_shipments.find_one({**of, "id": shipment_id}, {"_id": 0})
    if not sh:
        raise HTTPException(404, "Shipment not found")
    packages = await db.inv_packages.find({**of, "id": {"$in": sh.get("package_ids", [])}}, {"_id": 0}).to_list(500)
    unit_ids = [u for p in packages for u in p.get("unit_ids", [])]
    units = await db.inv_equipment_units.find({**of, "id": {"$in": unit_ids}}, {"_id": 0}).to_list(2000)
    # existing revisions of same type
    rev = await db.inv_documents.count_documents({**of, "shipment_id": shipment_id, "type": body.type}) + 1
    doc = {
        "id": _uid(), "organization_id": user.get("organization_id"), "shipment_id": shipment_id,
        "order_id": sh.get("order_id"), "type": body.type, "template": tpl["name"],
        "template_version": tpl["version"], "revision": rev, "language": "en",
        "currency": (sh.get("customs") or {}).get("currency") or "GBP",
        "reference": f"{body.type.upper()[:3]}-{sh['reference']}-R{rev}",
        "content": {
            "shipment": sh["reference"], "carrier": sh.get("carrier"), "tracking": sh.get("tracking"),
            "dealer": sh.get("dealer_name"), "destination": sh.get("destination"),
            "country": sh.get("dealer_country"),
            "packages": [{"package": p["package_number"], "type": p.get("type"), "units": len(p.get("unit_ids", []))} for p in packages],
            "lines": [{"serial": u.get("serial_number"), "model": u.get("model"), "product_code": u.get("product_code")} for u in units],
            "customs": sh.get("customs"),
        },
        "status": "final", "generated_by": user.get("email"), "created_at": _now(),
    }
    await db.inv_documents.insert_one({**doc})
    await _audit(user, "document_generated", "document", doc["id"], {"type": body.type, "revision": rev})
    doc.pop("_id", None)
    return {"document": doc}


@router.get("/shipments/{shipment_id}/documents")
async def list_documents(shipment_id: str, user=Depends(get_current_user)):
    rows = await db.inv_documents.find({**_of(user), "shipment_id": shipment_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"documents": rows, "templates": DOC_TEMPLATES}


# ──────────────────────────── Dealer receipt (Dealer Portal calls this too) ────────────────────────────
class ReceiveIn(BaseModel):
    confirmed_serials: List[str] = []
    damaged_serials: List[str] = []
    missing_serials: List[str] = []
    notes: Optional[str] = None
    signature: Optional[str] = None


@router.post("/shipments/{shipment_id}/receive")
async def dealer_receive(shipment_id: str, body: ReceiveIn, user=Depends(get_current_user)):
    of = _of(user)
    sh = await db.inv_shipments.find_one({**of, "id": shipment_id})
    if not sh:
        raise HTTPException(404, "Shipment not found")
    packages = await db.inv_packages.find({**of, "id": {"$in": sh.get("package_ids", [])}}, {"_id": 0}).to_list(500)
    unit_ids = [u for p in packages for u in p.get("unit_ids", [])]
    shipment_units = await db.inv_equipment_units.find({**of, "id": {"$in": unit_ids}}, {"_id": 0}).to_list(2000)
    by_norm = {_normalise_serial(u.get("serial_number") or ""): u for u in shipment_units}

    def resolve(serials):
        found, unknown = [], []
        for s in serials:
            u = by_norm.get(_normalise_serial(s))
            (found if u else unknown).append(u or s)
        return found, unknown

    confirmed, bad_conf = resolve(body.confirmed_serials)
    damaged, bad_dmg = resolve(body.damaged_serials)
    unknown = [s for s in bad_conf + bad_dmg if isinstance(s, str)]
    if unknown:
        raise HTTPException(409, {"error": "serial_not_in_shipment", "message": f"Serial(s) not part of this shipment: {', '.join(unknown)}"})

    # Confirmed → dealer held + dealer inventory holdings
    for u in confirmed:
        await _touch_unit(user, u["id"], "dealer_held", extra={"physical_location": "dealer_warehouse", "custodian": "dealer"})
        await db.dealer_inventory_holdings.update_one(
            {**of, "unit_id": u["id"]},
            {"$set": {
                "id": _uid(), "organization_id": user.get("organization_id"), "unit_id": u["id"],
                "dealer_id": sh.get("dealer_id"), "dealer_name": sh.get("dealer_name"),
                "product_code": u.get("product_code"), "model": u.get("model"),
                "serial_number": u.get("serial_number"), "shipment_id": shipment_id,
                "order_id": sh.get("order_id"), "status": "available", "intended_customer_id": None,
                "received_date": _now(), "updated_at": _now(),
            }}, upsert=True,
        )
        await _movement(user, "dealer_receipt", serial_number=u.get("serial_number"), quantity=1, unit_id=u["id"],
                        order_id=sh.get("order_id"), source_status="in_transit", destination_status="dealer_available")
    for u in damaged:
        await _touch_unit(user, u["id"], "returned", extra={"damaged": True})

    total = len(shipment_units)
    ok = len(confirmed)
    has_issue = bool(damaged) or (ok + len(damaged) < total) or bool(body.missing_serials)
    receipt_status = "fully_received" if (ok == total and not damaged) else ("discrepancy_reported" if has_issue else "partially_received")
    shipment_status = "delivered" if receipt_status == "fully_received" else "delivery_discrepancy"

    receipt = {
        "id": _uid(), "organization_id": user.get("organization_id"), "shipment_id": shipment_id,
        "order_id": sh.get("order_id"), "dealer_id": sh.get("dealer_id"), "dealer_name": sh.get("dealer_name"),
        "confirmed": [u.get("serial_number") for u in confirmed],
        "damaged": [u.get("serial_number") for u in damaged],
        "missing": body.missing_serials, "notes": body.notes, "signature": body.signature,
        "status": receipt_status, "received_by": user.get("email"), "created_at": _now(),
    }
    await db.dealer_receipts.update_one({**of, "shipment_id": shipment_id}, {"$set": receipt}, upsert=True)
    await db.inv_shipments.update_one({"id": shipment_id}, {"$set": {"status": shipment_status, "updated_at": _now()}})
    if sh.get("order_id"):
        await db.inv_distribution_orders.update_one(
            {**of, "id": sh["order_id"]},
            {"$set": {"status": "received_by_dealer" if receipt_status == "fully_received" else "partially_received", "updated_at": _now()}},
        )
    await _audit(user, "dealer_receipt", "shipment", shipment_id, {"confirmed": ok, "damaged": len(damaged), "status": receipt_status})
    return {"receipt_status": receipt_status, "confirmed": ok, "damaged": len(damaged), "shipment_status": shipment_status}


# ──────────────────────────── Dealer inventory ────────────────────────────
@router.get("/dealer-inventory")
async def dealer_inventory(dealer_id: Optional[str] = None, status: Optional[str] = None, user=Depends(get_current_user)):
    flt = _of(user)
    if dealer_id:
        flt["dealer_id"] = dealer_id
    if status and status != "all":
        flt["status"] = status
    rows = await db.dealer_inventory_holdings.find(flt, {"_id": 0}).sort("received_date", -1).limit(500).to_list(500)
    return {"holdings": rows}


# ──────────────────────────── Transfer orders ────────────────────────────
TRANSFER_STATUSES = ["draft", "awaiting_approval", "approved", "picking", "dispatched", "in_transit",
                     "partially_received", "received", "discrepancy", "cancelled"]


class TransferIn(BaseModel):
    source_warehouse_id: str
    dest_warehouse_id: str
    unit_ids: List[str] = []
    notes: Optional[str] = None


@router.get("/transfers")
async def list_transfers(user=Depends(get_current_user)):
    rows = await db.inv_transfer_orders.find(_of(user), {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"transfers": rows}


@router.post("/transfers")
async def create_transfer(body: TransferIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    if body.source_warehouse_id == body.dest_warehouse_id:
        raise HTTPException(400, "Source and destination must differ")
    ref = await _next_ref(user, "TRF", db.inv_transfer_orders)
    doc = {
        "id": _uid(), "organization_id": user.get("organization_id"), "reference": ref,
        "source_warehouse_id": body.source_warehouse_id, "dest_warehouse_id": body.dest_warehouse_id,
        "unit_ids": body.unit_ids, "notes": body.notes, "status": "awaiting_approval",
        "created_by": user.get("email"), "created_at": _now(),
    }
    await db.inv_transfer_orders.insert_one({**doc})
    await _audit(user, "transfer_created", "transfer", doc["id"], {"ref": ref, "units": len(body.unit_ids)})
    doc.pop("_id", None)
    return doc


@router.post("/transfers/{transfer_id}/{action}")
async def transfer_action(transfer_id: str, action: str, user=Depends(get_current_user)):
    _require_ops_role(user)
    t = await db.inv_transfer_orders.find_one({**_of(user), "id": transfer_id})
    if not t:
        raise HTTPException(404, "Transfer not found")
    flow = {"approve": "approved", "dispatch": "in_transit", "receive": "received", "cancel": "cancelled"}
    if action not in flow:
        raise HTTPException(400, f"Unknown action. Options: {list(flow)}")
    new_status = flow[action]
    await db.inv_transfer_orders.update_one({"id": transfer_id}, {"$set": {"status": new_status, "updated_at": _now()}})
    if action == "dispatch":
        for uid in t.get("unit_ids", []):
            await _touch_unit(user, uid, "in_transit", extra={"physical_location": "in_transit"})
            await _movement(user, "transfer_dispatch", quantity=1, unit_id=uid, source=t["source_warehouse_id"], destination="in_transit")
    if action == "receive":
        for uid in t.get("unit_ids", []):
            await _touch_unit(user, uid, "quality_checked", extra={"warehouse_id": t["dest_warehouse_id"], "physical_location": "pulse_warehouse"})
            await _movement(user, "transfer_receipt", quantity=1, unit_id=uid, source="in_transit", destination=t["dest_warehouse_id"])
    await _audit(user, f"transfer_{action}", "transfer", transfer_id, {"status": new_status})
    return {"ok": True, "status": new_status}


# ──────────────────────────── Distribution dashboard extras ────────────────────────────
@router.get("/summary")
async def distribution_summary(user=Depends(get_current_user)):
    of = _of(user)
    return {
        "shipments_in_transit": await db.inv_shipments.count_documents({**of, "status": "in_transit"}),
        "shipments_delivered": await db.inv_shipments.count_documents({**of, "status": "delivered"}),
        "delivery_discrepancies": await db.inv_shipments.count_documents({**of, "status": "delivery_discrepancy"}),
        "dealer_held_units": await db.dealer_inventory_holdings.count_documents(of),
        "open_transfers": await db.inv_transfer_orders.count_documents({**of, "status": {"$nin": ["received", "cancelled"]}}),
    }
