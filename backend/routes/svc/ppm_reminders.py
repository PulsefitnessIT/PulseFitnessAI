"""GymAxis Service Operations — PPM-due notification sweeper (Iter 220dm).

`ppm_due` was declared in ``PUSH_NOTIFICATION_KINDS`` but nothing
actually fired it. This module closes the loop by adding a sweep
endpoint that:

  * Finds open PPM cases (``case_type='ppm'``, status ∈ open) that are
    scheduled within the next ``hours_ahead`` window (default 24h).
  * For each, creates a ``ppm_due`` notification for the assigned
    engineer (which fans out to Web Push via the existing pipeline).
  * Deduplicates: same case → at most one notification per
    ``DEDUPE_WINDOW_HOURS`` (default 18h) to avoid spamming the
    engineer when a daily cron + a manual trigger both hit.

Operator hits this from the master-admin dashboard or wires it to
an external cron once per shift. Idempotent + safe to run multiple
times in the same window.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


DEDUPE_WINDOW_HOURS = 18
DEFAULT_HOURS_AHEAD = 24
OPEN_STATES = {"new", "scheduled", "assigned"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_admin(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    if (user.get("role") or "").lower() in ("owner", "manager"):
        return
    raise HTTPException(403, "Owner / Manager / Master Admin required")


async def _ppm_due_was_recently_sent(case_id: str, user_id: str) -> bool:
    """Dedupe guard: returns True when a ``ppm_due`` notification was
    already created for this case+engineer within the last
    ``DEDUPE_WINDOW_HOURS``."""
    cutoff = (_now() - timedelta(hours=DEDUPE_WINDOW_HOURS)).isoformat()
    existing = await db.svc_notifications.find_one(
        {
            "kind": "ppm_due",
            "source_type": "case",
            "source_id": case_id,
            "user_id": user_id,
            "created_at": {"$gte": cutoff},
        },
        {"_id": 0, "id": 1},
    )
    return existing is not None


@router.post("/svc/admin/ppm/fire-due-reminders")
async def fire_ppm_due_reminders(
    hours_ahead: int = Query(
        DEFAULT_HOURS_AHEAD, ge=1, le=168,
        description="Look forward window for PPM jobs (1–168 h).",
    ),
    organization_id: Optional[str] = Query(
        None,
        description="Master-Admin only — sweep one tenant explicitly.",
    ),
    user=Depends(get_current_user),
):
    """Sweep open PPM jobs and emit a ``ppm_due`` notification for
    each assigned engineer. Returns counts so the operator can see
    what fired."""
    _require_admin(user)
    now = _now()
    cutoff = (now + timedelta(hours=hours_ahead)).isoformat()
    earliest = now.isoformat()

    # Master-admin can target a specific org; others always scoped to their own.
    flt: dict = {
        "case_type": "ppm",
        "status": {"$in": list(OPEN_STATES)},
        "assigned_engineer_id": {"$exists": True, "$ne": None},
        "scheduled_at": {"$gte": earliest, "$lte": cutoff},
    }
    if user.get("is_master_admin") and organization_id:
        flt["organization_id"] = organization_id
    elif not user.get("is_master_admin"):
        flt["organization_id"] = (user.get("organization_id") or user.get("service_org_id"))

    cases = await db.svc_cases.find(
        flt,
        {
            "_id": 0, "id": 1, "reference": 1, "title": 1, "site_name": 1,
            "scheduled_at": 1, "assigned_engineer_id": 1,
            "organization_id": 1,
        },
    ).sort("scheduled_at", 1).limit(500).to_list(500)

    fired = 0
    skipped_dupe = 0
    skipped_self_assigned_only = 0

    from routes.svc.notifications import create_notification

    for c in cases:
        eng = c.get("assigned_engineer_id")
        if not eng:
            skipped_self_assigned_only += 1
            continue
        if await _ppm_due_was_recently_sent(c["id"], eng):
            skipped_dupe += 1
            continue
        try:
            when_str = datetime.fromisoformat(
                c["scheduled_at"].replace("Z", "+00:00"),
            ).strftime("%a %d %b · %H:%M")
        except Exception:
            when_str = "soon"
        ref = c.get("reference") or c["id"][:8]
        site = c.get("site_name") or "Site"
        try:
            await create_notification(
                user_id=eng,
                organization_id=c["organization_id"],
                kind="ppm_due",
                title=f"PPM due: {ref}",
                body=f"{site} — scheduled {when_str}",
                link=f"/svc/engineer/jobs/{c['id']}",
                source_type="case",
                source_id=c["id"],
            )
            fired += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("ppm_due notify failed for case=%s: %s", c["id"], exc)

    return {
        "ok": True,
        "scanned": len(cases),
        "fired": fired,
        "skipped_dupe": skipped_dupe,
        "skipped_unassigned": skipped_self_assigned_only,
        "window_hours_ahead": hours_ahead,
    }


__all__ = ["router", "DEDUPE_WINDOW_HOURS"]
