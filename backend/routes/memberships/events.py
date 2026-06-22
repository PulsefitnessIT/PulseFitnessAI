"""Studio Events, Recitals & Costumes — Phase D (iter 216ac).

A first-class scheduling primitive distinct from regular weekly classes:
showcases, recitals, competitions, workshops, summer camps. Each event
can carry a ticket schedule, a costume tracker (per-student / per-event),
and a rehearsal sub-schedule.

Collections:
  • studio_events          { id, organization_id, name, kind:"recital"|
                             "showcase"|"competition"|"workshop"|"camp"|
                             "other", starts_at, ends_at, venue,
                             description, ticket_price_pence,
                             ticket_capacity, tickets_sold,
                             cover_image_url, archived,
                             created_at, updated_at }
  • event_rehearsals       { id, organization_id, event_id, name,
                             starts_at, ends_at, room, notes }
  • event_costumes         { id, organization_id, event_id,
                             member_id, sub_profile_id?, attendee_name,
                             costume_name, size, ordered_at?,
                             arrived_at?, fitted_at?, notes,
                             total_pence, paid_pence, status:
                             "needed"|"ordered"|"arrived"|"fitted"|
                             "paid"|"refunded" }
  • event_ticket_orders    { id, organization_id, event_id, member_id?,
                             buyer_name, buyer_email, qty,
                             total_pence, stripe_session_id?,
                             status:"pending"|"paid"|"refunded",
                             created_at }

Endpoints:
  GET    /api/memberships/events
  POST   /api/memberships/events
  GET    /api/memberships/events/{id}
  PUT    /api/memberships/events/{id}
  DELETE /api/memberships/events/{id}                    (archive)

  GET    /api/memberships/events/{id}/rehearsals
  POST   /api/memberships/events/{id}/rehearsals
  DELETE /api/memberships/events/{id}/rehearsals/{rid}

  GET    /api/memberships/events/{id}/costumes
  POST   /api/memberships/events/{id}/costumes
  PATCH  /api/memberships/events/{id}/costumes/{cid}
  DELETE /api/memberships/events/{id}/costumes/{cid}

  POST   /api/memberships/events/{id}/announce         (Resend bulk email)
  POST   /api/memberships/events/{id}/ai-comms         (Claude-drafted copy)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_operator_org,
    _uuid,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-events"])


_EVENT_KINDS = {"recital", "showcase", "competition", "workshop", "camp", "other"}
_COSTUME_STATUSES = {"needed", "ordered", "arrived", "fitted", "paid", "refunded"}


# ─────────────────────────────────────────────────────────────────
# Events
# ─────────────────────────────────────────────────────────────────

class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["recital", "showcase", "competition", "workshop", "camp", "other"] = "recital"
    starts_at: str
    ends_at: str
    venue: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = Field(default=None, max_length=4000)
    ticket_price_pence: int = Field(default=0, ge=0, le=100_000)
    ticket_capacity: int = Field(default=0, ge=0, le=100_000)
    cover_image_url: Optional[str] = None


def _validate_window(starts_at: str, ends_at: str) -> tuple[str, str]:
    try:
        s = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        e = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Invalid ISO timestamp") from exc
    if e < s:
        raise HTTPException(400, "ends_at must be on or after starts_at")
    return s.isoformat(), e.isoformat()


@router.get(
    "/memberships/events", dependencies=[Depends(require_module("memberships"))],
)
async def list_events(
    upcoming_only: bool = Query(False),
    user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if upcoming_only:
        q["ends_at"] = {"$gte": _now_iso()}
    rows = await db.studio_events.find(q, {"_id": 0}).sort("starts_at", 1).to_list(500)
    return {"events": rows, "count": len(rows)}


@router.post(
    "/memberships/events", dependencies=[Depends(require_module("memberships"))],
)
async def create_event(body: EventIn, user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    starts, ends = _validate_window(body.starts_at, body.ends_at)
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "name": body.name.strip(),
        "kind": body.kind,
        "starts_at": starts,
        "ends_at": ends,
        "venue": (body.venue or "").strip(),
        "description": (body.description or "").strip(),
        "ticket_price_pence": int(body.ticket_price_pence),
        "ticket_capacity": int(body.ticket_capacity),
        "tickets_sold": 0,
        "cover_image_url": (body.cover_image_url or "").strip() or None,
        "archived": False,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "created_by_id": user.get("id"),
    }
    await db.studio_events.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get(
    "/memberships/events/{event_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def get_event(event_id: str, user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    row = await db.studio_events.find_one(
        {"id": event_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "Event not found")
    return row


@router.put(
    "/memberships/events/{event_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def update_event(
    event_id: str, body: EventIn = Body(...), user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    starts, ends = _validate_window(body.starts_at, body.ends_at)
    res = await db.studio_events.update_one(
        {"id": event_id, "organization_id": org_id},
        {"$set": {
            "name": body.name.strip(),
            "kind": body.kind,
            "starts_at": starts,
            "ends_at": ends,
            "venue": (body.venue or "").strip(),
            "description": (body.description or "").strip(),
            "ticket_price_pence": int(body.ticket_price_pence),
            "ticket_capacity": int(body.ticket_capacity),
            "cover_image_url": (body.cover_image_url or "").strip() or None,
            "updated_at": _now_iso(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Event not found")
    return await db.studio_events.find_one({"id": event_id}, {"_id": 0})


@router.delete(
    "/memberships/events/{event_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def archive_event(event_id: str, user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    res = await db.studio_events.update_one(
        {"id": event_id, "organization_id": org_id},
        {"$set": {"archived": True, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Event not found")
    return {"ok": True, "id": event_id}


# ─────────────────────────────────────────────────────────────────
# Bootstrap from kind (Iter 216h251)
# ─────────────────────────────────────────────────────────────────
#
# Auto-populate a brand-new event with the rehearsals + costume rows a
# typical studio expects for that event kind. Saves a dance-studio
# operator 15–20 minutes of typing on every recital. Idempotent on the
# rehearsal+costume keys: re-running on a populated event is a no-op
# (skip rehearsal names that already exist; skip costume rows for
# attendees that already exist for the event).

# Each kind's template: a list of rehearsals (relative to the event's
# starts_at) + whether costume rows should be auto-created for every
# active member of the org.
_KIND_TEMPLATES: dict[str, dict] = {
    "recital": {
        "rehearsals": [
            {"name": "Tech rehearsal", "offset_days": -7, "start_hhmm": "16:00", "duration_minutes": 120},
            {"name": "Dress rehearsal", "offset_days": -1, "start_hhmm": "17:00", "duration_minutes": 120},
        ],
        "auto_costumes": True,
        "default_costume_name": "Recital costume — TBC",
    },
    "showcase": {
        "rehearsals": [
            {"name": "Dress rehearsal", "offset_days": -1, "start_hhmm": "18:00", "duration_minutes": 90},
        ],
        "auto_costumes": True,
        "default_costume_name": "Showcase outfit — TBC",
    },
    "competition": {
        "rehearsals": [
            {"name": "Practice run", "offset_days": -14, "start_hhmm": "16:00", "duration_minutes": 120},
            {"name": "Final run-through", "offset_days": -2, "start_hhmm": "17:00", "duration_minutes": 120},
        ],
        "auto_costumes": True,
        "default_costume_name": "Competition costume — TBC",
    },
    "workshop": {
        "rehearsals": [
            {"name": "Prep meeting", "offset_days": -3, "start_hhmm": "10:00", "duration_minutes": 30},
        ],
        "auto_costumes": False,
        "default_costume_name": "",
    },
    "camp": {
        "rehearsals": [
            {"name": "Welcome briefing", "offset_days": 0, "start_hhmm": "09:00", "duration_minutes": 30},
        ],
        "auto_costumes": False,
        "default_costume_name": "",
    },
    "other": {
        "rehearsals": [],
        "auto_costumes": False,
        "default_costume_name": "",
    },
}


class BootstrapIn(BaseModel):
    # Reserved for future toggles (e.g. opt-out of costumes). Empty body
    # is fine — defaults match the kind's template.
    include_rehearsals: bool = True
    include_costumes: bool = True


@router.post(
    "/memberships/events/{event_id}/bootstrap-from-kind",
    dependencies=[Depends(require_module("memberships"))],
)
async def bootstrap_event_from_kind(
    event_id: str,
    body: BootstrapIn = Body(default=BootstrapIn()),
    user=Depends(get_current_user),
):
    """Populate default rehearsals + costume rows based on the event's
    kind. Returns counts of items created. Safe to call multiple times.
    """
    org_id = await _require_operator_org(user)
    event = await db.studio_events.find_one(
        {"id": event_id, "organization_id": org_id}, {"_id": 0},
    )
    if not event:
        raise HTTPException(404, "Event not found")

    kind = event.get("kind") or "other"
    template = _KIND_TEMPLATES.get(kind, _KIND_TEMPLATES["other"])

    try:
        starts = datetime.fromisoformat(str(event["starts_at"]).replace("Z", "+00:00"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Event has an invalid starts_at") from exc

    from datetime import timedelta

    rehearsals_created = 0
    rehearsals_skipped = 0
    if body.include_rehearsals:
        # Existing rehearsal names so we don't duplicate on re-runs.
        existing_names = {
            r.get("name", "").strip().lower()
            async for r in db.event_rehearsals.find(
                {"event_id": event_id, "organization_id": org_id},
                {"_id": 0, "name": 1},
            )
        }
        for r in template["rehearsals"]:
            if r["name"].strip().lower() in existing_names:
                rehearsals_skipped += 1
                continue
            try:
                hh, mm = (int(x) for x in r["start_hhmm"].split(":"))
            except (ValueError, AttributeError):
                hh, mm = 17, 0
            r_start = (starts + timedelta(days=r["offset_days"])).replace(
                hour=hh, minute=mm, second=0, microsecond=0,
            )
            r_end = r_start + timedelta(minutes=int(r["duration_minutes"]))
            await db.event_rehearsals.insert_one({
                "id": _uuid(),
                "organization_id": org_id,
                "event_id": event_id,
                "name": r["name"],
                "starts_at": r_start.isoformat(),
                "ends_at": r_end.isoformat(),
                "room": "",
                "notes": "Auto-generated from event template — edit anytime.",
                "created_at": _now_iso(),
                "auto_generated": True,
            })
            rehearsals_created += 1

    costumes_created = 0
    costumes_skipped = 0
    if body.include_costumes and template.get("auto_costumes"):
        # Active org members, capped at 500 so a huge studio doesn't
        # accidentally drown the costume tracker.
        members = await db.members.find(
            {"organization_id": org_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1},
        ).limit(500).to_list(500)

        # Existing attendee_name set (case-insensitive) so we don't
        # double-add rows on re-runs.
        existing_attendees = {
            (c.get("attendee_name") or "").strip().lower()
            async for c in db.event_costumes.find(
                {"event_id": event_id, "organization_id": org_id},
                {"_id": 0, "attendee_name": 1},
            )
        }
        default_costume = template.get("default_costume_name") or "Costume — TBC"
        for m in members:
            attendee = f"{m.get('first_name', '').strip()} {m.get('last_name', '').strip()}".strip()
            if not attendee or attendee.lower() in existing_attendees:
                costumes_skipped += 1
                continue
            await db.event_costumes.insert_one({
                "id": _uuid(),
                "organization_id": org_id,
                "event_id": event_id,
                "member_id": m.get("id"),
                "sub_profile_id": None,
                "attendee_name": attendee,
                "costume_name": default_costume,
                "size": "",
                "notes": "",
                "total_pence": 0,
                "paid_pence": 0,
                "status": "needed",
                "created_at": _now_iso(),
                "auto_generated": True,
            })
            costumes_created += 1

    return {
        "ok": True,
        "kind": kind,
        "rehearsals_created": rehearsals_created,
        "rehearsals_skipped": rehearsals_skipped,
        "costumes_created": costumes_created,
        "costumes_skipped": costumes_skipped,
    }


# ─────────────────────────────────────────────────────────────────
# Rehearsals
# ─────────────────────────────────────────────────────────────────

class RehearsalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    starts_at: str
    ends_at: str
    room: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=600)


@router.get(
    "/memberships/events/{event_id}/rehearsals",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_rehearsals(event_id: str, user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rows = await db.event_rehearsals.find(
        {"organization_id": org_id, "event_id": event_id}, {"_id": 0},
    ).sort("starts_at", 1).to_list(500)
    return {"rehearsals": rows, "count": len(rows)}


@router.post(
    "/memberships/events/{event_id}/rehearsals",
    dependencies=[Depends(require_module("memberships"))],
)
async def create_rehearsal(
    event_id: str, body: RehearsalIn = Body(...), user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    if not await db.studio_events.find_one(
        {"id": event_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    ):
        raise HTTPException(404, "Event not found")
    starts, ends = _validate_window(body.starts_at, body.ends_at)
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "event_id": event_id,
        "name": body.name.strip(),
        "starts_at": starts,
        "ends_at": ends,
        "room": (body.room or "").strip(),
        "notes": (body.notes or "").strip(),
        "created_at": _now_iso(),
    }
    await db.event_rehearsals.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete(
    "/memberships/events/{event_id}/rehearsals/{rid}",
    dependencies=[Depends(require_module("memberships"))],
)
async def delete_rehearsal(
    event_id: str, rid: str, user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    res = await db.event_rehearsals.delete_one(
        {"id": rid, "event_id": event_id, "organization_id": org_id},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Rehearsal not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Costumes
# ─────────────────────────────────────────────────────────────────

class CostumeIn(BaseModel):
    member_id: Optional[str] = None
    sub_profile_id: Optional[str] = None
    attendee_name: str = Field(min_length=1, max_length=120)
    costume_name: str = Field(min_length=1, max_length=120)
    size: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=400)
    total_pence: int = Field(default=0, ge=0, le=100_000)
    status: Literal["needed", "ordered", "arrived", "fitted", "paid", "refunded"] = "needed"


class CostumePatchIn(BaseModel):
    status: Optional[str] = None
    size: Optional[str] = None
    notes: Optional[str] = None
    total_pence: Optional[int] = None
    paid_pence: Optional[int] = None
    ordered_at: Optional[str] = None
    arrived_at: Optional[str] = None
    fitted_at: Optional[str] = None
    costume_name: Optional[str] = None


@router.get(
    "/memberships/events/{event_id}/costumes",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_costumes(event_id: str, user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rows = await db.event_costumes.find(
        {"organization_id": org_id, "event_id": event_id}, {"_id": 0},
    ).sort("attendee_name", 1).to_list(2000)
    summary = {
        "total_count": len(rows),
        "total_pence": sum(int(r.get("total_pence") or 0) for r in rows),
        "paid_pence":  sum(int(r.get("paid_pence")  or 0) for r in rows),
        "by_status": {},
    }
    for r in rows:
        s = r.get("status") or "needed"
        summary["by_status"][s] = summary["by_status"].get(s, 0) + 1
    return {"costumes": rows, "count": len(rows), "summary": summary}


@router.post(
    "/memberships/events/{event_id}/costumes",
    dependencies=[Depends(require_module("memberships"))],
)
async def create_costume(
    event_id: str, body: CostumeIn = Body(...), user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    if not await db.studio_events.find_one(
        {"id": event_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    ):
        raise HTTPException(404, "Event not found")
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "event_id": event_id,
        "member_id": body.member_id,
        "sub_profile_id": body.sub_profile_id,
        "attendee_name": body.attendee_name.strip(),
        "costume_name": body.costume_name.strip(),
        "size": (body.size or "").strip(),
        "notes": (body.notes or "").strip(),
        "total_pence": int(body.total_pence),
        "paid_pence": 0,
        "status": body.status,
        "ordered_at": None, "arrived_at": None, "fitted_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.event_costumes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch(
    "/memberships/events/{event_id}/costumes/{cid}",
    dependencies=[Depends(require_module("memberships"))],
)
async def patch_costume(
    event_id: str, cid: str, body: CostumePatchIn = Body(...),
    user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    update: dict = {}
    payload = body.dict(exclude_none=True)
    if "status" in payload:
        if payload["status"] not in _COSTUME_STATUSES:
            raise HTTPException(400, f"status must be one of {sorted(_COSTUME_STATUSES)}")
        # Auto-stamp the timestamp on first transition.
        ts_map = {"ordered": "ordered_at", "arrived": "arrived_at", "fitted": "fitted_at"}
        ts_field = ts_map.get(payload["status"])
        if ts_field:
            existing = await db.event_costumes.find_one(
                {"id": cid, "organization_id": org_id, "event_id": event_id},
                {"_id": 0, ts_field: 1},
            ) or {}
            if not existing.get(ts_field):
                update[ts_field] = _now_iso()
    update.update(payload)
    update["updated_at"] = _now_iso()
    res = await db.event_costumes.update_one(
        {"id": cid, "organization_id": org_id, "event_id": event_id},
        {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Costume not found")
    return await db.event_costumes.find_one(
        {"id": cid, "organization_id": org_id, "event_id": event_id}, {"_id": 0},
    )


@router.delete(
    "/memberships/events/{event_id}/costumes/{cid}",
    dependencies=[Depends(require_module("memberships"))],
)
async def delete_costume(
    event_id: str, cid: str, user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    res = await db.event_costumes.delete_one(
        {"id": cid, "organization_id": org_id, "event_id": event_id},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Costume not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# AI-drafted comms + bulk announcement
# ─────────────────────────────────────────────────────────────────

class AnnounceIn(BaseModel):
    subject: str = Field(min_length=1, max_length=180)
    body_html: str = Field(min_length=10, max_length=20_000)
    audience: Literal["all_members", "event_attendees"] = "all_members"


@router.post(
    "/memberships/events/{event_id}/announce",
    dependencies=[Depends(require_module("memberships"))],
)
async def announce_event(
    event_id: str, body: AnnounceIn = Body(...), user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    event = await db.studio_events.find_one(
        {"id": event_id, "organization_id": org_id}, {"_id": 0},
    )
    if not event:
        raise HTTPException(404, "Event not found")

    if body.audience == "event_attendees":
        member_ids = sorted({c.get("member_id") for c in await db.event_costumes.find(
            {"organization_id": org_id, "event_id": event_id}, {"_id": 0, "member_id": 1},
        ).to_list(5000) if c.get("member_id")})
        if not member_ids:
            return {"ok": True, "sent": 0, "audience_size": 0,
                    "note": "No costumed attendees yet — fall back to all_members"}
        members = await db.members.find(
            {"organization_id": org_id, "id": {"$in": member_ids}, "email": {"$ne": None}},
            {"_id": 0, "email": 1, "first_name": 1},
        ).to_list(len(member_ids) + 1)
    else:
        members = await db.members.find(
            {"organization_id": org_id, "status": {"$ne": "cancelled"},
             "email": {"$ne": None}},
            {"_id": 0, "email": 1, "first_name": 1},
        ).to_list(5000)

    sent = 0
    for m in members:
        to = (m.get("email") or "").strip()
        if not to or "@" not in to:
            continue
        try:
            ok = await send_email(to=to, subject=body.subject, html=body.body_html, category="memberships")
            if ok:
                sent += 1
        except Exception:
            logger.warning("event announce send failed", exc_info=True)
    await db.studio_events.update_one(
        {"id": event_id},
        {"$set": {"last_announce_at": _now_iso(), "last_announce_count": sent}},
    )
    return {"ok": True, "sent": sent, "audience_size": len(members)}


@router.post(
    "/memberships/events/{event_id}/ai-comms",
    dependencies=[Depends(require_module("memberships"))],
)
async def ai_event_comms(
    event_id: str, prompt: dict = Body(default_factory=dict),
    user=Depends(get_current_user),
):
    """Use Claude Haiku via the Emergent LLM key to draft a parent-friendly
    rehearsal-week comms email for the supplied event. Returns subject +
    body — the operator reviews & sends via /announce."""
    org_id = await _require_operator_org(user)
    event = await db.studio_events.find_one(
        {"id": event_id, "organization_id": org_id}, {"_id": 0},
    )
    if not event:
        raise HTTPException(404, "Event not found")
    rehearsals = await db.event_rehearsals.find(
        {"organization_id": org_id, "event_id": event_id}, {"_id": 0},
    ).sort("starts_at", 1).to_list(50)

    # Lazy LLM import — uses the same emergentintegrations pattern as
    # utils/memberships_ai_insights.py.
    import os
    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
    if not api_key:
        return {
            "subject": f"{event.get('name')} — important update for parents",
            "body_html": (
                "<p>Dear families,</p>"
                f"<p>Just a quick note ahead of <strong>{event.get('name')}</strong> on "
                f"<strong>{(event.get('starts_at') or '')[:16]}</strong>"
                f" at <strong>{event.get('venue') or 'our studio'}</strong>.</p>"
                "<p>Please drop your dancers off 30 minutes before the curtain.</p>"
                "<p>Thank you,<br>The team</p>"
            ),
            "model": "fallback_template_no_key",
        }

    extra = (prompt or {}).get("instructions") or ""
    rehearsal_lines = "\n".join(
        f"- {r.get('name')} on {(r.get('starts_at') or '')[:16]} ({r.get('room') or 'TBC'})"
        for r in rehearsals[:10]
    ) or "(no rehearsals scheduled)"
    user_prompt = (
        "Draft a warm, professional email to parents about an upcoming studio event. "
        "Keep it under 220 words, clear paragraphs, no emoji. Output ONLY HTML body — "
        "no <html> or <head>; start with <p>.\n\n"
        f"Event: {event.get('name')}\n"
        f"Type: {event.get('kind')}\n"
        f"When: {(event.get('starts_at') or '')[:16]} → {(event.get('ends_at') or '')[:16]}\n"
        f"Venue: {event.get('venue') or 'Our studio'}\n"
        f"Description: {event.get('description') or '(none)'}\n"
        f"Rehearsals:\n{rehearsal_lines}\n\n"
        f"Operator notes for the AI: {extra or '(none)'}"
    )
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"event-comms-{event_id}",
            system_message="You are a friendly, professional studio admin writing to parents.",
        ).with_model("anthropic", "claude-haiku-4-5")
        body_html = await chat.send_message(UserMessage(text=user_prompt))
    except Exception:
        logger.exception("Claude draft failed; returning fallback")
        body_html = (
            f"<p>Dear families,</p><p>Quick reminder about <strong>{event.get('name')}</strong> on "
            f"<strong>{(event.get('starts_at') or '')[:16]}</strong>.</p>"
        )
    return {
        "subject": f"{event.get('name')} — what parents need to know",
        "body_html": body_html,
        "model": "claude_haiku_4_5",
    }



# ═════════════ Member-side event ticketing (iter 216ak · Sprint B · G6) ═════════════

from routes.memberships.helpers import _require_current_member  # noqa: E402


@router.get("/member/events")
async def member_list_events(
    member: dict = Depends(_require_current_member),
    upcoming_only: bool = Query(True),
):
    """Member-facing: list events for the member's org. Used by the Events
    tab in the member portal. Hides archived and past events by default.
    Annotates each row with `my_tickets` (the member's own ticket count)
    so the UI can show 'You have 2 tickets' inline."""
    org_id = member.get("organization_id")
    if not org_id:
        raise HTTPException(400, "Member has no organization")
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if upcoming_only:
        q["ends_at"] = {"$gte": _now_iso()}
    rows = await db.studio_events.find(q, {"_id": 0}).sort("starts_at", 1).to_list(200)

    # Batch-load the member's own tickets so we can stamp counts without
    # hitting the DB per-row.
    event_ids = [r["id"] for r in rows]
    my_counts: dict[str, int] = {}
    if event_ids:
        async for t in db.studio_event_tickets.find(
            {"event_id": {"$in": event_ids}, "buyer_member_id": member["id"],
             "status": {"$in": ["paid", "pending_invoice"]}},
            {"_id": 0, "event_id": 1, "quantity": 1},
        ):
            my_counts[t["event_id"]] = my_counts.get(t["event_id"], 0) + int(t.get("quantity") or 1)
    for r in rows:
        r["my_tickets"] = my_counts.get(r["id"], 0)
        r["tickets_remaining"] = max(
            int(r.get("ticket_capacity") or 0) - int(r.get("tickets_sold") or 0), 0,
        ) if int(r.get("ticket_capacity") or 0) > 0 else None
    return {"events": rows, "count": len(rows)}


@router.post("/member/events/{event_id}/tickets")
async def member_buy_event_tickets(
    event_id: str,
    body: dict = Body(...),
    member: dict = Depends(_require_current_member),
):
    """Member purchases N tickets for an event.

    Body: { "quantity": 1..8, "payment": "credit"|"on-statement" }
    - "on-statement" (default) adds the tickets as a line on the next
      monthly invoice — same pattern as the costume→invoice hook. No
      immediate charge, safest for family plans.
    - "credit" reserved for future Stripe one-shot checkout; returns 400
      for now so operators know it's not wired yet.

    Enforces capacity (hard block), returns 409 when sold-out.
    """
    org_id = member.get("organization_id")
    raw_qty = (body or {}).get("quantity", 1)
    try:
        qty = int(raw_qty)
    except (TypeError, ValueError):
        qty = 0
    if qty < 1 or qty > 8:
        raise HTTPException(400, "quantity must be 1..8")
    payment = ((body or {}).get("payment") or "on-statement").lower()
    if payment == "credit":
        raise HTTPException(400, "Card checkout for event tickets is not available yet — use 'on-statement'")
    if payment not in ("on-statement",):
        raise HTTPException(400, "payment must be 'on-statement'")

    ev = await db.studio_events.find_one(
        {"id": event_id, "organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    )
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.get("ends_at") and ev["ends_at"] < _now_iso():
        raise HTTPException(400, "Event has ended")
    cap = int(ev.get("ticket_capacity") or 0)
    sold = int(ev.get("tickets_sold") or 0)
    if cap > 0 and sold + qty > cap:
        raise HTTPException(409, f"Only {max(cap - sold, 0)} ticket(s) left")

    unit = int(ev.get("ticket_price_pence") or 0)
    total = unit * qty

    ticket = {
        "id": _uuid(),
        "organization_id": org_id,
        "event_id": event_id,
        "buyer_member_id": member["id"],
        "quantity": qty,
        "unit_pence": unit,
        "total_pence": total,
        "status": "paid" if total == 0 else "pending_invoice",
        "payment_method": "on_statement",
        "created_at": _now_iso(),
    }
    await db.studio_event_tickets.insert_one(ticket)
    await db.studio_events.update_one(
        {"id": event_id}, {"$inc": {"tickets_sold": qty}},
    )
    return {
        "ok": True,
        "ticket": {k: v for k, v in ticket.items() if k != "_id"},
        "event_name": ev.get("name"),
        "total_pence": total,
    }


# ═════════════ Home widget: "Next class" + unread (G12) ═════════════


@router.get("/member/home-widget")
async def member_home_widget(member: dict = Depends(_require_current_member)):
    """Iter 216ak — compact endpoint powering the member portal's Home
    hero. Single round-trip so the first paint is fast.

    Returns:
      {
        next_class: { id, name, starts_at, room_name, in_minutes, booked_count },
        last_booked: [... last 3 class occurrences ...],
        unread_notifications: int,
        unsigned_forms: int,
        outstanding_invoice_pence: int,
      }
    """
    org_id = member.get("organization_id")
    now_iso = _now_iso()

    # Next booking (own + sub-profiles) — the closest upcoming "booked"/"waitlist".
    sub_ids: list[str] = []
    async for sp in db.member_sub_profiles.find(
        {"organization_id": org_id, "member_id": member["id"]}, {"_id": 0, "id": 1},
    ):
        sub_ids.append(sp["id"])
    booking_q = {
        "organization_id": org_id,
        "status": {"$in": ["booked", "waitlist"]},
        "$or": [{"member_id": member["id"]}],
    }
    if sub_ids:
        booking_q["$or"].append({"attendee_sub_profile_id": {"$in": sub_ids}})
    bookings = await db.bookings.find(
        booking_q, {"_id": 0, "occurrence_id": 1, "status": 1},
    ).to_list(50)
    occ_ids = [b["occurrence_id"] for b in bookings]
    next_class = None
    if occ_ids:
        occ_docs = await db.class_occurrences.find(
            {"id": {"$in": occ_ids}, "starts_at": {"$gte": now_iso}, "status": "scheduled"},
            {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "ends_at": 1,
             "room_name": 1, "bookings_count": 1, "capacity": 1},
        ).sort("starts_at", 1).to_list(20)
        if occ_docs:
            top = occ_docs[0]
            try:
                delta = datetime.fromisoformat(top["starts_at"]) - datetime.now(timezone.utc)
                in_minutes = max(int(delta.total_seconds() // 60), 0)
            except Exception:  # noqa: BLE001
                in_minutes = None
            next_class = {
                "id": top["id"],
                "name": top.get("name"),
                "starts_at": top["starts_at"],
                "ends_at": top.get("ends_at"),
                "room_name": top.get("room_name"),
                "in_minutes": in_minutes,
                "booked_count": int(top.get("bookings_count") or 0),
                "capacity": int(top.get("capacity") or 0),
            }

    # "Last booked" — the 3 most recent class templates the member used.
    # Used for the one-tap rebook widget.
    recent_tpl_ids: list[str] = []
    seen: set[str] = set()
    recent_bookings = await db.bookings.find(
        {"organization_id": org_id, "member_id": member["id"], "status": {"$in": ["attended", "booked"]}},
        {"_id": 0, "occurrence_id": 1, "booked_at": 1},
    ).sort("booked_at", -1).to_list(30)
    for b in recent_bookings:
        occ = await db.class_occurrences.find_one(
            {"id": b["occurrence_id"]}, {"_id": 0, "template_id": 1, "name": 1},
        )
        if not occ or not occ.get("template_id"):
            continue
        tid = occ["template_id"]
        if tid in seen:
            continue
        seen.add(tid)
        recent_tpl_ids.append(tid)
        if len(recent_tpl_ids) >= 3:
            break
    last_booked: list[dict] = []
    if recent_tpl_ids:
        last_booked = await db.class_templates.find(
            {"id": {"$in": recent_tpl_ids}},
            {"_id": 0, "id": 1, "name": 1, "duration_min": 1, "colour": 1},
        ).to_list(10)

    unsigned_forms = await db.member_consent_signatures.count_documents(
        {"member_id": member["id"], "status": "due"},
    ) if hasattr(db, "member_consent_signatures") else 0

    inv_cursor = db.membership_class_invoices.aggregate([
        {"$match": {"organization_id": org_id, "member_id": member["id"],
                    "status": {"$in": ["sent", "overdue"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_pence"}}},
    ])
    inv_agg = await inv_cursor.to_list(length=1)
    outstanding = int(inv_agg[0]["total"]) if inv_agg else 0

    return {
        "next_class": next_class,
        "last_booked": last_booked,
        "unread_notifications": 0,  # reserved
        "unsigned_forms": int(unsigned_forms or 0),
        "outstanding_invoice_pence": outstanding,
    }


__all__ = ["router"]
