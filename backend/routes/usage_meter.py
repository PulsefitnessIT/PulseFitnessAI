"""Usage meter endpoints (iter 215c0).

Surfaces the per-tenant usage summary to operator dashboards and master
admins. All endpoints return current-period counters + soft-cap warnings,
never raw billing data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.usage_tracker import get_usage_summary, record_usage

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/me")
async def my_usage(user: dict = Depends(get_current_user)) -> dict:
    """Return the current org's usage snapshot."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="User is not attached to an organisation")
    return await get_usage_summary(org_id)


@router.post("/track")
async def track_usage(payload: dict, user: dict = Depends(get_current_user)) -> dict:
    """Bump a usage counter from the frontend (e.g. after an AI call returns).

    Body: ``{"metric": "ai_tokens" | "sms" | "api_calls" | "emails", "qty": 1}``
    """
    metric = (payload or {}).get("metric")
    qty = int((payload or {}).get("qty", 1) or 0)
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organisation")
    if metric not in {"ai_tokens", "sms", "api_calls", "emails"}:
        raise HTTPException(status_code=400, detail="Unknown metric")
    await record_usage(org_id, metric, qty)
    return {"ok": True}


@router.get("/master-admin/{organization_id}")
async def admin_org_usage(organization_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Master-admin view of any org's usage."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    return await get_usage_summary(organization_id)
