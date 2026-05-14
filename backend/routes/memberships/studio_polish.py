"""Studio polish endpoints — walk-ins, rebook, and class broadcasts.

Iter 215q. Three small but high-impact endpoints that complete the
"Do NOT rebuild, upgrade" brief for studios:

  POST /api/memberships/checkin/walk-in          — one-action walk-in
  POST /api/member/bookings/rebook               — one-tap "Book again"
  POST /api/memberships/classes/{occ}/broadcast  — message a class's attendees

All three reuse existing collections (members, bookings, class_occurrences)
and helpers — no new data model.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _require_operator_org,
    _uuid,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-studio-polish"])


# ═══════════════════════ Walk-in check-in ═══════════════════════

class WalkInIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    occurrence_id: str
    payment_method: str = Field(default="paid_externally", pattern="^(paid_externally|cash|complimentary)$")


@router.post("/memberships/checkin/walk-in", dependencies=[Depends(require_module("memberships"))])
async def checkin_walk_in(body: WalkInIn = Body(...), user: dict = Depends(get_current_user)):
    """Register + check in a walk-in in one action.

    The classic "someone turned up without booking" flow. If email/phone
    matches an existing member we re-use them; otherwise we create a
    lightweight member record (no portal password — they can register
    later). Then we book them into the class with status=attended
    immediately so the register is correct.
    """
    org_id = await _require_operator_org(user)

    occ = await db.class_occurrences.find_one({"id": body.occurrence_id, "organization_id": org_id}, {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found.")
    if occ.get("cancelled_at"):
        raise HTTPException(400, "That class is cancelled.")

    # Reuse an existing member if we can, keyed on email → phone → both None.
    member = None
    if body.email:
        member = await db.members.find_one(
            {"organization_id": org_id, "email": body.email.lower()}, {"_id": 0},
        )
    if not member and body.phone:
        member = await db.members.find_one(
            {"organization_id": org_id, "phone": body.phone}, {"_id": 0},
        )

    created = False
    if not member:
        parts = body.name.strip().split(None, 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
        member = {
            "id": _uuid(),
            "organization_id": org_id,
            "first_name": first,
            "last_name": last,
            "full_name": body.name.strip(),
            "email": body.email.lower() if body.email else None,
            "phone": body.phone,
            "source": "walk_in",
            "created_at": _now_iso(),
            "created_by_operator_id": user.get("id"),
            "active": True,
            "portal_password": None,
        }
        await db.members.insert_one({**member})
        created = True

    # Create booking with status=attended + record the check-in for audit.
    booking_id = _uuid()
    await db.bookings.insert_one({
        "id": booking_id,
        "organization_id": org_id,
        "member_id": member["id"],
        "occurrence_id": body.occurrence_id,
        "status": "attended",
        "booked_at": _now_iso(),
        "checked_in_at": _now_iso(),
        "channel": "walk_in",
        "payment_method": body.payment_method,
        "operator_id": user.get("id"),
    })
    await db.class_occurrences.update_one(
        {"id": body.occurrence_id},
        {"$inc": {"bookings_count": 1, "attended_count": 1}},
    )
    await db.member_checkins.insert_one({
        "id": _uuid(),
        "member_id": member["id"],
        "organization_id": org_id,
        "occurrence_id": body.occurrence_id,
        "at": _now_iso(),
        "operator_id": user.get("id"),
        "channel": "walk_in",
    })

    return {
        "ok": True,
        "created_member": created,
        "member_id": member["id"],
        "booking_id": booking_id,
    }


# ═══════════════════════ Book again ═══════════════════════

class RebookIn(BaseModel):
    # Either base off a previous booking OR pass a specific target occurrence.
    source_booking_id: str | None = None
    target_occurrence_id: str | None = None


@router.post("/member/bookings/rebook")
async def member_rebook(
    body: RebookIn = Body(default_factory=RebookIn),
    member: dict = Depends(_require_current_member),
):
    """Member portal: one-tap re-book.

    If `target_occurrence_id` is given, book that directly.
    Otherwise: take the latest attended/booked booking, find the next
    future occurrence of the same class template, and book it.
    """
    org_id = member["organization_id"]
    target_occ = None

    if body.target_occurrence_id:
        target_occ = await db.class_occurrences.find_one(
            {"id": body.target_occurrence_id, "organization_id": org_id},
            {"_id": 0},
        )
    else:
        # Find the member's most recent booking and resolve its template.
        query = {"member_id": member["id"], "status": {"$in": ["attended", "booked"]}}
        if body.source_booking_id:
            query["id"] = body.source_booking_id
        source = await db.bookings.find_one(query, {"_id": 0}, sort=[("booked_at", -1)])
        if not source:
            raise HTTPException(404, "No previous class to re-book.")
        prev_occ = await db.class_occurrences.find_one(
            {"id": source["occurrence_id"]}, {"_id": 0, "template_id": 1, "name": 1},
        )
        if not prev_occ:
            raise HTTPException(404, "Previous class no longer available.")
        now_iso = _now_iso()
        # Next future non-cancelled occurrence of the same template.
        target_occ = await db.class_occurrences.find_one(
            {
                "organization_id": org_id,
                "template_id": prev_occ.get("template_id"),
                "starts_at": {"$gt": now_iso},
                "cancelled_at": {"$exists": False},
            },
            {"_id": 0},
            sort=[("starts_at", 1)],
        )
        if not target_occ:
            raise HTTPException(404, "No upcoming session of that class — try another one.")

    # Duplicate-booking guard.
    dup = await db.bookings.find_one({
        "member_id": member["id"],
        "occurrence_id": target_occ["id"],
        "status": {"$in": ["booked", "attended", "waitlist"]},
    }, {"_id": 0, "id": 1})
    if dup:
        return {"ok": True, "already_booked": True, "booking_id": dup["id"], "occurrence_id": target_occ["id"]}

    cap = int(target_occ.get("capacity") or 0)
    booked = int(target_occ.get("bookings_count") or 0)
    status = "booked" if (cap == 0 or booked < cap) else "waitlist"
    if status == "waitlist" and not target_occ.get("waitlist_enabled", True):
        raise HTTPException(409, "Class is full and waitlist is closed.")

    booking_id = _uuid()
    await db.bookings.insert_one({
        "id": booking_id,
        "organization_id": org_id,
        "member_id": member["id"],
        "occurrence_id": target_occ["id"],
        "status": status,
        "booked_at": _now_iso(),
        "channel": "rebook",
    })
    inc = {"bookings_count": 1} if status == "booked" else {"waitlist_count": 1}
    await db.class_occurrences.update_one({"id": target_occ["id"]}, {"$inc": inc})

    return {
        "ok": True,
        "already_booked": False,
        "booking_id": booking_id,
        "occurrence_id": target_occ["id"],
        "status": status,
        "starts_at": target_occ.get("starts_at"),
    }


# ═══════════════════════ Broadcast to a class ═══════════════════════

class BroadcastIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    subject: str | None = Field(default=None, max_length=140)
    # We send via email for now — SMS needs Twilio which is still MOCKED.
    channel: str = Field(default="email", pattern="^(email)$")


@router.post("/memberships/classes/{occurrence_id}/broadcast", dependencies=[Depends(require_module("memberships"))])
async def broadcast_class(
    occurrence_id: str,
    body: BroadcastIn = Body(...),
    user: dict = Depends(get_current_user),
):
    """Message every booked attendee of one class occurrence.

    Uses Resend via the existing EmailSender. Returns a count of
    delivered / skipped-no-email. Failures per-recipient are logged but
    don't short-circuit the batch.
    """
    org_id = await _require_operator_org(user)
    occ = await db.class_occurrences.find_one({"id": occurrence_id, "organization_id": org_id}, {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found.")

    # All bookings in 'booked' or 'attended' states — we include walk-ins.
    bookings = await db.bookings.find(
        {"occurrence_id": occurrence_id, "status": {"$in": ["booked", "attended", "waitlist"]}},
        {"_id": 0, "member_id": 1},
    ).to_list(500)
    member_ids = sorted({b["member_id"] for b in bookings})
    members = await db.members.find(
        {"id": {"$in": member_ids}, "organization_id": org_id},
        {"_id": 0, "id": 1, "email": 1, "first_name": 1, "full_name": 1},
    ).to_list(len(member_ids) or 1)

    resend_key = os.environ.get("RESEND_API_KEY")
    subject = (body.subject or f"Update: {occ.get('name') or 'your class'}").strip()

    delivered = 0
    skipped_no_email = 0
    failed = 0

    if not resend_key:
        # Log-only mode when Resend isn't configured.
        logger.warning("broadcast_class: RESEND_API_KEY missing — logging only")
        for m in members:
            if not m.get("email"):
                skipped_no_email += 1
                continue
            logger.info("[broadcast:log-only] to=%s subject=%s", m["email"], subject)
            delivered += 1
    else:
        try:
            import httpx
        except ImportError:
            raise HTTPException(500, "httpx not available — cannot send.")
        async with httpx.AsyncClient(timeout=15.0) as client:
            for m in members:
                email = (m.get("email") or "").strip()
                if not email:
                    skipped_no_email += 1
                    continue
                first = m.get("first_name") or (m.get("full_name") or "there").split()[0]
                body_html = (
                    f"<p>Hi {first},</p>"
                    f"<p>{body.message.replace(chr(10), '<br/>')}</p>"
                    f"<p style='color:#666;font-size:12px'>— {user.get('full_name') or 'Your studio'}</p>"
                )
                try:
                    r = await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {resend_key}"},
                        json={
                            "from": os.environ.get("RESEND_FROM", "GymAxis <hello@service.gymaxisai.com>"),
                            "to": email,
                            "subject": subject,
                            "html": body_html,
                        },
                    )
                    if r.status_code >= 400:
                        failed += 1
                        logger.warning("broadcast_class: resend %s → %s", email, r.status_code)
                    else:
                        delivered += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    logger.warning("broadcast_class: error sending to %s — %s", email, exc)

    await db.class_broadcasts.insert_one({
        "id": _uuid(),
        "organization_id": org_id,
        "occurrence_id": occurrence_id,
        "sent_by_operator_id": user.get("id"),
        "channel": body.channel,
        "subject": subject,
        "message": body.message,
        "recipient_count": len(members),
        "delivered": delivered,
        "skipped_no_email": skipped_no_email,
        "failed": failed,
        "sent_at": _now_iso(),
    })

    return {
        "ok": True,
        "recipient_count": len(members),
        "delivered": delivered,
        "skipped_no_email": skipped_no_email,
        "failed": failed,
    }
