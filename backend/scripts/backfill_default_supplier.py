"""One-time backfill — ensure every organisation has the locked Pulse Fitness
Ltd default supplier. Idempotent; safe to re-run.

Run:  cd /app/backend && PYTHONPATH=/app/backend python scripts/backfill_default_supplier.py
"""
import asyncio

from utils.database import db
from utils.default_supplier import ensure_default_supplier, MOD_SERVICE_EMAIL, COMMERCIAL_SERVICE_EMAIL


async def main():
    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1, "account_type": 1, "is_mod": 1}).to_list(None)
    created = repaired = 0
    mod_ct = com_ct = 0
    for org in orgs:
        oid = org.get("id")
        if not oid:
            continue
        before = await db.suppliers.find_one({"organization_id": oid, "is_default_pulse": True}, {"_id": 0, "id": 1})
        doc = await ensure_default_supplier(oid, org)
        if not doc:
            continue
        if before:
            repaired += 1
        else:
            created += 1
        if doc.get("email") == MOD_SERVICE_EMAIL:
            mod_ct += 1
        elif doc.get("email") == COMMERCIAL_SERVICE_EMAIL:
            com_ct += 1
    print(f"Scanned {len(orgs)} orgs · created {created} defaults · already had {repaired}")
    print(f"  MOD→{MOD_SERVICE_EMAIL}: {mod_ct}   Commercial→{COMMERCIAL_SERVICE_EMAIL}: {com_ct}")


if __name__ == "__main__":
    asyncio.run(main())
