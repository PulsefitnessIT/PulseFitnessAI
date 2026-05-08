"""Augment the Memberships demo seed with 12 weeks of historical data so
the Analytics engine has meaningful charts to draw.

Idempotent: tagged documents are fingerprinted with `seed_tag="analytics"`
so repeated runs are no-ops.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)

DEMO_ORG_ID = "mbr-demo-org"
_SEED_TAG = "analytics_v1"
random.seed(42)  # deterministic


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def seed_memberships_analytics_demo() -> None:
    """Fill 12 weeks of bookings, check-ins, payments, churn events."""
    if await db.payment_transactions.find_one({"organization_id": DEMO_ORG_ID, "seed_tag": _SEED_TAG}):
        return  # already seeded

    now = datetime.now(timezone.utc)
    members = await db.members.find({"organization_id": DEMO_ORG_ID}, {"_id": 0}).to_list(200)
    plans = await db.membership_plans.find({"organization_id": DEMO_ORG_ID}, {"_id": 0}).to_list(50)
    plan_by_kind = {p["kind"]: p for p in plans}
    if not members or not plans:
        logger.info("Analytics seed: no base data yet, skipping")
        return

    # 1) 12 weeks of payment transactions (monthly + occasional fail/refund)
    paid_rows = []
    for weeks_ago in range(12, -1, -1):
        batch_dt = now - timedelta(weeks=weeks_ago)
        for i, m in enumerate(members):
            # Skip 40% of weeks to simulate real billing (most paid monthly)
            if weeks_ago % 4 != 0 and random.random() > 0.1:
                continue
            plan = plan_by_kind.get("recurring") or plans[0]
            status = "paid"
            if random.random() < 0.06:
                status = "failed"
            elif random.random() < 0.03:
                status = "refunded"
            paid_rows.append({
                "id": str(uuid.uuid4()),
                "organization_id": DEMO_ORG_ID,
                "member_id": m["id"],
                "plan_id": plan["id"],
                "amount_pence": int(plan["price_pence"] or 0),
                "currency": "GBP",
                "mode": "manual",
                "method": random.choice(["card_terminal", "bank_transfer", "direct_debit"]),
                "status": "complete" if status == "paid" else status,
                "payment_status": status,
                "created_at": _iso(batch_dt),
                "seed_tag": _SEED_TAG,
            })
    if paid_rows:
        await db.payment_transactions.insert_many(paid_rows)
        logger.info("Analytics seed: %s payment rows", len(paid_rows))

    # 2) Member check-ins (visits) distributed over last 60 days
    checkins = []
    for weeks_ago in range(8, -1, -1):
        for m in members:
            # Vary engagement per member so segmentation has variety
            base = [0, 1, 3, 5][hash(m["id"]) % 4]
            week_visits = max(0, base + random.randint(-1, 2))
            for _ in range(week_visits):
                delta_day = random.randint(0, 6)
                delta_hour = random.choice([6, 7, 8, 9, 12, 17, 18, 19, 20])
                at = (now - timedelta(weeks=weeks_ago, days=delta_day,
                                       hours=24 - delta_hour)).replace(minute=random.randint(0, 59))
                checkins.append({
                    "id": str(uuid.uuid4()),
                    "member_id": m["id"],
                    "organization_id": DEMO_ORG_ID,
                    "occurrence_id": None,
                    "at": _iso(at),
                    "seed_tag": _SEED_TAG,
                })
    if checkins:
        await db.member_checkins.insert_many(checkins)
        logger.info("Analytics seed: %s check-ins", len(checkins))

    # 3) Attendance fill-in on past class_occurrences so class analytics
    #    has something interesting to report (bookings_count, attended_count,
    #    no_show_count already exist but can be stale from test loops).
    #    Because the default seed only materialises FUTURE occurrences, we
    #    backfill 8 weeks of past occurrences for each template here.
    templates = await db.class_templates.find(
        {"organization_id": DEMO_ORG_ID, "archived": {"$ne": True}}, {"_id": 0},
    ).to_list(200)
    past_occ_rows = []
    for tpl in templates:
        days_set = set(int(d) for d in (tpl.get("recurs_days") or []))
        if not days_set:
            continue
        try:
            hh, mm = [int(x) for x in (tpl.get("start_time") or "07:00").split(":", 1)]
        except Exception:
            hh, mm = 7, 0
        duration = int(tpl.get("duration_min") or 45)
        cap = int(tpl.get("capacity") or 20)
        cursor = now - timedelta(weeks=8)
        while cursor < now:
            if cursor.weekday() in days_set:
                starts = cursor.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if starts < now:
                    existing = await db.class_occurrences.find_one(
                        {"template_id": tpl["id"], "starts_at": starts.isoformat()},
                        {"_id": 0, "id": 1})
                    if not existing:
                        booked = random.randint(int(cap * 0.45), cap)
                        attended = int(booked * random.uniform(0.72, 0.95))
                        no_show = max(0, booked - attended)
                        past_occ_rows.append({
                            "id": str(uuid.uuid4()),
                            "template_id": tpl["id"],
                            "organization_id": DEMO_ORG_ID,
                            "site_id": tpl.get("site_id"),
                            "name": tpl.get("name"),
                            "colour": tpl.get("colour", "#19CDFF"),
                            "starts_at": starts.isoformat(),
                            "ends_at": (starts + timedelta(minutes=duration)).isoformat(),
                            "instructor_name": tpl.get("instructor_name"),
                            "instructor_user_id": tpl.get("instructor_user_id"),
                            "room_name": tpl.get("room_name"),
                            "capacity": cap,
                            "bookings_count": booked,
                            "attended_count": attended,
                            "no_show_count": no_show,
                            "waitlist_count": random.randint(0, 3),
                            "status": "completed",
                            "created_at": (starts - timedelta(days=7)).isoformat(),
                            "seed_tag": _SEED_TAG,
                        })
            cursor += timedelta(days=1)
    if past_occ_rows:
        await db.class_occurrences.insert_many(past_occ_rows)
        logger.info("Analytics seed: %s past occurrences", len(past_occ_rows))

    # 3b) Also synthesise attended bookings for those past occurrences so
    #     instructor "unique members" + booking conversion have signal.
    member_ids = [m["id"] for m in members]
    past_booking_rows = []
    for occ in past_occ_rows[:150]:  # cap
        n_attended = occ["attended_count"]
        # pick n_attended random members without duplicates
        if len(member_ids) == 0 or n_attended == 0:
            continue
        sample = random.sample(member_ids, min(n_attended, len(member_ids)))
        for mid in sample:
            past_booking_rows.append({
                "id": str(uuid.uuid4()),
                "occurrence_id": occ["id"],
                "member_id": mid,
                "organization_id": DEMO_ORG_ID,
                "site_id": occ.get("site_id"),
                "status": "attended",
                "credits_charged": 0,
                "booked_at": (datetime.fromisoformat(occ["starts_at"]) - timedelta(hours=random.randint(1, 48))).isoformat(),
                "checked_in_at": occ["starts_at"],
                "channel": "seed",
                "seed_tag": _SEED_TAG,
            })
    if past_booking_rows:
        await db.bookings.insert_many(past_booking_rows)
        logger.info("Analytics seed: %s past bookings", len(past_booking_rows))

    # 4) A handful of cancelled memberships for churn cohort charts.
    #    We flip every 5th member's oldest membership doc to cancelled
    #    with a cancel_effective_date in the last 60 days.
    churn_members = members[::5]
    for m in churn_members:
        mm = await db.member_memberships.find_one(
            {"member_id": m["id"], "organization_id": DEMO_ORG_ID, "status": "active"},
            sort=[("joined_at", 1)],
        )
        if not mm:
            continue
        days_ago = random.randint(3, 60)
        cancelled_dt = now - timedelta(days=days_ago)
        await db.member_memberships.update_one(
            {"id": mm["id"]},
            {"$set": {
                "status": "cancelled",
                "cancel_effective_date": _iso(cancelled_dt),
                "cancel_reason": random.choice([
                    "too_expensive", "moved_away", "lack_of_time",
                    "found_alternative", "not_using_enough",
                ]),
                "seed_tag": _SEED_TAG,
            }},
        )

    # 5) Stagger member created_at for varied cohort buckets (only if created_at is recent)
    async for m in db.members.find(
        {"organization_id": DEMO_ORG_ID, "seed_tag": {"$ne": _SEED_TAG}},
        {"_id": 0, "id": 1, "created_at": 1},
    ):
        created = m.get("created_at")
        if not created:
            continue
        # Shift half of members to 30-180 days ago so cohort matrix has 3+ rows
        if random.random() < 0.5:
            shift_days = random.randint(30, 180)
            new_dt = now - timedelta(days=shift_days)
            await db.members.update_one(
                {"id": m["id"]},
                {"$set": {"created_at": _iso(new_dt), "seed_tag": _SEED_TAG}},
            )

    # 6) Failed-payment-linked member: Oliver gets 2 failed payments for
    #    the at-risk model
    oliver = await db.members.find_one({"id": "mbr-oliver"}, {"_id": 0, "id": 1})
    if oliver:
        for i in range(2):
            await db.payment_transactions.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": DEMO_ORG_ID,
                "member_id": "mbr-oliver",
                "amount_pence": 2900,
                "currency": "GBP",
                "mode": "auto",
                "method": "direct_debit",
                "status": "failed",
                "payment_status": "failed",
                "created_at": _iso(now - timedelta(days=7 * (i + 1))),
                "seed_tag": _SEED_TAG,
            })

    # 7) Referral leaderboard: make Emma a super-referrer with 5 friends (3 earned, 2 pending)
    emma = await db.members.find_one({"id": "mbr-emma"}, {"_id": 0})
    if emma:
        if not emma.get("referral_code"):
            await db.members.update_one({"id": "mbr-emma"}, {"$set": {"referral_code": "EMMA-FIT7"}})
        await db.members.update_one({"id": "mbr-emma"}, {"$set": {"promo_credit_pence": 1500}})
        for i, (status, days_ago) in enumerate([
            ("earned", 40), ("earned", 24), ("earned", 9),
            ("pending", 14), ("pending", 3),
        ]):
            await db.referrals.insert_one({
                "id": str(uuid.uuid4()),
                "referrer_id": "mbr-emma",
                "referee_id": f"mbr-emma-friend-{i}",
                "referee_email": f"friend{i}@example.com",
                "organization_id": DEMO_ORG_ID,
                "status": status,
                "credit_pence": 500,
                "created_at": _iso(now - timedelta(days=days_ago)),
                "earned_at": _iso(now - timedelta(days=days_ago - 3)) if status == "earned" else None,
                "seed_tag": _SEED_TAG,
            })
    # Sophia + James get 1 earned each for a competitive leaderboard
    for mid, days in (("mbr-sophia", 20), ("mbr-james", 12)):
        m = await db.members.find_one({"id": mid}, {"_id": 0})
        if m:
            await db.members.update_one({"id": mid}, {"$set": {"promo_credit_pence": 500}})
            await db.referrals.insert_one({
                "id": str(uuid.uuid4()),
                "referrer_id": mid,
                "referee_id": f"{mid}-friend",
                "referee_email": f"{mid}-friend@example.com",
                "organization_id": DEMO_ORG_ID,
                "status": "earned",
                "credit_pence": 500,
                "created_at": _iso(now - timedelta(days=days)),
                "earned_at": _iso(now - timedelta(days=days - 2)),
                "seed_tag": _SEED_TAG,
            })

    logger.info("Analytics demo seed complete")
