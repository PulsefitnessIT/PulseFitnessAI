"""Seed a small, realistic set of 'delivered by us' machines into the iso
demo estate so the CAPEX 'Delivered by us' view shows real cost + age +
a non-zero replacement forecast for the director demo.

Idempotent: every doc is tagged demo_seed='capex_delivered' and wiped on
re-run. Run:  cd /app/backend && PYTHONPATH=/app/backend \
    python scripts/seed_capex_delivered_demo.py
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

ORG = "iso-demo-org"
TAG = "capex_delivered"
now = datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


def days_ago(n):
    return now - timedelta(days=n)


# (name, type, site, location, cost, years_in_service, warranty_years, n_faults, n_critical)
MACHINES = [
    ("Pulse Runner GP",     "Treadmill",     "iso-demo-site-a", "Cardio Zone",   4500, 6.5, 2,  9, 2),
    ("Pulse Power Cable",   "Cable Machine", "iso-demo-site-a", "Strength Zone", 4500, 5.0, 5,  7, 1),
    ("Pulse Bike 500",      "Exercise Bike", "iso-demo-site-b", "Cardio Zone",   899,  1.2, 3,  1, 0),
    ("Pulse Cross X",       "Cross Trainer", "iso-demo-site-b", "Cardio Zone",   2800, 2.0, 5,  0, 0),
]


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    # wipe prior seed
    await db.equipment.delete_many({"organization_id": ORG, "demo_seed": TAG})
    await db.issues.delete_many({"organization_id": ORG, "demo_seed": TAG})

    for name, etype, site, loc, cost, yrs, wyrs, nf, ncrit in MACHINES:
        install = days_ago(int(yrs * 365))
        warranty_expiry = install + timedelta(days=int(wyrs * 365))
        serial = f"GPDIST-{uuid.uuid4().hex[:8].upper()}"
        eq_id = str(uuid.uuid4())
        await db.equipment.insert_one({
            "id": eq_id, "organization_id": ORG, "user_id": "seed",
            "name": f"{name} — {serial}", "equipment_type": etype,
            "manufacturer": "Pulse Fitness", "model": name,
            "serial_number": serial,
            "site_id": site, "location": loc,
            "status": "operational",
            "supplier": "Pulse Fitness", "supplier_email": "service.dept@pulsefitness.com",
            "purchase_cost": cost, "replacement_cost": cost,
            "install_date": iso(install), "purchase_date": iso(install),
            "warranty_expiry": iso(warranty_expiry),
            "source": "distribution_install", "asset_source": "dealer_distribution",
            "demo_seed": TAG,
            "created_at": iso(install), "updated_at": iso(now),
        })
        # fault history spread across the service period
        for i in range(nf):
            created = days_ago(int((yrs * 365) * (i + 1) / (nf + 1)))
            sev = "critical" if i < ncrit else ("medium" if i % 2 == 0 else "low")
            await db.issues.insert_one({
                "id": str(uuid.uuid4()), "organization_id": ORG,
                "equipment_id": eq_id, "serial_number": serial,
                "issue_description": f"{etype} fault #{i + 1}",
                "severity": sev, "status": "resolved",
                "resolution_type": "engineer_fix",
                "created_at": iso(created), "resolved_at": iso(created + timedelta(days=2)),
                "updated_at": iso(created + timedelta(days=2)),
                "demo_seed": TAG,
            })
        print(f"seeded {name}: £{cost}, {yrs}y in service, {nf} faults, expiry {warranty_expiry.date()}")

    c.close()
    print("done — CAPEX 'Delivered by us' now has realistic demo assets.")


if __name__ == "__main__":
    asyncio.run(main())
