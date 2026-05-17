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
from utils.slow_request_log import SLOW_REQUESTS

router = APIRouter(prefix="/master-admin/perf", tags=["master-admin-perf"])


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")


@router.get("/cache")
async def cache_stats(user: dict = Depends(get_current_user)) -> dict:
    """Aggregate observability for the in-process cache + truncation
    telemetry + slow-request log.

    Iter 216h170 added cache stats; iter 216h171 added truncation
    events; iter 216h172 added slow-request telemetry. The Master
    Admin Integration Health panel polls this single endpoint and
    renders all three sections — keeps the wire surface tight and
    the panel discovery story consistent."""
    _require_master_admin(user)
    return {
        **CACHE.stats(),
        **TRUNCATION.snapshot(),
        "slow_requests": SLOW_REQUESTS.snapshot(),
    }


@router.post("/slow-requests/clear")
async def slow_requests_clear(user: dict = Depends(get_current_user)) -> dict:
    """Drop the slow-request ring so the panel starts from a clean
    baseline (used after a fix has shipped + been deployed)."""
    _require_master_admin(user)
    cleared = SLOW_REQUESTS.reset()
    return {"cleared": cleared}


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
