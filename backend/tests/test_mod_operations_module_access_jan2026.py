"""
Tests for the 'MOD Operations' module-access grant/revoke catalog and the
BFPO staff gate that now honours module_overrides.mod_operations.

Strategy:
  * Master-admin routes are MFA-protected → we invoke the route functions
    in-process with a synthetic user dict (is_master_admin=True), which is
    exactly how the main agent self-tested.
  * BFPO HTTP endpoints are exercised via requests against the public URL
    with real seeded credentials (bfpo staff / bfpo engineer), plus a
    granted-but-non-bfpo user (owner@isodemo.com) whose module_overrides
    flag we flip directly in Mongo for the test (cleaned up afterwards).
"""
import os
import sys
import asyncio
import time
import requests
import pytest

sys.path.insert(0, "/app/backend")

from utils.database import db  # noqa: E402
from routes.master_admin_users import (  # noqa: E402
    get_user_module_access,
    grant_user_module_access,
    revoke_user_module_access,
)
from fastapi import HTTPException  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
RL_BYPASS = {"x-ratelimit-bypass": "test-bypass-secret-for-ci-runs-only-2026"}
TARGET_USER_ID = "3355e0bb-e71a-4811-85e9-1c08c06dc362"  # Lee Somers (Pulse staff)

ADMIN_USER = {
    "id": "master-admin",
    "email": "admin@pulsefitness.com",
    "is_master_admin": True,
    "_jwt_mfa_verified": True,
}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────
# Master-admin module-access catalog
# ─────────────────────────────────────────────────────────────
class TestModuleAccessCatalog:

    def test_catalog_has_mod_operations_row(self):
        # ensure clean state on target
        _run(db.users.update_one({"id": TARGET_USER_ID},
                                 {"$unset": {"module_overrides.mod_operations": ""}}))
        payload = _run(get_user_module_access(TARGET_USER_ID, user=ADMIN_USER))
        modules = payload["modules"]
        row = next((m for m in modules if m["key"] == "mod_operations"), None)
        assert row is not None, "mod_operations row missing from catalog"
        assert row["label"] == "MOD Operations"
        if not payload.get("is_privileged"):
            assert row["user_access"] is False
            assert row["fix_action"] == "grant_flag"

    def test_grant_flow_sets_override_and_row_flips(self):
        # grant
        p = _run(grant_user_module_access(TARGET_USER_ID, "mod_operations", user=ADMIN_USER))
        assert p.get("result") == "granted_flag"
        row = next(m for m in p["modules"] if m["key"] == "mod_operations")
        assert row["user_access"] is True
        assert row["fix_action"] == "revoke_flag"
        # DB check
        u = _run(db.users.find_one({"id": TARGET_USER_ID}, {"_id": 0, "module_overrides": 1}))
        assert (u.get("module_overrides") or {}).get("mod_operations") is True

    def test_revoke_flow_clears_override_and_row_flips(self):
        # revoke (scope defaults to user – body optional)
        p = _run(revoke_user_module_access(TARGET_USER_ID, "mod_operations",
                                           body={}, user=ADMIN_USER))
        row = next(m for m in p["modules"] if m["key"] == "mod_operations")
        assert row["user_access"] is False
        assert row["fix_action"] == "grant_flag"
        u = _run(db.users.find_one({"id": TARGET_USER_ID}, {"_id": 0, "module_overrides": 1}))
        assert (u.get("module_overrides") or {}).get("mod_operations") is False

    def test_bogus_module_key_returns_400_on_grant(self):
        with pytest.raises(HTTPException) as ei:
            _run(grant_user_module_access(TARGET_USER_ID, "not_a_module", user=ADMIN_USER))
        assert ei.value.status_code == 400

    def test_bogus_module_key_returns_400_on_revoke(self):
        with pytest.raises(HTTPException) as ei:
            _run(revoke_user_module_access(TARGET_USER_ID, "not_a_module",
                                           body={}, user=ADMIN_USER))
        assert ei.value.status_code == 400


# ─────────────────────────────────────────────────────────────
# BFPO staff-endpoint gate
# ─────────────────────────────────────────────────────────────
def _login(email, password, portal=None):
    body = {"email": email, "password": password}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE}/api/auth/login", json=body, headers=RL_BYPASS, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def bfpo_staff_token():
    return _login("staff@bfpo.pulsefitness.test", "Bfpo123!", portal="mod")


@pytest.fixture(scope="module")
def bfpo_engineer_token():
    return _login("engineer.gib@bfpo.pulsefitness.test", "Bfpo123!", portal="mod")


@pytest.fixture(scope="module")
def iso_owner_token():
    # owner@isodemo.com – Pulse operator user with NO bfpo_role.
    return _login("owner@isodemo.com", "IsoDemo123!")


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


STAFF_ENDPOINTS = ["/api/bfpo/staff/team", "/api/bfpo/staff/territories", "/api/bfpo/sites"]


class TestBfpoGate:

    def test_real_bfpo_staff_can_hit_staff_endpoints(self, bfpo_staff_token):
        for ep in STAFF_ENDPOINTS:
            r = requests.get(f"{BASE}{ep}", headers=_hdr(bfpo_staff_token), timeout=30)
            assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"

    def test_engineer_is_not_staff_but_can_hit_engineer_endpoints(self, bfpo_engineer_token):
        # engineer must NOT resolve as staff
        r = requests.get(f"{BASE}/api/bfpo/staff/team",
                         headers=_hdr(bfpo_engineer_token), timeout=30)
        assert r.status_code == 403
        # but engineer endpoints should work
        for ep in ["/api/bfpo/me", "/api/bfpo/jobs", "/api/bfpo/sites"]:
            r = requests.get(f"{BASE}{ep}", headers=_hdr(bfpo_engineer_token), timeout=30)
            assert r.status_code == 200, f"engineer {ep}: {r.status_code} {r.text[:200]}"

    def test_non_bfpo_user_without_flag_gets_403(self, iso_owner_token):
        # sanity: ensure flag is OFF first
        _run(db.users.update_one({"email": "owner@isodemo.com"},
                                 {"$unset": {"module_overrides.mod_operations": ""}}))
        for ep in STAFF_ENDPOINTS:
            r = requests.get(f"{BASE}{ep}", headers=_hdr(iso_owner_token), timeout=30)
            assert r.status_code == 403, f"{ep} expected 403 got {r.status_code}"

    def test_non_bfpo_user_with_mod_operations_flag_is_treated_as_staff(self, iso_owner_token):
        # Flip flag ON in Mongo
        _run(db.users.update_one({"email": "owner@isodemo.com"},
                                 {"$set": {"module_overrides.mod_operations": True}}))
        try:
            for ep in STAFF_ENDPOINTS:
                r = requests.get(f"{BASE}{ep}", headers=_hdr(iso_owner_token), timeout=30)
                assert r.status_code == 200, (
                    f"{ep}: got {r.status_code} {r.text[:200]} — the granted-flag "
                    f"user should have staff access to /api/bfpo/staff/*")
        finally:
            # Clean up regardless of outcome
            _run(db.users.update_one({"email": "owner@isodemo.com"},
                                     {"$unset": {"module_overrides.mod_operations": ""}}))


def teardown_module(module):
    # Final safety cleanup — ensure we don't leave state behind.
    _run(db.users.update_one({"id": TARGET_USER_ID},
                             {"$unset": {"module_overrides.mod_operations": ""}}))
    _run(db.users.update_one({"email": "owner@isodemo.com"},
                             {"$unset": {"module_overrides.mod_operations": ""}}))
