"""Iter 279 — reproduce & verify the CRM-only login fallback fix.

Creates a crm_users-only account (as Master Admin would in a CRM-capable
org), then exercises the standard /api/auth/login, /api/auth/forgot-password
and /api/auth/reset-password paths against the LIVE backend.
"""
import asyncio
import os
import secrets
import sys
import uuid

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from routes.crm_auth import crm_hash_password  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
BASE = "http://localhost:8001"

EMAIL = f"crm.only.{uuid.uuid4().hex[:8]}@pulsefitness.test"
PASSWORD = "CrmOnly123!"


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # Build a CRM-capable org.
    org_id = str(uuid.uuid4())
    await db.organizations.insert_one({
        "id": org_id, "name": "CRM Fallback Test Org", "account_type": "full",
        "portal_type": "crm", "modules": {"crm": {"enabled": True}},
    })
    uid = str(uuid.uuid4())
    await db.crm_users.insert_one({
        "id": uid, "email": EMAIL, "full_name": "CRM Only Manager",
        "password": crm_hash_password(PASSWORD), "organization_id": org_id,
        "role": "manager", "created_at": "2026-06-01T00:00:00+00:00",
    })
    print(f"[seed] crm_users-only account {EMAIL} (org {org_id})")

    results = {}
    async with httpx.AsyncClient(timeout=30) as hc:
        # 1. Standard login should now succeed via crm fallback.
        r = await hc.post(f"{BASE}/api/auth/login",
                          json={"email": EMAIL, "password": PASSWORD},
                          headers={"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")})
        results["login_status"] = r.status_code
        results["login_has_token"] = bool(r.json().get("token")) if r.status_code == 200 else False

        # 2. A users row must now exist (self-heal mirror).
        mirrored = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1, "role": 1})
        results["mirrored_users_row"] = mirrored

        # 3. Forgot-password must find the account (even before mirror existed).
        r2 = await hc.post(f"{BASE}/api/auth/forgot-password", json={"email": EMAIL})
        results["forgot_status"] = r2.status_code

        # 4. Simulate a reset token then reset-password; verify new password works.
        token = secrets.token_urlsafe(32)
        from datetime import datetime, timezone, timedelta
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": uid, "email": EMAIL,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "used": False, "created_at": datetime.now(timezone.utc).isoformat(),
        })
        new_pw = "ResetPass456!"
        r3 = await hc.post(f"{BASE}/api/auth/reset-password", json={"token": token, "password": new_pw})
        results["reset_status"] = r3.status_code
        # Login with the NEW password.
        r4 = await hc.post(f"{BASE}/api/auth/login",
                          json={"email": EMAIL, "password": new_pw},
                          headers={"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")})
        results["login_after_reset_status"] = r4.status_code

    # Cleanup
    await db.crm_users.delete_many({"id": uid})
    await db.users.delete_many({"id": uid})
    await db.organizations.delete_many({"id": org_id})
    await db.password_reset_tokens.delete_many({"user_id": uid})

    print("[results]")
    for k, v in results.items():
        print(f"  {k}: {v}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
