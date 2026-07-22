"""
Inventory & Distribution — PHASE 3 · Warehouse Operations.

Order-driven fulfilment pipeline built on the Phase-1 distribution orders / equipment
units:  Release → Pick (scan exact serial) → Quality Control → Pack (scan units into
packages) → Dispatch (→ stock In Transit).  Scan validation rejects the wrong serial,
already-picked / already-dispatched units, and quarantined stock.  No duplicate records —
one pick task per serialised unit, one QC record per unit, units flow through the SAME
inv_equipment_units doc created at order time.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.inventory_distribution import (
    _of, _now, _uid, _next_ref, _audit, _require_ops_role, SERIALISED_TYPES, PHYSICAL_TYPES,
)

router = APIRouter(prefix="/inventory/ops", tags=["Inventory & Distribution · Warehouse Ops"])
logger = logging.getLogger(__name__)

DEFAULT_QC_CHECKS = [
    {"key": "model_correct", "label": "Correct model"},
    {"key": "serial_correct", "label": "Correct serial number"},
    {"key": "cosmetic", "label": "Cosmetic condition OK"},
    {"key": "accessories", "label": "Accessories & manuals included"},
    {"key": "power_test", "label": "Operating / power test passed"},
    {"key": "packaging", "label": "Packaging intact"},
]
QC_RESULTS = ["pass", "pass_note", "rework", "quarantine", "failed"]


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


# ── Release order to warehouse → generate pick tasks ──
@router.post("/orders/{order_id}/release")
async def release_order(order_id: str, user=Depends(get_current_user)):
    _require_ops_role(user)
    order = await db.inv_distribution_orders.find_one({**_of(user), "id": order_id})
    if not order:
        raise HTTPException(404, "Order not found")
    existing = await db.inv_pick_tasks.count_documents({**_of(user), "order_id": order_id})
    if existing:
        raise HTTPException(400, "Order already released to the warehouse")
    lines = await db.inv_distribution_order_lines.find({**_of(user), "order_id": order_id}, {"_id": 0}).to_list(500)
    units = await db.inv_equipment_units.find({**_of(user), "order_id": order_id}, {"_id": 0}).to_list(2000)
    tasks = []
    # one task per serialised unit
    for u in units:
        tasks.append({
            "id": _uid(), "organization_id": user.get("organization_id"), "order_id": order_id,
            "line_id": u.get("line_id"), "unit_id": u["id"], "product_code": u.get("product_code"),
            "serial_number": u.get("serial_number"), "required_qty": 1, "picked_qty": 0,
            "warehouse_id": u.get("warehouse_id"), "location_id": u.get("location_id"),
            "status": "ready", "kind": "serialised", "created_at": _now(),
        })
    # qty task per non-serialised physical line
    for ln in lines:
        if ln["product_type"] in PHYSICAL_TYPES and ln["product_type"] not in SERIALISED_TYPES:
            tasks.append({
                "id": _uid(), "organization_id": user.get("organization_id"), "order_id": order_id,
                "line_id": ln["id"], "unit_id": None, "product_code": ln["product_code"],
                "serial_number": None, "required_qty": ln["quantity"], "picked_qty": 0,
                "warehouse_id": ln.get("warehouse_id"), "location_id": None,
                "status": "ready", "kind": "qty", "created_at": _now(),
            })
    if tasks:
        await db.inv_pick_tasks.insert_many([{**t} for t in tasks])
    await db.inv_distribution_orders.update_one({**_of(user), "id": order_id}, {"$set": {"status": "released_to_warehouse", "updated_at": _now()}})
    await _audit(user, "order_released", "order", order_id, {"pick_tasks": len(tasks)})
    return {"pick_tasks": len(tasks), "status": "released_to_warehouse"}


# ── Racking / put-away ──
class RackIn(BaseModel):
    location_id: str


@router.post("/units/{unit_id}/rack")
async def rack_unit(unit_id: str, body: RackIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    unit = await db.inv_equipment_units.find_one({**_of(user), "id": unit_id})
    if not unit:
        raise HTTPException(404, "Unit not found")
    loc = await db.inv_locations.find_one({**_of(user), "id": body.location_id})
    if not loc:
        raise HTTPException(404, "Location not found")
    if loc.get("quarantine"):
        raise HTTPException(409, "Cannot rack into a quarantine location via normal put-away")
    await db.inv_equipment_units.update_one({**_of(user), "id": unit_id}, {"$set": {"location_id": body.location_id, "updated_at": _now()}})
    await _movement(user, "put_away", product_code=unit.get("product_code"), serial_number=unit.get("serial_number"),
                    quantity=1, destination=body.location_id, unit_id=unit_id, order_id=unit.get("order_id"))
    return {"ok": True, "location_id": body.location_id}


# ── Picking (scan exact serial) ──
class PickIn(BaseModel):
    serial: Optional[str] = None
    qty: Optional[int] = None


@router.post("/pick-tasks/{task_id}/pick")
async def pick_task(task_id: str, body: PickIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    task = await db.inv_pick_tasks.find_one({**_of(user), "id": task_id})
    if not task:
        raise HTTPException(404, "Pick task not found")
    if task["status"] == "picked":
        raise HTTPException(409, "Task already picked")
    if task["kind"] == "serialised":
        scanned = (body.serial or "").strip()
        if not scanned:
            raise HTTPException(400, "Scan the serial number to pick this unit")
        if task.get("serial_number") and scanned.upper() != str(task["serial_number"]).upper():
            raise HTTPException(409, {"error": "wrong_serial", "message": f"Scanned serial does not match this task ({task['serial_number']})"})
        # verify the unit isn't already dispatched
        unit = await db.inv_equipment_units.find_one({**_of(user), "id": task["unit_id"]})
        if unit and unit.get("status") in ("dispatched", "dealer_held"):
            raise HTTPException(409, "Unit already dispatched")
        await db.inv_pick_tasks.update_one({"id": task_id}, {"$set": {"status": "picked", "picked_qty": 1, "picked_at": _now()}})
        await _touch_unit(user, task["unit_id"], "picked")
        await _movement(user, "pick", product_code=task.get("product_code"), serial_number=task.get("serial_number"), quantity=1, unit_id=task["unit_id"], order_id=task["order_id"])
    else:
        qty = int(body.qty or task["required_qty"])
        status = "picked" if qty >= task["required_qty"] else "partially_picked"
        await db.inv_pick_tasks.update_one({"id": task_id}, {"$set": {"status": status, "picked_qty": qty, "picked_at": _now()}})
        await _movement(user, "pick", product_code=task.get("product_code"), quantity=qty, order_id=task["order_id"])
    # advance order status if all picked
    remaining = await db.inv_pick_tasks.count_documents({**_of(user), "order_id": task["order_id"], "status": {"$nin": ["picked"]}})
    await db.inv_distribution_orders.update_one({**_of(user), "id": task["order_id"]}, {"$set": {"status": "picked" if remaining == 0 else "picking", "updated_at": _now()}})
    return {"ok": True, "task_status": "picked", "order_fully_picked": remaining == 0}


# ── Quality control ──
@router.get("/qc/templates")
async def qc_templates(user=Depends(get_current_user)):
    rows = await db.inv_qc_templates.find(_of(user), {"_id": 0}).to_list(50)
    if not rows:
        doc = {"id": _uid(), "organization_id": user.get("organization_id"), "name": "Standard machine QC",
               "product_type": "serialised_machine", "checks": DEFAULT_QC_CHECKS, "created_at": _now()}
        await db.inv_qc_templates.insert_one({**doc})
        rows = [doc]
    return {"templates": rows}


class QcTemplateIn(BaseModel):
    name: str
    product_type: str = "serialised_machine"
    checks: List[dict]


@router.post("/qc/templates")
async def create_qc_template(body: QcTemplateIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    doc = {"id": _uid(), "organization_id": user.get("organization_id"), **body.model_dump(), "created_at": _now()}
    await db.inv_qc_templates.insert_one({**doc})
    return doc


class QcIn(BaseModel):
    template_id: Optional[str] = None
    result: str
    responses: dict = {}
    notes: Optional[str] = None


@router.post("/units/{unit_id}/qc")
async def qc_unit(unit_id: str, body: QcIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    if body.result not in QC_RESULTS:
        raise HTTPException(400, f"result must be one of {QC_RESULTS}")
    unit = await db.inv_equipment_units.find_one({**_of(user), "id": unit_id})
    if not unit:
        raise HTTPException(404, "Unit not found")
    await db.inv_qc_checks.insert_one({
        "id": _uid(), "organization_id": user.get("organization_id"), "unit_id": unit_id,
        "order_id": unit.get("order_id"), "template_id": body.template_id, "result": body.result,
        "responses": body.responses, "notes": body.notes, "checker": user.get("email"), "at": _now(),
    })
    passed = body.result in ("pass", "pass_note")
    await _touch_unit(user, unit_id, "quality_checked" if passed else "provisional",
                      extra={"qc_result": body.result, "quarantined": body.result == "quarantine"})
    await _audit(user, "qc_recorded", "equipment_unit", unit_id, {"result": body.result})
    return {"ok": True, "passed": passed, "result": body.result}


# ── Packing ──
class PackageIn(BaseModel):
    type: str = "carton"


@router.post("/orders/{order_id}/packages")
async def create_package(order_id: str, body: PackageIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    order = await db.inv_distribution_orders.find_one({**_of(user), "id": order_id})
    if not order:
        raise HTTPException(404, "Order not found")
    ref = await _next_ref(user, "PKG", db.inv_packages)
    doc = {"id": _uid(), "organization_id": user.get("organization_id"), "order_id": order_id,
           "package_number": ref, "barcode": f"PKG-{ref}", "type": body.type, "unit_ids": [],
           "status": "open", "weight": None, "dims": None, "created_at": _now()}
    await db.inv_packages.insert_one({**doc})
    doc.pop("_id", None)
    return doc


class AddUnitIn(BaseModel):
    unit_id: Optional[str] = None
    serial: Optional[str] = None


@router.post("/packages/{package_id}/add-unit")
async def add_unit_to_package(package_id: str, body: AddUnitIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    pkg = await db.inv_packages.find_one({**_of(user), "id": package_id})
    if not pkg:
        raise HTTPException(404, "Package not found")
    if pkg["status"] in ("sealed", "dispatched"):
        raise HTTPException(409, "Package is sealed")
    # resolve unit by id or scanned serial
    q = {**_of(user)}
    if body.unit_id:
        q["id"] = body.unit_id
    elif body.serial:
        q["normalised_serial"] = "".join(c for c in body.serial.upper() if c.isalnum())
    else:
        raise HTTPException(400, "Provide a unit id or scan a serial")
    unit = await db.inv_equipment_units.find_one(q)
    if not unit:
        raise HTTPException(404, "Unit not found for that scan")
    if unit.get("order_id") != pkg["order_id"]:
        raise HTTPException(409, {"error": "wrong_order", "message": "This unit belongs to a different order"})
    if unit.get("quarantined"):
        raise HTTPException(409, {"error": "quarantined", "message": "Quarantined unit cannot be packed"})
    if unit.get("status") not in ("picked", "quality_checked"):
        raise HTTPException(409, {"error": "not_ready", "message": f"Unit must be picked (and QC'd) before packing — current status {unit.get('status')}"})
    if unit["id"] in pkg.get("unit_ids", []):
        raise HTTPException(409, "Unit already in this package")
    await db.inv_packages.update_one({"id": package_id}, {"$addToSet": {"unit_ids": unit["id"]}, "$set": {"status": "packing"}})
    await _touch_unit(user, unit["id"], "packed")
    return {"ok": True, "unit_id": unit["id"], "serial": unit.get("serial_number")}


class SealIn(BaseModel):
    weight: Optional[float] = None
    dims: Optional[str] = None


@router.post("/packages/{package_id}/seal")
async def seal_package(package_id: str, body: SealIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    pkg = await db.inv_packages.find_one({**_of(user), "id": package_id})
    if not pkg:
        raise HTTPException(404, "Package not found")
    if not pkg.get("unit_ids"):
        raise HTTPException(400, "Cannot seal an empty package")
    await db.inv_packages.update_one({"id": package_id}, {"$set": {"status": "sealed", "weight": body.weight, "dims": body.dims, "sealed_at": _now()}})
    await db.inv_distribution_orders.update_one({**_of(user), "id": pkg["order_id"]}, {"$set": {"status": "packed", "updated_at": _now()}})
    return {"ok": True, "status": "sealed"}


# ── Dispatch ──
class DispatchIn(BaseModel):
    carrier: str
    tracking: Optional[str] = None
    service_level: Optional[str] = None


@router.post("/orders/{order_id}/dispatch")
async def dispatch_order(order_id: str, body: DispatchIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    order = await db.inv_distribution_orders.find_one({**_of(user), "id": order_id})
    if not order:
        raise HTTPException(404, "Order not found")
    packages = await db.inv_packages.find({**_of(user), "order_id": order_id}, {"_id": 0}).to_list(500)
    sealed = [p for p in packages if p["status"] in ("sealed", "dispatched")]
    if not sealed:
        raise HTTPException(400, "No sealed packages to dispatch")
    open_pkgs = [p for p in packages if p["status"] not in ("sealed", "dispatched")]
    ref = await _next_ref(user, "SHP", db.inv_shipments)
    shipment = {
        "id": _uid(), "organization_id": user.get("organization_id"), "order_id": order_id,
        "reference": ref, "carrier": body.carrier, "tracking": body.tracking, "service_level": body.service_level,
        "package_ids": [p["id"] for p in sealed], "status": "in_transit",
        "dealer_id": order.get("dealer_id"), "dealer_name": order.get("dealer_name"),
        "destination": order.get("delivery_address"), "dealer_country": order.get("dealer_country"),
        "dispatched_at": _now(), "created_at": _now(),
    }
    await db.inv_shipments.insert_one({**shipment})
    unit_ids = []
    for p in sealed:
        unit_ids.extend(p.get("unit_ids", []))
        await db.inv_packages.update_one({"id": p["id"]}, {"$set": {"status": "dispatched"}})
    for uid in unit_ids:
        await _touch_unit(user, uid, "dispatched")
        await _movement(user, "dispatch", quantity=1, unit_id=uid, order_id=order_id, destination="in_transit", source_status="packed", destination_status="in_transit")
    order_status = "dispatched" if not open_pkgs else "partially_dispatched"
    await db.inv_distribution_orders.update_one({**_of(user), "id": order_id}, {"$set": {"status": order_status, "updated_at": _now()}})
    await _audit(user, "order_dispatched", "shipment", shipment["id"], {"carrier": body.carrier, "packages": len(sealed), "units": len(unit_ids)})
    shipment.pop("_id", None)
    return {"shipment": shipment, "order_status": order_status, "units_dispatched": len(unit_ids)}


# ── Aggregated fulfilment view for one order + cross-order queues ──
@router.get("/orders/{order_id}/fulfilment")
async def fulfilment(order_id: str, user=Depends(get_current_user)):
    of = _of(user)
    order = await db.inv_distribution_orders.find_one({**of, "id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    pick_tasks = await db.inv_pick_tasks.find({**of, "order_id": order_id}, {"_id": 0}).to_list(2000)
    units = await db.inv_equipment_units.find({**of, "order_id": order_id}, {"_id": 0}).to_list(2000)
    qc = await db.inv_qc_checks.find({**of, "order_id": order_id}, {"_id": 0}).sort("at", -1).to_list(500)
    packages = await db.inv_packages.find({**of, "order_id": order_id}, {"_id": 0}).to_list(500)
    shipment = await db.inv_shipments.find_one({**of, "order_id": order_id}, {"_id": 0}, sort=[("created_at", -1)])
    return {"order": order, "pick_tasks": pick_tasks, "units": units, "qc": qc, "packages": packages, "shipment": shipment}


@router.get("/queues/{stage}")
async def queues(stage: str, user=Depends(get_current_user)):
    of = _of(user)
    STAGE_STATUSES = {
        "receiving": ["needs_validation", "awaiting_stock", "partially_available", "fully_available", "reserved"],
        "picking": ["released_to_warehouse", "picking", "partially_picked"],
        "qc": ["picked", "quality_control"],
        "packing": ["picked", "packing", "partially_packed"],
        "dispatch": ["packed", "awaiting_dispatch", "partially_dispatched"],
    }
    statuses = STAGE_STATUSES.get(stage)
    if statuses is None:
        raise HTTPException(400, "Unknown stage")
    rows = await db.inv_distribution_orders.find({**of, "status": {"$in": statuses}}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"stage": stage, "orders": rows}
