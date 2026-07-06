"""Tests for 3 production bug fixes (Jan 2026):
1) Master admin exempt from login rate limit (non-master still limited)
2) Module toggle on legacy-bool org normalizes and returns 200
3) User creation routes to Service Portal based on enabled modules, not stale portal_type
"""
import os
import time
import uuid
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"
BYPASS = "test-bypass-secret-for-ci-runs-only-2026"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def master_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
        headers={"X-RateLimit-Bypass": BYPASS},
        timeout=30,
    )
    assert r.status_code == 200, f"Master login failed: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# =========================================================
# Fix 1: rate-limit exemption for master admin
# =========================================================
class TestFix1MasterRateLimitExemption:
    def test_master_never_rate_limited(self):
        # 8 rapid wrong-password attempts — must all be 401, never 429
        for i in range(8):
            r = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": MASTER_EMAIL, "password": "wrong-password-xyz"},
                timeout=15,
            )
            assert r.status_code == 401, (
                f"attempt {i}: expected 401, got {r.status_code} {r.text[:200]}"
            )
        # Correct password → 200
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200, f"Master correct login: {r.status_code} {r.text}"
        assert "token" in r.json() or "access_token" in r.json()

    def test_non_master_is_rate_limited(self):
        # random email — 5 rapid wrong logins → 429
        rand_email = f"zz-notreal-{uuid.uuid4().hex[:8]}@zz.test"
        got_429 = False
        statuses = []
        for i in range(7):
            r = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": rand_email, "password": "whatever"},
                timeout=15,
            )
            statuses.append(r.status_code)
            if r.status_code == 429:
                got_429 = True
                break
        assert got_429, f"Expected 429 for non-master, got sequence: {statuses}"


# =========================================================
# Fix 2: module toggle on legacy-bool org
# =========================================================
class TestFix2LegacyBoolModuleToggle:
    def test_legacy_bool_toggle_normalizes(self, master_token, db):
        org_id = f"zz-legacybool-{uuid.uuid4().hex[:8]}"
        # Insert org with legacy bare-boolean modules
        _run(db.organizations.insert_one({
            "id": org_id,
            "name": "ZZ Legacy Bool Org",
            "portal_type": "service_portal",
            "account_type": "pulse_pro",
            "modules": {"operations": True},
            "enabled_modules": ["operations"],
            "status": "active",
        }))
        try:
            hdr = {
                "Authorization": f"Bearer {master_token}",
                "X-RateLimit-Bypass": BYPASS,
            }
            body = {
                "modules": {
                    "operations": {"enabled": True, "tier": "pro"},
                    "crm": {"enabled": True, "tier": "pro"},
                }
            }
            r = requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/features",
                json=body, headers=hdr, timeout=30,
            )
            assert r.status_code == 200, f"features PUT: {r.status_code} {r.text[:400]}"

            # Re-fetch org
            org = _run(db.organizations.find_one({"id": org_id}))
            assert org is not None
            mods = org.get("modules") or {}
            assert isinstance(mods.get("operations"), dict), f"operations not normalized: {mods}"
            assert mods["operations"].get("enabled") is True
            assert isinstance(mods.get("crm"), dict), f"crm not normalized: {mods}"
            assert mods["crm"].get("enabled") is True
            enabled = org.get("enabled_modules") or []
            assert "operations" in enabled and "crm" in enabled, f"enabled_modules={enabled}"
            # portal_type should become 'both' when CRM + operations both on
            assert org.get("portal_type") == "both", f"portal_type={org.get('portal_type')}"

            # Toggle crm off → persists
            body2 = {"modules": {"operations": {"enabled": True, "tier": "pro"},
                                   "crm": {"enabled": False, "tier": "pro"}}}
            r2 = requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/features",
                json=body2, headers=hdr, timeout=30,
            )
            assert r2.status_code == 200, f"toggle off: {r2.status_code} {r2.text[:400]}"
            org2 = _run(db.organizations.find_one({"id": org_id}))
            assert "crm" not in (org2.get("enabled_modules") or [])
        finally:
            _run(db.organizations.delete_one({"id": org_id}))


# =========================================================
# Fix 3: user creation routes to Service Portal for operator org
# =========================================================
class TestFix3UserCreationRouting:
    def test_operator_org_user_lands_in_service_portal(self, master_token, db):
        org_id = f"zz-oporg-{uuid.uuid4().hex[:8]}"
        _run(db.organizations.insert_one({
            "id": org_id,
            "name": "ZZ Op Org",
            "portal_type": "crm",  # stale/incorrect
            "account_type": "pulse_pro",
            "enabled_modules": ["operations"],
            "modules": {"operations": {"enabled": True, "tier": "pro"}},
            "status": "active",
        }))
        email = f"zz-user-{uuid.uuid4().hex[:8]}@zz.test"
        hdr = {
            "Authorization": f"Bearer {master_token}",
            "X-RateLimit-Bypass": BYPASS,
        }
        try:
            payload = {
                "email": email,
                "full_name": "ZZ Tester",
                "role": "manager",
            }
            r = requests.post(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/users",
                json=payload, headers=hdr, timeout=30,
            )
            assert r.status_code in (200, 201), f"user POST: {r.status_code} {r.text[:400]}"
            data = r.json()
            portal = (data.get("portal") or data.get("target_portal") or "").lower()
            assert "service" in portal, f"portal response wrong: {data}"

            # verify db.users has row
            u = _run(db.users.find_one({"email": email}))
            assert u is not None, "user not found in db.users (Service Portal collection)"
        finally:
            _run(db.organizations.delete_one({"id": org_id}))
            _run(db.users.delete_many({"email": email}))
            _run(db.crm_users.delete_many({"email": email}))
