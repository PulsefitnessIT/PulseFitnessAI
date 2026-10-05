"""Engineer-proposed equipment changes with office approval.

Field engineers can PROPOSE adding a new asset to a site, or PROPOSE removing
(archiving) an existing asset, from within a PPM job. Nothing is applied to the
site's live asset list until an office user approves it — keeping customer asset
lists accurate without letting the field change them unilaterally.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc", tags=["Service Ops · Equipment changes"])

COLL = "svc_equipment_change_requests"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _operator(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _strip(doc: dict | None) -> dict | None:
    if doc:
        doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Engineer — propose add / remove
# ─────────────────────────────────────────────────────────────────

@router.post("/engineer/equipment-change-requests")
async def propose_equipment_change(data: dict = Body(...), user=Depends(get_current_user)) -> dict:
    operator = _operator(user)
    case_id = (data.get("case_id") or "").strip()
    change_type = (data.get("change_type") or "").strip().lower()
    if change_type not in ("add", "remove"):
        raise HTTPException(400, "change_type must be 'add' or 'remove'")
    case = await db.svc_cases.find_one(
        {"id": case_id, "organization_id": operator},
        {"_id": 0, "id": 1, "reference": 1, "site_id": 1, "site_name": 1,
         "ppm_customer_org_id": 1, "customer_name": 1})
    if not case:
        raise HTTPException(404, "Job not found")
    customer_org = case.get("ppm_customer_org_id") or ""
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": operator,
        "customer_org_id": customer_org,
        "case_id": case_id,
        "case_reference": case.get("reference") or "",
        "site_id": case.get("site_id") or "",
        "site_name": case.get("site_name") or "",
        "customer_name": case.get("customer_name") or "",
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "Engineer",
        "change_type": change_type,
        "status": "pending",
        "created_at": _now(), "updated_at": _now(),
        "decided_by": None, "decided_by_name": None, "decided_at": None, "decision_note": None,
    }
    if change_type == "add":
        p = data.get("proposed") or {}
        name = (p.get("name") or data.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "Equipment name is required")
        doc["proposed"] = {
            "name": name,
            "equipment_type": (p.get("equipment_type") or data.get("equipment_type") or "").strip(),
            "manufacturer": (p.get("manufacturer") or "").strip(),
            "model": (p.get("model") or "").strip(),
            "serial_number": (p.get("serial_number") or "").strip(),
            "notes": (p.get("notes") or "").strip(),
        }
    else:
        equipment_id = (data.get("equipment_id") or "").strip()
        if not equipment_id:
            raise HTTPException(400, "equipment_id is required to propose a removal")
        doc["equipment_id"] = equipment_id
        doc["equipment_name"] = (data.get("equipment_name") or "").strip()
        doc["reason"] = (data.get("reason") or "").strip()
    await db.svc_equipment_change_requests.insert_one(doc)
    return {"success": True, "request": _strip(doc)}


@router.get("/engineer/jobs/{case_id}/equipment-change-requests")
async def list_case_change_requests(case_id: str, user=Depends(get_current_user)) -> dict:
    operator = _operator(user)
    rows = await db.svc_equipment_change_requests.find(
        {"organization_id": operator, "case_id": case_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return {"requests": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# Office — review queue + approve / reject
# ─────────────────────────────────────────────────────────────────

@router.get("/desk/equipment-change-requests")
async def list_change_requests(status: str = Query("pending"), user=Depends(get_current_user)) -> dict:
    operator = _operator(user)
    q: dict = {"organization_id": operator}
    if status and status != "all":
        q["status"] = status
    rows = await db.svc_equipment_change_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    pending = await db.svc_equipment_change_requests.count_documents(
        {"organization_id": operator, "status": "pending"})
    return {"requests": rows, "count": len(rows), "pending_count": pending}


@router.post("/desk/equipment-change-requests/{req_id}/approve")
async def approve_change_request(req_id: str, data: dict = Body(default={}), user=Depends(get_current_user)) -> dict:
    operator = _operator(user)
    req = await db.svc_equipment_change_requests.find_one(
        {"id": req_id, "organization_id": operator}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Change request not found")
    if req.get("status") != "pending":
        raise HTTPException(409, f"Request already {req.get('status')}")
    now = _now()
    applied: dict = {}
    if req["change_type"] == "add":
        p = req.get("proposed") or {}
        eq_id = str(uuid.uuid4())
        eq_doc = {
            "id": eq_id,
            "organization_id": req.get("customer_org_id") or operator,
            "site_id": req.get("site_id") or "",
            "name": p.get("name") or "Equipment",
            "equipment_type": p.get("equipment_type") or "",
            "manufacturer": p.get("manufacturer") or "",
            "model": p.get("model") or "",
            "serial_number": p.get("serial_number") or "",
            "notes": p.get("notes") or "",
            "status": "active",
            "created_via": "engineer_proposal",
            "created_by_id": req.get("engineer_id"),
            "created_at": now, "updated_at": now,
        }
        await db.equipment.insert_one(eq_doc)
        applied = {"equipment_id": eq_id}
    else:
        eq_id = req.get("equipment_id")
        await db.equipment.update_one(
            {"id": eq_id},
            {"$set": {"status": "archived", "archived_at": now,
                      "archived_by": user.get("full_name") or user.get("email"),
                      "updated_at": now}})
        applied = {"equipment_id": eq_id, "archived": True}
    await db.svc_equipment_change_requests.update_one(
        {"id": req_id, "organization_id": operator},
        {"$set": {"status": "approved", "decided_by": user["id"],
                  "decided_by_name": user.get("full_name") or user.get("email"),
                  "decided_at": now, "decision_note": (data.get("note") or "").strip(),
                  "applied": applied, "updated_at": now}})
    return {"success": True, "applied": applied}


@router.post("/desk/equipment-change-requests/{req_id}/reject")
async def reject_change_request(req_id: str, data: dict = Body(default={}), user=Depends(get_current_user)) -> dict:
    operator = _operator(user)
    req = await db.svc_equipment_change_requests.find_one(
        {"id": req_id, "organization_id": operator}, {"_id": 0, "status": 1})
    if not req:
        raise HTTPException(404, "Change request not found")
    if req.get("status") != "pending":
        raise HTTPException(409, f"Request already {req.get('status')}")
    now = _now()
    await db.svc_equipment_change_requests.update_one(
        {"id": req_id, "organization_id": operator},
        {"$set": {"status": "rejected", "decided_by": user["id"],
                  "decided_by_name": user.get("full_name") or user.get("email"),
                  "decided_at": now, "decision_note": (data.get("note") or "").strip(),
                  "updated_at": now}})
    return {"success": True}
