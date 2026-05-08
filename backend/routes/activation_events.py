"""Activation-event capture & funnel reporting.

Why: today we know how many trials we have but not what they DO. A trial
that uploaded 5 pieces of equipment and took its first booking by day 3
converts to paid 4× more than a trial that only logged in. Capturing
explicit activation events gives us:

  • A real conversion funnel per cohort.
  • A "magic moment" threshold to push customers toward.
  • A leading indicator of churn ("this org hasn't fired any activation
    event in 7 days").

Schema (`activation_events`)
==========================
::

    {
        "id":              uuid,
        "organization_id": str,
        "event_type":      "first_login" | "first_equipment_added" |
                           "first_member_added" | "first_booking_taken" |
                           "first_invoice_generated" | "first_staff_invited" |
                           "first_class_scheduled" | "module_activated",
        "occurred_at":     iso datetime,
        "trigger_user_id": str | null,
        "payload":         dict           # tiny, denormalised metadata
    }

Each event_type fires **only once per organisation** — duplicates are
silently ignored to keep the funnel honest.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)


EVENT_TYPES = (
    "first_login",
    "first_equipment_added",
    "first_member_added",
    "first_booking_taken",
    "first_invoice_generated",
    "first_staff_invited",
    "first_class_scheduled",
    "module_activated",
)

# Friendly labels surfaced in the UI funnel.
EVENT_LABELS: dict[str, str] = {
    "first_login":             "First login",
    "first_equipment_added":   "First piece of equipment added",
    "first_member_added":      "First member added",
    "first_booking_taken":     "First booking taken",
    "first_invoice_generated": "First invoice generated",
    "first_staff_invited":     "First staff member invited",
    "first_class_scheduled":   "First class scheduled",
    "module_activated":        "First module switched on",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Internal helper for in-process callers ──────────────────────────


async def record_activation_event(
    organization_id: str,
    event_type: str,
    *,
    trigger_user_id: str | None = None,
    payload: dict | None = None,
) -> bool:
    """Idempotent per (organization_id, event_type). Returns True if a row
    was inserted, False if the org has already fired this event before.

    Best-effort — never raises. Activation tracking must not gate primary
    workflows like creating equipment.
    """
    if event_type not in EVENT_TYPES:
        return False
    try:
        existing = await db.activation_events.find_one(
            {"organization_id": organization_id, "event_type": event_type},
            {"_id": 1},
        )
        if existing:
            return False
        await db.activation_events.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "event_type": event_type,
            "occurred_at": _iso_now(),
            "trigger_user_id": trigger_user_id,
            "payload": payload or {},
        })
        return True
    except Exception:
        logger.exception("activation_event insert failed for %s/%s", organization_id, event_type)
        return False


# ── Public endpoints ────────────────────────────────────────────────


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


@router.post("/activation/record")
async def record_event_endpoint(
    payload: dict,
    user: dict = Depends(get_current_user),
) -> dict:
    """Authenticated client-side hook. Operators (frontend) call this when
    a milestone happens (e.g. "first_member_added"). Resolves the
    organisation from the calling user.
    """
    org_id = user.get("organization_id")
    if not org_id:
        # Master admin / cross-org users have no single org — no-op.
        return {"recorded": False, "reason": "no_org"}
    event_type = (payload or {}).get("event_type")
    if event_type not in EVENT_TYPES:
        raise HTTPException(400, f"event_type must be one of {EVENT_TYPES}")
    inserted = await record_activation_event(
        org_id, event_type,
        trigger_user_id=user.get("id"),
        payload=(payload or {}).get("payload") or {},
    )
    return {"recorded": inserted}


@router.get("/activation/me")
async def activation_for_me(user: dict = Depends(get_current_user)) -> dict:
    """Operator-facing timeline — returns which milestones the caller's
    organisation has achieved. Master admins without an org return an
    empty timeline (they use `/master-admin/activation/funnel` instead).
    """
    org_id = user.get("organization_id")
    if not org_id:
        return {"timeline": [], "fired_count": 0, "total": len(EVENT_TYPES), "as_of": _iso_now()}
    rows = await db.activation_events.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("occurred_at", 1).to_list(length=50)
    fired_set = {r["event_type"]: r["occurred_at"] for r in rows}
    timeline: list[dict[str, Any]] = []
    for et in EVENT_TYPES:
        timeline.append({
            "event_type": et,
            "label": EVENT_LABELS.get(et, et),
            "fired": et in fired_set,
            "occurred_at": fired_set.get(et),
        })
    return {
        "timeline": timeline,
        "fired_count": len(fired_set),
        "total": len(EVENT_TYPES),
        "as_of": _iso_now(),
    }


@router.get("/master-admin/activation/funnel")
async def activation_funnel(user: dict = Depends(get_current_user)) -> dict:
    """Aggregated funnel for the master admin dashboard.

    Returns one row per event_type with: total firings, % of orgs that
    have hit it, and the median time-from-signup-to-event in days.
    """
    _require_master(user)

    total_orgs = await db.organizations.count_documents({"portal_type": {"$ne": "crm"}})
    if total_orgs == 0:
        return {"steps": [], "total_orgs": 0, "as_of": _iso_now()}

    steps = []
    for et in EVENT_TYPES:
        # How many distinct orgs have ever fired this event?
        cnt = await db.activation_events.count_documents({"event_type": et})
        steps.append({
            "event_type": et,
            "label": EVENT_LABELS.get(et, et),
            "orgs": cnt,
            "pct": round(cnt / total_orgs * 100, 1) if total_orgs else 0,
        })
    return {
        "steps": steps,
        "total_orgs": total_orgs,
        "as_of": _iso_now(),
    }


@router.get("/master-admin/activation/org/{org_id}")
async def activation_for_org(
    org_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Per-org checklist: which events have fired, when. Useful inside
    the org detail panel to spot stalled trials at a glance.
    """
    _require_master(user)
    rows = await db.activation_events.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("occurred_at", 1).to_list(length=50)
    fired_set = {r["event_type"]: r["occurred_at"] for r in rows}
    timeline: list[dict[str, Any]] = []
    for et in EVENT_TYPES:
        timeline.append({
            "event_type": et,
            "label": EVENT_LABELS.get(et, et),
            "fired": et in fired_set,
            "occurred_at": fired_set.get(et),
        })
    return {"timeline": timeline, "as_of": _iso_now()}


# ── Indexes ─────────────────────────────────────────────────────────


async def ensure_activation_indexes() -> None:
    try:
        await db.activation_events.create_index(
            [("organization_id", 1), ("event_type", 1)], unique=True,
        )
        await db.activation_events.create_index([("event_type", 1), ("occurred_at", -1)])
        await db.activation_events.create_index([("occurred_at", -1)])
    except Exception:
        logger.exception("ensure_activation_indexes failed (non-fatal)")
