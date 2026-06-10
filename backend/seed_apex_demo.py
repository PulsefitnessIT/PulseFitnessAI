"""Neutral, Pulse-free demo org for sales-deck screenshots.

Creates "Apex Fitness Group" (account_type=full → GymAxis branding) with
rich, brand-safe data across Operations + Memberships so every operator
feature slide can show a real, populated screenshot.

Idempotent: wipes anything tagged demo_seed_apex=True and reseeds.
Run:  cd /app/backend && set -a && . ./.env && set +a && python -m seed_apex_demo
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
import bcrypt

ORG_ID = "apex-demo-org"
OWNER_EMAIL = "owner@apexfitness.group"
OWNER_PW = "ApexDemo2026!"


def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def main():
    random.seed(7)
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    def iso(d=None):
        return (d or now).isoformat()

    # ── wipe prior apex seed ──
    for col in ("equipment", "issues", "audits", "check_sheet_completions", "fix_history",
                "membership_plans", "class_templates", "class_occurrences", "members",
                "member_memberships", "sites"):
        db[col].delete_many({"demo_seed_apex": True})

    # ── org ──
    modules = {
        "memberships": {"enabled": True, "source": "seed"},
        "crm": {"enabled": True, "source": "seed"},
        "marketing": {"enabled": True, "source": "seed"},
    }
    db.organizations.update_one({"id": ORG_ID}, {"$set": {
        "id": ORG_ID,
        "name": "Apex Fitness Group",
        "slug": "apex-fitness-group",
        "account_type": "full",
        "subscription_tier": "enterprise",
        "portal_type": "full",
        "currency": "GBP",
        "timezone": "Europe/London",
        "modules": modules,
        "enabled_modules": ["operations", "memberships", "crm", "marketing"],
        "member_app_display_name": "Apex Fitness Group",
        "branding": {"company_name": "Apex Fitness Group", "primary_colour": "#0B5FFF"},
        "setup_completed": True, "setup_step": "done",
        "demo_seed_apex": True,
        "created_at": iso(), "updated_at": iso(),
    }}, upsert=True)

    # ── owner user ──
    db.users.update_one({"email": OWNER_EMAIL}, {"$set": {
        "id": "apex-owner",
        "email": OWNER_EMAIL,
        "password": hash_pw(OWNER_PW),
        "full_name": "Sarah Mitchell",
        "organization_id": ORG_ID,
        "organization_name": "Apex Fitness Group",
        "role": "owner",
        "account_type": "full",
        "active": True,
        "is_master_admin": False,
        "profile_completed_at": iso(),
        "consent_terms_and_privacy": True,
        "consent_terms_and_privacy_at": iso(),
        "created_at": iso(), "password_changed_at": iso(),
    }}, upsert=True)

    # ── sites ──
    SITE_NAMES = ["Apex Manchester Central", "Apex Leeds Riverside", "Apex Bristol Harbourside"]
    site_ids = []
    for nm in SITE_NAMES:
        sid = str(uuid.uuid4())
        site_ids.append(sid)
        db.sites.insert_one({
            "id": sid, "organization_id": ORG_ID, "name": nm,
            "address": f"{nm.split()[1]}, UK", "active": True,
            "created_at": iso(), "demo_seed_apex": True,
        })

    # ── equipment (non-Pulse brands only) ──
    FLEET = [
        ("Life Fitness", "Integrity X Treadmill", "Treadmill", 5500),
        ("Life Fitness", "Discover SE4 Bike", "Bike", 3200),
        ("Life Fitness", "PowerMill Climber", "Stepper", 4900),
        ("Life Fitness", "Synrgy 360", "Functional", 9500),
        ("Technogym", "Excite Run 1000", "Treadmill", 5800),
        ("Technogym", "Skillrow", "Rower", 3800),
        ("Technogym", "Group Cycle Connect", "Bike", 2400),
        ("Technogym", "Selection Pro Leg Press", "Strength", 4200),
        ("Matrix", "T75 Treadmill", "Treadmill", 5300),
        ("Matrix", "S-Drive Performance", "Functional", 6200),
        ("Matrix", "Versa Lat Pulldown", "Strength", 2600),
        ("Precor", "EFX 885 Elliptical", "Elliptical", 5100),
        ("Precor", "RBK 885 Bike", "Bike", 3000),
        ("Concept2", "RowErg", "Rower", 1200),
        ("Concept2", "BikeErg", "Bike", 1100),
        ("Concept2", "SkiErg", "Cardio", 900),
        ("Wattbike", "Atom Smart Bike", "Bike", 2800),
        ("Wattbike", "AtomX", "Bike", 3400),
        ("Hammer Strength", "Plate-Loaded Chest Press", "Strength", 3600),
        ("Hammer Strength", "Iso-Lateral Row", "Strength", 3400),
        ("Eleiko", "Olympic Barbell Set", "Free Weights", 1800),
        ("Stairmaster", "8 Series Gauntlet", "Stepper", 5200),
    ]
    eq_docs = []
    for i, (mfr, model, etype, cost) in enumerate(FLEET):
        sid = site_ids[i % 3]
        age = random.randint(1, 6)
        eq_docs.append({
            "id": str(uuid.uuid4()),
            "organization_id": ORG_ID, "site_id": sid,
            "name": model, "equipment_type": etype,
            "manufacturer": mfr, "supplier_name": mfr, "model": model,
            "serial_number": f"{mfr[:3].upper()}-AX{i:02d}{random.randint(100,999)}",
            "purchase_date": iso(now - timedelta(days=age * 365)),
            "purchase_price": cost, "replacement_cost": cost,
            "status": "active",
            "warranty_expiry": (now + timedelta(days=random.randint(60, 600))).date().isoformat(),
            "warranty_expires_at": iso(now + timedelta(days=random.randint(60, 600))),
            "created_at": iso(), "demo_seed_apex": True,
        })
    db.equipment.insert_many(eq_docs)

    # ── faults (open + resolved) ──
    OPEN = [
        ("urgent", "open", 1, "Emergency stop fails to engage"),
        ("high", "open", 1, "Belt slipping above 8 km/h"),
        ("high", "in_progress", 2, "Incline motor stalls intermittently"),
        ("medium", "open", 2, "LED console dim — half visible"),
        ("medium", "open", 3, "Heart-rate strap unresponsive"),
        ("medium", "in_progress", 4, "Cable fray on lat pulldown"),
        ("low", "open", 2, "Seat pad tear (small)"),
        ("low", "open", 5, "Touchscreen calibration drift"),
    ]
    RESOLVED = [
        ("high", "resolved", 2, "Console reboot fixed ERR-2", "self_fix"),
        ("medium", "resolved", 3, "Belt waxed and re-tensioned", "self_fix"),
        ("high", "resolved", 4, "Replaced drive cable on chest press", "supplier"),
        ("medium", "resolved", 5, "Pulley bearing replaced", "supplier"),
        ("low", "resolved", 3, "Floor mat re-laid", "self_fix"),
        ("medium", "resolved", 6, "Lubrication serviced", "self_fix"),
        ("high", "resolved", 7, "Display recalibrated", "supplier"),
        ("low", "resolved", 4, "Drink holder swapped", "self_fix"),
    ]
    reporters = ["Floor team", "PT staff", "Cleaning team", "Member report", "Duty manager"]
    issues = []
    for sev, status, age, desc in OPEN:
        eq = random.choice(eq_docs)
        issues.append({
            "id": str(uuid.uuid4()), "organization_id": ORG_ID, "site_id": eq["site_id"],
            "equipment_id": eq["id"], "machine_type": eq["equipment_type"],
            "equipment_name": eq["name"],
            "issue_description": desc, "severity": sev, "priority": sev, "status": status,
            "reporter_name": random.choice(reporters), "reporter_email": "ops@apexfitness.group",
            "created_at": iso(now - timedelta(days=age, hours=random.randint(0, 20))),
            "demo_seed_apex": True,
        })
    for sev, status, age, desc, rtype in RESOLVED:
        eq = random.choice(eq_docs)
        created = now - timedelta(days=age + 1, hours=random.randint(0, 20))
        issues.append({
            "id": str(uuid.uuid4()), "organization_id": ORG_ID, "site_id": eq["site_id"],
            "equipment_id": eq["id"], "machine_type": eq["equipment_type"],
            "equipment_name": eq["name"],
            "issue_description": desc, "severity": sev, "priority": sev, "status": status,
            "resolved_at": iso(now - timedelta(days=max(0, age - 1))),
            "resolution_type": rtype, "resolved_by": "Sarah Mitchell" if rtype == "self_fix" else None,
            "reporter_name": random.choice(reporters), "reporter_email": "ops@apexfitness.group",
            "created_at": iso(created), "demo_seed_apex": True,
        })
    db.issues.insert_many(issues)

    # ── audits + check sheets (gym health) ──
    audits = []
    pool = [e["id"] for e in eq_docs]
    random.shuffle(pool)
    for eq_id in pool[: int(len(pool) * 0.7)]:
        completed = now - timedelta(days=random.randint(0, 6), hours=random.randint(0, 12))
        audits.append({
            "id": str(uuid.uuid4()), "organization_id": ORG_ID, "equipment_id": eq_id,
            "audit_type": random.choice(["Morning Walkround", "Strength Floor Audit",
                                         "Cardio Daily Check", "End-of-day Service Sweep"]),
            "completed_by": random.choice(["Sarah Mitchell", "Floor Manager", "Duty Manager"]),
            "score": random.randint(84, 99), "passed": True,
            "completed_at": iso(completed), "created_at": iso(completed), "demo_seed_apex": True,
        })
    db.audits.insert_many(audits)
    for a in audits[:20]:
        db.check_sheet_completions.insert_one({
            **a, "template_name": a["audit_type"],
            "completed_date": datetime.fromisoformat(a["completed_at"]).date().isoformat(),
            "site_id": site_ids[0],
            "items": [{"name": "All Areas Cleaned", "checked": True},
                      {"name": "Emergency Stops Tested", "checked": True},
                      {"name": "Cable Wear Inspection", "checked": True}],
        })

    # ── memberships: plans ──
    plans = [
        {"id": "apex-plan-monthly", "name": "Monthly Unlimited", "kind": "recurring",
         "billing_cycle": "monthly", "price_pence": 4900, "included_classes": "unlimited",
         "colour": "#0B5FFF", "display_order": 1, "credits_count": 0},
        {"id": "apex-plan-annual", "name": "Annual Unlimited", "kind": "recurring",
         "billing_cycle": "annual", "price_pence": 49000, "included_classes": "unlimited",
         "colour": "#8B5CF6", "display_order": 2, "credits_count": 0},
        {"id": "apex-plan-10pack", "name": "10-Class Pack", "kind": "class_pack",
         "billing_cycle": "oneoff", "price_pence": 7500, "included_classes": "credits_only",
         "colour": "#F59E0B", "display_order": 3, "credits_count": 10},
        {"id": "apex-plan-daypass", "name": "Day Pass", "kind": "payg",
         "billing_cycle": "oneoff", "price_pence": 1200, "included_classes": "credits_only",
         "colour": "#10B981", "display_order": 4, "credits_count": 1},
    ]
    for p in plans:
        db.membership_plans.insert_one({**p, "organization_id": ORG_ID, "active": True,
            "site_scope": "all_sites", "description": None, "duration_days": None,
            "cancel_notice_days": 30, "freeze_allowed": True, "freeze_max_days": 90,
            "upfront_fee_pence": 0, "created_at": iso(), "demo_seed_apex": True})

    # ── class templates + occurrences ──
    templates = [
        {"id": "apex-tpl-yoga", "name": "Vinyasa Yoga", "category": "Yoga", "duration_min": 60,
         "capacity": 18, "colour": "#8B5CF6", "recurs_days": [1, 3], "start_time": "07:00",
         "instructor_name": "Maya Patel"},
        {"id": "apex-tpl-hiit", "name": "HIIT Blast", "category": "HIIT", "duration_min": 45,
         "capacity": 24, "colour": "#EF4444", "recurs_days": [0, 2, 4], "start_time": "06:30",
         "instructor_name": "Jordan Reid"},
        {"id": "apex-tpl-spin", "name": "Rhythm Ride", "category": "Cycle", "duration_min": 45,
         "capacity": 28, "colour": "#F59E0B", "recurs_days": [1, 4], "start_time": "18:00",
         "instructor_name": "Sara O'Neill"},
        {"id": "apex-tpl-strength", "name": "Strength Fundamentals", "category": "Strength",
         "duration_min": 60, "capacity": 14, "colour": "#0EA5E9", "recurs_days": [2, 5],
         "start_time": "17:30", "instructor_name": "Tom Briggs"},
    ]
    for t in templates:
        doc = {"organization_id": ORG_ID, "site_id": None, "booking_opens_hours_before": 168,
               "cancellation_cutoff_hours_before": 12, "waitlist_enabled": True, "max_waitlist": 10,
               "credits_to_book": 1, "room_name": "Studio 1", "archived": False,
               "description": None, "instructor_user_id": None, "instructor_rate_pence": 0,
               "access_plans": None, "created_at": iso(), "demo_seed_apex": True, **t}
        db.class_templates.insert_one(doc)
        # materialise 6 weeks of occurrences
        hh, mm = [int(x) for x in t["start_time"].split(":")]
        cursor = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end = cursor + timedelta(weeks=6)
        days_set = set(t["recurs_days"])
        while cursor < end:
            if cursor.weekday() in days_set:
                starts = cursor.replace(hour=hh, minute=mm)
                if starts >= now - timedelta(hours=1):
                    booked = random.randint(int(t["capacity"] * 0.5), t["capacity"])
                    db.class_occurrences.insert_one({
                        "id": str(uuid.uuid4()), "template_id": t["id"], "organization_id": ORG_ID,
                        "site_id": None, "name": t["name"], "colour": t["colour"],
                        "starts_at": starts.isoformat(),
                        "ends_at": (starts + timedelta(minutes=t["duration_min"])).isoformat(),
                        "instructor_name": t["instructor_name"], "room_name": "Studio 1",
                        "capacity": t["capacity"], "bookings_count": booked, "waitlist_count": 0,
                        "attended_count": 0, "no_show_count": 0, "status": "scheduled",
                        "created_at": iso(), "demo_seed_apex": True,
                    })
            cursor += timedelta(days=1)

    # ── members ──
    FIRST = ["Emma", "Oliver", "Sophia", "Jack", "Ava", "Noah", "Mia", "Leo", "Isla", "Ethan",
             "Grace", "Harry", "Ruby", "Charlie", "Freya", "George", "Lily", "Oscar"]
    LAST = ["Wright", "Price", "Khan", "Stewart", "Hughes", "Foster", "Reed", "Barnes",
            "Cole", "Day", "Webb", "Knight", "Shaw", "Holt", "Lane", "Frost", "Wells", "Pope"]
    plan_ids = [p["id"] for p in plans]
    members = []
    for i in range(18):
        fn, ln = FIRST[i], LAST[i]
        mid = f"apex-mbr-{i:02d}"
        plan_id = random.choice(plan_ids)
        members.append({
            "id": mid, "email": f"{fn.lower()}.{ln.lower()}@apexdemo.member",
            "password": hash_pw("Member2026!"), "first_name": fn, "last_name": ln,
            "phone": f"+44 7700 9005{i:02d}", "organization_id": ORG_ID,
            "site_id": random.choice(site_ids), "account_type": "member",
            "status": "active", "tags": [], "no_show_count": 0,
            "lifetime_value_pence": random.randint(4900, 60000), "promo_credit_pence": 0,
            "referral_code": f"{fn.upper()}-{uuid.uuid4().hex[:4].upper()}", "referred_by": None,
            "created_at": iso(now - timedelta(days=random.randint(5, 400))), "demo_seed_apex": True,
            "_plan_id": plan_id,
        })
    for m in members:
        plan_id = m.pop("_plan_id")
        db.members.insert_one(m)
        plan = next(p for p in plans if p["id"] == plan_id)
        db.member_memberships.insert_one({
            "id": str(uuid.uuid4()), "member_id": m["id"], "plan_id": plan_id,
            "organization_id": ORG_ID, "status": "active", "start_date": iso(),
            "end_date": None, "billing_status": "current",
            "credits_remaining": plan.get("credits_count") or 0, "credits_used": 0,
            "joined_at": iso(), "demo_seed_apex": True,
            "next_billing_at": iso(now + timedelta(days=30)) if plan["kind"] == "recurring" else None,
        })

    print("Apex seed complete:")
    print("  equipment:", db.equipment.count_documents({"organization_id": ORG_ID}))
    print("  open issues:", db.issues.count_documents({"organization_id": ORG_ID, "status": {"$in": ["open", "in_progress"]}}))
    print("  resolved issues:", db.issues.count_documents({"organization_id": ORG_ID, "status": "resolved"}))
    print("  members:", db.members.count_documents({"organization_id": ORG_ID}))
    print("  plans:", db.membership_plans.count_documents({"organization_id": ORG_ID}))
    print("  class occurrences:", db.class_occurrences.count_documents({"organization_id": ORG_ID}))


if __name__ == "__main__":
    main()
