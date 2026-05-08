"""Iter 215c — Backfill: bundle Leisure CRM with Memberships.

For every org with `modules.memberships.enabled = true`, ensure
`modules.crm.enabled = true` so the operator can access the leisure
CRM straight away. Idempotent.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    fixed = 0
    examined = 0
    async for org in db.organizations.find({}, {"_id": 0, "id": 1, "modules": 1, "name": 1}):
        examined += 1
        modules = dict(org.get("modules") or {})
        memberships = modules.get("memberships") or {}
        crm = dict(modules.get("crm") or {})
        if memberships.get("enabled") and not crm.get("enabled"):
            crm["enabled"] = True
            crm.setdefault("tier", memberships.get("tier", "pro"))
            modules["crm"] = crm
            await db.organizations.update_one({"id": org["id"]}, {"$set": {"modules": modules}})
            fixed += 1
            print(f"  bundled CRM with memberships for {org.get('name')} ({org['id']})")
    print(f"Done. Examined {examined} orgs, bundled CRM on {fixed}.")


if __name__ == "__main__":
    asyncio.run(main())
