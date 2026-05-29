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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.security_plus import rate_limit_async
from utils.social_autopilot import (
    CHANNELS, FEATURE_PILLARS,
    generate_post_for_channel, generate_daily_drafts,
    generate_tiktok_video_for_post, video_path_for_post,
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
    # Iter 220bo · F-220bo-4 — per-admin LLM-budget rate limit. Each
    # call costs a Claude completion + a Nano Banana image; 20/hour
    # is plenty for a human operator iterating in the UI and tight
    # enough to block runaway scripts on a leaked token.
    await rate_limit_async(
        f"social_generate:{user.get('id')}", max_requests=20, window_seconds=3600,
    )
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
    # Iter 220bo · F-220bo-4 — same per-admin LLM-budget rate limit
    # as /generate. The endpoint is already idempotent per-day so
    # legitimate use won't trip the limit; abuse from a leaked token
    # will.
    await rate_limit_async(
        f"social_run_now:{user.get('id')}", max_requests=20, window_seconds=3600,
    )
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
    # Also clean the on-disk video if present.
    path = video_path_for_post(post_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    res = await db.social_autopilot_posts.delete_one({"id": post_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Post not found")
    return {"ok": True, "id": post_id}


# ── Iter 220bm — Sora 2 TikTok video generation ──────────────────────


class VideoGenRequest(BaseModel):
    model: str = Field("sora-2", pattern="^(sora-2|sora-2-pro)$")
    duration: int = Field(8, ge=4, le=12)


@router.post("/posts/{post_id}/generate-video")
async def trigger_video_generation(
    post_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[VideoGenRequest] = None,
    user: dict = Depends(get_current_user),
):
    """Kick off a Sora 2 video render for an existing TikTok post.
    Returns immediately with ``video_status='generating'``; the
    operator polls ``/status`` or refreshes the post list to see it
    flip to ``ready`` (typically 2-5 minutes)."""
    _require_master_admin(user)
    # Iter 220bo · F-220bo-4 — Sora 2 is the most expensive call in
    # the autopilot (~$/clip), so the per-admin ceiling is the
    # strictest of the lot: 5 video renders per hour per user.
    await rate_limit_async(
        f"social_video_gen:{user.get('id')}", max_requests=5, window_seconds=3600,
    )
    post = await db.social_autopilot_posts.find_one({"id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(404, "Post not found")
    if post.get("channel") != "tiktok":
        raise HTTPException(400, "Video generation is TikTok-only")
    if post.get("video_status") == "generating":
        return {"ok": True, "already_running": True, "id": post_id}

    body = payload or VideoGenRequest()
    background_tasks.add_task(
        generate_tiktok_video_for_post,
        db, post_id, model=body.model, duration=body.duration,
    )
    await db.social_autopilot_posts.update_one(
        {"id": post_id},
        {"$set": {"video_status": "queued", "updated_at": _now()}},
    )
    return {"ok": True, "id": post_id, "video_status": "queued",
            "model": body.model, "duration": body.duration}


@router.get("/posts/{post_id}/video")
async def stream_video(post_id: str, user: dict = Depends(get_current_user)):
    """Stream the generated MP4 from disk. Used by the <video> tag and
    by the "Download video" link in the UI."""
    _require_master_admin(user)
    path = video_path_for_post(post_id)
    if not os.path.exists(path):
        raise HTTPException(404, "Video not found — generate it first")
    return FileResponse(
        path, media_type="video/mp4",
        filename=f"gymaxis-tiktok-{post_id[:8]}.mp4",
    )


# ── Iter 220bm — Legacy library access (delete-only) ─────────────────


@router.get("/legacy-library")
async def legacy_library_list(user: dict = Depends(get_current_user)):
    """Return rows from the OLD ``social_media_library`` collection so
    operators can clean up legacy posts now that the Catalogue →
    Social Media tab is gone. Read + delete only — no new writes."""
    _require_master_admin(user)
    rows = await db.social_media_library.find({}, {"_id": 0}).sort(
        "created_at", -1,
    ).to_list(500)
    return {"rows": rows, "count": len(rows)}


@router.delete("/legacy-library/{post_id}")
async def legacy_library_delete(
    post_id: str, user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    res = await db.social_media_library.delete_one({"id": post_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Post not found")
    return {"ok": True, "id": post_id}


__all__ = ["router", "run_daily_social_loop"]


# ── Iter 220bn — Daily Social Autopilot scheduler ────────────────────


import asyncio  # noqa: E402  — bottom-of-file to avoid circular imports
import logging  # noqa: E402

logger = logging.getLogger(__name__)


def _london_now():
    """Wall clock in Europe/London for the daily trigger."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        return _dt.now(ZoneInfo("Europe/London"))
    except Exception:  # pragma: no cover
        return datetime.now(timezone.utc)


async def _social_already_ran_today(date_str: str) -> bool:
    doc = await db.social_autopilot_runs.find_one(
        {"date": date_str}, {"_id": 0, "date": 1},
    )
    return bool(doc)


async def _stamp_social_run(date_str: str, result) -> None:
    await db.social_autopilot_runs.update_one(
        {"date": date_str},
        {"$set": {"date": date_str, "result": result, "ran_at": _now()}},
        upsert=True,
    )


async def _social_run_as_background() -> dict:
    """Server-side daily run — bypasses HTTP auth, honours
    ``channels_enabled`` config, and stamps ``social_autopilot_runs``
    so the loop is idempotent."""
    cfg = await _load_config()
    enabled_map = cfg.get("channels_enabled") or {}
    channels = [c["id"] for c in CHANNELS if enabled_map.get(c["id"], True)]
    if not channels:
        return {"ok": False, "reason": "no channels enabled"}
    try:
        return {"ok": True,
                "drafts": await generate_daily_drafts(db, channels=channels)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[social-autopilot] daily run failed: %s", exc)
        return {"ok": False, "reason": str(exc)[:200]}


async def run_daily_social_loop(*, hour: int = 9) -> None:
    """Background loop — checks every 15 minutes whether it's the
    configured London-time hour AND we haven't yet fired today. Mirrors
    the SEO autopilot loop so the operator sees three fresh social
    drafts in their morning inbox alongside the SEO article.

    The hour is read from the persisted ``social_autopilot_config``
    every iteration, so the master admin's UI toggle takes effect
    without a backend restart. The ``hour`` kwarg is only the cold-boot
    fallback before the first config save."""
    while True:
        try:
            cfg = await _load_config()
            cfg_enabled = bool(cfg.get("enabled", True))
            cfg_hour = int(cfg.get("hour_uk") or hour)
            london = _london_now()
            today = london.date().isoformat()
            if (
                cfg_enabled
                and london.hour == cfg_hour
                and not await _social_already_ran_today(today)
            ):
                logger.info(
                    "[social-autopilot] firing daily run for %s @ %02d:00 Europe/London",
                    today, cfg_hour,
                )
                result = await _social_run_as_background()
                await _stamp_social_run(today, result)
                logger.info("[social-autopilot] daily result: %s",
                            (result or {}).get("ok"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[social-autopilot] loop iteration error: %s", exc)
        await asyncio.sleep(15 * 60)
