"""Per-gym booking-rule overrides (cancel windows, late-cancel fees, etc.).

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations


from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_operator_org,
)

router = APIRouter(tags=["memberships"])


#
# Each gym sets their own booking rules. Until they save the first override
# they inherit the platform-default rules from `memberships_global_rules`
# (managed by master admin under master-admin/memberships/booking-rules).

class GymBookingRulesBody(BaseModel):
    booking_window_hours: int = Field(ge=1, le=4320)
    cancellation_cutoff_hours: int = Field(ge=0, le=720)
    waitlist_enabled: bool
    max_waitlist: int = Field(ge=0, le=500)
    default_capacity: int = Field(ge=1, le=500)
    no_show_penalty: str = Field(pattern="^(warning|credit_forfeit|suspension)$")
    no_show_strikes_before_block: int = Field(ge=1, le=20)
    checkin_window_min: int = Field(ge=0, le=120)
    instructor_assignment: str = Field(pattern="^(manual|auto|balanced)$")
    allow_site_overrides: bool


_PLATFORM_DEFAULT_BOOKING_RULES = {
    "booking_window_hours": 168,
    "cancellation_cutoff_hours": 12,
    "waitlist_enabled": True,
    "max_waitlist": 10,
    "default_capacity": 20,
    "no_show_penalty": "warning",
    "no_show_strikes_before_block": 3,
    "checkin_window_min": 15,
    "instructor_assignment": "manual",
    "allow_site_overrides": True,
}


@router.get("/memberships/booking-rules", dependencies=[Depends(require_module("memberships"))])
async def gym_booking_rules_get(user: dict = Depends(get_current_user)):
    """Return this gym's booking rules. If they haven't set their own yet,
    fall back to the platform default and flag the response as inherited.
    """
    org_id = await _require_operator_org(user)
    own = await db.memberships_org_rules.find_one(
        {"organization_id": org_id, "kind": "booking"}, {"_id": 0},
    )
    if own:
        return {"rules": {k: v for k, v in own.items() if k not in ("kind",)}, "inherited": False}
    # Inherit platform defaults
    platform = await db.memberships_global_rules.find_one({"id": "booking"}, {"_id": 0}) or {}
    base = {**_PLATFORM_DEFAULT_BOOKING_RULES, **{k: v for k, v in platform.items()
                                                    if k in _PLATFORM_DEFAULT_BOOKING_RULES}}
    return {
        "rules": {**base, "organization_id": org_id, "updated_at": None, "updated_by": None},
        "inherited": True,
    }


@router.put("/memberships/booking-rules", dependencies=[Depends(require_module("memberships"))])
async def gym_booking_rules_put(body: GymBookingRulesBody, user: dict = Depends(get_current_user)):
    """Save this gym's booking-rule overrides. Becomes their authoritative
    config; platform defaults stop applying once this is set."""
    org_id = await _require_operator_org(user)
    payload = body.model_dump()
    now = _now_iso()
    await db.memberships_org_rules.update_one(
        {"organization_id": org_id, "kind": "booking"},
        {"$set": {**payload, "organization_id": org_id, "kind": "booking",
                  "updated_at": now, "updated_by": user.get("email")}},
        upsert=True,
    )
    return {"ok": True, "inherited": False}


@router.post("/memberships/booking-rules/reset-to-platform", dependencies=[Depends(require_module("memberships"))])
async def gym_booking_rules_reset(user: dict = Depends(get_current_user)):
    """Drop the gym-level override so this gym re-inherits the platform
    defaults (useful if a manager wants to roll back local changes)."""
    org_id = await _require_operator_org(user)
    await db.memberships_org_rules.delete_one({"organization_id": org_id, "kind": "booking"})
    return {"ok": True, "inherited": True}
