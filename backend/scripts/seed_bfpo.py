"""Seed realistic MOD / BFPO Engineer Portal demo data.

Run:  cd /app/backend && python -m scripts.seed_bfpo

Idempotent — safe to re-run. Creates the dedicated BFPO org, territories
(Gibraltar, Falklands, Cyprus, Kenya), sites, equipment, engineer/lead/staff
login users and a spread of sample service cases in the shared svc_cases engine.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import db
from utils.auth import hash_password

ORG = "bfpo-mod-org"


def now():
    return datetime.now(timezone.utc).isoformat()


def iso(days=0, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


TERRITORIES = [
    {"id": "terr-gib", "name": "Gibraltar", "country": "Gibraltar", "code": "GIB", "timezone": "Europe/Gibraltar"},
    {"id": "terr-falk", "name": "Falkland Islands", "country": "Falkland Islands", "code": "FALK", "timezone": "Atlantic/Stanley"},
    {"id": "terr-cyp", "name": "Cyprus (SBA)", "country": "Cyprus", "code": "CYP", "timezone": "Asia/Nicosia"},
    {"id": "terr-ken", "name": "Kenya (BATUK)", "country": "Kenya", "code": "KEN", "timezone": "Africa/Nairobi"},
]

SITES = [
    {"id": "site-gib-1", "territory_id": "terr-gib", "name": "HMS Rooke Gymnasium",
     "country": "Gibraltar", "timezone": "Europe/Gibraltar",
     "access_instructions": "Report to main gate with MOD90. Gym is Block C, first floor.",
     "security_notes": "Photography restricted outside the gym. Escort required past reception.",
     "contact_name": "WO2 D. Marsh", "contact_phone": "+350 200 51234", "contact_email": "gib.rooke@bfpo.pulsefitness.test"},
    {"id": "site-gib-2", "territory_id": "terr-gib", "name": "Devil's Tower Camp Fitness Centre",
     "country": "Gibraltar", "timezone": "Europe/Gibraltar",
     "access_instructions": "Vehicle pass required. Loading bay at rear.",
     "security_notes": "Standard MOD site rules apply.",
     "contact_name": "Sgt A. Coombe", "contact_phone": "+350 200 55678"},
    {"id": "site-falk-1", "territory_id": "terr-falk", "name": "MPC Mount Pleasant Gymnasium",
     "country": "Falkland Islands", "timezone": "Atlantic/Stanley",
     "access_instructions": "Air-bridge only. Coordinate freight 6 weeks ahead. Gym in the East Complex.",
     "security_notes": "Restricted airfield zone — full pass vetting required.",
     "contact_name": "Fl Lt J. Okafor", "contact_phone": "+500 76123"},
    {"id": "site-cyp-1", "territory_id": "terr-cyp", "name": "Akrotiri Station Gym",
     "country": "Cyprus", "timezone": "Asia/Nicosia",
     "access_instructions": "SBA pass at Akrotiri gate. Gym next to the medical centre.",
     "security_notes": "Sovereign Base Area — do not photograph aircraft.",
     "contact_name": "Cpl M. Georgiou", "contact_phone": "+357 2500 1122"},
    {"id": "site-cyp-2", "territory_id": "terr-cyp", "name": "Dhekelia Garrison Fitness Suite",
     "country": "Cyprus", "timezone": "Asia/Nicosia",
     "access_instructions": "Garrison gate pass. Fitness suite is Building 14.",
     "security_notes": "Standard SBA rules.",
     "contact_name": "SSgt R. Patel", "contact_phone": "+357 2400 3344"},
    {"id": "site-ken-1", "territory_id": "terr-ken", "name": "BATUK Nyati Barracks Gym",
     "country": "Kenya", "timezone": "Africa/Nairobi",
     "access_instructions": "Nanyuki. Escort from BATUK HQ. 4x4 recommended in wet season.",
     "security_notes": "Local security brief mandatory. No lone working after dark.",
     "contact_name": "Capt L. Wanjiru", "contact_phone": "+254 720 445566"},
]

MODELS = [
    ("Pulse Fitness", "260G Treadmill", "treadmill"),
    ("Pulse Fitness", "280G Cross Trainer", "cross_trainer"),
    ("Pulse Fitness", "250G Upright Bike", "bike"),
    ("Concept2", "Model D Rower", "rower"),
    ("Pulse Fitness", "Fusion Multi Gym", "strength"),
]


def make_equipment():
    eqs = []
    i = 0
    for s in SITES:
        for mi, (mfr, model, etype) in enumerate(MODELS):
            if s["id"] in ("site-gib-2", "site-cyp-2") and mi > 2:
                continue
            i += 1
            eqs.append({
                "id": f"eq-{s['id']}-{mi}", "organization_id": ORG, "site_id": s["id"],
                "site_name": s["name"], "territory_id": s["territory_id"], "country": s["country"],
                "name": model, "manufacturer": mfr, "model": model, "equipment_type": etype,
                "serial_number": f"PF{s['id'][-3:].upper()}{1000+i}",
                "parts": [
                    {"name": "Drive belt", "part_number": ""},
                    {"name": "Console display", "part_number": ""},
                    {"name": "Running deck", "part_number": ""},
                ] if etype == "treadmill" else [
                    {"name": "Pedal assembly", "part_number": ""},
                    {"name": "Console display", "part_number": ""},
                ],
                "created_at": now(),
            })
    return eqs


USERS = [
    {"id": "bfpo-eng-gib", "email": "engineer.gib@bfpo.pulsefitness.test", "full_name": "Tomás Bianchi",
     "bfpo_role": "engineer", "bfpo_territory_ids": ["terr-gib"], "pw": "Bfpo123!"},
    {"id": "bfpo-eng-cyp", "email": "engineer.cyp@bfpo.pulsefitness.test", "full_name": "Elena Nikolaou",
     "bfpo_role": "engineer", "bfpo_territory_ids": ["terr-cyp"], "pw": "Bfpo123!"},
    {"id": "bfpo-lead", "email": "lead@bfpo.pulsefitness.test", "full_name": "Marcus Field",
     "bfpo_role": "lead", "bfpo_territory_ids": ["terr-gib", "terr-cyp", "terr-falk", "terr-ken"], "pw": "Bfpo123!"},
    {"id": "bfpo-staff", "email": "staff@bfpo.pulsefitness.test", "full_name": "Priya Sharma",
     "bfpo_role": "staff", "bfpo_territory_ids": [], "pw": "Bfpo123!"},
]


CASES = [
    # (site_id, eq_idx, priority, safety_critical, status, title, desc, engineer_id, extra)
    ("site-gib-1", 0, "p1", True, "new", "Treadmill belt slipping under load",
     "Belt slips badly when a user runs — reported as a trip hazard.", "", {}),
    ("site-gib-1", 2, "p3", False, "assigned", "Upright bike console blank",
     "Console does not power on.", "bfpo-eng-gib", {}),
    ("site-gib-2", 1, "p2", False, "paused_parts", "Cross trainer grinding noise",
     "Loud grinding from the flywheel — needs a bearing.", "bfpo-eng-gib",
     {"waiting_reason": "Parts required"}),
    ("site-cyp-1", 0, "p2", False, "on_site", "Treadmill incline stuck",
     "Incline motor will not raise beyond 2%.", "bfpo-eng-cyp", {}),
    ("site-cyp-1", 3, "p4", False, "new", "Rower seat roller worn",
     "Seat catches on the rail.", "", {}),
    ("site-cyp-2", 1, "p3", False, "closed", "Cross trainer pedal replaced",
     "Left pedal cracked.", "bfpo-eng-cyp", {"resolution_notes": "Fitted new pedal assembly, tested OK."}),
    ("site-falk-1", 0, "p1", True, "new", "Treadmill emergency stop faulty",
     "E-stop does not cut power reliably — safety critical.", "", {}),
    ("site-ken-1", 4, "p2", False, "new", "Multi gym cable frayed",
     "Lat pulldown cable frayed — withdrawn from use.", "", {}),
    ("site-gib-1", 1, "p3", False, "new", "Cross trainer display flickering",
     "Display intermittently blanks.", "", {}),
]


async def seed():
    # org
    await db.organizations.update_one({"id": ORG}, {"$set": {
        "id": ORG, "name": "Pulse Fitness MOD Aftersales", "account_type": "mod_org",
        "is_mod_org": True, "created_at": now(),
    }}, upsert=True)

    for t in TERRITORIES:
        await db.bfpo_territories.update_one({"id": t["id"]}, {"$set": {**t, "organization_id": ORG}}, upsert=True)

    for s in SITES:
        terr = next(t for t in TERRITORIES if t["id"] == s["territory_id"])
        await db.sites.update_one({"id": s["id"]}, {"$set": {
            **s, "organization_id": ORG, "territory_name": terr["name"], "created_at": now(),
            "ppm_frequency": "quarterly", "ppm_next_due": iso(days=-1)[:10],
        }}, upsert=True)

    eqs = make_equipment()
    for e in eqs:
        await db.equipment.update_one({"id": e["id"]}, {"$set": e}, upsert=True)

    for u in USERS:
        await db.users.update_one({"id": u["id"]}, {"$set": {
            "id": u["id"], "organization_id": ORG, "email": u["email"], "username": u["email"],
            "full_name": u["full_name"], "password": hash_password(u["pw"]),
            "role": "engineer" if u["bfpo_role"] in ("engineer", "lead") else "staff",
            "bfpo_role": u["bfpo_role"], "bfpo_territory_ids": u["bfpo_territory_ids"],
            "module_overrides": ({"mod_operations": True} if u["bfpo_role"] == "staff" else {}),
            "account_type": "mod_site", "is_mod_user": True, "is_active": True,
            "must_change_password": False, "created_at": now(),
        }}, upsert=True)
        # engineer profile mirror
        if u["bfpo_role"] in ("engineer", "lead"):
            await db.svc_engineers.update_one({"id": u["id"], "organization_id": ORG}, {"$set": {
                "id": u["id"], "organization_id": ORG, "full_name": u["full_name"],
                "email": u["email"], "active": True, "created_at": now(),
            }}, upsert=True)

    # cases — wipe & reseed the demo set for a clean state
    await db.svc_cases.delete_many({"organization_id": ORG})
    await db.svc_case_events.delete_many({"organization_id": ORG})
    await db.svc_counters.delete_many({"organization_id": ORG})
    await db.bfpo_parts_requests.delete_many({"organization_id": ORG})
    await db.bfpo_ppm_services.delete_many({"organization_id": ORG})
    await db.bfpo_ppm_inspections.delete_many({"organization_id": ORG})
    await db.bfpo_ppm_counter.delete_many({"organization_id": ORG})
    await db.bfpo_visiting_access.delete_many({"organization_id": ORG})
    seq = 0
    eq_by_site: dict = {}
    for e in eqs:
        eq_by_site.setdefault(e["site_id"], []).append(e)
    for (site_id, eq_idx, priority, safety, status, title, desc, eng_id, extra) in CASES:
        seq += 1
        site = next(s for s in SITES if s["id"] == site_id)
        terr = next(t for t in TERRITORIES if t["id"] == site["territory_id"])
        site_eqs = eq_by_site.get(site_id, [])
        eq = site_eqs[eq_idx] if eq_idx < len(site_eqs) else (site_eqs[0] if site_eqs else None)
        eng = next((u for u in USERS if u["id"] == eng_id), None)
        # overdue for the two p1s that are still new
        resolve = iso(days=-1) if (priority == "p1" and status == "new") else iso(days=2)
        cid = str(uuid.uuid4())
        case = {
            "id": cid, "organization_id": ORG, "bfpo": True,
            "reference": f"SVC-{seq:05d}", "status": status, "priority": priority,
            "case_type": "repair", "cover_type": "contract", "title": title, "description": desc,
            "safety_critical": safety, "fault_code": "",
            "territory_id": terr["id"], "territory_name": terr["name"], "country": terr["country"],
            "site_id": site_id, "site_name": site["name"], "site_timezone": site["timezone"],
            "customer_name": "Ministry of Defence",
            "asset_id": eq["id"] if eq else "", "asset_name": (eq["model"] if eq else ""),
            "equipment_ids": [eq["id"]] if eq else [],
            "assigned_engineer_id": eng_id, "assigned_engineer_name": (eng["full_name"] if eng else ""),
            "scheduled_at": None, "return_visit": False, "waiting_reason": extra.get("waiting_reason", ""),
            "resolution_notes": extra.get("resolution_notes", ""),
            "sla_response_at": iso(hours=4), "sla_resolve_at": resolve, "sla_paused_at": None,
            "closed_at": iso(days=-2) if status == "closed" else None,
            "source": "modservice", "created_at": iso(days=-3), "updated_at": now(),
        }
        await db.svc_cases.insert_one(case)
        await db.svc_case_events.insert_one({
            "id": str(uuid.uuid4()), "case_id": cid, "organization_id": ORG, "type": "intake",
            "body": "Case logged via MOD service portal", "actor_name": "MOD Service Desk",
            "extra": {"source": "modservice"}, "at": iso(days=-3),
        })
    # counter so new refs continue
    await db.svc_counters.update_one(
        {"organization_id": ORG, "key": "case_seq"},
        {"$set": {"value": seq, "created_at": now()}}, upsert=True)

    print(f"Seeded: {len(TERRITORIES)} territories, {len(SITES)} sites, {len(eqs)} equipment, "
          f"{len(USERS)} users, {len(CASES)} cases.")

    # PPM checklist templates (idempotent per category)
    from routes.bfpo_ppm import DEFAULT_TEMPLATES, _items
    for category, labels in DEFAULT_TEMPLATES.items():
        existing = await db.bfpo_ppm_templates.find_one({"organization_id": ORG, "category": category}, {"_id": 0})
        if existing:
            continue
        await db.bfpo_ppm_templates.insert_one({
            "id": str(uuid.uuid4()), "organization_id": ORG, "category": category,
            "name": category.replace("_", " ").title() + " service", "items": _items(labels),
            "updated_at": now(), "updated_by": "seed",
        })
    print(f"Seeded PPM templates: {len(DEFAULT_TEMPLATES)} categories.")


if __name__ == "__main__":
    asyncio.run(seed())
