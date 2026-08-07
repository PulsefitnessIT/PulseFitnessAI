"""Seed a two-site multi-site isolation test scenario.

Creates (idempotently): an operator org with Memberships/CRM/Marketing
enabled, two sites (A=Head Office, B), an owner, a manager restricted to
site A, and MARKER data under BOTH sites across all three modules so the
no-leak assertion is meaningful (an empty disallowed site is a false pass).

Run:  python -m scripts.seed_site_isolation_demo
"""
import asyncio
from datetime import datetime, timezone

from utils.auth import hash_password
from utils.database import db

# ── Production safety guard (utils/seed_guard.py) — never seed a prod DB ──
from utils.seed_guard import assert_seeding_allowed  # noqa: E402
assert_seeding_allowed(__file__)

ORG_ID = "iso-demo-org"
SITE_A = "iso-demo-site-a"   # Head Office (manager allowed)
SITE_B = "iso-demo-site-b"   # manager NOT allowed
OWNER_EMAIL = "owner@isodemo.com"
MANAGER_EMAIL = "manager@isodemo.com"
PASSWORD = "IsoDemo123!"


def _now():
    return datetime.now(timezone.utc).isoformat()


async def main():
    # ── Org with all three isolated modules enabled ──
    await db.organizations.update_one(
        {"id": ORG_ID},
        {"$set": {
            "id": ORG_ID, "name": "Iso Demo Fitness", "account_type": "full",
            "address": "1 Demo Street", "created_at": _now(),
            "modules": {
                "memberships": {"enabled": True},
                "crm": {"enabled": True, "business_enabled": True},
                "marketing": {"enabled": True},
                "operations": {"enabled": True},
            },
        }},
        upsert=True,
    )

    # ── Sites ──
    await db.sites.update_one({"id": SITE_A}, {"$set": {
        "id": SITE_A, "organization_id": ORG_ID, "name": "Demo Head Office",
        "is_head_office": True, "created_at": "2026-01-01T00:00:00+00:00",
    }}, upsert=True)
    await db.sites.update_one({"id": SITE_B}, {"$set": {
        "id": SITE_B, "organization_id": ORG_ID, "name": "Demo Branch B",
        "is_head_office": False, "created_at": "2026-01-02T00:00:00+00:00",
    }}, upsert=True)

    # ── Users (owner = unrestricted, manager = restricted to site A) ──
    pw = hash_password(PASSWORD)
    await db.users.update_one({"email": OWNER_EMAIL}, {"$set": {
        "id": "iso-owner", "email": OWNER_EMAIL, "password": pw,
        "full_name": "Demo Owner", "role": "owner", "organization_id": ORG_ID,
        "account_type": "full", "allowed_site_ids": [], "created_at": _now(),
    }}, upsert=True)
    await db.users.update_one({"email": MANAGER_EMAIL}, {"$set": {
        "id": "iso-manager", "email": MANAGER_EMAIL, "password": pw,
        "full_name": "Demo Manager A", "role": "manager", "organization_id": ORG_ID,
        "account_type": "full", "allowed_site_ids": [SITE_A], "created_at": _now(),
    }}, upsert=True)

    # ── Marker data under BOTH sites (so no-leak is provable) ──
    async def reseed(coll, docs):
        await db[coll].delete_many({"organization_id": ORG_ID})
        if docs:
            await db[coll].insert_many(docs)

    base = {"organization_id": ORG_ID, "created_at": _now()}
    await reseed("members", [
        {**base, "id": "iso-mA", "site_id": SITE_A, "email": "ma@x.com", "first_name": "AlphaMember", "last_name": "A", "status": "active"},
        {**base, "id": "iso-mB", "site_id": SITE_B, "email": "mb@x.com", "first_name": "BravoMember", "last_name": "B", "status": "active"},
    ])
    await reseed("crm2_companies", [
        {**base, "id": "iso-cA", "site_id": SITE_A, "name": "AlphaCo (Site A)", "type": "customer", "owner_id": "iso-manager"},
        {**base, "id": "iso-cB", "site_id": SITE_B, "name": "BravoCo (Site B)", "type": "customer", "owner_id": "iso-owner"},
    ])
    await reseed("crm2_opportunities", [
        {**base, "id": "iso-oA", "site_id": SITE_A, "title": "AlphaDeal (Site A)", "stage": "qualified", "value": 1000, "owner_id": "iso-manager"},
        {**base, "id": "iso-oB", "site_id": SITE_B, "title": "BravoDeal (Site B)", "stage": "qualified", "value": 2000, "owner_id": "iso-owner"},
    ])
    await reseed("marketing_campaigns", [
        {**base, "id": "iso-caA", "site_id": SITE_A, "name": "AlphaCampaign (Site A)", "status": "sent", "sent_at": _now(), "metrics": {"sent": 5, "opened": 2}},
        {**base, "id": "iso-caB", "site_id": SITE_B, "name": "BravoCampaign (Site B)", "status": "sent", "sent_at": _now(), "metrics": {"sent": 9, "opened": 4}},
    ])

    print("Seeded iso-demo scenario.")
    print(f"  Org: {ORG_ID} (memberships/crm/marketing enabled)")
    print(f"  Sites: {SITE_A} (HQ), {SITE_B}")
    print(f"  Owner   : {OWNER_EMAIL} / {PASSWORD}  (sees both sites)")
    print(f"  Manager : {MANAGER_EMAIL} / {PASSWORD} (restricted to {SITE_A})")


if __name__ == "__main__":
    asyncio.run(main())
