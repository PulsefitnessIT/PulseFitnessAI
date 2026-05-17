"""Iter 216h170 — Master Admin performance + cache inspection endpoints.

Surfaces:
  GET  /api/master-admin/perf/cache       Cache stats (entries/hits/ratio).
  POST /api/master-admin/perf/cache/clear Drop all in-process cache entries.

Why this lives in its own file:
  • Stays out of `master_admin.py` (already 4,270 LoC — refactor target).
  • Lets us add additional perf telemetry (slow-query log, integration
    health) here without touching the legacy file.
  • Master Admin auth-gated, never reachable by tenants.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from utils.aggregate_cache import CACHE
from utils.auth import get_current_user
from utils.safe_paginate import TRUNCATION

router = APIRouter(prefix="/master-admin/perf", tags=["master-admin-perf"])


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")


@router.get("/cache")
async def cache_stats(user: dict = Depends(get_current_user)) -> dict:
    """Lightweight observability for the in-process aggregate cache.

    Useful before/after a deploy to confirm the cache is actually
    serving hits (good rule of thumb: hit_ratio should climb above
    0.6 within a couple of minutes of normal traffic on a multi-tab
    operator session). Iter 216h171 — now also surfaces pagination
    truncation events so operators can spot tenants whose dashboards
    are silently dropping tail rows."""
    _require_master_admin(user)
    return {**CACHE.stats(), **TRUNCATION.snapshot()}


@router.post("/cache/clear")
async def cache_clear(
    prefix: str = "",
    user: dict = Depends(get_current_user),
) -> dict:
    """Bust the cache. `prefix` lets you target a single namespace
    (e.g. `?prefix=v1::capex_board`) or omit it to drop everything."""
    _require_master_admin(user)
    cleared = CACHE.invalidate(prefix)
    return {"cleared": cleared, "prefix": prefix or None}


__all__ = ["router"]
