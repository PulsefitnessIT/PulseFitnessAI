"""
Inventory & Distribution — PHASE 7 · Intelligence (Monitoring Agents, Reports, Replenishment).

Agents ANALYSE existing distribution data and raise alerts — they NEVER auto-approve any
commercial, financial or stock change ("Agent insight — human review required").  Alerts carry
evidence + a suggested action + an owner.  Reports and replenishment read the shared records.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.inventory_distribution import _of, _now, _uid, _audit, _require_ops_role

router = APIRouter(prefix="/inventory/intel", tags=["Inventory & Distribution · Intelligence"])
logger = logging.getLogger(__name__)

SEVERITIES = ["information", "monitor", "warning", "critical"]
ALERT_STATES = ["new", "assigned", "under_review", "resolved", "dismissed"]


def _age_days(iso: Optional[str]) -> float:
    if not iso:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return 0.0


def _alert(agent, severity, title, evidence, suggested_action, affected=None):
    return {
        "agent": agent, "severity": severity, "title": title, "evidence": evidence,
        "suggested_action": suggested_action, "affected": affected or {},
        "requires_human_review": True,
    }


# ──────────────────────────── Agents (read-only analysis) ────────────────────────────
async def _run_agents(user) -> list:
    of = _of(user)
    findings = []

    # Serial & Asset Integrity
    dup = {}
    async for u in db.inv_equipment_units.find({**of, "normalised_serial": {"$ne": None}}, {"_id": 0, "normalised_serial": 1, "serial_number": 1}):
        dup.setdefault(u["normalised_serial"], []).append(u.get("serial_number"))
    for norm, serials in dup.items():
        if len(serials) > 1:
            findings.append(_alert("Serial & Asset Integrity", "critical", "Duplicate serial detected",
                                   {"normalised": norm, "count": len(serials)}, "Investigate and reconcile duplicate serial numbers.", {"serial": serials[0]}))
    dispatched_no_pkg = await db.inv_equipment_units.count_documents({**of, "status": "dispatched", "asset_id": None})
    # (asset_id is set at allocation; dispatched-without-receipt is a watch item)

    # Order Exception — orders stuck early too long
    async for o in db.inv_distribution_orders.find({**of, "status": {"$in": ["needs_validation", "awaiting_stock", "released_to_warehouse", "picking"]}}, {"_id": 0, "reference": 1, "status": 1, "created_at": 1, "id": 1}):
        age = _age_days(o.get("created_at"))
        if age > 3:
            findings.append(_alert("Order Exception", "warning", f"Order {o['reference']} stuck in {o['status']}",
                                   {"days": round(age, 1), "status": o["status"]}, "Review order and progress the next warehouse step.", {"order": o["reference"]}))

    # Inventory Risk — quarantined units, dealer stock not confirmed, low stock
    quarantined = await db.inv_equipment_units.count_documents({**of, "quarantined": True})
    if quarantined:
        findings.append(_alert("Inventory Risk", "warning", f"{quarantined} unit(s) quarantined",
                               {"count": quarantined}, "Inspect and release or dispose of quarantined units.", {}))
    async for h in db.inv_stock_holdings.find(of, {"_id": 0, "product_code": 1, "qty_on_hand": 1, "qty_reserved": 1, "warehouse_id": 1}):
        avail = (h.get("qty_on_hand", 0) - h.get("qty_reserved", 0))
        if avail <= 1:
            findings.append(_alert("Inventory Risk", "monitor", f"Low available stock: {h['product_code']}",
                                   {"available": avail}, "Consider replenishment.", {"product": h["product_code"]}))

    # Dealer Allocation — awaiting installation too long, dealer-held not allocated
    async for a in db.dealer_customer_allocations.find({**of, "status": "awaiting_installation"}, {"_id": 0, "reference": 1, "created_at": 1, "serial_number": 1}):
        age = _age_days(a.get("created_at"))
        if age > 7:
            findings.append(_alert("Dealer Allocation", "warning", f"Installation overdue: {a['reference']}",
                                   {"days": round(age, 1)}, "Chase engineer scheduling / installation.", {"serial": a.get("serial_number")}))
    stale_dealer = 0
    async for h in db.dealer_inventory_holdings.find({**of, "status": "available"}, {"_id": 0, "received_date": 1}):
        if _age_days(h.get("received_date")) > 30:
            stale_dealer += 1
    if stale_dealer:
        findings.append(_alert("Dealer Allocation", "monitor", f"{stale_dealer} dealer-held machine(s) unallocated >30 days",
                               {"count": stale_dealer}, "Ask dealer to allocate to a customer or transfer.", {}))

    # Sage Integration Health
    needs_map = await db.sage_order_mirrors.count_documents({**of, "sync_state": "needs_mapping"})
    open_err = await db.sage_sync_errors.count_documents({**of, "resolved": False})
    if needs_map or open_err:
        findings.append(_alert("Sage Integration Health", "warning", "Sage sync needs attention",
                               {"needs_mapping": needs_map, "open_errors": open_err}, "Resolve mappings in Order Exceptions.", {}))

    # Document Compliance — delivered shipments without a delivery note
    async for s in db.inv_shipments.find({**of, "status": {"$in": ["delivered", "delivery_discrepancy"]}}, {"_id": 0, "id": 1, "reference": 1}):
        has_note = await db.inv_documents.count_documents({**of, "shipment_id": s["id"], "type": {"$in": ["delivery_note", "packing_list"]}})
        if not has_note:
            findings.append(_alert("Document Compliance", "monitor", f"Shipment {s['reference']} delivered without paperwork",
                                   {}, "Generate the delivery note / packing list.", {"shipment": s["reference"]}))

    return findings


@router.post("/scan")
async def scan(user=Depends(get_current_user)):
    _require_ops_role(user)
    findings = await _run_agents(user)
    # replace previous open (new) alerts with a fresh sweep; keep triaged ones
    await db.inv_monitoring_alerts.delete_many({**_of(user), "status": "new"})
    inserted = 0
    for f in findings:
        await db.inv_monitoring_alerts.insert_one({
            "id": _uid(), "organization_id": user.get("organization_id"),
            "status": "new", "created_at": _now(), **f,
        })
        inserted += 1
    await _audit(user, "intel_scan", "monitoring", "sweep", {"alerts": inserted})
    return {"alerts_raised": inserted, "agents_run": 7}


@router.get("/alerts")
async def alerts(severity: Optional[str] = None, status: Optional[str] = None, user=Depends(get_current_user)):
    flt = _of(user)
    if severity and severity != "all":
        flt["severity"] = severity
    if status and status != "all":
        flt["status"] = status
    rows = await db.inv_monitoring_alerts.find(flt, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    counts = {}
    for s in SEVERITIES:
        counts[s] = await db.inv_monitoring_alerts.count_documents({**_of(user), "severity": s, "status": {"$nin": ["resolved", "dismissed"]}})
    return {"alerts": rows, "counts": counts}


class AlertStatusIn(BaseModel):
    status: str


@router.post("/alerts/{alert_id}/status")
async def set_alert_status(alert_id: str, body: AlertStatusIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    if body.status not in ALERT_STATES:
        raise HTTPException(400, f"status must be one of {ALERT_STATES}")
    r = await db.inv_monitoring_alerts.update_one({**_of(user), "id": alert_id}, {"$set": {"status": body.status, "updated_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, "Alert not found")
    return {"ok": True, "status": body.status}


# ──────────────────────────── Reports ────────────────────────────
@router.get("/reports/{report}")
async def reports(report: str, user=Depends(get_current_user)):
    of = _of(user)
    if report == "serial_register":
        rows = await db.inv_equipment_units.find(of, {"_id": 0, "serial_number": 1, "model": 1, "product_code": 1, "status": 1, "order_id": 1, "asset_id": 1}).sort("created_at", -1).limit(1000).to_list(1000)
        return {"report": report, "columns": ["serial_number", "model", "product_code", "status", "asset_id"], "rows": rows}
    if report == "stock_ledger":
        rows = await db.inv_stock_movements.find(of, {"_id": 0, "movement_ref": 1, "type": 1, "product_code": 1, "serial_number": 1, "quantity": 1, "created_at": 1}).sort("created_at", -1).limit(500).to_list(500)
        return {"report": report, "columns": ["movement_ref", "type", "product_code", "serial_number", "quantity", "created_at"], "rows": rows}
    if report == "order_progress":
        pipe = [{"$match": of}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
        rows = [{"status": r["_id"], "count": r["count"]} async for r in db.inv_distribution_orders.aggregate(pipe)]
        return {"report": report, "columns": ["status", "count"], "rows": rows}
    if report == "dealer_stock_ageing":
        rows = []
        async for h in db.dealer_inventory_holdings.find(of, {"_id": 0, "serial_number": 1, "dealer_name": 1, "status": 1, "received_date": 1}):
            rows.append({**h, "age_days": round(_age_days(h.get("received_date")), 1)})
        return {"report": report, "columns": ["serial_number", "dealer_name", "status", "age_days"], "rows": rows}
    raise HTTPException(400, "Unknown report. Options: serial_register, stock_ledger, order_progress, dealer_stock_ageing")


# ──────────────────────────── Replenishment ────────────────────────────
@router.get("/replenishment")
async def replenishment(reorder_point: int = 2, user=Depends(get_current_user)):
    of = _of(user)
    recs = []
    async for h in db.inv_stock_holdings.find(of, {"_id": 0, "product_code": 1, "warehouse_id": 1, "qty_on_hand": 1, "qty_reserved": 1}):
        avail = h.get("qty_on_hand", 0) - h.get("qty_reserved", 0)
        if avail <= reorder_point:
            recs.append({"product_code": h["product_code"], "warehouse_id": h.get("warehouse_id"),
                         "available": avail, "reorder_point": reorder_point,
                         "recommended_qty": max(reorder_point * 2 - avail, reorder_point)})
    return {"reorder_point": reorder_point, "recommendations": recs,
            "note": "Recommendations require human approval — no Sage purchase order is created automatically."}


@router.get("/overview")
async def overview(user=Depends(get_current_user)):
    of = _of(user)
    counts = {}
    for s in SEVERITIES:
        counts[s] = await db.inv_monitoring_alerts.count_documents({**of, "severity": s, "status": {"$nin": ["resolved", "dismissed"]}})
    return {
        "alert_counts": counts,
        "open_alerts": await db.inv_monitoring_alerts.count_documents({**of, "status": {"$nin": ["resolved", "dismissed"]}}),
        "last_scan": (await db.inv_monitoring_alerts.find_one(of, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)]) or {}).get("created_at"),
    }
