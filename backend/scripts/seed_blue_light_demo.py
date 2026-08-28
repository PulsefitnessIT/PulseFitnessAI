"""Seed a realistic Blue Light / Multi-Site PTE Service demo contract for
acceptance testing (§65). Creates one Fire & Rescue customer + ~82 stations +
mixed assets (incl. treadmills) under the CRM org of a chosen operator user.

Idempotent: re-running clears the prior demo contract's stations/assets and
rebuilds them. Safe for PREVIEW only. Run:

    cd /app/backend && python -m scripts.seed_blue_light_demo
"""
import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import db  # noqa: E402

SEED_TAG = "blue_light_demo_v1"
OWNER_EMAIL = os.environ.get("SEED_OWNER_EMAIL", "owner@isodemo.com")
NUM_STATIONS = 82

random.seed(42)

STATION_TOWNS = [
    "Exeter Central", "Exeter Middlemoor", "Exmouth", "Topsham", "Crediton", "Tiverton",
    "Cullompton", "Honiton", "Axminster", "Sidmouth", "Ottery St Mary", "Budleigh Salterton",
    "Dawlish", "Teignmouth", "Newton Abbot", "Ashburton", "Buckfastleigh", "Totnes",
    "Dartmouth", "Brixham", "Paignton", "Torquay", "Ivybridge", "Modbury", "Kingsbridge",
    "Salcombe", "Plymstock", "Plympton", "Crownhill", "Camels Head", "Greenbank", "Yelverton",
    "Tavistock", "Princetown", "Okehampton", "Hatherleigh", "Holsworthy", "Bude", "Bideford",
    "Appledore", "Barnstaple", "Braunton", "Ilfracombe", "Combe Martin", "Lynton", "South Molton",
    "Chulmleigh", "Witheridge", "Bampton", "Colyton", "Seaton", "Beer", "Chard", "Ilminster",
    "Taunton", "Wellington", "Wiveliscombe", "Williton", "Minehead", "Dulverton", "Wellington East",
    "Bridgwater", "Nether Stowey", "Burnham-on-Sea", "Cheddar", "Wells", "Glastonbury", "Street",
    "Somerton", "Langport", "Martock", "Yeovil", "Chard South", "Crewkerne", "Castle Cary",
    "Shepton Mallet", "Frome", "Wincanton", "Templecombe", "Bruton", "Highbridge", "Nailsea",
]

FIRST_NAMES = ["Watch Manager Sarah", "Crew Manager Dave", "Station Officer Mark", "Watch Manager Priya",
               "Crew Manager Tom", "Station Officer Emma", "Watch Manager Raj", "Crew Manager Lucy"]
SURNAMES = ["Hancock", "Reeves", "Patel", "O'Brien", "Nguyen", "Clarke", "Ahmed", "Foster",
            "Whitmore", "Osei", "Lindqvist", "Bianchi"]

# (equipment_type, manufacturer, model_prefix, is_treadmill)
ASSET_TYPES = [
    ("Treadmill", "Pulse Fitness", "Series 3 Treadmill", True),
    ("Treadmill", "Technogym", "Run 1000", True),
    ("Upright Bike", "Pulse Fitness", "Series 3 Bike", False),
    ("Cross Trainer", "Pulse Fitness", "Series 3 Cross Trainer", False),
    ("Rower", "Concept2", "Model D", False),
    ("Indoor Cycle", "Keiser", "M3i", False),
    ("Multi Gym", "Pulse Fitness", "Fusion Multi Station", False),
    ("Functional Rig", "Pulse Fitness", "HD Rig", False),
    ("Dumbbell Set", "Pulse Fitness", "Urethane Set", False),
]


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _find_org_id():
    for coll in ("crm_users", "users"):
        u = await db[coll].find_one({"email": OWNER_EMAIL})
        if u and u.get("organization_id"):
            return u["organization_id"]
    # fallback: org with most CRM companies
    agg = await db.crm2_companies.aggregate([
        {"$group": {"_id": "$organization_id", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 1},
    ]).to_list(1)
    if agg:
        return agg[0]["_id"]
    raise SystemExit("Could not resolve an organization_id to seed under.")


async def main():
    org_id = await _find_org_id()
    print(f"Seeding under organization_id={org_id}")

    # 1) Customer company
    company = await db.crm2_companies.find_one({"organization_id": org_id, "seed_tag": SEED_TAG})
    if not company:
        company = {
            "id": str(uuid.uuid4()), "organization_id": org_id,
            "name": "Example Fire & Rescue Service",
            "industry": "Fire & Rescue Service", "customer_type": "fire_rescue",
            "seed_tag": SEED_TAG, "created_at": _now(), "updated_at": _now(),
        }
        await db.crm2_companies.insert_one(company)
        print("Created company Example Fire & Rescue Service")
    company_id = company["id"]

    # 2) Contract (rebuild stations/assets on re-run)
    start = datetime.now(timezone.utc).strftime("%Y-01-01")
    end = datetime.now(timezone.utc).strftime("%Y-12-31")
    contract = await db.crm2_contracts.find_one({"organization_id": org_id, "seed_tag": SEED_TAG})
    blue_light = {
        "customer_type": "fire_rescue", "service_frequency_months": 6,
        "calibration_required": True, "speed_points_mph": [3, 6, 9, 12],
        "incline_points_pct": [0, 5, 10, 15], "tolerance_pct": 5.0,
        "incline_zero_abs_tolerance": 0.5, "review_pct": None,
        "asset_audit_required": True, "certificate_approval_mode": "office_review",
        "certificate_template_id": None, "customer_logo_url": None,
        "certificate_recipients": ["fleet.fitness@example-frs.gov.uk"],
        "mandatory_check_sheets": [], "engineer_skills_required": [],
    }
    if not contract:
        contract = {
            "id": str(uuid.uuid4()), "organization_id": org_id,
            "contract_number": "CTR-BLFRS1",
            "title": "2026 Annual Service Programme — Example Fire & Rescue",
            "type": "service", "tier": "gold", "status": "active",
            "contract_type": "blue_light_multisite", "is_blue_light": True,
            "customer_type": "fire_rescue", "blue_light": blue_light,
            "company_id": company_id, "company_name": company["name"],
            "start_date": start, "end_date": end,
            "billing_frequency": "annual", "annual_value": 165000.0, "total_value": 165000.0,
            "seed_tag": SEED_TAG, "created_at": _now(), "updated_at": _now(),
        }
        await db.crm2_contracts.insert_one(contract)
        print(f"Created contract {contract['contract_number']}")
    else:
        await db.crm2_contracts.update_one(
            {"id": contract["id"]},
            {"$set": {"contract_type": "blue_light_multisite", "is_blue_light": True,
                      "customer_type": "fire_rescue", "blue_light": blue_light,
                      "status": "active", "updated_at": _now()}})
    contract_id = contract["id"]

    # wipe prior demo stations/assets
    await db.crm2_contract_sites.delete_many({"contract_id": contract_id})
    await db.crm2_contract_assets.delete_many({"contract_id": contract_id})

    today = datetime.now(timezone.utc)
    stations, assets = [], []
    for i in range(NUM_STATIONS):
        town = STATION_TOWNS[i % len(STATION_TOWNS)]
        name = f"{town} Fire Station"
        sid = str(uuid.uuid4())
        # spread service state across the estate for a realistic dashboard
        bucket = i % 5
        next_due = (today + timedelta(days=random.randint(10, 150))).strftime("%Y-%m-%d")
        scheduled = ""
        vstatus = "not_planned"
        last_service = ""
        if bucket == 0:  # overdue
            next_due = (today - timedelta(days=random.randint(5, 40))).strftime("%Y-%m-%d")
            vstatus = "overdue"
        elif bucket == 1:  # scheduled
            scheduled = (today + timedelta(days=random.randint(2, 30))).strftime("%Y-%m-%d")
            vstatus = "scheduled"
        elif bucket == 2:  # awaiting booking
            vstatus = "not_planned"
        # buckets 3,4 left as planned/not_planned baseline
        stations.append({
            "id": sid, "contract_id": contract_id, "organization_id": org_id,
            "site_name": name,
            "address": f"{random.randint(1, 120)} Station Road",
            "city": town, "postcode": f"EX{random.randint(1, 39)} {random.randint(1, 9)}{random.choice('ABDEFGH')}{random.choice('ABDEFGH')}",
            "contact_name": f"{random.choice(FIRST_NAMES)} {random.choice(SURNAMES)}",
            "telephone": f"01392 {random.randint(200000, 999999)}",
            "email": f"{town.lower().replace(' ', '.').replace(chr(39), '')}@example-frs.gov.uk",
            "access_instructions": "Appliance bay side door — ring bell for watch room.",
            "parking_info": "Visitor bay to rear of drill yard.",
            "opening_times": "24/7 — crewed station",
            "next_service_due": next_due, "scheduled_date": scheduled,
            "visit_status": vstatus, "last_service": last_service,
            "follow_up_required": bucket == 0 and random.random() < 0.4,
            "seed_tag": SEED_TAG, "created_at": _now(),
        })
        # 3–8 assets per station, guarantee 1–3 treadmills at most stations
        n_assets = random.randint(3, 8)
        n_tm = 0 if (i % 11 == 0) else random.randint(1, 3)  # some zero-treadmill stations (§27)
        picks = []
        for _ in range(n_tm):
            picks.append(random.choice([a for a in ASSET_TYPES if a[3]]))
        while len(picks) < n_assets:
            picks.append(random.choice([a for a in ASSET_TYPES if not a[3]]))
        for j, (etype, manu, model, _tm) in enumerate(picks):
            serial = f"PF-{town[:3].upper()}-{i:02d}{j:02d}"
            assets.append({
                "id": str(uuid.uuid4()), "contract_id": contract_id, "organization_id": org_id,
                "site_id": sid, "asset_id": "",
                "asset_name": f"{manu} {model}", "equipment_type": etype,
                "model_code": model, "serial_number": serial,
                "warranty_end": (today + timedelta(days=random.randint(-200, 700))).strftime("%Y-%m-%d"),
                "coverage_type": "full", "seed_tag": SEED_TAG, "created_at": _now(),
            })

    await db.crm2_contract_sites.insert_many(stations)
    await db.crm2_contract_assets.insert_many(assets)
    tms = sum(1 for a in assets if a["equipment_type"] == "Treadmill")
    print(f"Seeded {len(stations)} stations, {len(assets)} assets ({tms} treadmills).")
    print(f"Contract id: {contract_id}")


if __name__ == "__main__":
    asyncio.run(main())
