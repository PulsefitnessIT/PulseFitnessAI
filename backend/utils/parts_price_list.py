"""Load the bundled Pulse Fitness parts price list into the operator parts catalogue (once per file version)."""
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone

from pymongo import UpdateOne

from utils.database import db

logger = logging.getLogger(__name__)
PRICE_LIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed_data", "pulse_price_list.xlsx")


def _rows(path: str) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    it = wb.worksheets[0].iter_rows(values_only=True)
    head = [str(h or "").strip().lower() for h in next(it)]
    out = []
    for r in it:
        d = dict(zip(head, r))
        sku = str(d.get("code") or "").strip().upper()
        name = str(d.get("name") or "").strip()
        if sku and name:
            out.append({"sku": sku, "name": name, "category": str(d.get("product group description") or "").strip(),
                        "manufacturer": str(d.get("manufacturer") or "").strip(),
                        "cost": float(d.get("average buying price") or 0), "list_price": float(d.get("sales price") or 0)})
    return out


async def import_price_list(org_id: str, rows: list[dict]) -> tuple[int, int]:
    now = datetime.now(timezone.utc).isoformat()
    ops = [UpdateOne(
        {"organization_id": org_id, "sku": r["sku"]},
        {"$set": {**{k: v for k, v in r.items() if k != "sku" and (v or k in ("cost", "list_price"))}, "updated_at": now,
                  "price_source": "pulse_price_list"},
         "$setOnInsert": {"id": str(uuid.uuid4()), "sku": r["sku"], "organization_id": org_id, "active": True, "created_at": now}},
        upsert=True) for r in rows]
    created = updated = 0
    for i in range(0, len(ops), 1000):
        res = await db.svc_parts.bulk_write(ops[i:i + 1000], ordered=False)
        created += res.upserted_count
        updated += res.modified_count
    return created, updated


async def seed_pulse_price_list() -> int:
    if not os.path.exists(PRICE_LIST):
        return 0
    with open(PRICE_LIST, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()[:16]
    marker = f"pulse_price_list:{digest}"
    if await db.migrations.find_one({"_id": marker}):
        return 0
    orgs = [o["id"] async for o in db.organizations.find(
        {"is_operator_company": True, "name": {"$regex": "^Pulse Fitness", "$options": "i"}}, {"_id": 0, "id": 1})]
    if not orgs:
        return 0
    await db.svc_parts.create_index([("organization_id", 1), ("sku", 1)])
    rows = _rows(PRICE_LIST)
    total = 0
    for org_id in orgs:
        c, u = await import_price_list(org_id, rows)
        logger.info("Pulse price list → org %s: %d new, %d updated", org_id, c, u)
        total += c + u
    await db.migrations.update_one({"_id": marker}, {"$set": {"ran_at": datetime.now(timezone.utc).isoformat(), "rows": len(rows), "orgs": orgs}}, upsert=True)
    return total
