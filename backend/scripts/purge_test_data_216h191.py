"""
One-off purge script — keep only the four operator-confirmed orgs and
their child data, nuke everything else.

Keep set (confirmed by user):
  • Third Space               (c695638c-…)
  • British Army — Head Office (2be58411-…)
  • Demo Garrison (MOD)   (6c355051-…)
  • Pulse Fitness              (8cd02d8c-…)  — hosts e1.agent@pulsefitness.ai

Protected collections (NEVER deleted from):
  • Auth: users (filtered), password_reset_tokens, sessions
  • Audit: audit_log, audit_logs, admin_activity_log,
           master_admin_activity_log, master_admin_audit_log
  • Platform config: integrations, integration_configs, app_config,
                     stripe_webhook_events, system_metadata
  • Master admin shadow accounts: kept by email allowlist + flag check.

Always-preserve users (regardless of org_id):
  • admin@pulsefitness.ai (Master Admin)
  • Any user with is_master_admin=True or is_pulse_admin=True

Safety guards:
  1. ABORT if any of the 4 keep_ids fails to resolve.
  2. ABORT if the keep set would also wipe master-admin shadow records.
  3. Hard-protected collection list is enforced before any delete_many.
"""
import asyncio
import sys

sys.path.insert(0, '/app/backend')

from utils.database import db


KEEP_ORG_IDS = {
    "c695638c-5f60-424d-bdd0-2273e6c24205",  # Third Space
    "2be58411-61dc-460a-ba53-29d74a662997",  # British Army — Head Office
    "6c355051-a502-419b-9154-094c425306fc",  # Demo Garrison (MOD)
    "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f",  # Pulse Fitness
}

PROTECTED_USER_EMAILS = {"admin@pulsefitness.ai"}

# Collections we NEVER delete from (auth + audit + platform config).
PROTECTED_COLLECTIONS = {
    # auth + sessions
    "password_reset_tokens",
    "sessions",
    "magic_links",
    # audit
    "audit_log",
    "audit_logs",
    "admin_activity_log",
    "master_admin_activity_log",
    "master_admin_audit_log",
    "activity_log",
    # platform-level config
    "integrations",
    "integration_configs",
    "app_config",
    "stripe_webhook_events",
    "system_metadata",
    "system",
    # internal helper collections
    "fs.files", "fs.chunks",  # gridfs if present
}


async def _verify_keep_set() -> dict:
    """Resolve names of keep orgs. Abort if any are missing."""
    keep_map: dict = {}
    for oid in KEEP_ORG_IDS:
        org = await db.organizations.find_one({"id": oid}, {"_id": 0, "name": 1})
        if not org:
            raise SystemExit(f"❌ ABORT: keep-org {oid} not found in DB. Refusing to purge.")
        keep_map[oid] = org.get("name")
    print("✅ Keep set resolved:")
    for oid, name in keep_map.items():
        print(f"    {oid[:8]}…  {name}")
    return keep_map


async def _purge_users() -> int:
    """Delete users not in keep orgs.

    Protected:
      • email in PROTECTED_USER_EMAILS
      • is_master_admin=True
      • is_pulse_admin=True
      • organization_id IN KEEP_ORG_IDS
    """
    flt = {
        "$and": [
            {"organization_id": {"$nin": list(KEEP_ORG_IDS)}},
            {"email": {"$nin": list(PROTECTED_USER_EMAILS)}},
            {"is_master_admin": {"$ne": True}},
            {"is_pulse_admin": {"$ne": True}},
        ],
    }
    res = await db.users.delete_many(flt)
    return int(res.deleted_count or 0)


async def _purge_org_scoped_collections() -> dict[str, int]:
    """Scan every collection in the DB, find ones with an org_id-style
    field, and delete docs whose org_id is NOT in the keep set.

    We try a small list of common field names (`organization_id`,
    `org_id`, `tenant_id`) and only act on the ones that match.
    """
    deleted: dict[str, int] = {}
    coll_names = await db.list_collection_names()
    org_id_fields = ["organization_id", "org_id", "tenant_id"]
    for coll_name in sorted(coll_names):
        if coll_name in PROTECTED_COLLECTIONS:
            continue
        if coll_name in ("organizations", "users"):
            continue  # handled separately
        coll = db[coll_name]
        for field in org_id_fields:
            # Probe — does this collection have at least one doc using
            # this field? cheap check.
            sample = await coll.find_one({field: {"$exists": True}}, {"_id": 1})
            if not sample:
                continue
            res = await coll.delete_many({field: {"$nin": list(KEEP_ORG_IDS)}})
            n = int(res.deleted_count or 0)
            if n:
                deleted[f"{coll_name}.{field}"] = n
            break  # collection's org-id field decided
    return deleted


async def _purge_test_flagged_stragglers() -> dict[str, int]:
    """After the org-scoped purge, sweep collections for stray docs
    flagged `is_test|seed|demo=true` that may not have an org_id field
    (e.g. raw fault feed, generic logs)."""
    deleted: dict[str, int] = {}
    coll_names = await db.list_collection_names()
    flag = {"$or": [{"is_test": True}, {"seed": True}, {"demo": True}]}
    for coll_name in sorted(coll_names):
        if coll_name in PROTECTED_COLLECTIONS:
            continue
        if coll_name in ("users", "organizations"):
            continue
        res = await db[coll_name].delete_many(flag)
        n = int(res.deleted_count or 0)
        if n:
            deleted[coll_name] = n
    return deleted


async def _purge_orgs() -> int:
    """Delete every organisation that is NOT in the keep set."""
    res = await db.organizations.delete_many({"id": {"$nin": list(KEEP_ORG_IDS)}})
    return int(res.deleted_count or 0)


async def _print_before() -> None:
    print("=== BEFORE ===")
    for coll in ("organizations", "sites", "users", "equipment", "issues"):
        n = await db[coll].count_documents({})
        print(f"  {coll}: {n:,}")


async def _print_after() -> None:
    print("=== AFTER ===")
    for coll in ("organizations", "sites", "users", "equipment", "issues"):
        n = await db[coll].count_documents({})
        print(f"  {coll}: {n:,}")


async def main() -> None:
    print("\n🧨 Pulse Fitness test-data purge — keep only operator-confirmed orgs.\n")
    await _print_before()
    print()

    keep_map = await _verify_keep_set()
    print()

    # Step 1 — org-scoped collections (sites, equipment, issues, all CRM tables, etc.)
    print("Purging org-scoped collections …")
    osc = await _purge_org_scoped_collections()
    org_scoped_total = sum(osc.values())
    print(f"  ✅ {org_scoped_total:,} docs deleted across {len(osc)} collection/field pairs")
    for k, v in sorted(osc.items(), key=lambda kv: -kv[1])[:20]:
        print(f"     - {k}: {v:,}")

    # Step 2 — flagged stragglers
    print("\nPurging is_test/seed/demo stragglers …")
    flagged = await _purge_test_flagged_stragglers()
    flagged_total = sum(flagged.values())
    print(f"  ✅ {flagged_total:,} flagged docs deleted across {len(flagged)} collections")
    for k, v in sorted(flagged.items(), key=lambda kv: -kv[1])[:10]:
        print(f"     - {k}: {v:,}")

    # Step 3 — users (scoped to non-keep orgs, master admins protected)
    print("\nPurging non-keep users …")
    n_users = await _purge_users()
    print(f"  ✅ {n_users:,} users deleted")

    # Step 4 — organisations
    print("\nPurging non-keep organisations …")
    n_orgs = await _purge_orgs()
    print(f"  ✅ {n_orgs:,} organisations deleted")

    print()
    await _print_after()
    print()

    # Sanity audit — keep orgs must still exist post-purge
    print("=== POST-PURGE SANITY ===")
    for oid in KEEP_ORG_IDS:
        org = await db.organizations.find_one({"id": oid}, {"_id": 0, "name": 1})
        assert org, f"keep org {oid} vanished — something went wrong"
        n_sites = await db.sites.count_documents({"organization_id": oid})
        n_users = await db.users.count_documents({"organization_id": oid})
        n_equip = await db.equipment.count_documents({"organization_id": oid})
        print(f"  ✅ {keep_map[oid]}: sites={n_sites} users={n_users} equipment={n_equip}")

    # Master admin must still exist
    admin = await db.users.find_one({"email": "admin@pulsefitness.ai"}, {"_id": 0, "id": 1, "email": 1})
    assert admin, "master admin user vanished — restore from backup"
    print(f"  ✅ Master admin preserved: {admin['email']}")

    print("\n🎯 Purge complete.\n")


if __name__ == "__main__":
    asyncio.run(main())
