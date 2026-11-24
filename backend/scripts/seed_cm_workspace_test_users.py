"""Seed fictional Pulse Fitness Ltd staff for Contract Management workspace tests.

Run: cd /app/backend && PYTHONPATH=/app/backend python scripts/seed_cm_workspace_test_users.py
Idempotent; resets passwords and explicit workspace roles each run.
"""
import asyncio
from datetime import datetime, timezone

from utils.database import db
from utils.auth import hash_password

PASSWORD = "CmTest2026!"
USERS = [
    ("cm-test-coord", "cm.coordinator@pulsefitness.test", "Casey Coordinator", "contract_coordinator", True),
    ("cm-test-sales", "cm.sales@pulsefitness.test", "Sam Sales", None, True),
    ("cm-test-asm", "cm.aftersales@pulsefitness.test", "Alex Aftersales", "aftersales_manager", True),
    ("cm-test-fin", "cm.finance@pulsefitness.test", "Fran Finance", "finance", True),
    ("cm-test-none", "cm.noaccess@pulsefitness.test", "Nico NoCRM", None, False),
    ("cm-test-admin", "cm.admin@pulsefitness.test", "Ada Admin", "admin", True),
]


async def main():
    op = await db.organizations.find_one({"is_operator_company": True}, {"_id": 0, "id": 1})
    for uid, email, name, ws_role, crm in USERS:
        await db.users.update_one({"id": uid}, {"$set": {
            "id": uid, "email": email, "full_name": name, "role": "staff",
            "organization_id": op["id"], "password": hash_password(PASSWORD),
            "must_change_password": False, "crm_workspace_role": ws_role,
            "module_overrides": {"crm": crm, "operations": False, "memberships": False, "marketing": False},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }}, upsert=True)
    print("seeded", len(USERS), "users; password:", PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
