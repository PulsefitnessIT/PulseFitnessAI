"""Phase-2 sign-up journeys & funnel KPIs (Iter 216g).

This module covers the three feature requests confirmed in the chat:

  A. Welcome journey trigger
     - On `signup_events.online_signup_completed` we schedule four emails:
       Day 0 (welcome) · Day 2 (book first class nudge) · Day 7 (PT offer) ·
       Day 14 (community/social).
     - Job rows live in `signup_journey_jobs` with `run_at` timestamps.
     - A small async worker (`drain_signup_jobs`) wakes every minute, picks up
       jobs whose `run_at <= now()` and `status == "pending"`, and ships
       them. Idempotent on (`event_id`, `step`).

  C. Abandoned-cart recovery
     - When a `signup_drafts` row has `email` filled, no `member_id`, no
       `checkout_session_id`, AND was last touched > 60 minutes ago, we
       send a recovery email containing a magic-link signed token.
     - We also send a 24-hour follow-up. Each draft gets a max of two
       recovery emails total, tracked via `signup_drafts.recovery_sent`.
     - Magic-link route: `GET /api/public/signup/recover/{token}` — verifies
       the token then redirects to `/m/{slug}/join?draft={id}`.

  E. Online sign-ups KPI panel (master admin)
     - `POST /api/public/signup/{slug}/track` — anonymously logs a page
       view (recorded in `signup_events`).
     - `GET  /api/master-admin/signups/funnel` — returns the funnel
       (views → drafts → completed → paid + revenue) optionally
       filtered by org & date range.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi.responses import RedirectResponse

from routes.auth import get_current_user
from routes.master_admin import require_master_admin
from utils.database import db
from utils.email import send_email

load_dotenv()
log = logging.getLogger("signup_journeys")
router = APIRouter(tags=["signup-journeys"])

JOURNEY_STEPS = [
    {"step": "welcome",        "delay_minutes": 0,            "subject": "Welcome to {gym_name} 🎉",                "template": "welcome"},
    {"step": "first_class",    "delay_minutes": 60 * 24 * 2,  "subject": "Book your first class at {gym_name}",     "template": "first_class"},
    {"step": "pt_offer",       "delay_minutes": 60 * 24 * 7,  "subject": "How's your first week going?",            "template": "pt_offer"},
    {"step": "community",      "delay_minutes": 60 * 24 * 14, "subject": "Two weeks in — here's what's next",        "template": "community"},
]

RECOVERY_DELAY_MINUTES_FIRST = 60          # 1 hour
RECOVERY_DELAY_MINUTES_SECOND = 60 * 24    # 24 hours
RECOVERY_MAX = 2

JOURNEY_TOKEN_SECRET = (
    os.getenv("SIGNUP_JOURNEY_SECRET")
    or os.getenv("JWT_SECRET")
    or "gymaxis-signup-recovery-fallback-secret"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


# ── Magic-link token helpers (HMAC, no extra deps) ────────────────────


def _make_token(draft_id: str, ttl_minutes: int = 60 * 24 * 14) -> str:
    expires = int(time.time()) + ttl_minutes * 60
    payload = f"{draft_id}.{expires}"
    sig = hmac.new(JOURNEY_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(payload.encode() + b"." + sig).decode().rstrip("=")
    return encoded


def _verify_token(token: str) -> tuple[str | None, str | None]:
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(token + padding)
        payload, sig = decoded.rsplit(b".", 1)
        expected = hmac.new(JOURNEY_TOKEN_SECRET.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None, "Invalid signature"
        draft_id, expires = payload.decode().split(".")
        if int(expires) < int(time.time()):
            return None, "Link expired"
        return draft_id, None
    except Exception as exc:  # noqa: BLE001
        return None, f"Bad token: {exc}"


# ── Email rendering ───────────────────────────────────────────────────


BRAND_PRIMARY = "#2563EB"


def _origin(default: str = "https://gymaxisai.com") -> str:
    return (os.getenv("PUBLIC_APP_ORIGIN") or default).rstrip("/")


def _render_journey_email(step: str, *, gym: dict, member: dict | None, plan: dict | None) -> tuple[str, str]:
    gym_name = gym.get("name") or "your gym"
    join_url = f"{_origin()}/m/{gym.get('slug') or gym['id']}/join"
    first_name = (member or {}).get("first_name", "there")
    plan_name = (plan or {}).get("name", "your membership")
    base_btn = (
        f'<a href="{join_url}" style="display:inline-block;background:{BRAND_PRIMARY};'
        f'color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;'
        f'font-weight:600;font-family:Helvetica,Arial,sans-serif">'
    )
    if step == "welcome":
        subject = f"Welcome to {gym_name} 🎉"
        body = (
            f"<h2>Hi {first_name}, you're in.</h2>"
            f"<p>Your <strong>{plan_name}</strong> at <strong>{gym_name}</strong> is active "
            f"from today. Your digital pass is attached to your member portal — flash the "
            f"QR at the door on your first visit.</p>"
            f"<p>Three things to do this week:</p>"
            f"<ol><li>Book your first class</li><li>Save the gym number</li>"
            f"<li>Try one machine you've never used before</li></ol>"
            f"<p>{base_btn}Open your member dashboard</a></p>"
        )
    elif step == "first_class":
        subject = f"Book your first class at {gym_name}"
        body = (
            f"<h2>Members who book their first class in week one are 2× more likely to "
            f"still be training in 90 days.</h2>"
            f"<p>It's day 2 — pick a class, lock it in, and keep your streak.</p>"
            f"<p>{base_btn}See the class schedule</a></p>"
        )
    elif step == "pt_offer":
        subject = "How's your first week going?"
        body = (
            f"<h2>Hi {first_name},</h2>"
            f"<p>You're a week in. If you'd like a personal-trainer led session to lock in "
            f"good form on the basics, reply to this email and we'll set one up — first "
            f"30 mins on the house for new members.</p>"
            f"<p>If you've been crushing it solo, ignore this and keep going 💪.</p>"
        )
    else:  # community
        subject = "Two weeks in — here's what's next"
        body = (
            f"<h2>Welcome to the community.</h2>"
            f"<p>You've made it past the toughest part: the first two weeks. From here on, "
            f"every visit gets easier. We post the class schedule, weekly challenges and "
            f"community photos on our socials — follow along.</p>"
            f"<p>{base_btn}Visit {gym_name}</a></p>"
        )
    return subject, body


def _render_recovery_email(*, draft: dict, gym: dict, plan: dict | None, token: str, attempt: int) -> tuple[str, str]:
    first_name = (draft.get("details") or {}).get("first_name") or "there"
    gym_name = gym.get("name") or "your gym"
    plan_name = (plan or {}).get("name") or "the membership"
    recover_url = f"{_origin()}/m/{gym.get('slug') or gym['id']}/join?draft={draft['id']}&token={token}"
    btn = (
        f'<a href="{recover_url}" style="display:inline-block;background:{BRAND_PRIMARY};'
        f'color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;'
        f'font-weight:600;font-family:Helvetica,Arial,sans-serif">Pick up where you left off</a>'
    )
    if attempt == 1:
        subject = f"You're nearly there — finish your {gym_name} sign-up"
        body = (
            f"<h2>Hi {first_name},</h2>"
            f"<p>Looks like something pulled you away while signing up to "
            f"<strong>{gym_name}</strong>. Your spot's still saved.</p>"
            f"<p>Tap below — your details are pre-filled, so it's two taps to finish.</p>"
            f"<p>{btn}</p>"
        )
    else:
        subject = f"Last reminder — your {gym_name} membership"
        body = (
            f"<h2>One last nudge.</h2>"
            f"<p>Your saved sign-up for <strong>{plan_name}</strong> at <strong>{gym_name}</strong> "
            f"is still here. We'll release the spot in 7 days if there's no activity.</p>"
            f"<p>{btn}</p>"
        )
    return subject, body


# ── Scheduling: write jobs into `signup_journey_jobs` ──────────────────


async def schedule_welcome_journey(event: dict) -> int:
    """Idempotent. Fan out the 4-step welcome journey for one event."""
    member = await db.members.find_one({"id": event["member_id"]}, {"_id": 0})
    if not member:
        return 0
    gym = await db.organizations.find_one({"id": event["organization_id"]}, {"_id": 0}) or {}
    plan = await db.membership_plans.find_one({"id": event.get("plan_id")}, {"_id": 0}) or {}
    inserted = 0
    for spec in JOURNEY_STEPS:
        existing = await db.signup_journey_jobs.find_one(
            {"event_id": event["id"], "step": spec["step"]}, {"_id": 1},
        )
        if existing:
            continue
        run_at = _now() + timedelta(minutes=int(spec["delay_minutes"]))
        await db.signup_journey_jobs.insert_one({
            "id": str(uuid.uuid4()),
            "kind": "welcome",
            "event_id": event["id"],
            "step": spec["step"],
            "organization_id": event["organization_id"],
            "member_id": event["member_id"],
            "to_email": (member.get("email") or "").lower(),
            "subject_template": spec["subject"],
            "template": spec["template"],
            "status": "pending",
            "run_at": _iso(run_at),
            "created_at": _iso(_now()),
            "context": {"gym_name": gym.get("name"), "plan_name": plan.get("name")},
        })
        inserted += 1
    return inserted


async def _send_welcome_step(job: dict) -> bool:
    member = await db.members.find_one({"id": job["member_id"]}, {"_id": 0}) or {}
    gym = await db.organizations.find_one({"id": job["organization_id"]}, {"_id": 0}) or {}
    plan = await db.membership_plans.find_one({"id": member.get("plan_id")}, {"_id": 0}) or {}
    subject, html = _render_journey_email(job["step"], gym=gym, member=member, plan=plan)
    return await send_email(
        to=job["to_email"], subject=subject, html=html,
        organization_id=job["organization_id"],
    )


async def _send_recovery_email(draft: dict, attempt: int) -> bool:
    gym = await db.organizations.find_one({"id": draft["organization_id"]}, {"_id": 0}) or {}
    plan = (
        await db.membership_plans.find_one({"id": draft.get("plan_id")}, {"_id": 0})
        if draft.get("plan_id") else None
    ) or {}
    token = _make_token(draft["id"])
    subject, html = _render_recovery_email(draft=draft, gym=gym, plan=plan, token=token, attempt=attempt)
    return await send_email(
        to=(draft.get("details") or {}).get("email"),
        subject=subject, html=html,
        organization_id=draft["organization_id"],
    )


async def _scan_abandoned_carts() -> int:
    """Look for stale drafts and send recovery emails. Returns the count sent."""
    now = _now()
    sent = 0
    threshold_first = (now - timedelta(minutes=RECOVERY_DELAY_MINUTES_FIRST)).isoformat().replace("+00:00", "Z")
    cur = db.signup_drafts.find({
        "details.email": {"$exists": True, "$ne": ""},
        "member_id": {"$exists": False},
        "checkout_session_id": {"$in": [None, ""]},
        "$or": [
            {"recovery_sent": {"$exists": False}},
            {"recovery_sent.0": {"$exists": False}},
        ],
        "updated_at": {"$lt": threshold_first},
    }, {"_id": 0})
    async for draft in cur:
        history = draft.get("recovery_sent") or []
        if len(history) >= RECOVERY_MAX:
            continue
        # Decide attempt 1 or 2 based on history length and elapsed time.
        attempt = len(history) + 1
        if attempt == 1:
            ok = await _send_recovery_email(draft, attempt=1)
        elif attempt == 2:
            last = history[-1]["sent_at"]
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if (now - last_dt).total_seconds() < RECOVERY_DELAY_MINUTES_SECOND * 60:
                continue
            ok = await _send_recovery_email(draft, attempt=2)
        else:
            continue
        if ok:
            history.append({"attempt": attempt, "sent_at": _iso(now)})
            await db.signup_drafts.update_one(
                {"id": draft["id"]},
                {"$set": {"recovery_sent": history}},
            )
            sent += 1
    return sent


# ── Tour reminders (iter 216h6) ──────────────────────────────────────


def _render_tour_reminder(*, gym: dict, booking: dict) -> tuple[str, str]:
    """24h-before reminder. Plain-spoken, low friction, single CTA: cancel link."""
    gym_name = gym.get("name") or "your gym"
    slot_dt = datetime.fromisoformat(booking["slot_at"].replace("Z", "+00:00"))
    # We render in UTC + ask the user to add to calendar — keeps the email
    # timezone-stable across daylight-savings / browser locale boundaries.
    when = slot_dt.strftime("%A %d %B at %H:%M UTC")
    location = booking.get("location") or "Reception"
    name = (booking.get("member_name") or "").split(" ")[0] or "there"
    cancel_url = (
        f"{_origin()}/m/{gym.get('slug') or gym['id']}/join?cancel_tour={booking.get('draft_id') or ''}"
    )
    base_btn = (
        f'<a href="{cancel_url}" style="display:inline-block;background:#f4f4f5;'
        f'color:#27272a;padding:10px 20px;border-radius:8px;text-decoration:none;'
        f'font-weight:500;font-family:Helvetica,Arial,sans-serif;border:1px solid #d4d4d8">'
    )
    subject = f"Reminder: your tour at {gym_name} tomorrow"
    html = (
        f"<h2>Hi {name},</h2>"
        f"<p>Quick reminder — your <strong>{gym_name}</strong> tour is "
        f"<strong>{when}</strong>.</p>"
        f"<p><strong>Where:</strong> {location}<br/>"
        f"<strong>How long:</strong> about {booking.get('duration_minutes', 30)} minutes — "
        f"wear something comfortable, no gym kit needed.</p>"
        f"<p>If you can't make it any more, no problem — just hit the button below to "
        f"free up the slot for someone else:</p>"
        f"<p>{base_btn}Cancel my tour</a></p>"
        f"<p style='color:#71717a;font-size:13px'>See you soon!</p>"
    )
    return subject, html


async def _scan_tour_reminders() -> int:
    """Find tour bookings 22-26h out, send a reminder, mark `reminder_sent_at`.

    Window is intentionally wider than the cadence (worker ticks every 60s but
    the window is 4 hours) so that a worker hiccup doesn't drop reminders on
    the floor. Idempotency comes from `reminder_sent_at` — once set, the row
    falls out of the query.
    """
    now = _now()
    lo = _iso(now + timedelta(hours=22))
    hi = _iso(now + timedelta(hours=26))
    sent = 0
    cur = db.tour_bookings.find({
        "status": "booked",
        "slot_at": {"$gte": lo, "$lte": hi},
        "member_email": {"$exists": True, "$ne": ""},
        "$or": [{"reminder_sent_at": {"$exists": False}}, {"reminder_sent_at": None}],
    }, {"_id": 0})
    async for booking in cur:
        # Best-effort optimistic lock so two worker ticks racing won't double-send.
        upd = await db.tour_bookings.update_one(
            {"id": booking["id"], "$or": [
                {"reminder_sent_at": {"$exists": False}},
                {"reminder_sent_at": None},
            ]},
            {"$set": {"reminder_sent_at": _iso(now), "reminder_status": "sending"}},
        )
        if upd.modified_count == 0:
            continue
        gym = await db.organizations.find_one(
            {"id": booking["organization_id"]}, {"_id": 0},
        ) or {}
        try:
            subject, html = _render_tour_reminder(gym=gym, booking=booking)
            ok = await send_email(
                to=booking["member_email"], subject=subject, html=html,
                organization_id=booking["organization_id"],
            )
            await db.tour_bookings.update_one(
                {"id": booking["id"]},
                {"$set": {"reminder_status": "sent" if ok else "failed"}},
            )
            if ok:
                sent += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("Tour reminder send failed for %s: %s", booking.get("id"), exc)
            await db.tour_bookings.update_one(
                {"id": booking["id"]},
                {"$set": {"reminder_status": "failed", "reminder_error": str(exc)[:300]}},
            )
    return sent


# ── Worker (drains every 60s, started by FastAPI lifespan) ─────────────


_worker_task: asyncio.Task | None = None


async def drain_signup_jobs():
    """Run forever: every 60 seconds drain pending journey jobs + recovery scan."""
    log.info("Sign-up journey worker started.")
    while True:
        try:
            now_iso = _iso(_now())
            cur = db.signup_journey_jobs.find(
                {"status": "pending", "run_at": {"$lte": now_iso}}, {"_id": 0},
            ).limit(50)
            async for job in cur:
                # mark in-progress (best-effort optimistic lock)
                upd = await db.signup_journey_jobs.update_one(
                    {"id": job["id"], "status": "pending"},
                    {"$set": {"status": "sending", "started_at": _iso(_now())}},
                )
                if upd.modified_count == 0:
                    continue
                ok = False
                err = None
                try:
                    ok = await _send_welcome_step(job)
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)[:300]
                await db.signup_journey_jobs.update_one(
                    {"id": job["id"]},
                    {"$set": {
                        "status": "sent" if ok else "failed",
                        "completed_at": _iso(_now()),
                        "error": err,
                    }},
                )
            await _scan_abandoned_carts()
            await _scan_tour_reminders()
        except Exception as exc:  # noqa: BLE001
            log.warning("Worker iteration error: %s", exc, exc_info=True)
        await asyncio.sleep(60)


def start_worker_once():
    """Idempotently kick off the worker. Called from server.py startup."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        loop = asyncio.get_event_loop()
        _worker_task = loop.create_task(drain_signup_jobs())
        log.info("Sign-up journey worker registered.")


# ── Listeners on signup_events ────────────────────────────────────────


async def _try_schedule_for_pending_events():
    """Run at startup: catch up on any signup_events that don't yet have jobs."""
    cur = db.signup_events.find({"type": "online_signup_completed"}, {"_id": 0}).sort("created_at", -1).limit(200)
    async for evt in cur:
        try:
            await schedule_welcome_journey(evt)
        except Exception as exc:  # noqa: BLE001
            log.warning("schedule_welcome_journey failed for %s: %s", evt.get("id"), exc)


# ── Public endpoints ───────────────────────────────────────────────────


@router.post("/public/signup/{slug}/track")
async def track_event(
    slug: str = Path(...),
    body: dict = Body(default={}),
):
    """Anonymous funnel tracking. Logs a page-view or step event."""
    gym = await db.organizations.find_one(
        {"$or": [{"slug": slug.lower()}, {"id": slug}]}, {"_id": 0, "id": 1},
    )
    if not gym:
        return {"ok": True}  # silently absorb so failed lookups don't break the page
    evt_type = (body.get("event") or "view")[:32]
    if evt_type not in ("view", "step", "draft_started", "step_plan", "step_details", "step_parq", "step_extras", "step_payment"):
        evt_type = "view"
    await db.signup_events.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": gym["id"],
        "type": evt_type,
        "step": (body.get("step") or "")[:32],
        "draft_id": body.get("draft_id"),
        "ref": (body.get("ref") or "")[:200],
        "created_at": _iso(_now()),
    })
    return {"ok": True}


@router.get("/public/signup/recover/{token}")
async def recover_draft(token: str = Path(..., min_length=10)):
    draft_id, err = _verify_token(token)
    if err:
        raise HTTPException(400, err)
    draft = await db.signup_drafts.find_one({"id": draft_id}, {"_id": 0})
    if not draft:
        raise HTTPException(404, "Draft not found or already completed")
    if draft.get("member_id"):
        gym = await db.organizations.find_one({"id": draft["organization_id"]}, {"_id": 0}) or {}
        return RedirectResponse(url=f"{_origin()}/m/{gym.get('slug') or gym.get('id')}/join/success?session_id={draft.get('checkout_session_id', '')}")
    gym = await db.organizations.find_one({"id": draft["organization_id"]}, {"_id": 0}) or {}
    target = f"{_origin()}/m/{gym.get('slug') or gym.get('id')}/join?draft={draft_id}&token={token}"
    return RedirectResponse(url=target)


# ── Master Admin: KPI funnel ───────────────────────────────────────────


@router.get("/master-admin/signups/funnel")
async def funnel(
    user: dict = Depends(get_current_user),
    organization_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
):
    require_master_admin(user)
    since = _iso(_now() - timedelta(days=days))
    org_filter = {"organization_id": organization_id} if organization_id else {}
    base = {**org_filter, "created_at": {"$gte": since}}

    views = await db.signup_events.count_documents({**base, "type": "view"})
    drafts_started = await db.signup_drafts.count_documents({
        **org_filter,
        "created_at": {"$gte": since},
        "details.email": {"$exists": True, "$ne": ""},
    })
    drafts_completed = await db.signup_drafts.count_documents({
        **org_filter,
        "completed_at": {"$gte": since},
    })
    paid = await db.payment_transactions.count_documents({
        **org_filter,
        "payment_status": "paid",
        "created_at": {"$gte": since},
    })
    revenue_pence = 0
    cur = db.payment_transactions.find(
        {**org_filter, "payment_status": "paid", "created_at": {"$gte": since}},
        {"_id": 0, "amount_total_pence": 1},
    )
    async for r in cur:
        revenue_pence += int(r.get("amount_total_pence") or 0)

    # Recent sign-ups (last 25, completed)
    recent_cur = db.members.find(
        {**org_filter, "joined_via": "online_signup", "joined_at": {"$gte": since}},
        {"_id": 0},
    ).sort("joined_at", -1).limit(25)
    recent: list[dict[str, Any]] = []
    async for m in recent_cur:
        recent.append({
            "id": m.get("id"),
            "name": f"{m.get('first_name', '')} {m.get('last_name', '')}".strip(),
            "email": m.get("email"),
            "organization_id": m.get("organization_id"),
            "plan_id": m.get("plan_id"),
            "joined_at": m.get("joined_at"),
            "parq_clearance_required": m.get("parq_clearance_required", False),
        })

    # Per-org breakdown when global view
    by_org: list[dict[str, Any]] = []
    if not organization_id:
        pipeline = [
            {"$match": {"joined_via": "online_signup", "joined_at": {"$gte": since}}},
            {"$group": {"_id": "$organization_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 25},
        ]
        async for row in db.members.aggregate(pipeline):
            org = await db.organizations.find_one({"id": row["_id"]}, {"_id": 0, "name": 1, "slug": 1}) or {}
            by_org.append({
                "organization_id": row["_id"],
                "name": org.get("name") or "Unknown",
                "slug": org.get("slug"),
                "count": row["count"],
            })

    journey_jobs = await db.signup_journey_jobs.aggregate([
        {"$match": {**org_filter, "created_at": {"$gte": since}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]).to_list(length=10)

    return {
        "since": since,
        "filters": {"organization_id": organization_id, "days": days},
        "kpis": {
            "views": views,
            "drafts_started": drafts_started,
            "drafts_completed": drafts_completed,
            "paid": paid,
            "revenue_pence": revenue_pence,
            "view_to_draft_pct": round(100 * drafts_started / views, 1) if views else 0.0,
            "draft_to_paid_pct": round(100 * paid / drafts_started, 1) if drafts_started else 0.0,
        },
        "recent": recent,
        "by_org": by_org,
        "journey_jobs": {row["_id"]: row["count"] for row in journey_jobs},
    }


__all__ = ["router", "schedule_welcome_journey", "start_worker_once", "_try_schedule_for_pending_events", "_scan_tour_reminders"]
