"""One-shot data fixes after the iteration-204 sanitisation overhaul.

What this does
==============
1. Decodes HTML entities (``&#x27;`` → ``'``, ``&amp;`` → ``&`` …) inside
   any text fields that were stored *while* ``sanitise_string`` was using
   ``html.escape``. The escape was unnecessary because React already
   escapes ``{value}`` JSX expressions; pre-encoding caused suppliers and
   operators to see literal entity strings on the page.
2. Backfills ``organization_id`` and ``organization_account_type`` on
   existing ``supplier_cases`` documents so the brand-aware email link
   helper (utils/brand_urls) can pick the correct domain.

Idempotent
----------
Both passes are safe to re-run — they only touch documents that *need*
changing. Production deploy steps:

    cd backend
    python scripts/fix_iteration204_data.py
"""
from __future__ import annotations

import asyncio
import html
import sys
from pathlib import Path

# Resolve backend/ root so the script works no matter where it's run from.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from utils.database import db


# Collections + fields that flowed through sanitise_string before the fix.
ENTITY_TARGETS: list[tuple[str, list[str]]] = [
    ("issues",         ["issue_description", "machine_type", "supplier", "steps_taken"]),
    ("issues_archive", ["issue_description"]),
    ("mod_site_staff", ["name", "role", "phone"]),
    ("supplier_case_comments", ["body"]),
    ("public_contact_submissions", ["name", "message", "phone", "company"]),
]


_NEEDS_DECODE = ("&#", "&amp;", "&lt;", "&gt;", "&quot;", "&apos;")


def _has_entity(value: str) -> bool:
    return isinstance(value, str) and any(tag in value for tag in _NEEDS_DECODE)


async def fix_html_entities() -> int:
    """Pass 1 — decode HTML entities in stored user-input fields."""
    fixed = 0
    for coll_name, fields in ENTITY_TARGETS:
        if coll_name not in await db.list_collection_names():
            continue
        # Match docs where ANY of the target fields contain an entity prefix.
        # Cheap server-side filter so we don't pull the whole collection.
        cursor = db[coll_name].find(
            {"$or": [{f: {"$regex": "&[#a-z]+;?", "$options": "i"}} for f in fields]},
            {f: 1 for f in fields},
        )
        async for doc in cursor:
            updates = {}
            for f in fields:
                v = doc.get(f)
                if _has_entity(v):
                    decoded = html.unescape(v)
                    if decoded != v:
                        updates[f] = decoded
            if updates:
                await db[coll_name].update_one({"_id": doc["_id"]}, {"$set": updates})
                fixed += 1
        print(f"  • {coll_name}: scanned and fixed entries with entities")
    return fixed


async def backfill_supplier_brand() -> int:
    """Pass 2 — populate ``organization_id`` + ``organization_account_type``
    on supplier_cases so brand-aware URLs render correctly."""
    fixed = 0
    cursor = db.supplier_cases.find(
        {"organization_account_type": {"$exists": False}},
        {"_id": 1, "issue_id": 1},
    )
    async for case in cursor:
        issue = await db.issues.find_one(
            {"id": case["issue_id"]},
            {"_id": 0, "organization_id": 1},
        )
        if not issue:
            continue
        org = await db.organizations.find_one(
            {"id": issue["organization_id"]},
            {"_id": 0, "account_type": 1},
        )
        if not org:
            continue
        await db.supplier_cases.update_one(
            {"_id": case["_id"]},
            {"$set": {
                "organization_id": issue["organization_id"],
                "organization_account_type": org.get("account_type"),
            }},
        )
        fixed += 1
    return fixed


async def main() -> None:
    print("[fix_iteration204_data] decoding HTML entities …")
    n1 = await fix_html_entities()
    print(f"    → {n1} documents fixed")
    print("[fix_iteration204_data] backfilling supplier-case brand …")
    n2 = await backfill_supplier_brand()
    print(f"    → {n2} documents fixed")
    print("[fix_iteration204_data] done.")


if __name__ == "__main__":
    asyncio.run(main())
