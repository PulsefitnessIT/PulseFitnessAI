"""Iter 279 — seed a Pulse Pro operator account so the Lite dashboard /
Lite Documents tab (with the new document-type picker) can be exercised."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import hash_password  # noqa: E402

# ── Production safety guard (utils/seed_guard.py) — never seed a prod DB ──
from utils.seed_guard import assert_seeding_allowed  # noqa: E402
assert_seeding_allowed(__file__)

EMAIL = "lite.docs@pulsedemo.test"
PASSWORD = "LiteDocs123!"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()

    org = await db.organizations.find_one({"name": "Lite Docs Demo Gym"}, {"_id": 0, "id": 1})
    if org:
        org_id = org["id"]
    else:
        org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": org_id, "name": "Lite Docs Demo Gym", "account_type": "pulse_pro",
            "portal_type": "both", "subscription_tier": "pro",
            "modules": {
                "operations": {"enabled": True, "tier": "pro"},
                "crm": {"enabled": True, "tier": "pro"},
            },
            "enabled_modules": ["operations", "crm"],
            "created_at": now,
        })

    await db.users.update_one(
        {"email": EMAIL},
        {"$set": {
            "id": str(uuid.uuid4()) if not await db.users.find_one({"email": EMAIL}) else (await db.users.find_one({"email": EMAIL}))["id"],
            "email": EMAIL, "full_name": "Lite Docs Owner",
            "password": hash_password(PASSWORD), "organization_id": org_id,
            "role": "owner", "account_type": "pulse_pro", "created_at": now,
        }},
        upsert=True,
    )
    print(f"seeded {EMAIL} / {PASSWORD} (org {org_id}, account_type pulse_pro)")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
