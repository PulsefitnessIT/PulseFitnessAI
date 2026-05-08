"""
Proactive-nudge API — surfaces open trust_events (type="nudge.*") scoped to
the caller's organization so the dashboard can render a gentle banner.

Endpoints (all /api prefixed by the router registration):
  GET    /nudges                → list open nudges for the caller's org
  POST   /nudges/{id}/dismiss   → mark a nudge acknowledged (owner/manager only)
  POST   /nudges/run            → master-admin manual trigger (for QA)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.proactive_nudges import run_proactive_nudges

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_manager(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    if user.get("role") not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Only owners or managers can dismiss nudges")


@router.get("/nudges")
async def list_nudges(user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        return {"nudges": [], "count": 0}
    cursor = db.trust_events.find(
        {
            "org_id": org_id,
            "type": {"$regex": r"^nudge\."},
            "state": "open",
        },
        {"_id": 0, "id": 1, "type": 1, "severity": 1, "summary": 1,
         "customer_safe_message": 1, "payload": 1, "created_at": 1,
         "last_seen_at": 1, "state": 1, "occurrences": 1},
    ).sort("created_at", -1)
    nudges = await cursor.to_list(50)
    return {"nudges": nudges, "count": len(nudges)}


@router.post("/nudges/{nudge_id}/dismiss")
async def dismiss_nudge(nudge_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_manager(user)
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="Nudge not found")
    res = await db.trust_events.update_one(
        {"id": nudge_id, "org_id": org_id,
         "type": {"$regex": r"^nudge\."},
         "state": {"$in": ["open", "acknowledged"]}},
        {"$set": {
            "state": "acknowledged",
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_by": user.get("id"),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Nudge not found")
    return {"success": True}


@router.post("/nudges/run")
async def trigger_nudges(user: dict = Depends(get_current_user)) -> dict:
    """Master-admin manual trigger — useful for QA and demos."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    totals = await run_proactive_nudges()
    return {"success": True, **totals}
