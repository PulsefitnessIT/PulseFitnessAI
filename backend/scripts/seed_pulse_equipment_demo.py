"""Seed a Pulse Fitness equipment estate for the iso-demo-org (deck screenshots).
Idempotent: clears prior deck-demo docs first. Run: python scripts/seed_pulse_equipment_demo.py
"""
import os, sys, uuid
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = "iso-demo-org"
SITE = "iso-demo-site-a"
now = datetime.now(timezone.utc)

def iso(y, m=6, d=1):
    return datetime(y, m, d, tzinfo=timezone.utc).isoformat()

# wipe previous demo equipment + issues for a clean estate
db.equipment.delete_many({"organization_id": ORG})
db.issues.delete_many({"organization_id": ORG})

P = "Pulse Fitness"
CARDIO, STR, FUNC, STUDIO = "Cardio Zone", "Strength Floor", "Functional Zone", "Studio 1"
IMG = "/pulse-photos/"

# (name, type, model, serial, location, purchase_year, cost, life, warranty_year, photo)
ITEMS = [
    ("Pulse 260G Treadmill",        "Treadmill",     "260G",  "PF-TM-260-01", CARDIO, 2020, 4200, 10, 2027, "gym-treadmill-row.webp"),
    ("Pulse 260G Treadmill",        "Treadmill",     "260G",  "PF-TM-260-02", CARDIO, 2016, 4200, 10, 2025, "gym-treadmill-row.webp"),
    ("Pulse 220G Cross Trainer",    "Cross Trainer", "220G",  "PF-XT-220-01", CARDIO, 2021, 3600, 10, 2028, "product-crosstrainer.webp"),
    ("Pulse 220G Cross Trainer",    "Cross Trainer", "220G",  "PF-XT-220-02", CARDIO, 2021, 3600, 10, 2028, "product-crosstrainer.webp"),
    ("Pulse 230G Upright Bike",     "Exercise Bike", "230G",  "PF-UB-230-01", CARDIO, 2021, 2400, 10, 2028, "product-bike.webp"),
    ("Pulse 240G Recumbent Bike",   "Exercise Bike", "240G",  "PF-RB-240-01", CARDIO, 2021, 2600, 10, 2028, "product-bike.webp"),
    ("Pulse 250G StepMill",         "Stepper",       "250G",  "PF-SM-250-01", CARDIO, 2019, 5200, 10, 2026, "product-stepmill.webp"),
    ("Pulse H2X Rower",             "Rower",         "H2X",   "PF-RW-H2X-01", FUNC,   2022, 1900,  8, 2028, "gym-cardio-angle.webp"),
    ("Pulse Fusion Cable Machine",  "Strength",      "Fusion","PF-ST-CAB-01", STR,    2020, 4800, 12, 2027, "product-cable-machine.webp"),
    ("Pulse Uprise Leg Press",      "Strength",      "Uprise","PF-ST-LP-01",  STR,    2020, 3900, 12, 2027, "strength-floor.webp"),
    ("Pulse Fusion Lat Pulldown",   "Strength",      "Fusion","PF-ST-LAT-01", STR,    2021, 3100, 12, 2028, "product-cable-machine.webp"),
    ("Pulse Group Cycle Bike",      "Group Cycle",   "GC",    "PF-GC-01",     STUDIO, 2021, 1500,  8, 2027, "product-bike.webp"),
]

eq_ids = {}
docs = []
for (name, typ, model, sn, loc, py, cost, life, wy, photo) in ITEMS:
    eid = str(uuid.uuid4())
    eq_ids[sn] = eid
    docs.append({
        "id": eid, "organization_id": ORG, "site_id": SITE,
        "name": name, "equipment_type": typ, "manufacturer": P, "model": model,
        "serial_number": sn, "location": loc,
        "purchase_date": iso(py, 3, 12), "purchase_cost": cost, "replacement_cost": int(cost * 1.08),
        "expected_lifespan_years": life,
        "warranty_expiry": iso(wy, 3, 12),
        "photo_url": IMG + photo,
        "status": "operational",
        "created_at": now.isoformat(), "_pulse_deck_demo": True,
    })
db.equipment.insert_many(docs)

# faults — mix of open / in-progress / resolved with realistic descriptions
FAULTS = [
    ("PF-TM-260-02", "high",   "Running belt slipping under load — machine taken out of service", "open", None),
    ("PF-SM-250-01", "medium", "Step chain noisy and intermittent — needs inspection",            "open", None),
    ("PF-ST-CAB-01", "medium", "Cable fraying on high pulley — flagged for replacement",           "in_progress", None),
    ("PF-XT-220-02", "low",    "Console display flickering intermittently",                        "open", None),
    ("PF-TM-260-01", "low",    "Handrail heart-rate sensor not reading",                           "resolved", 8),
    ("PF-UB-230-01", "medium", "Pedal strap worn — replaced",                                      "resolved", 20),
    ("PF-RW-H2X-01", "low",    "Seat roller squeaking — lubricated",                               "resolved", 30),
    ("PF-TM-260-02", "high",   "Motor overheating warning during peak hours",                      "open", None),
]
fdocs = []
for i, (sn, sev, desc, status, days_ago_res) in enumerate(FAULTS):
    created = now - timedelta(days=(2 + i * 3))
    d = {
        "id": str(uuid.uuid4()), "organization_id": ORG, "site_id": SITE,
        "equipment_id": eq_ids[sn], "serial_number": sn,
        "severity": sev, "issue_description": desc, "status": status,
        "created_at": created.isoformat(), "_pulse_deck_demo": True,
    }
    if days_ago_res:
        d["resolved_at"] = (created + timedelta(hours=days_ago_res)).isoformat()
    fdocs.append(d)
db.issues.insert_many(fdocs)

# CAPEX flag on the aged treadmill so the replacement report has evidence
db.equipment.update_one({"serial_number": "PF-TM-260-02", "organization_id": ORG},
                        {"$set": {"_capex_demo": True}})

print(f"Seeded {len(docs)} Pulse Fitness equipment + {len(fdocs)} faults for {ORG}/{SITE}")
