"""Social Media Autopilot routes (Iter 220bl).

Master-admin-only endpoints that drive the Social Autopilot. Mirrors
the SEO Autopilot route shape for consistency:

  GET    /api/marketing/social-autopilot/status
  PUT    /api/marketing/social-autopilot/config
  GET    /api/marketing/social-autopilot/posts
  POST   /api/marketing/social-autopilot/generate
  POST   /api/marketing/social-autopilot/run-now
  POST   /api/marketing/social-autopilot/posts/{id}/approve
  POST   /api/marketing/social-autopilot/posts/{id}/archive
  DELETE /api/marketing/social-autopilot/posts/{id}
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.social_autopilot import (
    CHANNELS, FEATURE_PILLARS,
    generate_post_for_channel, generate_daily_drafts,
)


router = APIRouter(prefix="/api/marketing/social-autopilot", tags=["social-autopilot"])


def _require_master_admin(user: dict) -> None:
    if not (user or {}).get("is_master_admin"):
        raise HTTPException(403, "Master admin only")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_collection():
    return db.social_autopilot_config


async def _load_config() -> dict:
    doc = await _config_collection().find_one({"id": "singleton"}, {"_id": 0})
    if doc:
        return doc
    hour = int(os.environ.get("SOCIAL_AUTOPILOT_HOUR", "10"))
    return {
        "id": "singleton",
        "enabled": os.environ.get("SOCIAL_AUTOPILOT_ENABLED", "1") != "0",
        "hour_uk": max(0, min(23, hour)),
        "channels_enabled": {"instagram": True, "tiktok": True, "linkedin": True},
        "updated_at": None,
        "updated_by": None,
    }


class SocialConfigPayload(BaseModel):
    enabled: Optional[bool] = None
    hour_uk: Optional[int] = Field(None, ge=0, le=23)
    channels_enabled: Optional[dict] = None


# ── Status / Config ──────────────────────────────────────────────────


@router.get("/status")
async def status(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    cfg = await _load_config()
    today = datetime.now(timezone.utc).date().isoformat()
    last = await db.social_autopilot_runs.find_one({}, {"_id": 0},
                                                    sort=[("date", -1)])
    ran_today = bool(last and last.get("date") == today)
    # Channel-level draft counts so the UI can show per-channel state.
    counts = {}
    for c in CHANNELS:
        counts[c["id"]] = await db.social_autopilot_posts.count_documents(
            {"channel": c["id"], "status": "draft"},
        )
    return {
        "enabled": bool(cfg.get("enabled")),
        "hour_uk": int(cfg.get("hour_uk", 10)),
        "channels_enabled": cfg.get("channels_enabled", {}),
        "channels": CHANNELS,
        "feature_pillars": FEATURE_PILLARS,
        "draft_counts": counts,
        "ran_today": ran_today,
        "last_run": last or None,
    }


@router.put("/config")
async def update_config(
    payload: SocialConfigPayload,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
               if v is not None}
    if not updates:
        return await _load_config()
    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("id")
    await _config_collection().update_one(
        {"id": "singleton"},
        {"$set": updates, "$setOnInsert": {"id": "singleton"}},
        upsert=True,
    )
    return await _load_config()


# ── Posts list / lifecycle ───────────────────────────────────────────


@router.get("/posts")
async def list_posts(
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    q: dict = {}
    if channel:
        q["channel"] = channel
    if status:
        q["status"] = status
    cursor = db.social_autopilot_posts.find(q, {"_id": 0})
    rows = await cursor.sort("created_at", -1).limit(limit).to_list(limit)
    return {"posts": rows, "count": len(rows)}


class GenerateRequest(BaseModel):
    channel: str
    topic_kind: Optional[str] = None  # forces feature/industry; otherwise auto


@router.post("/generate")
async def generate_one(
    payload: GenerateRequest,
    user: dict = Depends(get_current_user),
):
    """Generate ONE draft for a specific channel. Used by the
    "Generate {channel} post" buttons in the UI."""
    _require_master_admin(user)
    if payload.channel not in {c["id"] for c in CHANNELS}:
        raise HTTPException(400, "Unknown channel")
    doc = await generate_post_for_channel(db, payload.channel)
    return doc


@router.post("/run-now")
async def run_now(user: dict = Depends(get_current_user)):
    """Generate today's drafts for ALL enabled channels (one per
    channel). Idempotent on (date) — already-fired-today returns
    early so the daily cron + manual button can't double-fire."""
    _require_master_admin(user)
    cfg = await _load_config()
    today = datetime.now(timezone.utc).date().isoformat()
    existing = await db.social_autopilot_runs.find_one({"date": today})
    if existing:
        return {"ok": False, "reason": "already ran today", "date": today,
                "result": existing.get("result")}
    enabled_map = cfg.get("channels_enabled") or {}
    channels = [c["id"] for c in CHANNELS
                if enabled_map.get(c["id"], True)]
    drafts = await generate_daily_drafts(db, channels=channels)
    await db.social_autopilot_runs.update_one(
        {"date": today},
        {"$set": {"date": today, "ran_at": _now(), "result": drafts}},
        upsert=True,
    )
    return {"ok": True, "date": today, "result": drafts}


@router.post("/posts/{post_id}/approve")
async def approve_post(post_id: str, user: dict = Depends(get_current_user)):
    """Mark a draft as 'approved' so the operator knows it's ready to
    post manually. Approved posts stay in the list but get a green
    pill in the UI."""
    _require_master_admin(user)
    res = await db.social_autopilot_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "approved", "approved_at": _now(),
                  "approved_by": user.get("id"), "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Post not found")
    return {"ok": True, "id": post_id, "status": "approved"}


@router.post("/posts/{post_id}/archive")
async def archive_post(post_id: str, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    res = await db.social_autopilot_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "archived", "archived_at": _now(),
                  "archived_by": user.get("id"), "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Post not found")
    return {"ok": True, "id": post_id, "status": "archived"}


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    res = await db.social_autopilot_posts.delete_one({"id": post_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Post not found")
    return {"ok": True, "id": post_id}


__all__ = ["router"]
