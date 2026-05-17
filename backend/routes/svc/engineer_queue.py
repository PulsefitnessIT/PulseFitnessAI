"""
GymAxis Service Operations — Engineer Self-Allocation Queue.

Iter 216h147 (Phase 5 follow-on).

Lets a field engineer see all unassigned org-wide jobs and atomically
self-claim one without a dispatcher. Race-safe via Mongo
`find_one_and_update` with `assigned_engineer_id == null` precondition,
so two engineers can never grab the same job.

Endpoints (gated by `require_engineer_app_access`):
  GET  /api/svc/engineer/queue/unassigned       — list jobs needing an engineer
  GET  /api/svc/engineer/queue/stats            — quick stat strip (open / risk / today)
  POST /api/svc/engineer/queue/{case_id}/claim  — atomically assign to caller
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/svc/engineer/queue",
    tags=["Service Ops · Engineer Queue"],
    dependencies=[Depends(require_engineer_app_access)],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _unassigned_query(org_id: str) -> dict:
    """An 'unassigned' job is one that's still open and either has no
    engineer set, or no scheduled time set, or has been explicitly
    marked as needing pickup."""
    return {
        "organization_id": org_id,
        "status": {"$nin": ["closed", "invoiced", "cancelled", "void"]},
        "$or": [
            {"assigned_engineer_id": {"$in": [None, ""]}},
            {"assigned_engineer_id": {"$exists": False}},
        ],
    }


@router.get("/unassigned")
async def list_unassigned(
    priority: Optional[str] = Query(None, description="P1|P2|P3|P4 — optional filter"),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
):
    of = _of(user)
    q = _unassigned_query(of["organization_id"])
    if priority:
        q["priority"] = priority.upper()
    rows = await db.svc_cases.find(
        q,
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
         "status": 1, "site_name": 1, "site_postcode": 1, "customer_name": 1,
         "scheduled_at": 1, "sla_resolve_at": 1, "estimated_minutes": 1,
         "intake_channel": 1, "description": 1, "created_at": 1},
    ).sort([("priority", 1), ("sla_resolve_at", 1), ("created_at", -1)]) \
     .limit(limit).to_list(limit)
    return {"jobs": rows, "count": len(rows)}


@router.get("/stats")
async def queue_stats(user=Depends(get_current_user)):
    of = _of(user)
    base = _unassigned_query(of["organization_id"])
    total = await db.svc_cases.count_documents(base)
    today = datetime.now(timezone.utc).date().isoformat()
    risk_cutoff = datetime.now(timezone.utc).replace(microsecond=0)
    risk_cutoff_iso = risk_cutoff.isoformat()
    risk = await db.svc_cases.count_documents({
        **base, "sla_resolve_at": {"$lt": risk_cutoff_iso},
    })
    p1 = await db.svc_cases.count_documents({**base, "priority": "P1"})
    return {"total": total, "p1": p1, "sla_breached_or_due": risk, "date": today}


class ClaimIn(BaseModel):
    scheduled_at: Optional[str] = Field(
        None, description="Optional ISO datetime — when you plan to start"
    )
    estimated_minutes: Optional[int] = Field(None, ge=15, le=600)


@router.post("/{case_id}/claim")
async def claim_case(
    case_id: str,
    body: ClaimIn = Body(default_factory=ClaimIn),
    user=Depends(get_current_user),
):
    of = _of(user)
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], **of}, {"_id": 0, "id": 1, "full_name": 1},
    )
    if not eng:
        raise HTTPException(403, "Engineer profile required to claim jobs")
    if body.scheduled_at:
        try:
            datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "scheduled_at must be ISO datetime")

    upd = {
        "assigned_engineer_id": user["id"],
        "assigned_engineer_name": eng.get("full_name"),
        "self_claimed_at": _now(),
        "updated_at": _now(),
    }
    if body.scheduled_at:
        upd["scheduled_at"] = body.scheduled_at
    if body.estimated_minutes:
        upd["estimated_minutes"] = body.estimated_minutes

    # Race-safe: only assign if still unassigned.
    result = await db.svc_cases.find_one_and_update(
        {
            "id": case_id, **of,
            "status": {"$nin": ["closed", "invoiced", "cancelled", "void"]},
            "$or": [
                {"assigned_engineer_id": {"$in": [None, ""]}},
                {"assigned_engineer_id": {"$exists": False}},
            ],
        },
        {"$set": upd},
        projection={"_id": 0, "id": 1, "reference": 1, "title": 1,
                    "site_name": 1, "scheduled_at": 1, "priority": 1},
        return_document=True,  # equivalent of pymongo ReturnDocument.AFTER → True
    )
    if not result:
        # Could be: not found, already claimed, or closed.
        existing = await db.svc_cases.find_one(
            {"id": case_id, **of},
            {"_id": 0, "assigned_engineer_id": 1, "status": 1, "reference": 1,
             "assigned_engineer_name": 1},
        )
        if not existing:
            raise HTTPException(404, "Job not found")
        if existing.get("status") in ("closed", "invoiced", "cancelled", "void"):
            raise HTTPException(409, {"code": "closed",
                                      "detail": f"Job is {existing['status']}"})
        raise HTTPException(409, {
            "code": "already_claimed",
            "detail": f"Already claimed by {existing.get('assigned_engineer_name') or 'another engineer'}",
            "reference": existing.get("reference"),
        })

    # Fire an in-app notification to the claimer themselves so it
    # surfaces in the bell badge ("you took job X"). Best-effort.
    try:
        from routes.svc.notifications import create_notification
        await create_notification(
            user_id=user["id"],
            organization_id=of["organization_id"],
            kind="job_self_claimed",
            title=f"Claimed: {result.get('reference')} · {result.get('title') or ''}",
            body=(result.get("site_name") or "Site TBC") +
                 (f" — scheduled {result['scheduled_at'][:16]}" if result.get("scheduled_at") else ""),
            link=f"/svc/engineer/jobs/{case_id}",
            source_type="case",
            source_id=case_id,
            fire_push=False,  # no need to push to the engineer's own device — they just tapped it
        )
    except Exception:
        pass

    return {"ok": True, "case_id": case_id, "reference": result.get("reference"),
            "scheduled_at": result.get("scheduled_at")}


__all__ = ["router"]
