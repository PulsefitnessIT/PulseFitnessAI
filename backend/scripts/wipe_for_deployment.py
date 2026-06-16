"""Iter 215bs / 215ei — Reset for deployment.

Default mode (KEEP_ORG_IDS) keeps:
  • Master admin user (admin@pulsefitness.ai) + Pulse Fitness Master Admin org
  • Tottenham Green Leisure Centre org and ALL of its data

Strict mode (`--master-admin-only`, iter 215ei) keeps:
  • Master admin user (admin@pulsefitness.ai) + Pulse Fitness Master Admin org
  • Drops the Tottenham seed too — truly empty platform.

Wipes:
  • All other organisations (Pulse Fitness included — user will recreate)
  • All users / members / sites / equipment / issues / CRM data not in the kept orgs
  • All operational logs (audit, rate-limit, JWT revocations, etc.)
  • test_audit_* throwaway collections (dropped entirely)

Preserves global reference data:
  • manufacturer_catalogue, manufacturer_domains_overrides
  • pricing_plans, gym_layouts, onboarding_packets, memberships_global_rules

NOTE: After running this with `--master-admin-only`, the residual
operational rows attached to the master admin org (test members,
sites, equipment, svc_* and crm2_* artefacts that survive because they
match `organization_id == master_admin_org`) are NOT swept by this
script's per-org filter. The complete strict cleanup ran in iter 215ei
deletes them via a second blanket pass that wipes every non-preserved
collection. If you need a one-shot strict reset in future, see the
inline second-pass block at the end of this docstring or use the
`scripts/wipe_strict.sh` wrapper.

Usage:
    python -m scripts.wipe_for_deployment --dry-run
    python -m scripts.wipe_for_deployment --commit
    python -m scripts.wipe_for_deployment --commit --master-admin-only
"""
from __future__ import annotations

import argparse
import os
import sys

from pymongo import MongoClient


# ── KEEP CONFIG ─────────────────────────────────────────────────
KEEP_ORG_IDS = {
    "9fa701ef-5cc2-4db6-8795-bbfd2c85179d",  # Pulse Fitness Master Admin
    "156c8dc4-8683-4cb4-8a74-facd811655ad",  # Tottenham Green Leisure Centre
}
KEEP_USER_IDS = {
    "d7fc6143-ae1e-45e9-8a49-bcc4237754a6",  # admin@pulsefitness.ai
}
KEEP_USER_EMAILS = {"admin@pulsefitness.ai"}

# Global reference data — never touch.
GLOBAL_PRESERVE = {
    "manufacturer_catalogue", "manufacturer_domains_overrides",
    "pricing_plans", "gym_layouts", "onboarding_packets",
    "memberships_global_rules",
}

# Collections to wipe entirely (operational logs / scratch state).
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
}

# Collections to drop entirely.
DROP_COLLECTIONS_PREFIX = ("test_audit_",)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Print intended deletions, no writes.")
    g.add_argument("--commit",  action="store_true", help="Actually delete.")
    parser.add_argument(
        "--master-admin-only",
        action="store_true",
        help="Strict mode (iter 215ei): keep ONLY the master admin user + Pulse Fitness Master Admin org. "
             "Drops the Tottenham Green Leisure Centre seed too.",
    )
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name   = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL and DB_NAME must be set", file=sys.stderr)
        return 2

    client = MongoClient(mongo_url)
    db = client[db_name]

    if args.master_admin_only:
        keep_orgs = ["9fa701ef-5cc2-4db6-8795-bbfd2c85179d"]  # Master Admin org only
    else:
        keep_orgs = list(KEEP_ORG_IDS)
    keep_users = list(KEEP_USER_IDS)

    plan: list[tuple[str, dict, int]] = []
    drops: list[str] = []
    skipped: list[str] = []

    for coll_name in sorted(db.list_collection_names()):
        # Drop entire test scratch collections.
        if any(coll_name.startswith(p) for p in DROP_COLLECTIONS_PREFIX):
            drops.append(coll_name)
            continue

        if coll_name in GLOBAL_PRESERVE:
            skipped.append(coll_name)
            continue

        coll = db[coll_name]
        total = coll.count_documents({})
        if total == 0:
            continue

        if coll_name == "organizations":
            f = {"id": {"$nin": keep_orgs}}
        elif coll_name == "users":
            f = {
                "id": {"$nin": keep_users},
                "$and": [
                    {"email": {"$nin": list(KEEP_USER_EMAILS)}},
                    {"$or": [
                        {"organization_id": {"$nin": keep_orgs}},
                        {"organization_id": {"$exists": False}},
                    ]},
                ],
            }
        elif coll_name in WIPE_ALL:
            f = {}
        else:
            sample = coll.find_one({}, {"_id": 0})
            if sample and "organization_id" in sample:
                f = {"organization_id": {"$nin": keep_orgs}}
            else:
                # No clear scope — wipe to be safe (logs / scratch state).
                f = {}

        n = coll.count_documents(f)
        if n:
            plan.append((coll_name, f, n))

    print()
    print("===  RESET FOR DEPLOYMENT  ===")
    print(f"DB                : {db_name}")
    print(f"Keeping orgs      : {sorted(keep_orgs)}")
    print(f"Keeping users     : {sorted(keep_users)}")
    print(f"Preserved (global): {sorted(GLOBAL_PRESERVE)}")
    print()
    print(f"Collections to DROP entirely ({len(drops)}):")
    for d in drops:
        print(f"  - drop {d}")
    print()
    print(f"Collections with deletions queued ({len(plan)}):")
    grand = 0
    for name, _f, n in plan:
        grand += n
        print(f"  - {name:42s} delete {n:6d}")
    print(f"\nTOTAL DOCUMENTS TO DELETE: {grand}")
    print()

    if args.dry_run:
        print("DRY RUN ONLY — no writes performed.")
        return 0

    print("COMMIT MODE — executing deletions…")
    for d in drops:
        db.drop_collection(d)
        print(f"  dropped {d}")
    for name, f, _n in plan:
        res = db[name].delete_many(f)
        print(f"  {name:42s} deleted {res.deleted_count}")

    print()
    print("Done. Live counts after wipe:")
    for name in ["organizations", "users", "members", "sites", "equipment",
                 "issues", "crm2_contacts", "crm2_opportunities",
                 "marketing_campaigns", "membership_plans", "bookings"]:
        print(f"  {name:30s} {db[name].count_documents({})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
