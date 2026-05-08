"""Studio Mode — lightweight UI variant for small studio operators.

Iter 215p. Upgrades the Memberships module to serve freelance
instructors, boutique studios, yoga/dance/pilates schools, and wellness
coaches without rebuilding the module. Two endpoints:

  GET  /api/memberships/studio/settings     — read flag + quickstart status
  POST /api/memberships/studio/settings     — toggle studio_mode
  POST /api/memberships/studio/quickstart   — one-click "ready to book in
                                              under 10 minutes": creates a
                                              sample drop-in plan, a
                                              weekly class template, the
                                              first occurrence, and
                                              returns the shareable public
                                              booking URL.

Design notes
------------
- Studio Mode is a pure UI toggle; data model is unchanged. The existing
  6 plan kinds, waitlists, courses, sub-profiles, check-in, and embed
  timetable already cover the functional requirements. Studio Mode hides
  enterprise-heavy tabs and surfaces a 3-panel "Schedule / Members /
  Money" layout.
- Quickstart is idempotent and safe to re-run: it skips creation if the
  org already has a sample plan + class template with our reserved
  `studio_quickstart` tag.
- Owner / manager only. Master admins can impersonate via the usual
  flow.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import _now_iso, _require_operator_org, _uuid

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-studio"])


# ═══════════════════════ Settings ═══════════════════════

class StudioSettingsIn(BaseModel):
    studio_mode: bool


@router.get("/memberships/studio/settings", dependencies=[Depends(require_module("memberships"))])
async def get_studio_settings(user: dict = Depends(get_current_user)):
    """Return the org's studio_mode flag + quickstart completion state."""
    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "studio_mode": 1, "studio_quickstart_completed_at": 1}) or {}
    return {
        "studio_mode": bool(org.get("studio_mode", False)),
        "quickstart_completed": bool(org.get("studio_quickstart_completed_at")),
        "quickstart_completed_at": org.get("studio_quickstart_completed_at"),
    }


@router.post("/memberships/studio/settings", dependencies=[Depends(require_module("memberships"))])
async def set_studio_settings(
    payload: StudioSettingsIn = Body(...),
    user: dict = Depends(get_current_user),
):
    """Enable / disable Studio Mode for the org. Owner / manager only."""
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can toggle Studio Mode.")
    org_id = await _require_operator_org(user)
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"studio_mode": bool(payload.studio_mode), "studio_mode_updated_at": _now_iso()}},
    )
    return {"studio_mode": bool(payload.studio_mode)}


# ═══════════════════════ Quickstart ═══════════════════════

class QuickstartIn(BaseModel):
    studio_name: str | None = None
    class_name: str | None = "Open Flow Yoga"
    class_price_pence: int = 1500           # £15 drop-in
    monthly_price_pence: int = 6500         # £65/mo unlimited
    class_capacity: int = 12
    weekly_day: int = 1                     # Monday=1 ... Sunday=7
    weekly_start_time: str = "18:00"        # 24h HH:MM
    duration_minutes: int = 60


@router.post("/memberships/studio/quickstart", dependencies=[Depends(require_module("memberships"))])
async def run_studio_quickstart(
    payload: QuickstartIn = Body(default_factory=QuickstartIn),
    user: dict = Depends(get_current_user),
):
    """Run the "Start Your Studio in 10 Minutes" flow.

    Creates (idempotently):
      1. A £X drop-in plan (payg, 1 credit, expires in 30 days)
      2. A £Y monthly unlimited plan (recurring, monthly)
      3. A weekly class template + next 8 occurrences
    Then marks the org as quickstart-complete and returns the public
    booking URL so the operator can share it immediately (QR / IG link).
    """
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can run the Studio quickstart.")

    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organization not found.")

    now_iso = _now_iso()
    created = {"plans": [], "class_template_id": None, "occurrences": 0, "reused_existing": False}

    # ── 1. Drop-in plan (payg) ─────────────────────────────────────
    existing_dropin = await db.membership_plans.find_one(
        {"organization_id": org_id, "studio_quickstart_tag": "dropin"},
        {"_id": 0, "id": 1},
    )
    if existing_dropin:
        created["plans"].append({"id": existing_dropin["id"], "kind": "payg", "reused": True})
        created["reused_existing"] = True
    else:
        dropin_id = _uuid()
        await db.membership_plans.insert_one({
            "id": dropin_id,
            "organization_id": org_id,
            "name": "Drop-in class",
            "kind": "payg",
            "price_pence": int(payload.class_price_pence),
            "billing_cycle": "oneoff",
            "upfront_fee_pence": 0,
            "credits_count": 1,
            "credits_expire_days": 30,
            "included_classes": "credits_only",
            "colour": "#00B2C7",
            "active": True,
            "freeze_allowed": False,
            "created_at": now_iso,
            "studio_quickstart_tag": "dropin",
        })
        created["plans"].append({"id": dropin_id, "kind": "payg", "reused": False})

    # ── 2. Monthly unlimited plan (recurring) ──────────────────────
    existing_monthly = await db.membership_plans.find_one(
        {"organization_id": org_id, "studio_quickstart_tag": "monthly"},
        {"_id": 0, "id": 1},
    )
    if existing_monthly:
        created["plans"].append({"id": existing_monthly["id"], "kind": "recurring", "reused": True})
        created["reused_existing"] = True
    else:
        monthly_id = _uuid()
        await db.membership_plans.insert_one({
            "id": monthly_id,
            "organization_id": org_id,
            "name": "Monthly unlimited",
            "kind": "recurring",
            "price_pence": int(payload.monthly_price_pence),
            "billing_cycle": "monthly",
            "upfront_fee_pence": 0,
            "included_classes": "unlimited",
            "colour": "#7C3AED",
            "active": True,
            "freeze_allowed": True,
            "freeze_max_days": 30,
            "cancel_notice_days": 0,
            "created_at": now_iso,
            "studio_quickstart_tag": "monthly",
        })
        created["plans"].append({"id": monthly_id, "kind": "recurring", "reused": False})

    # ── 3. Class template + 8 weekly occurrences ───────────────────
    existing_tpl = await db.class_templates.find_one(
        {"organization_id": org_id, "studio_quickstart_tag": "first_class"},
        {"_id": 0, "id": 1},
    )
    if existing_tpl:
        created["class_template_id"] = existing_tpl["id"]
        created["reused_existing"] = True
    else:
        tpl_id = _uuid()
        await db.class_templates.insert_one({
            "id": tpl_id,
            "organization_id": org_id,
            "name": payload.class_name or "Open Flow Yoga",
            "description": "A welcoming class for all levels — breath, movement, stillness.",
            "duration_minutes": int(payload.duration_minutes),
            "capacity": int(payload.class_capacity),
            "colour": "#10B981",
            "waitlist_enabled": True,
            "max_waitlist": 10,
            "credits_to_book": 1,
            "cancel_deadline_hours": 2,
            "active": True,
            "created_at": now_iso,
            "studio_quickstart_tag": "first_class",
        })
        created["class_template_id"] = tpl_id
        # Materialise 8 upcoming weekly occurrences starting next <weekly_day>.
        try:
            start_hour, start_minute = (int(x) for x in (payload.weekly_start_time or "18:00").split(":", 1))
        except ValueError:
            start_hour, start_minute = 18, 0
        target_weekday = max(1, min(7, int(payload.weekly_day))) - 1  # Mon=0 ... Sun=6
        today = datetime.now(timezone.utc).replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        days_ahead = (target_weekday - today.weekday()) % 7 or 7  # always future
        first = today + timedelta(days=days_ahead)
        occurrences = []
        for i in range(8):
            starts = first + timedelta(weeks=i)
            occurrences.append({
                "id": _uuid(),
                "organization_id": org_id,
                "template_id": tpl_id,
                "name": payload.class_name or "Open Flow Yoga",
                "description": "A welcoming class for all levels — breath, movement, stillness.",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(minutes=int(payload.duration_minutes))).isoformat(),
                "capacity": int(payload.class_capacity),
                "bookings_count": 0,
                "status": "scheduled",
                "colour": "#10B981",
                "waitlist_enabled": True,
                "max_waitlist": 10,
                "credits_to_book": 1,
                "active": True,
                "created_at": now_iso,
                "studio_quickstart_tag": "first_class",
            })
        if occurrences:
            await db.class_occurrences.insert_many(occurrences)
        created["occurrences"] = len(occurrences)

    # ── 4. Mark quickstart complete ────────────────────────────────
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "studio_mode": True,
            "studio_quickstart_completed_at": now_iso,
            "studio_mode_updated_at": now_iso,
        }},
    )

    # ── 5. Public booking URL ─────────────────────────────────────
    # Uses the existing PublicClassPage route. Slug is the org id so it's
    # stable, private-by-obscurity, and survives org renaming.
    public_url = f"/book/{org_id}"

    return {
        "ok": True,
        "created": created,
        "public_booking_url": public_url,
        "studio_mode": True,
        "quickstart_completed_at": now_iso,
    }
