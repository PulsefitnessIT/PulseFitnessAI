"""Iter 216h136 — Engineer App Phase 3.5: Parts Request Workflow.

When an engineer encounters a part on a job that isn't in their van
stock (or isn't in the catalogue at all), they file a "parts request".
A master/operator admin sees these in a dedicated inbox, approves or
rejects them. On approve, the part is automatically allocated to the
case (and to the engineer's van) so it shows up on the next page
refresh in the Parts tab.

Endpoints (engineer-facing, gated by `require_engineer_app_access`):
  • POST   /api/svc/engineer/parts-requests
      Body: {case_id, part_sku, part_name?, qty, urgency?, notes?}
      → svc_parts_requests doc with status="pending"
  • GET    /api/svc/engineer/parts-requests           — my own requests
  • DELETE /api/svc/engineer/parts-requests/{id}      — cancel (pending only)

Admin-facing (master/operator admin):
  • GET    /api/admin/parts-requests                  — inbox (filterable)
  • POST   /api/admin/parts-requests/{id}/approve
      Body: {ship_from?: 'warehouse' | 'supplier_direct', supplier_ref?, notes?}
  • POST   /api/admin/parts-requests/{id}/reject
      Body: {reason}
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access
from routes.svc.integrations import sicon_sync
from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db
from utils.svc_state import append_event

logger = logging.getLogger(__name__)


URGENCIES = {"normal", "urgent", "critical"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _is_admin(user: dict) -> bool:
    return bool(user.get("is_master_admin")
                or user.get("is_pulse_admin")
                or user.get("account_type") == "gymaxis_admin"
                or (user.get("role") or "") in {"owner", "owner_admin", "manager"})


def _strip(doc):
    if isinstance(doc, dict):
        doc.pop("_id", None)
    return doc


# ──────────────────────────── Engineer side ─────────────────────────


engineer_router = APIRouter(
    prefix="/svc/engineer/parts-requests",
    tags=["Service Ops · Engineer Parts Requests"],
    dependencies=[Depends(require_engineer_app_access)],
)


class PartsRequestIn(BaseModel):
    case_id: str
    part_sku: str = Field(..., min_length=1)
    part_name: Optional[str] = None
    qty: int = Field(..., gt=0, le=999)
    urgency: str = Field(default="normal")
    notes: Optional[str] = ""


@engineer_router.post("", status_code=201)
async def create_request(body: PartsRequestIn, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": body.case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    urgency = body.urgency.lower()
    if urgency not in URGENCIES:
        raise HTTPException(422, f"urgency must be one of {sorted(URGENCIES)}")
    sku = body.part_sku.strip().upper()

    # Enrich from catalogue if known
    catalogue = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
    name = (body.part_name or "").strip() or (catalogue or {}).get("name") or sku
    list_price = float((catalogue or {}).get("list_price") or 0)

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": body.case_id,
        "case_reference": case.get("reference"),
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "part_sku": sku,
        "part_name": name,
        "qty": body.qty,
        "list_price_gbp": list_price,
        "urgency": urgency,
        "notes": (body.notes or "").strip(),
        "status": "pending",
        "in_catalogue": bool(catalogue),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_parts_requests.insert_one(doc)
    doc.pop("_id", None)
    await append_event(
        case_id=body.case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Parts request: {body.qty} × {sku} ({name})",
        extra={"kind": "parts_request", "request_id": doc["id"], "urgency": urgency},
    )
    return doc


@engineer_router.get("")
async def list_my_requests(case_id: Optional[str] = None, status: Optional[str] = None,
                           user=Depends(get_current_user)):
    of = _of(user)
    q = {**of, "engineer_id": user["id"]}
    if case_id:
        q["case_id"] = case_id
    if status:
        q["status"] = status
    rows = await db.svc_parts_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": rows}


@engineer_router.delete("/{request_id}")
async def cancel_request(request_id: str, user=Depends(get_current_user)):
    of = _of(user)
    req = await db.svc_parts_requests.find_one(
        {"id": request_id, **of, "engineer_id": user["id"]}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "pending":
        raise HTTPException(409, f"Cannot cancel a {req['status']} request")
    await db.svc_parts_requests.update_one(
        {"id": request_id, **of},
        {"$set": {"status": "cancelled", "cancelled_at": _now(), "updated_at": _now()}},
    )
    return {"ok": True}


# ────────────────────────────── Admin side ──────────────────────────


admin_router = APIRouter(
    prefix="/admin/parts-requests",
    tags=["Master Admin · Parts Requests"],
)


def _require_admin(user: dict) -> None:
    if not _is_admin(user):
        raise HTTPException(403, "Admin only")


class ApproveIn(BaseModel):
    ship_from: str = Field(default="warehouse")
    supplier_ref: Optional[str] = ""
    notes: Optional[str] = ""


class RejectIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=400)


@admin_router.get("")
async def admin_list_requests(status: Optional[str] = None,
                               urgency: Optional[str] = None,
                               limit: int = 100,
                               user=Depends(get_current_user)):
    _require_admin(user)
    of = _of(user)
    q = {**of}
    if status:
        q["status"] = status
    if urgency:
        q["urgency"] = urgency
    rows = await db.svc_parts_requests.find(q, {"_id": 0}) \
        .sort("created_at", -1).to_list(max(1, min(limit, 500)))
    # Counts by status (for the inbox badges)
    counts = {}
    for s in ("pending", "approved", "rejected", "cancelled"):
        counts[s] = await db.svc_parts_requests.count_documents({**of, "status": s})
    return {"items": rows, "counts": counts}


@admin_router.post("/{request_id}/approve")
async def admin_approve(request_id: str, body: ApproveIn,
                         user=Depends(get_current_user)):
    """Approve a parts request → allocate the part to the case and to
    the engineer's van so it shows up on the next refresh."""
    _require_admin(user)
    of = _of(user)
    req = await db.svc_parts_requests.find_one({"id": request_id, **of}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "pending":
        raise HTTPException(409, f"Request is {req['status']}")

    ship_from = (body.ship_from or "warehouse").strip().lower()
    if ship_from not in {"warehouse", "supplier_direct"}:
        raise HTTPException(422, "ship_from must be 'warehouse' or 'supplier_direct'")

    case = await db.svc_cases.find_one(
        {"id": req["case_id"], **of}, {"_id": 0},
    )
    if not case:
        raise HTTPException(409, "Case has been deleted — cannot allocate")

    allocation = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": req["case_id"],
        "case_reference": req.get("case_reference"),
        "part_sku": req["part_sku"],
        "part_name": req["part_name"],
        "qty": req["qty"],
        "list_price_gbp": req.get("list_price_gbp") or 0,
        "source": ship_from,
        "engineer_id": req["engineer_id"],
        "fulfilled": False,
        "allocated_by_id": user["id"],
        "allocated_by_name": user.get("full_name") or user.get("email") or "",
        "allocated_at": _now(),
        "from_request_id": request_id,
        "supplier_ref": (body.supplier_ref or "").strip() or None,
    }
    await db.svc_cases.update_one(
        {"id": req["case_id"], **of},
        {"$push": {"allocated_parts": allocation},
         "$set":  {"updated_at": _now()}},
    )
    await db.svc_part_movements.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": req["case_id"],
        "allocation_id": allocation["id"],
        "part_sku": req["part_sku"],
        "part_name": req["part_name"],
        "qty": req["qty"],
        "movement_type": "allocate",
        "source": ship_from,
        "engineer_id": req["engineer_id"],
        "actor_id": user["id"],
        "actor_name": user.get("full_name") or user.get("email") or "",
        "at": _now(),
        "from_request_id": request_id,
    })
    # Iter 216h153 — Sicon outbox push so the upstream stock-movement
    # ledger reflects the allocation (parts-request approval path was
    # missing this hook in the original Phase 8A wiring).
    try:
        case_doc = await db.svc_cases.find_one(
            {"id": req["case_id"], **of},
            {"_id": 0, "reference": 1},
        )
        await sicon_sync.push_part_movement(
            {
                **allocation,
                "case_id": req["case_id"],
                "movement_type": "allocate",
                "from_location": ship_from,
                "to_location": "case",
                "actor_id": user["id"],
                "actor_name": user.get("full_name") or user.get("email") or "",
                "at": _now(),
                "part_sku": req["part_sku"],
                "qty": req["qty"],
            },
            case_reference=(case_doc or {}).get("reference"),
        )
    except Exception as e:
        logger.warning("[svc→sicon] parts-request approve push failed: %s", e)
    # Iter 216h155 — compliance audit (parts chain-of-custody).
    try:
        await audit_log(
            action="svc.parts.approve",
            user_id=user.get("id", ""),
            user_email=user.get("email", ""),
            resource_type="svc_parts_request",
            resource_id=request_id,
            details=f"case={req.get('case_id', '')} · "
                    f"sku={req.get('part_sku')} · qty={req.get('qty')} · "
                    f"from={ship_from}",
        )
    except Exception as e:
        logger.warning("[audit] parts.approve failed: %s", e)
    await db.svc_parts_requests.update_one(
        {"id": request_id, **of},
        {"$set": {
            "status": "approved",
            "approved_at": _now(),
            "approved_by_id": user["id"],
            "approved_by_name": user.get("full_name") or user.get("email") or "",
            "ship_from": ship_from,
            "supplier_ref": (body.supplier_ref or "").strip() or None,
            "admin_notes": (body.notes or "").strip(),
            "allocation_id": allocation["id"],
            "updated_at": _now(),
        }},
    )
    await append_event(
        case_id=req["case_id"], organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Parts request approved: {req['qty']} × {req['part_sku']} via {ship_from}",
        extra={"kind": "parts_request_approved", "request_id": request_id,
               "allocation_id": allocation["id"]},
    )
    fresh = await db.svc_parts_requests.find_one({"id": request_id, **of}, {"_id": 0})
    return fresh or {"ok": True}


@admin_router.post("/{request_id}/reject")
async def admin_reject(request_id: str, body: RejectIn,
                        user=Depends(get_current_user)):
    _require_admin(user)
    of = _of(user)
    req = await db.svc_parts_requests.find_one({"id": request_id, **of}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "pending":
        raise HTTPException(409, f"Request is {req['status']}")
    await db.svc_parts_requests.update_one(
        {"id": request_id, **of},
        {"$set": {
            "status": "rejected",
            "rejected_at": _now(),
            "rejected_by_id": user["id"],
            "rejected_by_name": user.get("full_name") or user.get("email") or "",
            "reject_reason": body.reason.strip(),
            "updated_at": _now(),
        }},
    )
    await append_event(
        case_id=req["case_id"], organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Parts request rejected: {body.reason[:120]}",
        extra={"kind": "parts_request_rejected", "request_id": request_id},
    )
    fresh = await db.svc_parts_requests.find_one({"id": request_id, **of}, {"_id": 0})
    return fresh or {"ok": True}


__all__ = ["engineer_router", "admin_router"]
