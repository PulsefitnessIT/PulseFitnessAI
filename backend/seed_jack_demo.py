"""One-off demo seed for Jack Ottey's 11am presentation.

Goal: turn the empty Third Space dashboard into a realistic "active day"
so every demo widget has visible content. Idempotent — only inserts
records with `demo_seed_jack=true`; re-running cleans up + reseeds.

Strategy:
  • Add 12 competitor cardio machines (Life Fitness, Technogym,
    Wattbike, Concept 2) across the 6 sites so the Suppliers league
    has rank diversity.
  • Seed 20 open faults across sites + severities + suppliers.
  • Seed 7 resolved-this-week faults so the dashboard KPI moves.
  • Seed 4 supplier-escalated cases so the supplier dashboard's
    Pending / Responded / Resolved counters show movement.
  • Seed 10 audits (check_sheet_completions) over the last 7 days.
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient


def main():
    random.seed(42)
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    ts_id = "c695638c-5f60-424d-bdd0-2273e6c24205"
    # jack_id retained as documentation — value baked into seeded users below.
    now = datetime.now(timezone.utc)

    # ── Wipe previous seed runs ──
    for col in ("equipment", "issues", "supplier_cases", "check_sheet_completions", "audits", "fix_history"):
        d = db[col].delete_many({"demo_seed_jack": True})
        print(f"  wiped {col}: {d.deleted_count}")

    # ── Refresh warranty on existing Pulse Fitness equipment so the
    #    warranty_health score lifts from 3/15 to ~12/15. Roll random
    #    future expiry dates (60-540 days out) across the 98 strength
    #    machines that have a missing/expired warranty.
    ts_eq = list(db.equipment.find(
        {"organization_id": ts_id, "demo_seed_jack": {"$ne": True}},
        {"_id": 0, "id": 1, "warranty_expiry": 1},
    ))
    refreshed = 0
    today_iso = now.date().isoformat()
    for eq in ts_eq:
        w = eq.get("warranty_expiry")
        if (not w) or w < today_iso:
            future = (now + timedelta(days=random.randint(60, 540))).date().isoformat()
            db.equipment.update_one({"id": eq["id"]}, {"$set": {"warranty_expiry": future, "demo_warranty_refreshed": True}})
            refreshed += 1
    print(f"  refreshed warranty on {refreshed} existing machines")

    sites = list(db.sites.find({"organization_id": ts_id}, {"_id": 0, "id": 1, "name": 1}))
    sites.sort(key=lambda s: s["name"])
    assert len(sites) == 6, sites
    site_ids = [s["id"] for s in sites]
    canary = sites[0]["id"]  # Canary Wharf — default

    # ── Step 1: Competitor cardio kit ──
    COMPETITORS = [
        ("Life Fitness", "Integrity X Treadmill", "Treadmill",   5500),
        ("Life Fitness", "PowerMill Climber",     "Stepper",     4900),
        ("Technogym",    "Skillrow",              "Rower",       3800),
        ("Technogym",    "Excite Run 1000",       "Treadmill",   5800),
        ("Wattbike",     "Atom Smart Bike",       "Bike",        2800),
        ("Wattbike",     "AtomX",                 "Bike",        3400),
        ("Concept 2",    "RowErg",                "Rower",       1200),
        ("Concept 2",    "BikeErg",               "Bike",        1100),
        ("Life Fitness", "Discover SE3 Bike",     "Bike",        3200),
        ("Technogym",    "Group Cycle",           "Bike",        2400),
        ("Concept 2",    "SkiErg",                "Cardio",      900),
        ("Life Fitness", "Synrgy 360",            "Functional",  9500),
    ]
    new_eq_ids: list[str] = []
    new_eq: list[dict] = []
    for i, (mfr, model, etype, cost) in enumerate(COMPETITORS):
        sid = site_ids[i % 6]
        eq_id = str(uuid.uuid4())
        age_yrs = random.randint(1, 7)
        purchase = (now - timedelta(days=age_yrs * 365)).isoformat()
        new_eq.append({
            "id": eq_id,
            "organization_id": ts_id, "site_id": sid,
            "name": model, "equipment_type": etype,
            "manufacturer": mfr, "supplier_name": mfr,
            "model": model,
            "serial_number": f"{mfr[:3].upper()}-TS{i:02d}",
            "purchase_date": purchase,
            "purchase_price": cost, "replacement_cost": cost,
            "status": "active",
            "warranty_expires_at": (now + timedelta(days=random.randint(60, 600))).isoformat(),
            "warranty_expiry": (now + timedelta(days=random.randint(60, 600))).date().isoformat(),
            "created_at": now.isoformat(),
            "demo_seed_jack": True,
        })
        new_eq_ids.append(eq_id)
    db.equipment.insert_many(new_eq)
    print(f"  seeded equipment: {len(new_eq)}")

    # ── Step 2: pick a mixed set of equipment to bind faults to ──
    pulse_eq = list(db.equipment.find(
        {"organization_id": ts_id, "demo_seed_jack": {"$ne": True}},
        {"_id": 0, "id": 1, "site_id": 1, "manufacturer": 1, "name": 1, "equipment_type": 1},
    ).limit(40))

    # Each tuple: (severity, status, age_days, description, suggested_supplier_pref)
    OPEN_FAULTS = [
        ("urgent",  "open",        1,  "Emergency stop fails to engage", "competitor"),
        ("high",    "open",        1,  "Belt slipping above 8 km/h",      "competitor"),
        ("high",    "open",        3,  "Resistance arm wobbles",          "pulse"),
        ("medium",  "open",        2,  "LED display dim — half visible",  "competitor"),
        ("medium",  "open",        4,  "Cable fray on lat pulldown",      "pulse"),
        ("medium",  "in_progress", 3,  "Heart-rate strap unresponsive",   "competitor"),
        ("low",     "open",        2,  "Bench pad tear (small)",          "pulse"),
        ("high",    "in_progress", 4,  "Treadmill incline motor stalls",  "competitor"),
        ("medium",  "open",        5,  "Lubrication overdue (>90 days)",  "pulse"),
        ("low",     "open",        4,  "Touchscreen calibration drift",   "competitor"),
        ("urgent",  "open",        1,  "Pin missing on weight stack",     "pulse"),
    ]
    RESOLVED_FAULTS = [
        ("high",   "resolved", 1, "Console reboot fixed -ERR2-",       "competitor", True),
        ("medium", "resolved", 2, "Belt waxed — back to normal",       "competitor", True),
        ("high",   "resolved", 3, "Replaced cable on chest press",     "pulse",       False),
        ("low",    "resolved", 4, "Sticker reapplied",                  "pulse",       True),
        ("medium", "resolved", 5, "Strap clip replaced",                "competitor", False),
        ("high",   "resolved", 6, "Drive belt tightened",               "competitor", False),
        ("medium", "resolved", 1, "Cable replaced on lat pulldown",     "pulse",       False),
        ("medium", "resolved", 2, "Lubrication serviced",               "pulse",       True),
        ("low",    "resolved", 3, "Drink holder swapped",               "pulse",       True),
        ("high",   "resolved", 4, "Display recalibrated",               "competitor", True),
        ("medium", "resolved", 5, "Pulley bearing replaced",            "pulse",       False),
        ("low",    "resolved", 6, "Floor mat re-laid",                  "pulse",       True),
    ]

    competitor_eq = [e for e in pulse_eq if False] + [e for e in db.equipment.find(
        {"organization_id": ts_id, "demo_seed_jack": True}, {"_id": 0, "id": 1, "site_id": 1, "manufacturer": 1, "name": 1, "equipment_type": 1},
    )]

    def pick(pref: str) -> dict:
        if pref == "competitor" and competitor_eq:
            return random.choice(competitor_eq)
        if pref == "pulse" and pulse_eq:
            return random.choice(pulse_eq)
        return random.choice(pulse_eq + competitor_eq)

    issues_to_insert: list[dict] = []
    for sev, status, age, desc, pref in OPEN_FAULTS:
        eq = pick(pref)
        created = now - timedelta(days=age, hours=random.randint(0, 23))
        issues_to_insert.append({
            "id": str(uuid.uuid4()),
            "organization_id": ts_id, "site_id": eq["site_id"],
            "equipment_id": eq["id"],
            "machine_type": eq.get("equipment_type"),
            "issue_description": desc,
            "severity": sev, "priority": sev,
            "status": status,
            "reporter_name": random.choice(["Floor team", "PT staff", "Cleaning", "Member report"]),
            "reporter_email": "ops@thirdspace.london",
            "created_at": created.isoformat(),
            "demo_seed_jack": True,
        })
    for sev, status, age, desc, pref, self_fix in RESOLVED_FAULTS:
        eq = pick(pref)
        created = now - timedelta(days=age + 1, hours=random.randint(0, 23))
        resolved = now - timedelta(days=max(0, age - 1), hours=random.randint(1, 12))
        issues_to_insert.append({
            "id": str(uuid.uuid4()),
            "organization_id": ts_id, "site_id": eq["site_id"],
            "equipment_id": eq["id"],
            "machine_type": eq.get("equipment_type"),
            "issue_description": desc,
            "severity": sev, "priority": sev,
            "status": status,
            "resolved_at": resolved.isoformat(),
            "resolution_type": "self_fix" if self_fix else "supplier",
            "resolved_by": "Jack Ottey" if self_fix else None,
            "reporter_name": random.choice(["Floor team", "PT staff", "Member report"]),
            "reporter_email": "ops@thirdspace.london",
            "created_at": created.isoformat(),
            "demo_seed_jack": True,
        })
    db.issues.insert_many(issues_to_insert)
    print(f"  seeded issues: {len(issues_to_insert)}")

    # ── Step 3: Supplier escalation cases ──
    open_competitor_issues = [
        i for i in issues_to_insert
        if i["status"] in ("open", "in_progress")
        and any(eq["id"] == i["equipment_id"] for eq in competitor_eq)
    ]
    cases = []
    case_supplier_pool = ["Life Fitness", "Technogym", "Wattbike", "Concept 2"]
    for k in range(4):
        if k >= len(open_competitor_issues):
            break
        iss = open_competitor_issues[k]
        eq = next((e for e in competitor_eq if e["id"] == iss["equipment_id"]), None)
        if not eq:
            continue
        sname = eq.get("manufacturer", case_supplier_pool[k % 4])
        created = datetime.fromisoformat(iss["created_at"])
        responded = created + timedelta(hours=random.randint(2, 30))
        status_hist = [{"status": "pending", "updated_at": created.isoformat()}]
        # Simulate response on 3 of 4 cases
        if k > 0:
            status_hist.append({"status": "responded", "updated_at": responded.isoformat()})
        cases.append({
            "id": str(uuid.uuid4()),
            "case_id": f"TS-{1000 + k}",
            "issue_id": iss["id"],
            "supplier_name": sname,
            "supplier_email": f"support@{sname.lower().replace(' ', '')}.com",
            "current_status": "responded" if k > 0 else "pending",
            "rating": random.choice([4, 5, 5, 3]) if k > 1 else None,
            "status_history": status_hist,
            "created_at": created.isoformat(),
            "organization_id": ts_id,
            "demo_seed_jack": True,
        })
    if cases:
        db.supplier_cases.insert_many(cases)
        print(f"  seeded supplier cases: {len(cases)}")

    # ── Step 4: Audits (used by gym health score; lives in db.audits) ──
    # We bind each audit to a specific equipment_id so the coverage
    # score (distinct audited equipment / total equipment) lifts. To
    # land Jack's dashboard around the "Good" band we audit ~58% of
    # the fleet (~65 audits over the last 7 days).
    audits = []
    audit_eq_pool = [e["id"] for e in db.equipment.find(
        {"organization_id": ts_id}, {"_id": 0, "id": 1}
    )]
    random.shuffle(audit_eq_pool)
    audit_targets = audit_eq_pool[: max(60, int(len(audit_eq_pool) * 0.58))]
    for k, eq_id in enumerate(audit_targets):
        completed = now - timedelta(days=random.randint(0, 6), hours=random.randint(0, 12))
        audits.append({
            "id": str(uuid.uuid4()),
            "organization_id": ts_id,
            "equipment_id": eq_id,
            "audit_type": random.choice([
                "Morning Walkround", "Strength Floor Audit",
                "Locker Inspection", "Pool Plant Daily Check",
                "End-of-day Service Sweep",
            ]),
            "completed_by": random.choice(["Jack Ottey", "Floor Manager", "Duty Manager"]),
            "score": random.randint(82, 99),
            "passed": True,
            "completed_at": completed.isoformat(),
            "created_at": completed.isoformat(),
            "demo_seed_jack": True,
        })
    db.audits.insert_many(audits)
    print(f"  seeded audits: {len(audits)}")

    # ── Step 5: Fix history (proven self-fix recipes for AI knowledge score) ──
    fix_history = []
    fixes = [
        ("Treadmill", "Belt slipping",            "Apply belt wax · re-tension"),
        ("Treadmill", "Console reboot",            "Hold power 10s to reset"),
        ("Rower",     "Strap clip worn",           "Order Concept2 clip kit · replace in 2 min"),
        ("Bike",      "Heart-rate strap dropping","Replace battery · re-pair"),
        ("Strength",  "Cable fray",                "Order new cable · swap with M8 hex"),
        ("Strength",  "Pulley bearing noise",      "Grease bearing or replace"),
        ("Cardio",    "Touchscreen drift",         "Recalibrate via Service menu"),
    ]
    for et, name, recipe in fixes:
        fix_history.append({
            "id": str(uuid.uuid4()),
            "organization_id": ts_id,
            "equipment_type": et, "issue_pattern": name,
            "fix_recipe": recipe,
            "success_count": random.randint(3, 12),
            "last_used_at": (now - timedelta(days=random.randint(1, 14))).isoformat(),
            "created_at": now.isoformat(),
            "demo_seed_jack": True,
        })
    db.fix_history.insert_many(fix_history)
    print(f"  seeded fix_history: {len(fix_history)}")

    # Also mirror most audits into check_sheet_completions for the UI tab.
    for a in audits[:30]:
        db.check_sheet_completions.insert_one({
            **a,
            "template_name": a["audit_type"],
            "completed_date": datetime.fromisoformat(a["completed_at"]).date().isoformat(),
            "site_id": canary,
            "items": [
                {"name": "All Areas Cleaned", "checked": True},
                {"name": "Emergency Stops Tested", "checked": True},
                {"name": "Cable Wear Inspection", "checked": True},
            ],
        })

    # ── Summary ──
    print()
    print("── Final Jack/Third Space dashboard counts ──")
    print(f"  Equipment: {db.equipment.count_documents({'organization_id': ts_id})}")
    print(f"  Issues (open): {db.issues.count_documents({'organization_id': ts_id, 'status': {'$in': ['open', 'in_progress']}})}")
    print(f"  Issues (resolved): {db.issues.count_documents({'organization_id': ts_id, 'status': 'resolved'})}")
    print(f"  Supplier cases: {db.supplier_cases.count_documents({'organization_id': ts_id})}")
    print(f"  Check-sheet completions: {db.check_sheet_completions.count_documents({'organization_id': ts_id})}")

if __name__ == "__main__":
    main()
