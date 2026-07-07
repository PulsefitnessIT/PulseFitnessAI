"""Seed realistic Operations data for the Pulse Pro demo org (lite.docs@…)
so the upgraded Pulse Pro dashboard shows the GymAxis-style trend cards
(Open Faults / Audits Completed / Maintenance Tasks with live sparklines).

Idempotent — wipes PRODEMO_* rows first. Run from /app/backend:
    python scripts/seed_pulse_pro_dashboard_demo.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EMAIL = "lite.docs@pulsedemo.test"
TAG = "PRODEMO_"
now = datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    u = await db.users.find_one({"email": EMAIL}, {"_id": 0, "organization_id": 1})
    if not u:
        print("Pulse Pro demo user not found — run seed_lite_docs_demo.py first")
        return
    org = u["organization_id"]

    for coll in ("equipment", "issues", "audits"):
        await db[coll].delete_many({"id": {"$regex": f"^{TAG}"}})

    # ── Equipment (8 machines) ───────────────────────────────────────
    machines = [
        ("Life Fitness 95T Treadmill", "Cardio", "operational"),
        ("Concept2 RowErg", "Cardio", "operational"),
        ("Technogym Skillmill", "Cardio", "operational"),
        ("Life Fitness Leg Press", "Strength", "operational"),
        ("Hammer Strength Bench", "Strength", "operational"),
        ("Matrix Upright Bike", "Cardio", "out_of_order"),
        ("Precor Elliptical", "Cardio", "operational"),
        ("Wattbike Pro", "Cardio", "operational"),
    ]
    eq_docs = []
    for i, (name, cat, status) in enumerate(machines, 1):
        eq_docs.append({
            "id": f"{TAG}eq_{i}", "organization_id": org, "name": name,
            "equipment_type": cat, "category": cat, "status": status,
            "serial_number": f"PRO-{i:04d}", "site_name": "Lite Docs Demo Gym",
            "created_at": iso(now - timedelta(days=120)),
        })
    await db.equipment.insert_many(eq_docs)

    # ── Issues spread over the last 3 months (drives Open Faults trend) ──
    # month offsets: ~60d ago (2 mo back), ~30d ago (last mo), now (this mo)
    spread = [62, 58, 50, 33, 28, 20, 12, 6, 4, 2, 1, 0]
    iss_docs = []
    for i, age in enumerate(spread, 1):
        status = "open" if i % 3 != 0 else "resolved"
        created = now - timedelta(days=age)
        iss_docs.append({
            "id": f"{TAG}iss_{i}", "organization_id": org,
            "equipment_id": f"{TAG}eq_{(i % 8) + 1}",
            "serial_number": f"PRO-{(i % 8) + 1:04d}",
            "machine_type": "Cardio", "issue_description": f"Reported fault #{i}",
            "severity": "operational_fault" if i % 2 else "out_of_order",
            "status": status, "supplier": ["Life Fitness", "Technogym", "Precor"][i % 3],
            "created_at": iso(created),
            "resolved_at": iso(created + timedelta(days=2)) if status == "resolved" else None,
        })
    await db.issues.insert_many(iss_docs)

    # ── Audits spread over 3 months (drives Audits Completed trend) ─────
    aud_spread = [61, 55, 40, 31, 25, 18, 10, 5, 3, 1]
    aud_docs = []
    for i, age in enumerate(aud_spread, 1):
        aud_docs.append({
            "id": f"{TAG}aud_{i}", "organization_id": org,
            "equipment_id": f"{TAG}eq_{(i % 8) + 1}",
            "score": 80 + (i % 15), "created_at": iso(now - timedelta(days=age)),
        })
    await db.audits.insert_many(aud_docs)

    print(f"Seeded Pulse Pro dashboard demo for org {org} ({EMAIL}):")
    print(f"  • {len(eq_docs)} equipment, {len(iss_docs)} issues (open+resolved), {len(aud_docs)} audits")
    print("  • Maintenance Tasks card uses the built-in default tasks (count > 0 automatically)")
    print("  Verify: log in as lite.docs@pulsedemo.test → /pulse Dashboard → 3 sparkline trend cards")


if __name__ == "__main__":
    asyncio.run(main())
