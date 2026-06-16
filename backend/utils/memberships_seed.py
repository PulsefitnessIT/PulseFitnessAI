"""Idempotent Pulse Fitness Memberships demo seed.

Creates:
  • One demo studio org (`Pulse Studio · Leeds`) attached to the same
    master-admin user so login flows through the standard Pulse Fitness operator
    side.
  • 4 membership plans (Monthly Unlimited / 10-Class Pack / Annual /
    Day Pass).
  • 4 class templates across 5 weekdays (Yoga, HIIT, Spin, Strength).
  • 3 demo members with active memberships and a couple of bookings.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from passlib.context import CryptContext

from utils.database import db

logger = logging.getLogger(__name__)
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_ORG_ID = "mbr-demo-org"
DEMO_OPERATOR_EMAIL = os.environ.get("DEMO_OPERATOR_EMAIL", "studio.leeds@pulsefitness.ai")
DEMO_OPERATOR_PASSWORD = os.environ.get("DEMO_OPERATOR_PASSWORD", "Studio2026!")
DEMO_INSTRUCTOR_EMAIL = os.environ.get("DEMO_INSTRUCTOR_EMAIL", "jake.ellis@demo.gymaxis")
DEMO_INSTRUCTOR_PASSWORD = os.environ.get("DEMO_INSTRUCTOR_PASSWORD", "Instructor2026!")
DEMO_INSTRUCTOR_USER_ID = "usr-instructor-jake"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


async def seed_memberships_demo() -> None:
    if os.environ.get("MEMBERSHIPS_DEMO_SEED_DISABLED", "").lower() in {"1", "true", "yes"}:
        return
    now = _now()

    # 1) Demo operator org
    if not await db.organizations.find_one({"id": DEMO_ORG_ID}):
        await db.organizations.insert_one({
            "id": DEMO_ORG_ID,
            "name": "Pulse Studio · Leeds",
            "slug": "pulse-leeds",
            "account_type": "pulse_pro",
            "subscription_tier": "pro",
            "primary_brand_colour": "#19CDFF",
            "logo_url": None,
            "currency": "GBP",
            "timezone": "Europe/London",
            "payment_method": "manual",
            "setup_completed": True,
            "setup_step": "done",
            "created_at": _iso(now),
        })
        logger.info("Memberships: demo studio org created")

    # Backfill slug + branding on an existing org (upgrade path)
    await db.organizations.update_one(
        {"id": DEMO_ORG_ID, "slug": {"$in": [None, ""]}},
        {"$set": {"slug": "pulse-leeds", "currency": "GBP",
                  "timezone": "Europe/London", "payment_method": "manual",
                  "setup_completed": True, "setup_step": "done"}},
    )

    # 2) Operator login user
    if not await db.users.find_one({"email": DEMO_OPERATOR_EMAIL}):
        await db.users.insert_one({
            "id": "mbr-demo-operator",
            "email": DEMO_OPERATOR_EMAIL,
            "password": pwd_ctx.hash(DEMO_OPERATOR_PASSWORD),
            "full_name": "Pulse Studio Leeds — Manager",
            "organization_id": DEMO_ORG_ID,
            "role": "owner",
            "account_type": "pulse_pro",
            "created_at": _iso(now),
            "password_updated_at": _iso(now),
        })
        logger.info("Memberships: demo operator user created")

    # 2b) Demo instructor user
    if not await db.users.find_one({"email": DEMO_INSTRUCTOR_EMAIL}):
        await db.users.insert_one({
            "id": DEMO_INSTRUCTOR_USER_ID,
            "email": DEMO_INSTRUCTOR_EMAIL,
            "password": pwd_ctx.hash(DEMO_INSTRUCTOR_PASSWORD),
            "full_name": "Jake Ellis",
            "organization_id": DEMO_ORG_ID,
            "role": "instructor",
            "account_type": "pulse_pro",
            "is_instructor": True,
            "instructor_rate_pence": 2500,  # £25 per class
            "created_at": _iso(now),
            "password_updated_at": _iso(now),
        })
        logger.info("Memberships: demo instructor user created")

    # 3) Plans
    plans_seed = [
        {"id": "plan-monthly-unl", "name": "Monthly Unlimited",
         "kind": "recurring", "billing_cycle": "monthly",
         "price_pence": 6500, "upfront_fee_pence": 0,
         "included_classes": "unlimited", "colour": "#19CDFF",
         "display_order": 1, "cancel_notice_days": 30, "freeze_max_days": 90},
        {"id": "plan-annual-unl", "name": "Annual Unlimited",
         "kind": "recurring", "billing_cycle": "annual",
         "price_pence": 65000, "upfront_fee_pence": 0,
         "included_classes": "unlimited", "colour": "#8B5CF6",
         "display_order": 2},
        {"id": "plan-10pack", "name": "10-Class Pack",
         "kind": "class_pack", "billing_cycle": "oneoff",
         "price_pence": 9500, "credits_count": 10,
         "included_classes": "credits_only", "colour": "#F59E0B",
         "display_order": 3, "freeze_allowed": False, "cancel_notice_days": 0},
        {"id": "plan-day-pass", "name": "Day Pass",
         "kind": "payg", "billing_cycle": "oneoff",
         "price_pence": 1500, "credits_count": 1,
         "included_classes": "credits_only", "colour": "#10B981",
         "display_order": 4, "freeze_allowed": False, "cancel_notice_days": 0},
    ]
    for p in plans_seed:
        if not await db.membership_plans.find_one({"id": p["id"]}):
            await db.membership_plans.insert_one({
                **p, "organization_id": DEMO_ORG_ID, "active": True,
                "site_scope": "all_sites", "created_at": _iso(now),
                "description": None, "duration_days": None,
                "cancel_notice_days": p.get("cancel_notice_days", 30),
                "freeze_allowed": p.get("freeze_allowed", True),
                "freeze_max_days": p.get("freeze_max_days", 90),
            })

    # 4) Class templates — materialise 8 weeks of occurrences on first seed
    templates_seed = [
        {"id": "tpl-yoga", "name": "Vinyasa Yoga", "category": "Yoga",
         "duration_min": 60, "capacity": 15, "colour": "#8B5CF6",
         "recurs_days": [1, 3], "start_time": "07:00",
         "instructor_name": "Maya Patel"},
        {"id": "tpl-hiit", "name": "HIIT Blast", "category": "HIIT",
         "duration_min": 45, "capacity": 20, "colour": "#EF4444",
         "recurs_days": [0, 2, 4], "start_time": "06:30",
         "instructor_name": "Jake Ellis",
         "instructor_user_id": DEMO_INSTRUCTOR_USER_ID,
         "instructor_rate_pence": 2500},
        {"id": "tpl-spin", "name": "Rhythm Ride", "category": "Cycle",
         "duration_min": 45, "capacity": 25, "colour": "#F59E0B",
         "recurs_days": [1, 4], "start_time": "18:00",
         "instructor_name": "Sara O'Neill"},
        {"id": "tpl-strength", "name": "Strength Fundamentals", "category": "Strength",
         "duration_min": 60, "capacity": 12, "colour": "#0EA5E9",
         "recurs_days": [2, 5], "start_time": "17:30",
         "instructor_name": "Tom Briggs"},
    ]
    for t in templates_seed:
        if not await db.class_templates.find_one({"id": t["id"]}):
            doc = {
                "organization_id": DEMO_ORG_ID, "site_id": None,
                "booking_opens_hours_before": 168, "cancellation_cutoff_hours_before": 12,
                "waitlist_enabled": True, "max_waitlist": 10, "credits_to_book": 1,
                "room_name": "Studio 1", "archived": False, "created_at": _iso(now),
                "description": None, "instructor_user_id": None,
                "instructor_rate_pence": 0,
                "access_plans": None,
                **t,  # t overrides defaults
            }
            await db.class_templates.insert_one(doc)
            # Materialise occurrences
            await _materialise(doc, now)
    # Backfill instructor_user_id on an already-seeded HIIT template so the
    # instructor portal works on existing envs too.
    await db.class_templates.update_one(
        {"id": "tpl-hiit", "instructor_user_id": None},
        {"$set": {"instructor_user_id": DEMO_INSTRUCTOR_USER_ID, "instructor_rate_pence": 2500}},
    )
    await db.class_occurrences.update_many(
        {"template_id": "tpl-hiit"},
        {"$set": {"instructor_user_id": DEMO_INSTRUCTOR_USER_ID}},
    )

    # 5) Demo members with memberships
    members_seed = [
        {"id": "mbr-emma", "email": "emma.wright@demo.gymaxis", "password": "Member2026!",
         "first_name": "Emma", "last_name": "Wright", "phone": "+44 7700 900401",
         "plan_id": "plan-monthly-unl"},
        {"id": "mbr-oliver", "email": "oliver.price@demo.gymaxis", "password": "Member2026!",
         "first_name": "Oliver", "last_name": "Price", "phone": "+44 7700 900402",
         "plan_id": "plan-10pack"},
        {"id": "mbr-sophia", "email": "sophia.khan@demo.gymaxis", "password": "Member2026!",
         "first_name": "Sophia", "last_name": "Khan", "phone": "+44 7700 900403",
         "plan_id": "plan-annual-unl"},
    ]
    for m in members_seed:
        if await db.members.find_one({"id": m["id"]}):
            continue
        await db.members.insert_one({
            "id": m["id"], "email": m["email"],
            "password": pwd_ctx.hash(m["password"]),
            "first_name": m["first_name"], "last_name": m["last_name"],
            "phone": m["phone"], "organization_id": DEMO_ORG_ID, "site_id": None,
            "account_type": "member", "status": "active",
            "tags": [], "no_show_count": 0, "lifetime_value_pence": 0,
            "promo_credit_pence": 0,
            "referral_code": f"{m['first_name'].upper()}-{uuid.uuid4().hex[:4].upper()}",
            "referred_by": None,
            "created_at": _iso(now),
        })
        await db.qr_rotation_secret.insert_one({
            "member_id": m["id"], "secret_b32": pyotp.random_base32(),
            "created_at": _iso(now),
        })
        plan = await db.membership_plans.find_one({"id": m["plan_id"]}, {"_id": 0})
        if plan:
            await db.member_memberships.insert_one({
                "id": str(uuid.uuid4()),
                "member_id": m["id"],
                "plan_id": plan["id"],
                "organization_id": DEMO_ORG_ID,
                "status": "active",
                "start_date": _iso(now),
                "end_date": None,
                "billing_status": "current",
                "credits_remaining": plan.get("credits_count") or 0,
                "credits_used": 0,
                "joined_at": _iso(now),
                "next_billing_at": _iso(now + timedelta(days=30)) if plan["kind"] == "recurring" else None,
                "audit_log": [{"at": _iso(now), "actor_id": "seed", "action": "seeded"}],
            })
    # Referral-code backfill for any pre-existing seeded member
    async for m in db.members.find({"organization_id": DEMO_ORG_ID, "referral_code": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "first_name": 1}):
        code = f"{(m.get('first_name') or 'MBR').upper()}-{uuid.uuid4().hex[:4].upper()}"
        await db.members.update_one({"id": m["id"]}, {"$set": {"referral_code": code, "promo_credit_pence": 0}})

    # Demo ad so operators see the concept
    if not await db.ad_placements.find_one({"organization_id": DEMO_ORG_ID}):
        await db.ad_placements.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": DEMO_ORG_ID,
            "headline": "Refer a friend, get £5",
            "body": "Share your code from the Profile tab.",
            "cta_label": "See my code",
            "cta_url": None,
            "image_url": None,
            "placement": "book_top",
            "active": True,
            "background_colour": "#19CDFF",
            "starts_at": None, "ends_at": None,
            "impressions": 0, "clicks": 0,
            "created_at": _iso(now),
        })

    logger.info("Memberships demo seed complete")


async def _materialise(template: dict, now: datetime, weeks: int = 8) -> None:
    try:
        hh, mm = [int(x) for x in template["start_time"].split(":", 1)]
    except Exception:
        hh, mm = 7, 0
    duration = int(template["duration_min"])
    days_set = set(int(d) for d in template.get("recurs_days") or [])
    cursor = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    end_horizon = cursor + timedelta(weeks=weeks)
    while cursor < end_horizon:
        if cursor.weekday() in days_set:
            starts = cursor.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if starts >= now - timedelta(hours=1):
                await db.class_occurrences.update_one(
                    {"template_id": template["id"], "starts_at": starts.isoformat()},
                    {"$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "template_id": template["id"],
                        "organization_id": template["organization_id"],
                        "site_id": template.get("site_id"),
                        "name": template["name"],
                        "colour": template.get("colour", "#19CDFF"),
                        "starts_at": starts.isoformat(),
                        "ends_at": (starts + timedelta(minutes=duration)).isoformat(),
                        "instructor_name": template.get("instructor_name"),
                        "room_name": template.get("room_name"),
                        "capacity": template.get("capacity", 20),
                        "bookings_count": 0, "waitlist_count": 0,
                        "attended_count": 0, "no_show_count": 0,
                        "status": "scheduled", "created_at": _iso(now),
                    }},
                    upsert=True,
                )
        cursor += timedelta(days=1)
