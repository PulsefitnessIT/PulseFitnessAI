"""Iter 215bx — Backfill legacy `crm_contacts` / `crm_activities` /
`crm_deals` / `crm_companies` (v1) into the v2 collections (`crm2_*`).

Why: prior to iter 215bx, marketing forms and memberships analytics
push wrote to the v1 tables, while the live CRM portal reads from v2.
This script migrates any orphaned v1 records into v2 (deduped by email
for contacts and by name for companies) so existing tenants don't lose
their accumulated leads on the upgrade.

Usage:
    python -m backend.scripts.migrate_crm_v1_to_v2 --dry-run
    python -m backend.scripts.migrate_crm_v1_to_v2 --commit
"""
from __future__ import annotations

import argparse
import os
import sys

from pymongo import MongoClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit",  action="store_true")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name   = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL and DB_NAME must be set", file=sys.stderr)
        return 2
    client = MongoClient(mongo_url)
    db = client[db_name]

    plan: dict = {
        "contacts_migrated": 0,
        "contacts_skipped_dupe": 0,
        "companies_migrated": 0,
        "companies_skipped_dupe": 0,
        "activities_migrated": 0,
        "deals_migrated": 0,
    }

    # ── Companies (name-keyed) ─────────────────────────────────────
    for c in db.crm_companies.find({}):
        org = c.get("organization_id")
        nm = (c.get("name") or "").strip()
        if not org or not nm:
            continue
        needle = nm.lower()
        existing = db.crm2_companies.find_one(
            {"organization_id": org, "name_lower": needle}, {"_id": 0, "id": 1},
        )
        if existing:
            plan["companies_skipped_dupe"] += 1
            continue
        plan["companies_migrated"] += 1
        if args.commit:
            doc = dict(c)
            doc.pop("_id", None)
            doc["name_lower"] = needle
            doc.setdefault("source", "v1_migration")
            db.crm2_companies.insert_one(doc)

    # ── Contacts (email-keyed) ─────────────────────────────────────
    for c in db.crm_contacts.find({}):
        org = c.get("organization_id")
        em  = (c.get("email") or "").strip().lower()
        if not org or not em:
            continue
        existing = db.crm2_contacts.find_one(
            {"organization_id": org, "email": em}, {"_id": 0, "id": 1},
        )
        if existing:
            plan["contacts_skipped_dupe"] += 1
            continue
        plan["contacts_migrated"] += 1
        if args.commit:
            doc = dict(c)
            doc.pop("_id", None)
            doc["email"] = em
            doc.setdefault("source", c.get("source") or "v1_migration")
            db.crm2_contacts.insert_one(doc)

    # ── Activities (best-effort, by contact email match) ───────────
    for a in db.crm_activities.find({}):
        org = a.get("organization_id")
        if not org:
            continue
        plan["activities_migrated"] += 1
        if args.commit:
            doc = dict(a)
            doc.pop("_id", None)
            db.crm2_activities.insert_one(doc)

    # ── Deals → Opportunities ──────────────────────────────────────
    for d in db.crm_deals.find({}):
        if not d.get("organization_id"):
            continue
        plan["deals_migrated"] += 1
        if args.commit:
            doc = dict(d)
            doc.pop("_id", None)
            doc.setdefault("title", doc.pop("name", "Untitled"))
            db.crm2_opportunities.insert_one(doc)

    print()
    print("=== CRM v1 → v2 Backfill ===")
    print(f"DB: {db_name}")
    for k, v in plan.items():
        print(f"  {k:30s} {v}")
    print()
    if args.dry_run:
        print("DRY RUN — no writes performed.")
    else:
        print("COMMIT MODE — migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
