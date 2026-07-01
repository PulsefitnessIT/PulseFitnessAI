from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from utils.auth import get_current_user
from utils.audit import audit_log
from utils.database import db
from utils.svc_state import (
    OPEN_STATES, TERMINAL_STATES,
    ASSIGNED, NEW, TRIAGED, EN_ROUTE, ON_SITE,
    PAUSED_PARTS, PAUSED_CUSTOMER, REPAIRED, AWAITING_SIGN_OFF,
)
from routes.svc.scheduler import _score_engineers_for_case, _drive_minutes_estimate
from routes.svc.diary import admin_assign_case, AssignIn, _require_dispatcher
from routes.partners import require_engineer_app_access
from ._shared import *  # noqa: F401,F403


@engineer_router.get("")
async def my_schedule_changes(user=Depends(get_current_user)):
    of = _of(user)
    cutoff = (_now_dt() - timedelta(hours=48)).isoformat()
    rows = await db.scheduling_changes.find(
        {**of, "engineer_id": user["id"], "acknowledged": False,
         "created_at": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    return {"changes": rows, "count": len(rows)}


@engineer_router.post("/{change_id}/ack")
async def ack_schedule_change(change_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.scheduling_changes.update_one(
        {**of, "id": change_id, "engineer_id": user["id"]},
        {"$set": {"acknowledged": True, "acknowledged_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Change not found")
    return {"ok": True}


@engineer_router.post("/ack-all")
async def ack_all_schedule_changes(user=Depends(get_current_user)):
    of = _of(user)
    res = await db.scheduling_changes.update_many(
        {**of, "engineer_id": user["id"], "acknowledged": False},
        {"$set": {"acknowledged": True, "acknowledged_at": _now()}},
    )
    return {"ok": True, "acknowledged": res.modified_count}


# ── Settings ──────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    return {"settings": await _get_settings(of["organization_id"])}


@router.put("/settings")
async def put_settings(body: dict = Body(...), user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    allowed = set(_SETTINGS_DEFAULTS.keys())
    patch = {k: v for k, v in (body or {}).items() if k in allowed}
    patch["updated_at"] = _now()
    patch["updated_by"] = user.get("id")
    await db.scheduling_settings.update_one(
        {"organization_id": of["organization_id"]},
        {"$set": {"organization_id": of["organization_id"], **patch}},
        upsert=True,
    )
    await _audit(of["organization_id"], None, "settings_updated", user,
                 ", ".join(k for k in patch if k not in ("updated_at", "updated_by")))
    return {"settings": await _get_settings(of["organization_id"])}


# ── Customer comms on reschedule (gated) ─────────────────────────
