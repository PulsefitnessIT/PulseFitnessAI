"""Iter 278f — one-click "fix module access" from the People drawer.

`POST /api/master-admin/users/{id}/module-access/{module}/grant` must:
  • enable the module for the ORG when org-level is off, and
  • clear a blocking per-staff override when the org has it but the user
    was revoked,
returning refreshed diagnostics. Uses the platform master admin account.
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PW = "MasterAdmin123!"


def _db():
    url = os.environ.get("MONGO_URL")
    name = os.environ.get("DB_NAME")
    if not url or not name:
        pytest.skip("MONGO_URL/DB_NAME not set")
    return MongoClient(url)[name]


def _admin_headers():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
                      headers=rate_limit_bypass_headers(), timeout=15).json()
    tok = r.get("token") or r.get("access_token")
    if not tok:
        pytest.skip("master admin account not available")
    return {"Authorization": f"Bearer {tok}"}


def _crm_row(payload):
    return next(m for m in payload["modules"] if m["key"] == "crm")


def test_grant_enables_org_and_restores_user():
    db = _db()
    org_id = f"tmp-grant-{uuid.uuid4().hex}"
    uid = f"tmp-guser-{uuid.uuid4().hex}"
    db.organizations.insert_one({
        "id": org_id, "name": "Grant Test Co", "account_type": "pulse_pro",
        "modules": {"operations": {"enabled": True, "tier": "pro"}},  # CRM OFF
    })
    db.users.insert_one({
        "id": uid, "email": f"{uid}@ex.com", "role": "manager",
        "is_master_admin": False, "organization_id": org_id,
        "full_name": "Grant Mgr", "active": True,
    })
    try:
        h = _admin_headers()

        # Before: CRM org-off → diagnostics offers the grant_org fix.
        before = requests.get(f"{BASE}/api/master-admin/users/{uid}/module-access", headers=h, timeout=15).json()
        row = _crm_row(before)
        assert row["org_enabled"] is False and row["fix_action"] == "grant_org"

        # Grant → org CRM enabled, user now has access.
        after = requests.post(f"{BASE}/api/master-admin/users/{uid}/module-access/crm/grant", headers=h, timeout=15).json()
        assert after["result"] == "granted_org"
        row = _crm_row(after)
        assert row["org_enabled"] is True and row["user_access"] is True and row["fix_action"] is None

        # Org doc actually updated + legacy fields synced.
        org = db.organizations.find_one({"id": org_id}, {"_id": 0})
        assert org["modules"]["crm"]["enabled"] is True
        assert "crm" in org["enabled_modules"]

        # Now revoke at user level and verify the restore path.
        db.users.update_one({"id": uid}, {"$set": {"module_overrides": {"crm": False}}})
        diag = requests.get(f"{BASE}/api/master-admin/users/{uid}/module-access", headers=h, timeout=15).json()
        row = _crm_row(diag)
        assert row["user_access"] is False and row["fix_action"] == "restore_user"

        restored = requests.post(f"{BASE}/api/master-admin/users/{uid}/module-access/crm/grant", headers=h, timeout=15).json()
        assert restored["result"] == "restored_user"
        assert _crm_row(restored)["user_access"] is True
    finally:
        db.organizations.delete_many({"id": org_id})
        db.users.delete_many({"id": uid})
