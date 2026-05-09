"""Equipment back-in-service member notifier — Iter 216aw · Phase 4 #7.

Cross-module signal: when a fault transitions to ``resolved`` on an
equipment row that members can see (treadmill, bike, etc.), give the
operator a one-click way to broadcast a "back in service" message to
their membership base via the Comms Hub.

Endpoints:
  • GET  /api/memberships/back-in-service-notices
        → recent fault-resolutions in the last N days (default 7), with
          equipment + duration metadata + "already broadcast?" flag.
  • POST /api/memberships/back-in-service-notices/{issue_id}/broadcast
        → marks the notice as broadcast and writes a Comms-Hub
          announcement to the org-wide #general channel. Idempotent.

Module gate: requires BOTH `operations` and `memberships` access. Without
both modules enabled, this surface is invisible (cross-module value-add).
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from utils.module_access import resolve_module_access

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _require_dual_modules(user: dict) -> str:
    """Equipment back-in-service is a cross-module feature — both
    Operations and Memberships must be enabled, otherwise the endpoint
    is invisible (404). Returns the org_id."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "User has no organization")
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "modules": 1, "module_trials": 1, "account_type": 1},
    ) or {}
    access = resolve_module_access(user, org)
    if not (access.get("operations") and access.get("memberships")):
        raise HTTPException(404, "Endpoint requires both Operations and Memberships modules")
    return org_id


# ────────────────────── List recent notices ──────────────────────


@router.get("/memberships/back-in-service-notices")
async def list_back_in_service_notices(
    days: int = Query(7, ge=1, le=60),
    user: dict = Depends(get_current_user),
):
    """Recent equipment fault-resolutions visible as 'back in service'
    candidates. Joins `issues` with `equipment` to surface human-friendly
    naming and the broadcast-status flag."""
    org_id = await _require_dual_modules(user)

    since = (_now() - timedelta(days=days)).isoformat()

    issues = await db.issues.find(
        {
            "organization_id": org_id,
            "status": "resolved",
            "resolved_at": {"$gte": since},
            "equipment_id": {"$ne": None},
        },
        {"_id": 0, "id": 1, "equipment_id": 1, "title": 1, "fault_type": 1,
         "site_id": 1, "resolved_at": 1, "created_at": 1,
         "back_in_service_broadcast_at": 1},
    ).sort("resolved_at", -1).to_list(200)

    if not issues:
        return {"notices": [], "days": days}

    eq_ids = list({i["equipment_id"] for i in issues if i.get("equipment_id")})
    eq_map: dict[str, dict] = {}
    if eq_ids:
        async for eq in db.equipment.find(
            {"id": {"$in": eq_ids}, "organization_id": org_id},
            {"_id": 0, "id": 1, "name": 1, "category": 1, "manufacturer": 1, "site_id": 1},
        ):
            eq_map[eq["id"]] = eq

    notices = []
    for i in issues:
        eq = eq_map.get(i.get("equipment_id"))
        if not eq:
            continue
        try:
            opened = datetime.fromisoformat(str(i.get("created_at")).replace("Z", "+00:00"))
            resolved = datetime.fromisoformat(str(i.get("resolved_at")).replace("Z", "+00:00"))
            downtime_h = round((resolved - opened).total_seconds() / 3600, 1)
        except (TypeError, ValueError):
            downtime_h = None
        notices.append({
            "issue_id": i["id"],
            "equipment_id": eq["id"],
            "equipment_name": eq.get("name"),
            "equipment_category": eq.get("category"),
            "manufacturer": eq.get("manufacturer"),
            "site_id": eq.get("site_id") or i.get("site_id"),
            "fault_summary": i.get("title"),
            "fault_type": i.get("fault_type"),
            "downtime_hours": downtime_h,
            "resolved_at": i.get("resolved_at"),
            "broadcast_at": i.get("back_in_service_broadcast_at"),
        })
    return {"notices": notices, "days": days}


# ────────────────────── Broadcast a notice ──────────────────────


class BroadcastBody(BaseModel):
    custom_message: str | None = None
    site_id: str | None = None  # restrict broadcast to one site


@router.post("/memberships/back-in-service-notices/{issue_id}/broadcast")
async def broadcast_notice(
    issue_id: str,
    body: BroadcastBody = Body(default_factory=BroadcastBody),
    user: dict = Depends(get_current_user),
):
    """Mark the notice as broadcast and post a Comms Hub announcement.

    Idempotent — a second call returns the existing announcement_id.
    """
    org_id = await _require_dual_modules(user)
    issue = await db.issues.find_one(
        {"id": issue_id, "organization_id": org_id, "status": "resolved"},
        {"_id": 0},
    )
    if not issue:
        raise HTTPException(404, "Resolved issue not found in your org")

    # Idempotency check — if already broadcast within the last 24h, return
    # the original announcement id so the UI doesn't double-post.
    if issue.get("back_in_service_broadcast_at"):
        return {
            "ok": True,
            "already_broadcast": True,
            "announcement_id": issue.get("back_in_service_announcement_id"),
        }

    eq = await db.equipment.find_one(
        {"id": issue.get("equipment_id"), "organization_id": org_id},
        {"_id": 0, "id": 1, "name": 1},
    ) or {}
    eq_label = eq.get("name") or "An equipment item"
    msg = body.custom_message or f"Good news — {eq_label} is back in service. Thanks for your patience."

    # Write to the comms_announcements collection (Phase S3 infrastructure).
    announcement_id = str(uuid.uuid4())
    now_iso = _now().isoformat()
    await db.comms_announcements.insert_one({
        "id": announcement_id,
        "organization_id": org_id,
        "channel_id": "general",
        "title": f"{eq_label} — back in service",
        "body": msg,
        "kind": "back_in_service",
        "site_id": body.site_id,
        "source_issue_id": issue_id,
        "source_equipment_id": eq.get("id"),
        "created_at": now_iso,
        "created_by": user.get("email"),
        "read_count": 0,
        "ack_count": 0,
    })

    await db.issues.update_one(
        {"id": issue_id},
        {"$set": {
            "back_in_service_broadcast_at": now_iso,
            "back_in_service_announcement_id": announcement_id,
        }},
    )

    return {
        "ok": True,
        "already_broadcast": False,
        "announcement_id": announcement_id,
        "message": msg,
    }
