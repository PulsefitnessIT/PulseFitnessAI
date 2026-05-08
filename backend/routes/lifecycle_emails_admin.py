"""Lifecycle email admin endpoints (iter 215c2).

Master-admin can preview templates and run the dispatcher on demand for
testing. Cron runs the dispatcher every 30 minutes (wired in server.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.lifecycle_emails import (
    send_lifecycle_emails,
    _welcome, _day2_check, _mid_trial, _expiry_warn, _winback,
)

router = APIRouter(prefix="/admin/lifecycle-emails", tags=["lifecycle-emails"])

PREVIEWS = {
    "welcome": _welcome,
    "day2_check": _day2_check,
    "mid_trial": _mid_trial,
    "expiry_warn": lambda name: _expiry_warn(name, 6),
    "winback": _winback,
}


@router.get("/preview/{template}")
async def preview(template: str, user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    if template not in PREVIEWS:
        raise HTTPException(status_code=404, detail=f"Unknown template: {template}")
    subj, html = PREVIEWS[template]("Sample Operator")
    return {"template": template, "subject": subj, "html": html}


@router.post("/run")
async def run_now(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    return await send_lifecycle_emails()
