"""Master Admin observability + manual trigger for the equipment image
backfill pipeline (`utils.equipment_image_cron`).

Endpoints:
    GET  /api/master-admin/equipment-images/status
    POST /api/master-admin/equipment-images/backfill-now
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends

from utils.database import db
from utils.auth import get_current_user
from routes.master_admin import (
    PULSE_VISIBLE_ACCOUNT_TYPES,
    is_pulse_only,
    require_master_admin,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _next_monday_03_utc(now: datetime) -> str:
    """Compute the next Monday 03:00 UTC after ``now`` (the cron's window)."""
    days_ahead = (0 - now.weekday()) % 7  # 0 = Monday
    target = (now + timedelta(days=days_ahead)).replace(hour=3, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=7)
    return target.isoformat()


async def _scoped_org_filter(user: dict) -> dict:
    """Return the equipment-collection filter expression scoped to the
    caller's view (Pulse-only admins see only Pulse-visible orgs)."""
    if not is_pulse_only(user):
        return {}
    pulse_orgs = await db.organizations.find(
        {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
        {"_id": 0, "id": 1},
    ).to_list(length=None)
    return {"organization_id": {"$in": [o["id"] for o in pulse_orgs]}}


@router.get("/master-admin/equipment-images/status")
async def equipment_images_status(user: dict = Depends(get_current_user)) -> dict:
    """Snapshot of the AI image backfill pipeline."""
    require_master_admin(user)
    now = datetime.now(timezone.utc)
    scope = await _scoped_org_filter(user)

    missing_query = {
        **scope,
        "photo_url": {"$in": [None, ""]},
        "auto_image_url": {"$in": [None, ""]},
    }
    has_auto_query = {**scope, "auto_image_url": {"$nin": [None, ""]}}
    has_user_query = {**scope, "photo_url": {"$nin": [None, ""]}}

    missing_total = await db.equipment.count_documents(missing_query)
    has_auto = await db.equipment.count_documents(has_auto_query)
    has_user = await db.equipment.count_documents(has_user_query)
    total = await db.equipment.count_documents(scope)

    # Verified-by-vision sub-count (auto images that survived stage-2 GPT-4o vision check)
    verified = await db.equipment.count_documents({**has_auto_query, "auto_image_verified": True})

    # Recent backfill runs (audit trail).
    recent = await db.equipment_image_backfill_runs.find(
        {}, {"_id": 0},
    ).sort("at", -1).to_list(length=8)
    last_run = recent[0] if recent else None

    return {
        "ok": True,
        "totals": {
            "total_equipment": total,
            "with_user_photo": has_user,
            "with_auto_image": has_auto,
            "auto_verified_by_vision": verified,
            "missing_image": missing_total,
        },
        "last_run": last_run,
        "recent_runs": recent,
        "next_run_at": _next_monday_03_utc(now),
        "schedule": "Mondays 03:00 UTC",
        "scoped": is_pulse_only(user),
    }


@router.post("/master-admin/equipment-images/backfill-now")
async def equipment_images_backfill_now(
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Out-of-band manual trigger. Runs the same lookup pipeline used by the
    weekly cron, ignoring the Monday-03:00 schedule check, and respects an
    optional ``limit`` cap (default 25, max 200) to keep the operator's wait
    short. Returns the per-run summary inline.
    """
    require_master_admin(user)

    try:
        limit = int(body.get("limit") or 25)
    except (TypeError, ValueError):
        limit = 25
    limit = max(1, min(limit, 200))

    # Lazy-import the cron to avoid circular imports + keep cold-start fast.
    from utils.equipment_image_cron import (  # type: ignore
        GLOBAL_CAP,
        _now_iso,
        get_manufacturer_domain,
        lookup_equipment_image,
    )

    scope = await _scoped_org_filter(user)
    eq_filter = {
        **scope,
        "photo_url": {"$in": [None, ""]},
        "auto_image_url": {"$in": [None, ""]},
    }
    candidates = await db.equipment.find(eq_filter, {"_id": 0}).limit(limit).to_list(length=limit)

    processed = 0
    matched = 0
    skipped_no_manufacturer = 0
    failures = 0

    for eq in candidates:
        if processed >= GLOBAL_CAP:
            break
        processed += 1
        manufacturer = eq.get("manufacturer") or eq.get("supplier") or ""
        if not get_manufacturer_domain(manufacturer):
            skipped_no_manufacturer += 1
            continue
        try:
            result = await lookup_equipment_image(
                manufacturer=manufacturer,
                name=eq.get("name"),
                equipment_type=eq.get("equipment_type"),
                verify=True,
            )
            if result and result.get("image_url"):
                await db.equipment.update_one(
                    {"id": eq["id"]},
                    {"$set": {
                        "auto_image_url": result["image_url"],
                        "auto_image_source_url": result.get("source_url"),
                        "auto_image_verified": bool(result.get("verified")),
                        "auto_image_looked_up_at": _now_iso(),
                    }},
                )
                matched += 1
        except Exception as exc:  # pragma: no cover — defensive
            logger.info("[equipment-images-manual] lookup failed for %s: %s", eq.get("id"), exc)
            failures += 1

    summary = {
        "ok": True,
        "trigger": "manual",
        "triggered_by": user.get("email"),
        "processed": processed,
        "matched": matched,
        "skipped_no_manufacturer": skipped_no_manufacturer,
        "failures": failures,
        "limit_requested": limit,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    # Persist alongside the weekly runs so the audit trail is unified.
    await db.equipment_image_backfill_runs.insert_one(
        {**summary, "date": datetime.now(timezone.utc).date().isoformat()},
    )
    return summary


__all__ = ["router"]
