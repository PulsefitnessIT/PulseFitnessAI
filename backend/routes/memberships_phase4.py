"""Pulse Fitness Memberships — Phase 4.

Smart Waitlist / Fill System + Front-Desk Check-in console + Kiosk mode.

Endpoints (all `/api/memberships/*` prefix added by the api router):

  Operator (JWT):
    GET  /memberships/checkin/today                       — today's classes summary
    GET  /memberships/members/search?q=                   — front-desk lookup
    POST /memberships/checkin/{occ_id}/mark               — single mark-attended toggle
    POST /memberships/occurrences/{occ_id}/dropin-invite  — manual broadcast
    POST /memberships/checkin/kiosk-token                  — issue/rotate kiosk token
    GET  /memberships/checkin/kiosk-token                  — read current token
    GET  /memberships/phase4/analytics                     — fill-rate uplift, no-show, drop-in conversion

  Member (JWT kind=member):
    POST /member/dropin-optin                             — toggle drop-in invite consent
    GET  /member/waitlist-position?occurrence_id=         — see your spot in the queue

  Public kiosk (token query param, no JWT):
    GET  /memberships/kiosk/today?token=                  — public: today's classes
    POST /memberships/kiosk/lookup                        — public: search member by name
    POST /memberships/kiosk/checkin                       — public: TOTP verify + mark attended

The kiosk uses an opaque token tied to an org. Operators rotate it any
time via POST /checkin/kiosk-token. Tokens are stored hashed in
`db.kiosk_tokens`.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routes.memberships import _require_current_member, _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.memberships_emails import send_dropin_invite
from utils.module_guard import require_module
from utils.security_plus import rate_limit_async

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-phase4"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


# ═════════════════════ Drop-in invite engine ═════════════════════


# Auto-fire window. If the occurrence starts within DROPIN_WINDOW_HOURS
# AND the waitlist is empty AND there's at least one open spot, broadcast.
DROPIN_WINDOW_HOURS = 24
DROPIN_MAX_RECIPIENTS = 200


async def maybe_send_dropin_invites(occ: dict, background: BackgroundTasks | None) -> int:
    """Auto-trigger entrypoint called from member cancel flow.

    Returns number of invites scheduled (0 if not eligible)."""
    if not occ or not background:
        return 0
    cap = int(occ.get("capacity") or 0)
    booked = int(occ.get("bookings_count") or 0)
    wl = int(occ.get("waitlist_count") or 0)
    if cap <= 0 or booked >= cap or wl > 0:
        return 0
    starts_at = occ.get("starts_at")
    if not starts_at:
        return 0
    try:
        starts = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    except Exception:
        return 0
    if starts <= _now() or starts > _now() + timedelta(hours=DROPIN_WINDOW_HOURS):
        return 0
    return await _broadcast_dropin(occ, background, source="auto_cancel")


async def _broadcast_dropin(occ: dict, background: BackgroundTasks, source: str) -> int:
    """Find opted-in active members in this org without a booking on this
    occurrence, send invite emails (capped). Logs the run for analytics."""
    org_id = occ.get("organization_id")
    if not org_id:
        return 0
    # Members in this org who have opted in to drop-in invites
    optins = await db.members.find(
        {"organization_id": org_id, "drop_in_optin": True,
         "status": {"$in": ["active", "trialling"]}},
        {"_id": 0, "id": 1, "email": 1, "first_name": 1, "last_name": 1},
    ).limit(DROPIN_MAX_RECIPIENTS * 2).to_list(DROPIN_MAX_RECIPIENTS * 2)
    if not optins:
        return 0
    # Exclude members who already have a booking on this occurrence
    already_booked: set[str] = set()
    async for b in db.bookings.find(
        {"occurrence_id": occ["id"], "status": {"$in": ["booked", "waitlist"]}},
        {"_id": 0, "member_id": 1},
    ):
        already_booked.add(b["member_id"])

    recipients = [m for m in optins if m["id"] not in already_booked][:DROPIN_MAX_RECIPIENTS]
    if not recipients:
        return 0
    sent_ids: list[str] = []
    for mem in recipients:
        if mem.get("email"):
            background.add_task(send_dropin_invite, mem, occ, None)
            sent_ids.append(mem["id"])
    await db.dropin_invites.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "occurrence_id": occ["id"],
        "source": source,
        "sent_to_ids": sent_ids,
        "sent_count": len(sent_ids),
        "created_at": _now_iso(),
    })
    return len(sent_ids)


@router.post(
    "/memberships/occurrences/{occ_id}/dropin-invite",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_send_dropin_invites(
    occ_id: str, background: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Manual operator broadcast — fire drop-in invites for an
    under-capacity class right now, regardless of the auto-trigger
    window."""
    org_id = await _require_operator_org(user)
    occ = await db.class_occurrences.find_one(
        {"id": occ_id, "organization_id": org_id}, {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class not found")
    cap = int(occ.get("capacity") or 0)
    booked = int(occ.get("bookings_count") or 0)
    if cap <= 0 or booked >= cap:
        raise HTTPException(400, "Class is full — nothing to invite")
    sent = await _broadcast_dropin(occ, background, source="operator_manual")
    return {"ok": True, "invites_sent": sent}


# ═════════════════════ Member opt-in toggle ═════════════════════


class DropInOptIn(BaseModel):
    opt_in: bool


@router.post("/member/dropin-optin")
async def member_set_dropin_optin(
    body: DropInOptIn, member: dict = Depends(_require_current_member),
):
    await db.members.update_one(
        {"id": member["id"]},
        {"$set": {"drop_in_optin": bool(body.opt_in),
                  "drop_in_optin_at": _now_iso()}},
    )
    return {"ok": True, "drop_in_optin": bool(body.opt_in)}


@router.get("/member/waitlist-position")
async def member_waitlist_position(
    occurrence_id: str, member: dict = Depends(_require_current_member),
):
    """Returns 1-based position in the waitlist queue for this member,
    or null if not waitlisted on this occurrence."""
    b = await db.bookings.find_one(
        {"occurrence_id": occurrence_id, "member_id": member["id"], "status": "waitlist"},
        {"_id": 0, "booked_at": 1},
    )
    if not b:
        return {"position": None, "waitlist_count": 0}
    ahead = await db.bookings.count_documents({
        "occurrence_id": occurrence_id, "status": "waitlist",
        "booked_at": {"$lt": b.get("booked_at") or ""},
    })
    total = await db.bookings.count_documents({
        "occurrence_id": occurrence_id, "status": "waitlist",
    })
    return {"position": ahead + 1, "waitlist_count": total}


# ═════════════════════ Front-Desk Check-in console ═════════════════════


@router.get(
    "/memberships/checkin/today",
    dependencies=[Depends(require_module("memberships"))],
)
async def checkin_today(
    background: BackgroundTasks,
    days: int = Query(default=1, ge=1, le=7),
    user: dict = Depends(get_current_user),
):
    """Returns today (and optionally next N days) of scheduled classes
    for the front-desk check-in console."""
    org_id = await _require_operator_org(user)
    now = _now()
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    until = start_of_day + timedelta(days=days)
    occs = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": start_of_day.isoformat(), "$lte": until.isoformat()},
         "status": {"$ne": "cancelled"}},
        {"_id": 0},
    ).sort("starts_at", 1).to_list(200)
    # P1-3: schedule the lazy no-show marker as a background task so the
    # GET responds immediately. The next refresh of the check-in tab
    # (or the next periodic poll) will pick up the updated counts.
    eligible_ids = []
    cutoff = now - timedelta(minutes=15)
    for occ in occs:
        try:
            ends = datetime.fromisoformat(occ["starts_at"].replace("Z", "+00:00"))
            duration = int(occ.get("duration_min") or 0)
            ends_at = ends + timedelta(minutes=duration)
        except Exception:
            continue
        if (occ.get("status") != "completed" and ends_at < cutoff
                and not occ.get("attended_count") and not occ.get("no_show_count")):
            eligible_ids.append(occ["id"])
    if eligible_ids:
        background.add_task(_lazy_mark_no_shows, org_id, eligible_ids)

    return {"classes": occs, "count": len(occs)}


async def _lazy_mark_no_shows(org_id: str, occ_ids: list[str]) -> None:
    """Background worker: for each occurrence in `occ_ids`, flip every
    still-`booked` booking → `no_show`, increment member.no_show_count,
    and snapshot the occurrence as `completed`."""
    for occ_id in occ_ids:
        unmarked = await db.bookings.find(
            {"occurrence_id": occ_id, "organization_id": org_id,
             "status": "booked"},
            {"_id": 0, "id": 1, "member_id": 1},
        ).to_list(500)
        if not unmarked:
            continue
        ids = [b["id"] for b in unmarked]
        mids = [b["member_id"] for b in unmarked]
        await db.bookings.update_many(
            {"id": {"$in": ids}},
            {"$set": {"status": "no_show",
                      "marked_via": "auto_lazy",
                      "marked_at": _now_iso()}},
        )
        await db.class_occurrences.update_one(
            {"id": occ_id},
            {"$set": {"no_show_count": len(ids),
                      "status": "completed",
                      "completed_at": _now_iso(),
                      "completed_via": "auto_lazy"}},
        )
        if mids:
            await db.members.update_many(
                {"id": {"$in": mids}},
                {"$inc": {"no_show_count": 1}},
            )


@router.get(
    "/memberships/checkin/search-members",
    dependencies=[Depends(require_module("memberships"))],
)
async def members_search(
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """Front-desk lookup by name or email substring. Case-insensitive.
    Returns at most `limit` results."""
    org_id = await _require_operator_org(user)
    import re
    rx = re.compile(re.escape(q.strip()), re.IGNORECASE)
    rows = await db.members.find(
        {"organization_id": org_id,
         "$or": [{"first_name": rx}, {"last_name": rx},
                 {"email": rx}, {"phone": rx}]},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1,
         "email": 1, "phone": 1, "status": 1, "no_show_count": 1},
    ).limit(limit).to_list(limit)
    return {"results": rows, "count": len(rows)}


class MarkAttendanceBody(BaseModel):
    booking_id: str
    status: str = Field(pattern="^(attended|no_show|booked)$")


@router.post(
    "/memberships/checkin/{occ_id}/mark",
    dependencies=[Depends(require_module("memberships"))],
)
async def mark_single_attendance(
    occ_id: str, body: MarkAttendanceBody,
    user: dict = Depends(get_current_user),
):
    """Single-booking attendance toggle — used by the front-desk console
    when staff tap a row to flip attended ↔ no_show. Idempotent."""
    org_id = await _require_operator_org(user)
    bk = await db.bookings.find_one(
        {"id": body.booking_id, "occurrence_id": occ_id, "organization_id": org_id},
        {"_id": 0},
    )
    if not bk:
        raise HTTPException(404, "Booking not found")
    prev = bk.get("status")
    await db.bookings.update_one(
        {"id": bk["id"]},
        {"$set": {"status": body.status, "marked_by": user["id"],
                  "marked_at": _now_iso(), "marked_via": "frontdesk"}},
    )
    # Adjust member.no_show_count delta
    if body.status == "no_show" and prev != "no_show":
        await db.members.update_one(
            {"id": bk["member_id"]}, {"$inc": {"no_show_count": 1}},
        )
    elif prev == "no_show" and body.status != "no_show":
        await db.members.update_one(
            {"id": bk["member_id"]}, {"$inc": {"no_show_count": -1}},
        )
    # Snapshot occurrence counts
    attended = await db.bookings.count_documents(
        {"occurrence_id": occ_id, "status": "attended"},
    )
    no_show = await db.bookings.count_documents(
        {"occurrence_id": occ_id, "status": "no_show"},
    )
    await db.class_occurrences.update_one(
        {"id": occ_id},
        {"$set": {"attended_count": attended, "no_show_count": no_show}},
    )
    return {"ok": True, "previous": prev, "current": body.status,
            "totals": {"attended": attended, "no_show": no_show}}


# ═════════════════════ Kiosk token ═════════════════════


def _hash_token(t: str) -> str:
    import hashlib
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


@router.get(
    "/memberships/checkin/kiosk-token",
    dependencies=[Depends(require_module("memberships"))],
)
async def get_kiosk_token(user: dict = Depends(get_current_user)):
    """Returns metadata about the current kiosk token (does NOT return
    the secret — it's only shown once at issuance)."""
    org_id = await _require_operator_org(user)
    rec = await db.kiosk_tokens.find_one(
        {"organization_id": org_id}, {"_id": 0, "token_hash": 0},
    )
    return {"token": rec}  # may be None


@router.post(
    "/memberships/checkin/kiosk-token",
    dependencies=[Depends(require_module("memberships"))],
)
async def issue_kiosk_token(user: dict = Depends(get_current_user)):
    """Generate a fresh kiosk token. Replaces any existing one. The plain
    token is returned ONCE in the response — operator must save the
    kiosk URL immediately."""
    org_id = await _require_operator_org(user)
    plain = secrets.token_urlsafe(24)
    await db.kiosk_tokens.delete_many({"organization_id": org_id})
    await db.kiosk_tokens.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "token_hash": _hash_token(plain),
        "issued_by": user["id"],
        "issued_at": _now_iso(),
    })
    return {"ok": True, "token": plain,
            "kiosk_url_hint": f"/checkin/kiosk?token={plain}"}


async def _resolve_kiosk_org(token: str) -> str:
    if not token:
        raise HTTPException(401, "Kiosk token required")
    rec = await db.kiosk_tokens.find_one(
        {"token_hash": _hash_token(token)}, {"_id": 0, "organization_id": 1},
    )
    if not rec:
        raise HTTPException(401, "Invalid kiosk token")
    return rec["organization_id"]


# ═════════════════════ Public kiosk endpoints (no JWT) ═════════════════════


@router.get("/memberships/kiosk/today")
async def kiosk_today(token: str = Query(...)):
    """Public: today's classes for the kiosk display."""
    org_id = await _resolve_kiosk_org(token)
    now = _now()
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    until = start + timedelta(days=1)
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1, "company_name": 1},
    ) or {}
    classes = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": start.isoformat(), "$lte": until.isoformat()},
         "status": {"$ne": "cancelled"}},
        {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "duration_min": 1,
         "instructor_name": 1, "room_name": 1, "capacity": 1,
         "bookings_count": 1, "waitlist_count": 1, "attended_count": 1},
    ).sort("starts_at", 1).to_list(50)
    return {"organization_name": org.get("name") or org.get("company_name") or "Studio",
            "classes": classes, "count": len(classes)}


class KioskLookupBody(BaseModel):
    token: str
    q: str = Field(min_length=2, max_length=80)


@router.post("/memberships/kiosk/lookup")
async def kiosk_lookup_member(body: KioskLookupBody, request: Request):
    """Public: name/email substring search. Returns ID + initials only —
    NO contact info — to avoid PII leaks at a public kiosk."""
    org_id = await _resolve_kiosk_org(body.token)
    # Rate limit (P0-1) — 30 lookups / 60s per IP per kiosk-token
    ip = (request.client.host if request.client else "unknown")
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        ip = fwd.split(",")[0].strip() or ip
    await rate_limit_async(
        f"kiosk_lookup:{ip}:{body.token[:12]}", max_requests=30, window_seconds=60,
    )
    import re
    rx = re.compile(re.escape(body.q.strip()), re.IGNORECASE)
    rows = await db.members.find(
        {"organization_id": org_id, "status": {"$in": ["active", "trialling"]},
         "$or": [{"first_name": rx}, {"last_name": rx}, {"email": rx}]},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1},
    ).limit(8).to_list(8)
    out = []
    for m in rows:
        first = m.get("first_name") or ""
        last = m.get("last_name") or ""
        out.append({
            "id": m["id"],
            # Privacy-safe display: first name + last initial.
            "display_name": f"{first} {last[:1] + '.' if last else ''}".strip(),
        })
    return {"results": out, "count": len(out)}


class KioskCheckinBody(BaseModel):
    token: str
    member_id: str
    code: str = Field(min_length=6, max_length=6)


@router.post("/memberships/kiosk/checkin")
async def kiosk_checkin(body: KioskCheckinBody, request: Request):
    """Public: member taps name → enters 6-digit TOTP code from their
    Pass tab. Verified, then we mark the next-class booking as attended
    if there is one within +/- 60 min of now."""
    org_id = await _resolve_kiosk_org(body.token)
    # Rate limit (P0-1) — 8 attempts / 60s per IP per (token, member_id)
    # — defeats TOTP brute-force (1M codes / 90s window).
    ip = (request.client.host if request.client else "unknown")
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        ip = fwd.split(",")[0].strip() or ip
    await rate_limit_async(
        f"kiosk_checkin:{ip}:{body.token[:12]}:{body.member_id}",
        max_requests=8, window_seconds=60,
    )
    rec = await db.qr_rotation_secret.find_one(
        {"member_id": body.member_id}, {"_id": 0},
    )
    if not rec:
        raise HTTPException(404, "Unknown member pass")
    if not pyotp.TOTP(rec["secret_b32"]).verify(body.code, valid_window=1):
        raise HTTPException(401, "Code expired — please refresh your Pass tab")
    member = await db.members.find_one(
        {"id": body.member_id, "organization_id": org_id},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1},
    )
    if not member:
        raise HTTPException(404, "Member not on this site")
    # Find a next-class booking within +/- 60 min
    now = _now()
    early = (now - timedelta(minutes=60)).isoformat()
    late = (now + timedelta(minutes=60)).isoformat()
    next_book = None
    # P1-2 — defence-in-depth: org-filter the booking lookup as well,
    # not just the member. Eliminates any cross-org edge case if a member
    # ever exists in two orgs.
    async for b in db.bookings.find(
        {"member_id": body.member_id, "organization_id": org_id,
         "status": "booked"}, {"_id": 0},
    ):
        occ = await db.class_occurrences.find_one(
            {"id": b["occurrence_id"]}, {"_id": 0},
        )
        if not occ:
            continue
        if early <= occ.get("starts_at", "") <= late:
            next_book = (b, occ)
            break
    checked_booking = None
    next_class_name = None
    if next_book:
        b, occ = next_book
        await db.bookings.update_one(
            {"id": b["id"]},
            {"$set": {"status": "attended",
                      "checked_in_at": _now_iso(),
                      "marked_via": "kiosk"}},
        )
        await db.class_occurrences.update_one(
            {"id": occ["id"]}, {"$inc": {"attended_count": 1}},
        )
        checked_booking = b["id"]
        next_class_name = occ.get("name")
    await db.member_checkins.insert_one({
        "id": str(uuid.uuid4()),
        "member_id": body.member_id,
        "organization_id": org_id,
        "occurrence_id": next_book[1]["id"] if next_book else None,
        "at": _now_iso(),
        "via": "kiosk",
    })
    return {
        "ok": True,
        "first_name": member.get("first_name"),
        "next_class_name": next_class_name,
        "checked_booking_id": checked_booking,
    }


# ═════════════════════ Phase 4 analytics ═════════════════════


@router.get(
    "/memberships/phase4/analytics",
    dependencies=[Depends(require_module("memberships"))],
)
async def phase4_analytics(
    days: int = Query(default=30, ge=7, le=180),
    user: dict = Depends(get_current_user),
):
    """Operator analytics for Phase 4 — fill rate, no-show rate, drop-in
    conversion, waitlist promotion stats."""
    org_id = await _require_operator_org(user)
    now = _now()
    since = now - timedelta(days=days)
    occs = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": since.isoformat(), "$lte": now.isoformat()},
         "status": {"$ne": "cancelled"}},
        {"_id": 0, "capacity": 1, "bookings_count": 1, "attended_count": 1,
         "no_show_count": 1, "waitlist_count": 1},
    ).to_list(5000)
    cap_sum = sum(int(o.get("capacity") or 0) for o in occs) or 1
    booked_sum = sum(int(o.get("bookings_count") or 0) for o in occs)
    attended_sum = sum(int(o.get("attended_count") or 0) for o in occs)
    no_show_sum = sum(int(o.get("no_show_count") or 0) for o in occs)
    fill_pct = round(100.0 * booked_sum / cap_sum, 1)
    attendance_pct = round(100.0 * attended_sum / max(booked_sum, 1), 1)
    no_show_pct = round(100.0 * no_show_sum / max(booked_sum, 1), 1)

    # Waitlist promotions
    promoted = await db.bookings.count_documents({
        "organization_id": org_id, "promoted_from_waitlist_at": {"$gte": since.isoformat()},
    })

    # Drop-in invites + conversions (member booked the same occurrence after
    # we sent them an invite)
    invites = await db.dropin_invites.find(
        {"organization_id": org_id, "created_at": {"$gte": since.isoformat()}},
        {"_id": 0},
    ).to_list(500)
    invites_sent = sum(int(i.get("sent_count") or 0) for i in invites)
    invites_runs = len(invites)

    # P2-5: Batched conversion count — single bookings query for all invite
    # occurrences, then a per-invite in-memory filter. Replaces N+1
    # `count_documents` calls (one per invite run).
    conversions = 0
    eligible = [i for i in invites if i.get("sent_to_ids")]
    if eligible:
        occ_ids = list({i["occurrence_id"] for i in eligible})
        all_member_ids = list({mid for i in eligible for mid in i["sent_to_ids"]})
        earliest = min(i["created_at"] for i in eligible)
        candidate_bookings = await db.bookings.find(
            {"occurrence_id": {"$in": occ_ids},
             "member_id": {"$in": all_member_ids},
             "status": {"$in": ["booked", "attended"]},
             "booked_at": {"$gte": earliest}},
            {"_id": 0, "occurrence_id": 1, "member_id": 1, "booked_at": 1},
        ).to_list(20000)
        # Index candidates by occurrence_id so each invite-run filter is O(K)
        # over the same-occurrence subset (rather than O(all)).
        by_occ: dict[str, list[dict]] = {}
        for b in candidate_bookings:
            by_occ.setdefault(b["occurrence_id"], []).append(b)
        for inv in eligible:
            sent_set = set(inv["sent_to_ids"])
            inv_at = inv["created_at"]
            for b in by_occ.get(inv["occurrence_id"], []):
                if b["member_id"] in sent_set and b.get("booked_at", "") >= inv_at:
                    conversions += 1
    conversion_pct = round(100.0 * conversions / max(invites_sent, 1), 1)

    # Drop-in opt-in member count
    optins = await db.members.count_documents({
        "organization_id": org_id, "drop_in_optin": True,
        "status": {"$in": ["active", "trialling"]},
    })

    return {
        "window_days": days,
        "occurrences_count": len(occs),
        "fill_pct": fill_pct,
        "attendance_pct": attendance_pct,
        "no_show_pct": no_show_pct,
        "waitlist_promotions": promoted,
        "dropin": {
            "runs": invites_runs,
            "invites_sent": invites_sent,
            "conversions": conversions,
            "conversion_pct": conversion_pct,
            "optin_member_count": optins,
        },
    }


# ═════════════════════ Indexes ═════════════════════


async def ensure_phase4_indexes() -> None:
    await db.kiosk_tokens.create_index([("token_hash", 1)], unique=True)
    await db.kiosk_tokens.create_index([("organization_id", 1)])
    await db.dropin_invites.create_index(
        [("organization_id", 1), ("created_at", -1)],
    )
    await db.dropin_invites.create_index([("occurrence_id", 1)])
    await db.members.create_index(
        [("organization_id", 1), ("drop_in_optin", 1)],
    )


__all__ = ["router", "maybe_send_dropin_invites", "ensure_phase4_indexes"]
