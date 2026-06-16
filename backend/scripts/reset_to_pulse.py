"""Pulse Fitness AI — clean database reset.

Wipes ALL tenant/operational data so the platform starts fresh for
Pulse Fitness. Preserves only global reference/config collections that
the application needs to operate. The Master Admin account is recreated
automatically by bootstrap.seed.seed_master_admin() on the next backend
start (using MASTER_ADMIN_EMAIL / MASTER_ADMIN_PASSWORD from .env).

Usage:
    python -m scripts.reset_to_pulse --dry-run
    python -m scripts.reset_to_pulse --commit
"""
from __future__ import annotations

import argparse
import os
import sys

from pymongo import MongoClient

# Global reference data the app depends on — NEVER cleared.
GLOBAL_PRESERVE = {
    "manufacturer_catalogue",
    "manufacturer_domains_overrides",
    "pricing_plans",
    "gym_layouts",
    "onboarding_packets",
    "memberships_global_rules",
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    args = p.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL and DB_NAME must be set", file=sys.stderr)
        return 2

    client = MongoClient(mongo_url)
    db = client[db_name]

    print(f"== Pulse Fitness AI clean reset (db={db_name}) ==")
    print(f"   commit={args.commit} dry={args.dry_run}\n")

    plan: list[tuple[str, int]] = []
    for coll_name in sorted(db.list_collection_names()):
        if coll_name in GLOBAL_PRESERVE:
            continue
        cnt = db[coll_name].estimated_document_count()
        if cnt > 0:
            plan.append((coll_name, cnt))

    total = sum(c for _, c in plan)
    print(f"-- CLEAR PLAN ({total} docs across {len(plan)} collections) --")
    for name, cnt in plan:
        print(f"   clear {cnt:>7d} from {name}")
    print(f"\n-- PRESERVED (global reference) --")
    for name in sorted(GLOBAL_PRESERVE):
        if name in db.list_collection_names():
            print(f"   keep  {db[name].estimated_document_count():>7d} in {name}")

    if args.dry_run:
        print("\n[dry-run] no writes performed.")
        return 0

    print("\n-- EXECUTING --")
    for name, _ in plan:
        r = db[name].delete_many({})
        print(f"   {name}: cleared {r.deleted_count}")
    print("\n[commit] done. Restart backend to re-seed the Master Admin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
