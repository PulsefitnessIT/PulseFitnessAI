"""Member-facing utilities — referrals, streaks, social pulse.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db

from routes.memberships.helpers import (
    _gen_referral_code,
    _now_iso,
    _require_current_member,
)

router = APIRouter(tags=["memberships"])


@router.get("/member/plans")
async def member_plans(member: dict = Depends(_require_current_member)):
    """Return the active plans for this member's org. Member-token scoped."""
    plans = await db.membership_plans.find(
        {"organization_id": member["organization_id"], "archived": {"$ne": True}, "active": True},
        {"_id": 0},
    ).sort("display_order", 1).to_list(100)
    return {"plans": plans}


@router.get("/member/referrals")
async def member_referrals(member: dict = Depends(_require_current_member)):
    """Return this member's referral code + headline stats + friend list."""
    code = member.get("referral_code")
    if not code:
        code = _gen_referral_code(member.get("first_name") or "")
        await db.members.update_one({"id": member["id"]}, {"$set": {"referral_code": code}})
    cursor = db.referrals.find({"referrer_id": member["id"]}, {"_id": 0}).sort("created_at", -1)
    rows = await cursor.to_list(100)
    earned = [r for r in rows if r["status"] == "earned"]
    pending = [r for r in rows if r["status"] == "pending"]
    return {
        "code": code,
        "credit_per_referral_pence": 500,
        "stats": {
            "friends_joined": len(rows),
            "pending": len(pending),
            "earned": len(earned),
            "credit_earned_pence": int(member.get("promo_credit_pence") or 0),
        },
        "referrals": rows,
    }


_DEFAULT_REFERRAL_GOALS = [
    {"threshold": 1, "reward": "£5 credit",      "reward_pence": 500},
    {"threshold": 3, "reward": "1 month free",   "reward_pence": 2900},
    {"threshold": 5, "reward": "£20 credit",     "reward_pence": 2000},
]


@router.get("/member/referral-progress")
async def member_referral_progress(member: dict = Depends(_require_current_member)):
    """Gamified referral campaign — returns the member's next-goal target,
    how many more referrals they need, and the rewards ladder.

    Operators can override the ladder by setting `referral_goals` on the
    organization; otherwise the default 1 / 3 / 5 ladder is returned.
    """
    org = await db.organizations.find_one(
        {"id": member["organization_id"]}, {"_id": 0, "referral_goals": 1},
    )
    goals = (org or {}).get("referral_goals") or _DEFAULT_REFERRAL_GOALS
    # Count *earned* referrals only (drives commitment to conversion, not clicks)
    earned = await db.referrals.count_documents(
        {"referrer_id": member["id"], "status": "earned"},
    )
    total = await db.referrals.count_documents({"referrer_id": member["id"]})
    next_goal = next((g for g in goals if g["threshold"] > earned), None)
    return {
        "code": member.get("referral_code"),
        "earned": earned,
        "total": total,
        "goals": goals,
        "next_goal": next_goal,
        "gap": (next_goal["threshold"] - earned) if next_goal else 0,
        "percent": min(100, int(100 * earned / next_goal["threshold"])) if next_goal else 100,
        "campaign_dismissed_at": member.get("referral_campaign_dismissed_at"),
    }


@router.post("/member/referral-progress/dismiss")
async def dismiss_referral_campaign(member: dict = Depends(_require_current_member)):
    """Dismiss the in-app referral campaign banner for this member."""
    await db.members.update_one(
        {"id": member["id"]},
        {"$set": {"referral_campaign_dismissed_at": _now_iso()}},
    )
    return {"ok": True}



@router.get("/member/streak")
async def member_streak(member: dict = Depends(_require_current_member)):
    """Class-attendance streak gamification.

    Returns consecutive days of check-ins up to today, plus a weekly count
    toward a configurable goal (default 3). Drives retention by giving
    members a visible reason to come back.
    """
    # Attended signal = either a check-in OR an attended booking
    days: set[str] = set()
    async for c in db.member_checkins.find(
        {"member_id": member["id"]}, {"_id": 0, "at": 1},
    ):
        at = c.get("at")
        if at:
            days.add(str(at)[:10])
    async for b in db.bookings.find(
        {"member_id": member["id"], "status": "attended"},
        {"_id": 0, "checked_in_at": 1, "booked_at": 1},
    ):
        at = b.get("checked_in_at") or b.get("booked_at")
        if at:
            days.add(str(at)[:10])

    today = datetime.now(timezone.utc).date()
    # Current streak: walk backward from today/yesterday counting consecutive days
    current = 0
    probe = today
    if probe.isoformat() not in days:
        probe = probe - timedelta(days=1)  # grace — streak still alive if yesterday
    while probe.isoformat() in days:
        current += 1
        probe = probe - timedelta(days=1)

    # Longest streak over the entire history
    sorted_days = sorted(datetime.fromisoformat(d).date() for d in days)
    longest = 0
    run = 0
    prev = None
    for d in sorted_days:
        if prev is None or (d - prev).days == 1:
            run += 1
        elif d == prev:
            pass  # same day
        else:
            run = 1
        longest = max(longest, run)
        prev = d

    # Weekly count (ISO week starts Monday)
    week_start = today - timedelta(days=today.weekday())
    weekly = sum(1 for d in sorted_days if d >= week_start)

    # Per-member override, else org-level, else default 3
    goal = int(member.get("weekly_goal") or 0)
    if not goal:
        org = await db.organizations.find_one(
            {"id": member["organization_id"]},
            {"_id": 0, "weekly_streak_goal": 1},
        ) or {}
        goal = int(org.get("weekly_streak_goal") or 3)

    last_attended = max(sorted_days).isoformat() if sorted_days else None
    last_attended_dt = max(sorted_days) if sorted_days else None
    hours_since = None
    if last_attended_dt:
        # naive — counts whole days; finer signal computed from attended check-in time
        delta = (today - last_attended_dt).days
        hours_since = max(0, delta * 24)
    at_risk = bool(current > 0 and (hours_since is not None and hours_since >= 24))

    return {
        "current_streak_days": current,
        "longest_streak_days": longest,
        "weekly_count": weekly,
        "weekly_goal": goal,
        "weekly_remaining": max(0, goal - weekly),
        "last_attended_at": last_attended,
        "at_risk": at_risk,
    }


@router.get("/member/social-pulse/{occurrence_id}")
async def member_social_pulse(
    occurrence_id: str,
    member: dict = Depends(_require_current_member),
):
    """Light social proof for a given class occurrence.

    Returns:
      • `booked_this_week`  — total bookings (booked/attended/waitlist)
                              for the class *template* across the last 7 days
      • `recent_names`      — up to 3 most-recent distinct bookers on this
                              occurrence (first name + last initial, GDPR-safe),
                              excluding the current member.
    """
    occ = await db.class_occurrences.find_one(
        {"id": occurrence_id, "organization_id": member["organization_id"]},
        {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class not found")

    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    # All same-template occurrences within the last 7 days (past + future within the window)
    tpl_occ_ids: list[str] = []
    async for o in db.class_occurrences.find(
        {"organization_id": member["organization_id"],
         "template_id": occ.get("template_id"),
         "starts_at": {"$gte": since}},
        {"_id": 0, "id": 1},
    ):
        tpl_occ_ids.append(o["id"])
    booked_this_week = 0
    if tpl_occ_ids:
        booked_this_week = await db.bookings.count_documents({
            "occurrence_id": {"$in": tpl_occ_ids},
            "status": {"$in": ["booked", "attended", "waitlist"]},
        })

    # Recent distinct bookers on this occurrence (newest first, exclude self)
    recent_ids: list[str] = []
    async for b in db.bookings.find(
        {"occurrence_id": occurrence_id,
         "status": {"$in": ["booked", "attended", "waitlist"]},
         "member_id": {"$ne": member["id"]}},
        {"_id": 0, "member_id": 1, "booked_at": 1},
        sort=[("booked_at", -1)],
    ):
        mid = b.get("member_id")
        if mid and mid not in recent_ids:
            recent_ids.append(mid)
        if len(recent_ids) >= 3:
            break

    recent_names: list[str] = []
    if recent_ids:
        rows = {
            m["id"]: m for m in await db.members.find(
                {"id": {"$in": recent_ids}},
                {"_id": 0, "id": 1, "first_name": 1, "last_name": 1},
            ).to_list(3)
        }
        for mid in recent_ids:
            m = rows.get(mid) or {}
            first = (m.get("first_name") or "").strip()
            last = (m.get("last_name") or "").strip()
            if first:
                recent_names.append(f"{first} {last[:1]}.".strip())

    return {
        "booked_this_week": booked_this_week,
        "recent_names": recent_names,
    }
