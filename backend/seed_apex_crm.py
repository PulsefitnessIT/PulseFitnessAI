"""Apex CRM seed — CRM v2 collections (crm2_*). Pulse-free pipeline board."""
import os
import uuid
import random
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

ORG_ID = "apex-demo-org"
OWNER_ID = "8381dc4d-f299-4dc2-8539-cce33e8a9fd4"  # apex crm_user
OWNER_NAME = "Sarah Mitchell"


def main():
    random.seed(11)
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    def iso(d=None):
        return (d or now).isoformat()

    for col in ("crm2_opportunities", "crm2_companies", "crm2_contacts"):
        db[col].delete_many({"organization_id": ORG_ID, "demo_seed_apex": True})

    # (title, company, contact, stage, value, prob, sites)
    DEALS = [
        ("Northgate Leisure Trust — 12-site rollout", "Northgate Leisure Trust", "David Okafor", "negotiation", 84000, 75, 12),
        ("Summit Health Clubs — equipment fit-out", "Summit Health Clubs", "Rachel Lyne", "proposal", 56000, 60, 5),
        ("Velocity Gyms — service contract", "Velocity Gyms", "Marcus Bell", "qualified", 42000, 15, 7),
        ("Harbour Fitness — annual PPM", "Harbour Fitness", "Aisha Rahman", "closed_won", 28500, 100, 3),
        ("Ironworks Strength Co. — new site", "Ironworks Strength Co.", "Tom Hartley", "lead", 15000, 5, 1),
        ("Riverside Council — leisure tender", "Riverside Borough Council", "Helen Pryce", "proposal", 120000, 60, 9),
        ("PeakForm Studios — multi-site", "PeakForm Studios", "Sofia Marin", "discovery", 19500, 25, 4),
        ("Anvil CrossFit — kit upgrade", "Anvil CrossFit", "Jake Donnelly", "lead", 9800, 5, 2),
        ("Meridian Wellness Group — managed service", "Meridian Wellness Group", "Priya Shah", "negotiation", 67000, 75, 8),
        ("Coastline Fitness — cardio refresh", "Coastline Fitness", "Ben Carter", "closed_won", 33000, 100, 4),
        ("Urban Reps 24/7 — franchise pack", "Urban Reps", "Lola Adeyemi", "qualified", 22000, 15, 6),
        ("Foundry Performance Centre", "Foundry Performance", "Niall Quinn", "discovery", 12500, 25, 1),
        ("Apex Trade Show — inbound bundle", "Cobalt Leisure", "Erin Walsh", "solution", 47500, 40, 5),
    ]
    cities = ["Manchester", "Leeds", "Bristol", "Birmingham", "Glasgow", "Sheffield", "Liverpool", "Nottingham"]
    for i, (title, company, contact, stage, value, prob, sites) in enumerate(DEALS):
        coid = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        fn, ln = contact.split(" ", 1)
        slug = company.split()[0].lower()
        db.crm2_companies.insert_one({
            "id": coid, "organization_id": ORG_ID, "name": company,
            "website": f"{slug}.co.uk", "phone": "", "email": f"hello@{slug}.co.uk",
            "country": "United Kingdom", "city": random.choice(cities),
            "type": "customer" if stage == "closed_won" else "prospect",
            "status": "active", "sector": "Fitness & Leisure", "tags": [],
            "source": "seed", "created_at": iso(), "updated_at": iso(), "demo_seed_apex": True,
        })
        db.crm2_contacts.insert_one({
            "id": cid, "organization_id": ORG_ID, "first_name": fn, "last_name": ln,
            "email": f"{fn.lower()}@{slug}.co.uk", "phone": "",
            "lifecycle": "Customer" if stage == "closed_won" else "Lead",
            "company_id": coid, "company_name": company, "title": "Operations Director",
            "tags": [], "source": "outbound", "custom_fields": {"job_title": "Operations Director"},
            "communication_preferences": {}, "created_at": iso(), "updated_at": iso(),
            "demo_seed_apex": True,
        })
        created = now - timedelta(days=random.randint(2, 45))
        db.crm2_opportunities.insert_one({
            "id": str(uuid.uuid4()), "organization_id": ORG_ID, "title": title,
            "stage": stage, "value": float(value), "probability": prob,
            "weighted_value": round(value * prob / 100.0, 2),
            "company_id": coid, "company_name": company,
            "contact_id": cid, "contact_name": contact,
            "owner_id": OWNER_ID, "owner_name": OWNER_NAME,
            "source": "outbound",
            "close_date": (now + timedelta(days=random.randint(10, 90))).date().isoformat(),
            "next_step": random.choice(["Send proposal", "Book site survey", "Follow-up call",
                                        "Pricing review", "Contract sign-off"]),
            "stage_history": [{"stage": stage, "entered_at": iso(created)}],
            "created_at": iso(created), "updated_at": iso(), "demo_seed_apex": True,
        })

    print("Apex CRM v2 seed:")
    print("  opportunities:", db.crm2_opportunities.count_documents({"organization_id": ORG_ID}))
    print("  companies:", db.crm2_companies.count_documents({"organization_id": ORG_ID}))
    print("  contacts:", db.crm2_contacts.count_documents({"organization_id": ORG_ID}))


if __name__ == "__main__":
    main()
