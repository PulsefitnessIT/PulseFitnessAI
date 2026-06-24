"""Operator dashboard headline counts.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module
from utils.site_scope import build_site_filter, get_requested_site_id

from routes.memberships.helpers import (
    _require_operator_org,
)

router = APIRouter(tags=["memberships"])


# ═════════════════════ Dashboard (operator) ═════════════════════

@router.get("/memberships/dashboard", dependencies=[Depends(require_module("memberships"))])
async def operator_dashboard(
    site_id: str | None = Depends(get_requested_site_id),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    sf = build_site_filter(site_id)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = now.replace(hour=23, minute=59, second=59).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    active_members = await db.members.count_documents({"organization_id": org_id, "status": "active", **sf})
    new_signups_month = await db.members.count_documents({"organization_id": org_id, "created_at": {"$gte": month_start}, **sf})
    cancellations_month = await db.member_memberships.count_documents({"organization_id": org_id, "status": "cancelled", "cancel_effective_date": {"$gte": month_start}, **sf})
    frozen_memberships = await db.member_memberships.count_documents({"organization_id": org_id, "status": "frozen", **sf})
    expiring_7d = await db.member_memberships.count_documents({
        "organization_id": org_id, "status": "active", **sf,
        "end_date": {"$gte": now.isoformat(), "$lte": (now + timedelta(days=7)).isoformat()},
    })
    today_classes = await db.class_occurrences.count_documents({
        "organization_id": org_id, "starts_at": {"$gte": today_start, "$lte": today_end},
        "status": "scheduled", **sf,
    })
    today_occs = await db.class_occurrences.find({"organization_id": org_id, "starts_at": {"$gte": today_start, "$lte": today_end}, **sf}, {"_id": 0}).sort("starts_at", 1).to_list(50)
    today_bookings = sum((o.get("bookings_count") or 0) for o in today_occs)
    today_capacity = sum((o.get("capacity") or 0) for o in today_occs) or 1
    occupancy = round(100.0 * today_bookings / today_capacity, 1)
    no_shows_month = await db.bookings.count_documents({"organization_id": org_id, "status": "no_show", "booked_at": {"$gte": month_start}, **sf})
    waitlisted = await db.bookings.count_documents({"organization_id": org_id, "status": "waitlist", **sf})

    return {
        "active_members": active_members,
        "new_signups_month": new_signups_month,
        "cancellations_month": cancellations_month,
        "frozen_memberships": frozen_memberships,
        "expiring_7d": expiring_7d,
        "today_classes": today_classes,
        "occupancy_pct": occupancy,
        "today_bookings": today_bookings,
        "no_shows_month": no_shows_month,
        "waitlisted": waitlisted,
        "today_occurrences": today_occs,
    }


# ═════════════════════ Bookings (member-facing) ═════════════════════
