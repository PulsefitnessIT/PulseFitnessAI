"""Normalise dual-portal organisations so new users write to BOTH collections.

Background
----------
`routes.master_admin._create_org_user` routes a newly-created user to
`db.users` (service portal) and/or `db.crm_users` (CRM) based on the org's
`portal_type` and `enabled_modules`. A CRM-primary org (e.g. Pulse Fitness Ltd
historically had portal_type='crm') that also runs Operations would write staff
ONLY to `crm_users`, so they were invisible in Operations → Staff → HR until the
backfill union fix. This migration fixes the ROOT config: any org that has BOTH
a service-portal module AND CRM enabled gets `portal_type='both'` and a populated
`enabled_modules` list, so future writes hit both collections directly.

Safe + idempotent. Dry-run by default; pass --apply to write.

    python -m scripts.normalise_dual_portal_orgs          # dry-run (report only)
    python -m scripts.normalise_dual_portal_orgs --apply  # apply changes
"""
import asyncio
import sys

from utils.database import db

# Mirror routes.master_admin._create_org_user._SP_MODULES
SP_MODULES = {"operations", "memberships", "marketing", "staffing", "reporting"}


def _enabled_set(org: dict) -> set:
    """Resolve the set of enabled module keys from either representation."""
    enabled = set(org.get("enabled_modules") or [])
    modules = org.get("modules") or {}
    for k, v in modules.items():
        if isinstance(v, dict) and v.get("enabled"):
            enabled.add(k)
        elif v is True:
            enabled.add(k)
    return enabled


async def main(apply: bool) -> None:
    total = 0
    changed = 0
    async for org in db.organizations.find(
        {}, {"_id": 0, "id": 1, "name": 1, "portal_type": 1,
             "enabled_modules": 1, "modules": 1},
    ):
        total += 1
        enabled = _enabled_set(org)
        has_sp = bool(enabled & SP_MODULES)
        has_crm = "crm" in enabled
        if not (has_sp and has_crm):
            continue  # not a dual-portal org — leave it alone

        updates: dict = {}
        if org.get("portal_type") != "both":
            updates["portal_type"] = "both"
        # Ensure enabled_modules reflects every enabled module (so the
        # is_sp / is_crm detection in _create_org_user is reliable).
        current_list = set(org.get("enabled_modules") or [])
        if current_list != enabled:
            updates["enabled_modules"] = sorted(enabled)

        if not updates:
            continue
        changed += 1
        print(f"  • {org.get('name')} ({org['id']}): {updates}")
        if apply:
            await db.organizations.update_one({"id": org["id"]}, {"$set": updates})

    verb = "Applied" if apply else "Would change"
    print(f"\n{verb} {changed} of {total} organisation(s). "
          f"{'(dry-run — pass --apply to write)' if not apply else ''}")


async def normalise_dual_portal_orgs_once() -> int:
    """Startup-friendly variant: applies the normalisation silently and
    returns the number of orgs changed. Idempotent → cheap no-op once clean."""
    changed = 0
    async for org in db.organizations.find(
        {}, {"_id": 0, "id": 1, "portal_type": 1,
             "enabled_modules": 1, "modules": 1},
    ):
        enabled = _enabled_set(org)
        if not (bool(enabled & SP_MODULES) and "crm" in enabled):
            continue
        updates: dict = {}
        if org.get("portal_type") != "both":
            updates["portal_type"] = "both"
        if set(org.get("enabled_modules") or []) != enabled:
            updates["enabled_modules"] = sorted(enabled)
        if updates:
            await db.organizations.update_one({"id": org["id"]}, {"$set": updates})
            changed += 1
    return changed


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
