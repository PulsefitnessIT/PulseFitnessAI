"""Idempotent backfill: stamp siteless records onto each org's primary site.

Run:  python -m scripts.backfill_site_ids [memberships|crm|marketing ...]
With no args it backfills all isolated modules across all orgs.
"""
import asyncio
import sys

from utils.sites_isolation import backfill_all_orgs


async def main() -> None:
    modules = [a for a in sys.argv[1:]] or None
    summary = await backfill_all_orgs(modules=modules)
    total = sum(sum(c.values()) for c in summary.values())
    print(f"Backfilled {total} records across {len(summary)} organisation(s).")
    for org_id, changed in summary.items():
        print(f"  {org_id}: {changed}")


if __name__ == "__main__":
    asyncio.run(main())
