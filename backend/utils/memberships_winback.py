"""Pulse Fitness Memberships — "We've missed you" win-back dispatcher.

Scans all Memberships-enabled orgs once per poller cycle for active
members who:

  • had an attendance streak of 5+ days at some point, AND
  • haven't checked in for 7+ consecutive days, AND
  • haven't received a win-back in the last 14 days.

Sends each a personalised HTML email via Resend — reminder of their
streak, the studio's top class this week, and a direct CTA into the
white-label app. Idempotent via `winback_last_sent_at` on the member.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)


def _origin() -> str:
    return (os.environ.get("PUBLIC_ORIGIN")
            or os.environ.get("FRONTEND_ORIGIN")
            or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")


async def _longest_streak(member_id: str) -> int:
    days: set[str] = set()
    async for c in db.member_checkins.find({"member_id": member_id}, {"_id": 0, "at": 1}):
        if c.get("at"):
            days.add(str(c["at"])[:10])
    async for b in db.bookings.find(
        {"member_id": member_id, "status": "attended"},
        {"_id": 0, "checked_in_at": 1, "booked_at": 1},
    ):
        at = b.get("checked_in_at") or b.get("booked_at")
        if at:
            days.add(str(at)[:10])
    if not days:
        return 0
    sorted_days = sorted(datetime.fromisoformat(d).date() for d in days)
    longest, run, prev = 0, 0, None
    for d in sorted_days:
        if prev is None or (d - prev).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d
    return longest


async def _top_class_this_week(org_id: str) -> dict | None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    counts: Counter = Counter()
    names: dict[str, str] = {}
    async for o in db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": since.isoformat(), "$lte": now.isoformat()}},
        {"_id": 0, "template_id": 1, "name": 1, "attended_count": 1},
    ):
        tid = o.get("template_id") or "_"
        counts[tid] += int(o.get("attended_count") or 0)
        names.setdefault(tid, o.get("name") or "Class")
    if not counts:
        return None
    top_tid, top_count = counts.most_common(1)[0]
    return {"name": names[top_tid], "attended": top_count}


def _build_html(first_name: str, studio: str, brand: str, streak: int, app_url: str, top_class: dict | None) -> str:
    top_html = ""
    if top_class:
        top_html = f"""<div style="margin-top:18px;padding:14px 16px;border-left:3px solid {brand};background:rgba(25,205,255,0.06);border-radius:6px;">
          <div style="color:{brand};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:6px;">Trending this week</div>
          <div style="color:#fff;font-size:16px;font-weight:700;">{top_class['name']}</div>
          <div style="color:#9ca3af;font-size:12px;margin-top:2px;">{top_class['attended']} members attended · one spot has your name on it.</div>
        </div>"""
    streak_line = (
        f"You were on a {streak}-day streak with us." if streak >= 5 else
        "Your seat is still warm."
    )
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:620px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="padding:32px;background:linear-gradient(135deg,{brand}33 0%,transparent 100%);border-bottom:1px solid {brand}55;">
    <div style="color:{brand};font-size:10px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;margin-bottom:8px;">We've missed you</div>
    <h1 style="color:#fff;font-size:26px;margin:0;line-height:1.2;font-weight:800;">Hey {first_name}, your {studio} family noticed.</h1>
    <p style="color:#d1d5db;margin:16px 0 0;">{streak_line} It's been a week — let's pick it back up. No guilt, just good sessions.</p>
  </div>
  <div style="padding:24px 32px;background:#0A0C10;color:#e5e7eb;font-size:14px;line-height:1.6;">
    <a href="{app_url}" style="display:inline-block;padding:14px 28px;border-radius:10px;background:{brand};color:#05070A;font-weight:800;text-decoration:none;font-size:14px;letter-spacing:0.04em;">Book your next class →</a>
    {top_html}
    <p style="color:#9ca3af;font-size:12px;margin:22px 0 0;line-height:1.5;">If you want to pause your membership or chat to the team, reply to this email — we're here.</p>
  </div>
  <div style="background:#05070A;padding:14px 32px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;">
    <p style="color:#6b7280;font-size:11px;margin:0;">Pulse Fitness · {studio} · Win-back</p>
  </div>
</div>"""


async def send_winback_for_member(member: dict, org: dict, force: bool = False) -> dict:
    """Build + send the win-back email for a single member."""
    now = datetime.now(timezone.utc)
    if not force:
        last = member.get("winback_last_sent_at")
        if last:
            try:
                if (now - datetime.fromisoformat(last.replace("Z", "+00:00"))).days < 14:
                    return {"skipped": "already_sent_recently"}
            except Exception:
                pass
    if not member.get("email"):
        return {"skipped": "no_email"}
    slug = org.get("slug")
    origin = _origin()
    app_url = f"{origin}/m/{slug}" if slug else origin
    streak = await _longest_streak(member["id"])
    top_class = await _top_class_this_week(org["id"])
    html = _build_html(
        first_name=(member.get("first_name") or "there").strip() or "there",
        studio=org.get("name") or "the studio",
        brand=org.get("primary_brand_colour") or "#19CDFF",
        streak=streak,
        app_url=app_url,
        top_class=top_class,
    )
    ok = await send_email(
        member["email"],
        f"We've missed you at {org.get('name', 'the studio')} 💙",
        html,
    )
    await db.members.update_one(
        {"id": member["id"]},
        {"$set": {"winback_last_sent_at": now.isoformat(),
                  "winback_streak_ref": streak}},
    )
    return {"sent": ok, "streak": streak, "top_class": top_class}


async def run_winback_dispatcher(force: bool = False, dry_run: bool = False) -> dict:
    """Top-level cron entry. Scans orgs → candidates → fires emails."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=7)).isoformat()
    totals = {"orgs": 0, "candidates": 0, "sent": 0, "skipped": 0, "errors": 0}
    # Collect candidate member_ids: active, last check-in >= 7 days ago
    async for org in db.organizations.find(
        {"setup_completed": True, "slug": {"$exists": True, "$ne": None}},
        {"_id": 0},
    ):
        totals["orgs"] += 1
        org_id = org["id"]
        async for m in db.members.find(
            {"organization_id": org_id, "status": "active"},
            {"_id": 0, "password": 0},
        ):
            # Most-recent activity signal
            last_checkin = await db.member_checkins.find_one(
                {"member_id": m["id"]},
                {"_id": 0, "at": 1},
                sort=[("at", -1)],
            )
            last_booking = await db.bookings.find_one(
                {"member_id": m["id"], "status": "attended"},
                {"_id": 0, "checked_in_at": 1, "booked_at": 1},
                sort=[("checked_in_at", -1)],
            )
            last_at = (last_checkin or {}).get("at") or \
                      (last_booking or {}).get("checked_in_at") or \
                      (last_booking or {}).get("booked_at")
            if not last_at or str(last_at) >= cutoff:
                continue  # hasn't lapsed

            streak = await _longest_streak(m["id"])
            if streak < 5:
                continue  # don't win-back members who never committed

            totals["candidates"] += 1
            if dry_run:
                continue
            try:
                res = await send_winback_for_member(m, org, force=force)
                if res.get("sent"):
                    totals["sent"] += 1
                else:
                    totals["skipped"] += 1
            except Exception:
                totals["errors"] += 1
                logger.exception("[winback] member failed: %s", m.get("id"))
    logger.info(f"[winback] dispatcher complete {totals}")
    return totals
