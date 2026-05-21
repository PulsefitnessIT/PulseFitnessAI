"""Iter 216h277 — reconcile org module storage.

There are three places an organisation's module enablement can live:

  1. `portal_type` (legacy: 'service_portal' | 'crm' | 'both')
  2. `enabled_modules` (array, e.g. ['operations', 'crm'])
  3. `modules` (dict, e.g. {'crm': {'enabled': True, 'tier': 'pro'}})

The Master Admin "CRM Orgs" tab filters on (1) and (2), but the Features
tab writes to (3). When those drift, CRM-enabled orgs disappear from the
CRM tab.

This script makes (3) authoritative when present, then derives (1) and
(2) from it. If (3) is empty/missing it leaves (1) and (2) alone but
strips any invalid values from `enabled_modules`.

Run idempotently:
    cd /app/backend && set -a && . ./.env && set +a && \
      python -m scripts.reconcile_org_modules --commit
"""
from __future__ import annotations

import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

ALL_MODULE_IDS = ["operations", "crm", "memberships", "marketing", "staffing", "reporting"]
DICT_MODULE_KEYS = ("operations", "memberships", "marketing", "crm")


def _derive_portal_type(modules: list[str]) -> str:
    has_crm = "crm" in modules
    has_ops = any(m in modules for m in ("operations", "memberships", "marketing", "staffing", "reporting"))
    if has_crm and has_ops:
        return "both"
    if has_crm:
        return "crm"
    return "service_portal"


def _reconcile(org: dict) -> dict | None:
    modules_dict = org.get("modules") or {}
    enabled_arr = org.get("enabled_modules") or []
    portal_type = org.get("portal_type") or "service_portal"

    # 1. Strip invalid ids from enabled_modules.
    cleaned_arr = [m for m in enabled_arr if m in ALL_MODULE_IDS]

    # 2. Take the UNION of the modules dict and the cleaned array so we
    # never silently disable a module that was already on. Both shapes
    # are written by different UIs (Features tab vs Details picker) and
    # neither has ever been the canonical authority.
    from_dict = [k for k in DICT_MODULE_KEYS if (modules_dict.get(k) or {}).get("enabled")]
    union = set(from_dict) | set(cleaned_arr)
    # When an org has nothing in either storage, fall back to Operations
    # (matches `_modules_from_portal_type('service_portal')`). When the
    # modules dict explicitly toggled Operations off but the array still
    # carried it (legacy default), preserve Operations — disabling the
    # Service Portal is a destructive operation that should never come
    # from a reconcile script.
    if not union:
        union = {"operations"}
    if "operations" in cleaned_arr:
        union.add("operations")
    merged = [m for m in ALL_MODULE_IDS if m in union]

    if not merged:
        merged = ["operations"]

    new_portal = _derive_portal_type(merged)

    changes: dict = {}
    if merged != enabled_arr:
        changes["enabled_modules"] = merged
    if new_portal != portal_type:
        changes["portal_type"] = new_portal
    return changes or None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="Write changes (default: dry-run)")
    args = ap.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    cursor = db.organizations.find({}, {"_id": 0, "id": 1, "name": 1, "portal_type": 1, "enabled_modules": 1, "modules": 1})
    total = 0
    changed = 0
    async for org in cursor:
        total += 1
        diff = _reconcile(org)
        if not diff:
            continue
        changed += 1
        print(f"  {org.get('name')!r:50} -> {diff}")
        if args.commit:
            await db.organizations.update_one({"id": org["id"]}, {"$set": diff})
    suffix = "(dry-run, pass --commit to apply)" if not args.commit else "(committed)"
    print(f"Reconciled {changed}/{total} orgs {suffix}")


if __name__ == "__main__":
    asyncio.run(main())
