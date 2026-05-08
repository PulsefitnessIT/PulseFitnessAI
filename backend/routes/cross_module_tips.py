"""Cross-Module Awareness / Upsell Tips (Iter 231).

Each module (Operations, Memberships, Marketing, CRM) should be effective
on its own — but when a user has one but not another, we surface a
tasteful, dismissable banner pointing at what's missing. This drives
discovery without being pushy.

Resolution rules:
  • A tip fires when the user **has** the source module enabled but
    **lacks** the target module.
  • Tips are de-duplicated per (user, tip_id) using
    ``user_dismissed_tips``. Dismissed tips don't reappear for that user.
  • Master admins always see all tips (so they can preview the user
    experience), and there's no record kept for them.

Endpoints:
  GET    /api/notifications/cross-module-tips     — list active tips
  POST   /api/notifications/cross-module-tips/{tip_id}/dismiss
  POST   /api/notifications/cross-module-tips/{tip_id}/request-enable
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_access import resolve_module_access

logger = logging.getLogger(__name__)
router = APIRouter()


# Each tip:  source ⟶ target  (user has SOURCE, lacks TARGET ⇒ show this)
TIPS: list[dict] = [
    {
        "id": "marketing_to_crm",
        "source": "marketing",
        "target": "crm",
        "title": "Turn campaign leads into closed deals",
        "headline": "You're capturing leads — let's close them.",
        "body": (
            "Add the CRM module to push form submissions and email "
            "responders straight into a sales pipeline with auto-tasks, "
            "deal stages and quote-to-contract workflows."
        ),
        "cta": "Explore CRM",
        "value_props": [
            "Auto-create deals from form submissions",
            "Sales pipeline kanban + activity feed",
            "Quote → Contract → Sage 200 sync",
        ],
        "icon": "Briefcase",
    },
    {
        "id": "marketing_to_memberships",
        "source": "marketing",
        "target": "memberships",
        "title": "Convert leads into class bookings",
        "headline": "Your campaigns are working. Now book them in.",
        "body": (
            "Add the Memberships module to take members from a Marketing "
            "campaign straight to a live timetable, drop-in booking and "
            "first-class reminders."
        ),
        "cta": "Explore Memberships",
        "value_props": [
            "Live class timetable + waitlist",
            "Drop-in invites driven by your audiences",
            "Front-desk check-in console",
        ],
        "icon": "Calendar",
    },
    {
        "id": "marketing_to_operations",
        "source": "marketing",
        "target": "operations",
        "title": "Protect the brand promise on the gym floor",
        "headline": "Marketing is only as good as the experience.",
        "body": (
            "Add Operations so faulty kit, missed PPMs and SLA breaches "
            "don't undo the trust your campaigns build with members."
        ),
        "cta": "Explore Operations",
        "value_props": [
            "Equipment + PPM tracking",
            "Fault triage + supplier portal",
            "On-site staff QR check-ins",
        ],
        "icon": "Activity",
    },
    {
        "id": "crm_to_marketing",
        "source": "crm",
        "target": "marketing",
        "title": "Nurture every contact, automatically",
        "headline": "Your CRM is full of warm contacts.",
        "body": (
            "Add Marketing to launch automated email journeys, dynamic "
            "audiences and AI-generated creatives against the contacts "
            "you've already won."
        ),
        "cta": "Explore Marketing",
        "value_props": [
            "Dynamic lists that auto-refresh",
            "Email A/B testing + AI Director",
            "Forms + landing pages with one click",
        ],
        "icon": "Rocket",
    },
    {
        "id": "crm_to_operations",
        "source": "crm",
        "target": "operations",
        "title": "Close the loop from sale to install",
        "headline": "Your contracts deserve operational follow-through.",
        "body": (
            "Add Operations to track installed equipment, run PPM "
            "schedules and field-service the fleet you've contracted to."
        ),
        "cta": "Explore Operations",
        "value_props": [
            "Equipment fleet + asset tracking",
            "PPM schedules + check-sheets",
            "SLA-aware fault triage",
        ],
        "icon": "Activity",
    },
    {
        "id": "operations_to_memberships",
        "source": "operations",
        "target": "memberships",
        "title": "Fill classes with the same staff and floor",
        "headline": "Already running operations? Add member booking.",
        "body": (
            "Memberships layers class timetabling, member management and "
            "pricing on top of your existing Operations setup — same "
            "staff, same site, no duplicated admin."
        ),
        "cta": "Explore Memberships",
        "value_props": [
            "Class timetables + waitlists",
            "Member CSV bulk-import",
            "Per-gym booking rules",
        ],
        "icon": "Calendar",
    },
    {
        "id": "operations_to_marketing",
        "source": "operations",
        "target": "marketing",
        "title": "Turn operational excellence into demand",
        "headline": "Use your Operations data to win new members.",
        "body": (
            "Add Marketing to run AI-generated posters, automated email "
            "campaigns and lead-capture forms — fed by the live picture "
            "Operations already gives you."
        ),
        "cta": "Explore Marketing",
        "value_props": [
            "AI Creative Studio (Gemini Nano Banana)",
            "Audiences + Dynamic Lists",
            "Lead-capture forms + landing pages",
        ],
        "icon": "Rocket",
    },
    {
        "id": "memberships_to_operations",
        "source": "memberships",
        "target": "operations",
        "title": "Keep classes safe with operational visibility",
        "headline": "Members don't notice equipment until it breaks.",
        "body": (
            "Add Operations so faulty kit and missed servicing get caught "
            "before they show up in member feedback."
        ),
        "cta": "Explore Operations",
        "value_props": [
            "PPM schedules + check-sheets",
            "Fault triage + supplier escalation",
            "Equipment lifecycle tracking",
        ],
        "icon": "Activity",
    },
    {
        "id": "memberships_to_marketing",
        "source": "memberships",
        "target": "marketing",
        "title": "Stop empty classes — proactively",
        "headline": "Drive demand to your underperforming slots.",
        "body": (
            "Marketing plugs into your live class data — auto-target "
            "drop-in invites, run win-back campaigns to lapsed members "
            "and A/B-test offer copy."
        ),
        "cta": "Explore Marketing",
        "value_props": [
            "AI demand forecasting",
            "Drop-in invite engine",
            "Win-back automations",
        ],
        "icon": "Rocket",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _resolve_access(user: dict) -> dict[str, bool]:
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {"_id": 0, "account_type": 1, "modules": 1},
    )
    return resolve_module_access(user, org)


async def _dismissed_ids(user_id: str) -> set[str]:
    rows = await db.user_dismissed_tips.find(
        {"user_id": user_id}, {"_id": 0, "tip_id": 1},
    ).to_list(length=200)
    return {r["tip_id"] for r in rows if r.get("tip_id")}


@router.get("/notifications/cross-module-tips")
async def list_cross_module_tips(user: dict = Depends(get_current_user)):
    """Return tips that fire for THIS user. Master admins see everything
    (preview-mode); regular users see only tips where they have the
    source but not the target, minus anything they've dismissed."""
    access = await _resolve_access(user)
    is_master = bool(user.get("is_master_admin"))
    # Iter 215bw — previously master admins had `dismissed` forced to
    # an empty set, which meant their dismiss action was persisted but
    # never honoured on the next page load (tips kept reappearing).
    # Load dismissed ids for everyone so dismiss actions stick.
    dismissed = await _dismissed_ids(user["id"])
    out = []
    for tip in TIPS:
        if tip["id"] in dismissed:
            continue
        if is_master:
            applicable = True
        else:
            applicable = bool(access.get(tip["source"])) and not access.get(tip["target"])
        if applicable:
            out.append({**tip, "applicable": True})
    return {
        "tips": out,
        "module_access": access,
        "is_master_admin": is_master,
    }


@router.post("/notifications/cross-module-tips/{tip_id}/dismiss")
async def dismiss_tip(tip_id: str, user: dict = Depends(get_current_user)):
    if tip_id not in {t["id"] for t in TIPS}:
        raise HTTPException(404, "Unknown tip")
    await db.user_dismissed_tips.update_one(
        {"user_id": user["id"], "tip_id": tip_id},
        {"$set": {
            "user_id": user["id"],
            "tip_id": tip_id,
            "organization_id": user.get("organization_id"),
            "dismissed_at": _now_iso(),
        }},
        upsert=True,
    )
    return {"ok": True}


@router.post("/notifications/cross-module-tips/{tip_id}/request-enable")
async def request_module_enable(
    tip_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Operator clicks "Request enable" — files a master-admin task with
    the org context. Master admins resolve this in their inbox."""
    tip = next((t for t in TIPS if t["id"] == tip_id), None)
    if not tip:
        raise HTTPException(404, "Unknown tip")
    note = (body.get("note") or "").strip()[:500]
    record = {
        "id": f"req-{user['id']}-{tip_id}-{int(datetime.now(timezone.utc).timestamp())}",
        "user_id": user["id"],
        "user_email": user.get("email"),
        "organization_id": user.get("organization_id"),
        "tip_id": tip_id,
        "target_module": tip["target"],
        "note": note,
        "status": "open",
        "created_at": _now_iso(),
    }
    await db.module_enable_requests.insert_one(record)
    logger.info(
        "[cross-module-tips] enable request: org=%s user=%s target=%s",
        user.get("organization_id"), user["id"], tip["target"],
    )
    return {"ok": True, "request_id": record["id"]}
