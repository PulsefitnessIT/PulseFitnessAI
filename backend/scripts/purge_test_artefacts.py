#!/usr/bin/env python3
"""
Iter 215eu (Feb 2026) — bulk-purge test artefacts from the master-admin
DB. Identifies orgs whose name matches well-known test-suite patterns
(`TEST_*`, `Test Org`, `AddrTest`, `Address Test Co`, duplicate
`GymAxis AI`) and either ARCHIVES them then HARD-DELETES, or skips with
a clear log line.

Protected (never touched):
  • account_type == 'gymaxis_admin'   (master admin org)
  • name == 'Pulse Fitness'           (real customer org)

Idempotent — safe to re-run. Runs against the LIVE preview DB via the
master-admin API endpoints (so cascading site / user / CRM cleanup
goes through the same paths the UI would).
"""
import asyncio
import os
import re
import sys

import httpx

API_BASE = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://engineer-hub-114.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("PURGE_ADMIN_EMAIL", "admin@gymaxisai.com")
# Iter 216bo — read the dev master-admin password from env so the script
# can run unattended without a literal ending up in repository forks.
# Falls back to the documented dev password (see /app/memory/test_credentials.md)
# when run interactively in the local dev container.
ADMIN_PASSWORD = os.environ.get("PURGE_ADMIN_PASSWORD") or os.environ.get(
    "MASTER_ADMIN_PASSWORD",
    "MasterAdmin123!",
)

PROTECTED_ACCOUNT_TYPES = {"gymaxis_admin"}
PROTECTED_NAMES = {"Pulse Fitness"}

TEST_PATTERNS = [
    re.compile(r"^TEST[_ ]", re.IGNORECASE),
    re.compile(r"\bTest\s+Org", re.IGNORECASE),
    re.compile(r"\bAddr[Tt]est", re.IGNORECASE),
    re.compile(r"^Address Test", re.IGNORECASE),
    re.compile(r"DefaultCountry", re.IGNORECASE),
    re.compile(r"^Onboard\s?Test", re.IGNORECASE),
]


async def main():
    async with httpx.AsyncClient(timeout=120.0) as c:
        # 1. login
        r = await c.post(f"{API_BASE}/auth/login",
                         json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        r.raise_for_status()
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        # 2. list orgs
        r = await c.get(f"{API_BASE}/master-admin/organizations", headers=h)
        orgs = r.json().get("organizations", [])

        keep, to_delete = [], []
        for o in orgs:
            name = (o.get("name") or "").strip()
            acct = o.get("account_type") or ""
            if acct in PROTECTED_ACCOUNT_TYPES or name in PROTECTED_NAMES:
                keep.append(o)
                continue
            if any(p.search(name) for p in TEST_PATTERNS) or name == "GymAxis AI":
                to_delete.append(o)
                continue
            keep.append(o)

        print(f"Keeping {len(keep)} orgs:")
        for o in keep:
            print(f"  ✓ {o['id'][:8]}  {o['name']}")
        print(f"\nDeleting {len(to_delete)} test artefacts:")
        for o in to_delete:
            print(f"  ✗ {o['id'][:8]}  {o['name']}")
        if not to_delete:
            print("\nNothing to do.")
            return

        # 3. archive then hard-delete
        archived, deleted, failed = 0, 0, 0
        for o in to_delete:
            oid = o["id"]
            try:
                # Archive (idempotent — accepts already-archived)
                r = await c.put(f"{API_BASE}/master-admin/organizations/{oid}/status",
                                json={"status": "archived"}, headers=h)
                if r.status_code == 200:
                    archived += 1
                # Hard delete from archive
                r = await c.delete(f"{API_BASE}/master-admin/archive/{oid}", headers=h)
                if r.status_code == 200:
                    deleted += 1
                    print(f"  ✓ Purged {o['name']} → {r.json().get('purged', {})}")
                else:
                    failed += 1
                    print(f"  ✗ Failed {o['name']}: {r.status_code} {r.text[:200]}")
            except httpx.HTTPError as e:
                failed += 1
                print(f"  ✗ Error on {o['name']}: {e}")

        print(f"\nDone. archived={archived} deleted={deleted} failed={failed}")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
