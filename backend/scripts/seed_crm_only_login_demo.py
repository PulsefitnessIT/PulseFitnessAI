"""Iter 279 — seed a PERSISTENT crm_users-only account (as Master Admin
creates in a CRM-capable org). Used to regression-test the standard-login
cross-collection fallback fix. Idempotent."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from routes.crm_auth import crm_hash_password  # noqa: E402

# ── Production safety guard (utils/seed_guard.py) — never seed a prod DB ──
from utils.seed_guard import assert_seeding_allowed  # noqa: E402
assert_seeding_allowed(__file__)

EMAIL = "crmonly.manager@pulsedemo.test"
PASSWORD = "CrmOnly123!"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()

    org = await db.organizations.find_one({"name": "CRM Only Demo Org"}, {"_id": 0, "id": 1})
    org_id = org["id"] if org else str(uuid.uuid4())
    if not org:
        await db.organizations.insert_one({
            "id": org_id, "name": "CRM Only Demo Org", "account_type": "pulse_pro",
            "portal_type": "crm", "modules": {"crm": {"enabled": True, "tier": "pro"}},
            "enabled_modules": ["crm"], "created_at": now,
        })

    existing = await db.crm_users.find_one({"email": EMAIL}, {"_id": 0, "id": 1})
    uid = existing["id"] if existing else str(uuid.uuid4())
    # Ensure ONLY a crm_users row exists (delete any mirrored users row so the
    # fallback path is exercised fresh each run).
    await db.users.delete_many({"email": EMAIL})
    await db.crm_users.update_one(
        {"email": EMAIL},
        {"$set": {
            "id": uid, "email": EMAIL, "full_name": "CRM Only Manager",
            "password": crm_hash_password(PASSWORD), "organization_id": org_id,
            "role": "manager", "created_at": now,
        }},
        upsert=True,
    )
    print(f"seeded crm_users-ONLY {EMAIL} / {PASSWORD} (org {org_id}); users row removed")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
