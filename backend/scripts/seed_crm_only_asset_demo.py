"""Seed a CRM-only asset for the "Promote to register" action demo/regression.

Creates (idempotent):
  - links crm2_company `iso-cA` (AlphaCo) to org `iso-demo-org` so the
    equipment register can be resolved by `_resolve_linked_org`.
  - a CRM-only crm2_asset under that company (no equipment_id).

Run from /app/backend:  python scripts/seed_crm_only_asset_demo.py
"""
import asyncio
import os
import re

_env = open(os.path.join(os.path.dirname(__file__), "..", ".env")).read()
os.environ.setdefault("MONGO_URL", _env.split("MONGO_URL=")[1].split("\n")[0].strip().strip('"'))
_DB_NAME = re.search(r'DB_NAME="?([^"\n]+)', _env).group(1)

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

ORG_ID = "iso-demo-org"
COMPANY_ID = "iso-cA"
ASSET_ID = "iso-crmonly-asset-1"


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[_DB_NAME]
    now = datetime.now(timezone.utc).isoformat()

    await db.crm2_companies.update_one(
        {"id": COMPANY_ID, "organization_id": ORG_ID},
        {"$set": {"linked_organization_id": ORG_ID, "updated_at": now}},
    )

    await db.crm2_assets.update_one(
        {"id": ASSET_ID},
        {"$set": {
            "id": ASSET_ID,
            "organization_id": ORG_ID,
            "company_id": COMPANY_ID,
            "name": "Matrix Ascent Trainer (CRM-only)",
            "serial_number": "CRMONLY-QA-001",
            "status": "active",
            "source": "crm",
            "equipment_id": None,
            "site_id": "iso-demo-site-a",
            "install_date": "2025-01-15",
            "warranty_expiry": "2028-01-15",
            "updated_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    co = await db.crm2_companies.find_one({"id": COMPANY_ID}, {"_id": 0, "name": 1, "linked_organization_id": 1})
    asset = await db.crm2_assets.find_one({"id": ASSET_ID}, {"_id": 0, "name": 1, "equipment_id": 1, "source": 1})
    print("Company linked:", co)
    print("CRM-only asset:", asset)


if __name__ == "__main__":
    asyncio.run(main())
