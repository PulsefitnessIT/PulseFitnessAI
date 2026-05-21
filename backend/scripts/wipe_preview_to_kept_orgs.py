"""Iter 216h273 — One-shot preview wipe (user-scoped keep list).

Keeps ONLY:
  • GymAxis AI Admin    (9fa701ef-…3179d) + master admin user
  • Third Space         (c695638c-…4205)
  • British Army HQ     (2be58411-…2997)
  • Catterick Garrison  (6c355051-…06fc, mod_branch)
  • Catterick Garrison Gym (mod-site-army-catterick, mod_site under Catterick)

Nukes EVERYTHING ELSE (orgs, users, members, sites, equipment,
issues, CRM data, quotes, deals, audit logs, etc.) that doesn't
match the keep set.

Preserves global reference data (manufacturer_catalogue, pricing
plans, gym layouts, onboarding packets, memberships rules).

Usage:
    python -m scripts.wipe_preview_to_kept_orgs --dry-run
    python -m scripts.wipe_preview_to_kept_orgs --commit
"""
from __future__ import annotations

import argparse
import os
import sys

from pymongo import MongoClient


KEEP_ORG_IDS = {
    "9fa701ef-5cc2-4db6-8795-bbfd2c85179d",  # GymAxis AI Admin
    "c695638c-5f60-424d-bdd0-2273e6c24205",  # Third Space
    "2be58411-61dc-460a-ba53-29d74a662997",  # British Army — Head Office
    "6c355051-a502-419b-9154-094c425306fc",  # Catterick Garrison
    "mod-site-army-catterick",                # Catterick Garrison Gym (mod_site)
}

# Users that must survive irrespective of org membership.
KEEP_USER_EMAILS = {"admin@gymaxisai.com"}

# Global reference data — never touch.
GLOBAL_PRESERVE = {
    "manufacturer_catalogue", "manufacturer_domains_overrides",
    "pricing_plans", "gym_layouts", "onboarding_packets",
    "memberships_global_rules",
}

# Operational logs / scratch state — wipe entirely.
WIPE_ALL = {
    "admin_activity_log", "audit_logs", "security_audit_log",
    "jwt_revocations", "rate_buckets", "password_reset_tokens",
    "trust_events", "email_send_events", "document_access_log",
    "ui_error_events", "help_search_misses",
    "support_audit", "support_cases", "support_conversations",
    "support_feedback", "support_sessions", "support_analytics_daily",
    "service_desk_audit_log", "supplier_cases", "pulse_upgrade_requests",
    "system_jobs", "marketing_tour_state", "marketing_plans",
    "marketing_page_visits", "public_contact_submissions",
    "equipment_image_backfill_runs", "catalogue_jobs", "pricing_audit_log",
    "memberships_admin_audit", "crm_audit_log", "crm_loop_runs",
    "qr_rotation_secret",
    "crm_website_cache",  # h268 cache — repopulates on demand
}

DROP_COLLECTIONS_PREFIX = ("test_audit_",)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit",  action="store_true")
    args = p.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name   = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL and DB_NAME must be set", file=sys.stderr)
        return 2

    client = MongoClient(mongo_url)
    db = client[db_name]

    print(f"== Wipe preview → keep {len(KEEP_ORG_IDS)} orgs ==")
    print(f"   commit={args.commit}  dry={args.dry_run}\n")

    # 1. Resolve user-ids to keep (members of any kept org + KEEP_USER_EMAILS).
    keep_user_ids: set[str] = set()
    for u in db.users.find(
        {"$or": [
            {"organization_id": {"$in": list(KEEP_ORG_IDS)}},
            {"email": {"$in": list(KEEP_USER_EMAILS)}},
        ]},
        {"_id": 0, "id": 1, "email": 1, "organization_id": 1},
    ):
        if u.get("id"):
            keep_user_ids.add(u["id"])
    print(f"   keep_user_ids: {len(keep_user_ids)} users\n")

    # 2. Build per-collection deletion plan
    plan: list[tuple[str, dict, int]] = []
    drops: list[str] = []

    for coll_name in sorted(db.list_collection_names()):
        if any(coll_name.startswith(pref) for pref in DROP_COLLECTIONS_PREFIX):
            drops.append(coll_name)
            continue
        if coll_name in GLOBAL_PRESERVE:
            continue

        coll = db[coll_name]

        if coll_name == "organizations":
            f = {"id": {"$nin": list(KEEP_ORG_IDS)}}
        elif coll_name == "users":
            f = {"id": {"$nin": list(keep_user_ids)}}
        elif coll_name in WIPE_ALL:
            f = {}
        else:
            # Default: per-org filter on `organization_id`. Collections
            # without that field are left alone unless explicitly
            # listed in WIPE_ALL.
            sample = coll.find_one({}, {"_id": 0})
            if not sample:
                continue
            if "organization_id" in sample:
                f = {"organization_id": {"$nin": list(KEEP_ORG_IDS)}}
            else:
                # No org pointer — skip unless it's an operational log
                continue

        cnt = coll.count_documents(f) if f != {} else coll.estimated_document_count()
        if cnt > 0:
            plan.append((coll_name, f, cnt))

    # 3. Print plan
    total = sum(c for _, _, c in plan)
    print(f"-- DELETE PLAN ({total} docs across {len(plan)} collections) --")
    for name, _f, cnt in plan:
        print(f"   delete {cnt:>6d} from {name}")
    print(f"\n-- DROP COLLECTIONS ({len(drops)}) --")
    for d in drops:
        print(f"   drop {d}")

    if args.dry_run:
        print("\n[dry-run] no writes performed.")
        return 0

    # 4. EXECUTE
    print("\n-- EXECUTING --")
    for name, f, _ in plan:
        r = db[name].delete_many(f)
        print(f"   {name}: deleted {r.deleted_count}")
    for d in drops:
        db[d].drop()
        print(f"   dropped {d}")
    print("\n[commit] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
