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
from typing import Optional, Literal, List

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
            ok = await send_email(to=to, subject=body.subject, html=body.body_html)
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


__all__ = ["router"]
