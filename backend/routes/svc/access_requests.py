"""
Iter 276b — Engineer "Request access" to an operator's machine history.

When an engineer scans an Operations QR for a machine they don't yet
cover, the history endpoint returns 403. From that lockout they can ask
the operator's service desk to add them. Approving the request grants
`svc_engineers` membership in the operator's org — which satisfies the
machine-history access rule (b) and lets the operator allocate them work.

Endpoints (all authenticated):
  Engineer:
    POST /api/svc/engineer/machine-history/{equipment_id}/request-access
  Operator service desk:
    GET  /api/svc/access-requests
    POST /api/svc/access-requests/{id}/approve
    POST /api/svc/access-requests/{id}/decline
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.svc.notifications import create_notification
from routes.svc.engineer_qr import (
    _engineer_machine_access, _engineer_brand_for_user_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Service Ops · Machine access requests (iter 276b)"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _org_id(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _require_admin(user: dict) -> None:
    role = (user.get("role") or "").lower()
    if role in ("owner", "manager", "pulse_master_admin"):
        return
    if user.get("is_master_admin") or user.get("is_pulse_admin") or user.get("is_service_desk"):
        return
    raise HTTPException(403, "Owners, managers and service desk only")


async def _notify_org_admins(org_id: str, *, title: str, body: str, link: str | None,
                             kind: str = "access_request") -> None:
    """Best-effort notification to the operator's admins/service desk."""
    try:
        cursor = db.users.find(
            {
                "organization_id": org_id,
                "$or": [
                    {"role": {"$in": ["owner", "manager"]}},
                    {"is_master_admin": True},
                    {"is_pulse_admin": True},
                    {"is_service_desk": True},
                ],
            },
            {"_id": 0, "id": 1},
        ).limit(20)
        async for u in cursor:
            await create_notification(
                user_id=u["id"], organization_id=org_id, kind=kind,
                title=title, body=body, link=link,
                source_type="access_request",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[access-request] admin notify failed: %s", exc)


class RequestAccessBody(BaseModel):
    message: Optional[str] = None


@router.post("/svc/engineer/machine-history/{equipment_id}/request-access")
async def request_machine_access(
    equipment_id: str,
    payload: RequestAccessBody,
    user=Depends(get_current_user),
):
    """Engineer asks an operator's service desk to grant machine access."""
    eq = await db.equipment.find_one(
        {"id": equipment_id},
        {"_id": 0, "id": 1, "organization_id": 1, "name": 1},
    )
    if not eq:
        raise HTTPException(404, "Machine not found")

    if await _engineer_machine_access(eq, user):
        raise HTTPException(400, "You already have access to this machine.")

    op_org = eq["organization_id"]
    eng_user_id = user["id"]
    brand = await _engineer_brand_for_user_id(eng_user_id, None)

    # Dedupe: one pending request per engineer + operator org.
    existing = await db.svc_access_requests.find_one(
        {"organization_id": op_org, "engineer_user_id": eng_user_id, "status": "pending"},
        {"_id": 0, "id": 1},
    )
    if existing:
        return {"ok": True, "status": "pending", "request_id": existing["id"],
                "message": "You've already requested access — the operator has been notified."}

    req = {
        "id": str(uuid.uuid4()),
        "organization_id": op_org,
        "equipment_id": equipment_id,
        "equipment_name": eq.get("name") or "",
        "engineer_user_id": eng_user_id,
        "engineer_name": user.get("full_name") or user.get("email") or brand,
        "engineer_email": user.get("email") or "",
        "engineer_company": brand,
        "message": (payload.message or "").strip()[:500],
        "status": "pending",
        "created_at": _now(),
        "decided_at": None,
        "decided_by_id": None,
        "decided_by_name": None,
    }
    await db.svc_access_requests.insert_one(req)

    await _notify_org_admins(
        op_org,
        title="Engineer requested machine access",
        body=f"{req['engineer_name']} ({brand}) wants access to {req['equipment_name'] or 'a machine'}.",
        link="/svc/engineers",
    )
    return {"ok": True, "status": "pending", "request_id": req["id"],
            "message": "Request sent. The operator's service desk has been notified."}


@router.get("/svc/access-requests")
async def list_access_requests(status: str = "pending", user=Depends(get_current_user)):
    """Operator: list machine-access requests for their org."""
    _require_admin(user)
    q = {"organization_id": _org_id(user)}
    if status and status != "all":
        q["status"] = status
    rows = await db.svc_access_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {"requests": rows}


async def _load_request(req_id: str, user: dict) -> dict:
    req = await db.svc_access_requests.find_one(
        {"id": req_id, "organization_id": _org_id(user)}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Request not found")
    return req


@router.post("/svc/access-requests/{req_id}/approve")
async def approve_access_request(req_id: str, user=Depends(get_current_user)):
    """Operator: approve → grant svc_engineers membership in this org."""
    _require_admin(user)
    req = await _load_request(req_id, user)
    if req["status"] != "pending":
        raise HTTPException(409, f"Request already {req['status']}")

    org_id = req["organization_id"]
    eng_id = req["engineer_user_id"]
    now = _now()

    existing = await db.svc_engineers.find_one(
        {"id": eng_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    )
    if not existing:
        await db.svc_engineers.insert_one({
            "id": eng_id,
            "organization_id": org_id,
            "full_name": req.get("engineer_name") or "",
            "email": req.get("engineer_email") or "",
            "mobile": "",
            "skills": [],
            "working_hours": {},
            "active": True,
            "external": True,
            "source": "access_request",
            "company_name": req.get("engineer_company") or "",
            "created_at": now,
            "updated_at": now,
        })

    await db.svc_access_requests.update_one(
        {"id": req_id, "organization_id": org_id},
        {"$set": {"status": "approved", "decided_at": now,
                  "decided_by_id": user["id"],
                  "decided_by_name": user.get("full_name") or user.get("email") or ""}},
    )
    await create_notification(
        user_id=eng_id, organization_id=org_id, kind="access_request",
        title="Machine access approved",
        body=f"You can now view history & be assigned work on {req.get('equipment_name') or 'the machine'}.",
        link=f"/svc/engineer/machine/{req.get('equipment_id')}",
        source_type="access_request", source_id=req_id,
    )
    return {"ok": True, "status": "approved"}


@router.post("/svc/access-requests/{req_id}/decline")
async def decline_access_request(req_id: str, user=Depends(get_current_user)):
    """Operator: decline a machine-access request."""
    _require_admin(user)
    req = await _load_request(req_id, user)
    if req["status"] != "pending":
        raise HTTPException(409, f"Request already {req['status']}")
    now = _now()
    await db.svc_access_requests.update_one(
        {"id": req_id, "organization_id": req["organization_id"]},
        {"$set": {"status": "declined", "decided_at": now,
                  "decided_by_id": user["id"],
                  "decided_by_name": user.get("full_name") or user.get("email") or ""}},
    )
    return {"ok": True, "status": "declined"}


__all__ = ["router"]
