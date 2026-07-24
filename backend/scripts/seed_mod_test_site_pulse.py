"""Seed the 'MOD Test Site' with a realistic Pulse Fitness fleet (with photos).

Purpose: the sales team needs clean tender screenshots showing Pulse Fitness
equipment on a MOD site. This wipes the old ASER-QA placeholder machines on that
site and inserts a branded Pulse Fitness fleet, each with a product photo
(photo_url), serial, purchase/warranty dates and a couple of historic faults.

Idempotent: rows carry imported_via='mod_test_site_pulse'. Re-running clears the
previous seed (and the legacy ASER-QA items) first, then re-inserts.

Run: cd /app/backend && python scripts/seed_mod_test_site_pulse.py
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from utils.database import db

SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"  # MOD Test Site (mod_force=army)
SEED_TAG = "mod_test_site_pulse"

# (name, type, model, age_years, faults_12mo, replacement_cost, photo_url)
FLEET = [
    ("Pulse Fitness Series 3 Treadmill", "Treadmill", "Series 3 260G", 2, 0, 5200,
     "https://images.pexels.com/photos/12250460/pexels-photo-12250460.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"),
    ("Pulse Fitness Series 3 Upright Bike", "Bike", "Series 3 250G", 1, 0, 2600,
     "https://images.unsplash.com/photo-1637904215427-42481f0eaefa?crop=entropy&cs=srgb&fm=jpg&q=85&w=940"),
    ("Pulse Fitness Series 3 Recumbent Bike", "Bike", "Series 3 255G", 3, 1, 2900,
     "https://images.unsplash.com/photo-1637578371283-d9076f66ba8e?crop=entropy&cs=srgb&fm=jpg&q=85&w=940"),
    ("Pulse Fitness Series 3 Cross Trainer", "Cross Trainer", "Series 3 265G", 2, 1, 4100,
     "https://images.pexels.com/photos/6390237/pexels-photo-6390237.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"),
    ("Pulse Fitness Rower", "Rower", "Series 3 270G", 4, 2, 1500,
     "https://images.pexels.com/photos/8611382/pexels-photo-8611382.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"),
    ("Pulse Fitness Fusion Dual Adjustable Pulley", "Strength", "Fusion DAP", 3, 1, 4800,
     "https://images.unsplash.com/photo-1604480133435-25b86862d276?crop=entropy&cs=srgb&fm=jpg&q=85&w=940"),
    ("Pulse Fitness Fusion Leg Press", "Strength", "Fusion Leg Press", 5, 3, 5100,
     "https://images.pexels.com/photos/37570727/pexels-photo-37570727.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"),
    ("Pulse Fitness Fusion Functional Trainer", "Strength", "Fusion FT", 2, 0, 5400,
     "https://images.pexels.com/photos/30994839/pexels-photo-30994839.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"),
]
FAULT_TYPES = ["mechanical", "electrical", "wear", "safety", "cosmetic"]


async def main() -> None:
    site = await db.organizations.find_one({"id": SITE_ID}, {"_id": 0, "id": 1, "name": 1})
    if not site:
        raise SystemExit(f"MOD Test Site {SITE_ID} not found")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Wipe prior seed + legacy ASER-QA placeholders so screenshots are clean.
    del_eq = await db.equipment.delete_many({
        "organization_id": SITE_ID,
        "$or": [{"imported_via": SEED_TAG}, {"name": {"$regex": "ASER QA", "$options": "i"}}],
    })
    old_ids = []
    async for e in db.equipment.find({"organization_id": SITE_ID}, {"_id": 0, "id": 1}):
        old_ids.append(e["id"])
    del_fa = await db.issues.delete_many({"organization_id": SITE_ID, "imported_via": SEED_TAG})
    print(f"Cleared {del_eq.deleted_count} equipment, {del_fa.deleted_count} seeded faults")

    eq_created = fa_created = 0
    for idx, (name, etype, model, age, faults, cost, photo) in enumerate(FLEET):
        purchase_iso = (now - timedelta(days=int(age * 365))).isoformat()
        warranty_iso = (now - timedelta(days=int(age * 365)) + timedelta(days=int(2 * 365))).isoformat()
        eq_id = str(uuid.uuid4())
        await db.equipment.insert_one({
            "id": eq_id,
            "organization_id": SITE_ID,
            "name": name,
            "equipment_type": etype,
            "category": etype,
            "manufacturer": "Pulse Fitness",
            "supplier": "Pulse Fitness",
            "model": model,
            "serial_number": f"PF-MODTS-{idx + 1:03d}",
            "purchase_date": purchase_iso,
            "purchase_price": cost,
            "replacement_cost": cost,
            "warranty_expiry": warranty_iso,
            "status": "active" if faults < 3 else "out_of_service",
            "photo_url": photo,
            "created_at": now_iso,
            "imported_via": SEED_TAG,
        })
        eq_created += 1
        for j in range(faults):
            offset_days = int((j + 1) * (365 / max(faults + 1, 1)))
            created = now - timedelta(days=offset_days)
            ft = FAULT_TYPES[j % len(FAULT_TYPES)]
            await db.issues.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": SITE_ID,
                "equipment_id": eq_id,
                "fault_type_mod": ft,
                "issue_description": f"{ft.title()} fault reported on {name}",
                "status": "closed" if offset_days > 30 else "open",
                "priority": "high" if j < 2 else "normal",
                "severity": "high" if j < 2 else "normal",
                "reporter_name": "Duty NCO",
                "reporter_email": "duty@army.mod.local",
                "created_at": created.isoformat(),
                "imported_via": SEED_TAG,
            })
            fa_created += 1

    print(f"Seeded {eq_created} Pulse Fitness machines + {fa_created} faults into '{site['name']}'")


if __name__ == "__main__":
    asyncio.run(main())
