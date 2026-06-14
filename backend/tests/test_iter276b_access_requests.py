"""Iter 276b — Engineer "Request access" to operator machine history.

Flow: an unrelated engineer requests access to an operator's machine →
operator admin sees it → approves → engineer is granted svc_engineers
membership → machine-history now returns 200 (access=operator_engineer).
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()


def _db():
    url = os.environ.get("MONGO_URL")
    name = os.environ.get("DB_NAME")
    if not url or not name:
        pytest.skip("MONGO_URL/DB_NAME not set")
    return MongoClient(url)[name]


def _hash(pw):
    from utils.auth import hash_password
    return hash_password(pw)


def _login(email, pw):
    return requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw},
                         headers=rate_limit_bypass_headers(), timeout=15).json()["token"]


def test_request_access_approve_grants_history():
    db = _db()
    op_org = f"op-org-{uuid.uuid4().hex}"
    eq_id = f"op-eq-{uuid.uuid4().hex}"
    admin_email = f"opadmin.{uuid.uuid4().hex[:8]}@example.com"
    admin_uid = f"opadmin-{uuid.uuid4().hex}"
    eng_email = f"reqeng.{uuid.uuid4().hex[:8]}@example.com"
    eng_uid = f"reqeng-{uuid.uuid4().hex}"
    eng_org = f"reqeng-org-{uuid.uuid4().hex}"
    pw = "AccessReq123!"
    try:
        db.organizations.insert_many([
            {"id": op_org, "name": "Pulse Sutton", "account_type": "pulse_pro"},
            {"id": eng_org, "name": "FixIt (Engineer)", "account_type": "partner_engineer",
             "is_engineer_personal_org": True},
        ])
        db.users.insert_many([
            {"id": admin_uid, "email": admin_email, "password": _hash(pw),
             "role": "owner", "organization_id": op_org, "full_name": "Op Admin", "active": True},
            {"id": eng_uid, "email": eng_email, "password": _hash(pw),
             "role": "engineer_partner", "account_type": "partner_engineer",
             "is_partner_engineer": True, "organization_id": eng_org,
             "full_name": "Reg Engineer", "active": True},
        ])
        db.partner_engineers.insert_one({
            "id": f"pe-{uuid.uuid4().hex}", "user_id": eng_uid, "email": eng_email,
            "status": "approved", "company_name": "FixIt Ltd",
        })
        db.equipment.insert_one({
            "id": eq_id, "organization_id": op_org, "name": "Chest Press",
            "equipment_type": "Strength", "manufacturer": "Hammer",
        })

        eng_tok = _login(eng_email, pw)
        eh = {"Authorization": f"Bearer {eng_tok}"}

        # Unrelated engineer is blocked.
        assert requests.get(f"{BASE}/api/svc/engineer/machine-history/{eq_id}",
                            headers=eh, timeout=15).status_code == 403

        # Request access.
        r = requests.post(f"{BASE}/api/svc/engineer/machine-history/{eq_id}/request-access",
                          json={"message": "I service this site"}, headers=eh, timeout=15)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["status"] == "pending"

        # Dedupe — second request returns the same pending.
        r2 = requests.post(f"{BASE}/api/svc/engineer/machine-history/{eq_id}/request-access",
                           json={}, headers=eh, timeout=15)
        assert r2.status_code == 200
        assert db.svc_access_requests.count_documents(
            {"organization_id": op_org, "engineer_user_id": eng_uid, "status": "pending"}) == 1

        # Operator admin sees the pending request.
        ad_tok = _login(admin_email, pw)
        ah = {"Authorization": f"Bearer {ad_tok}"}
        lst = requests.get(f"{BASE}/api/svc/access-requests", headers=ah, timeout=15)
        assert lst.status_code == 200
        reqs = lst.json()["requests"]
        assert len(reqs) == 1 and reqs[0]["engineer_name"] == "Reg Engineer"
        req_id = reqs[0]["id"]

        # Approve → membership granted.
        ap = requests.post(f"{BASE}/api/svc/access-requests/{req_id}/approve", headers=ah, timeout=15)
        assert ap.status_code == 200
        assert db.svc_engineers.find_one({"id": eng_uid, "organization_id": op_org}) is not None

        # Engineer now has access.
        hist = requests.get(f"{BASE}/api/svc/engineer/machine-history/{eq_id}", headers=eh, timeout=15)
        assert hist.status_code == 200
        assert hist.json()["access"] == "operator_engineer"

        # Re-approving a decided request → 409.
        assert requests.post(f"{BASE}/api/svc/access-requests/{req_id}/approve",
                             headers=ah, timeout=15).status_code == 409

        # Already-has-access engineer requesting again → 400.
        assert requests.post(f"{BASE}/api/svc/engineer/machine-history/{eq_id}/request-access",
                            json={}, headers=eh, timeout=15).status_code == 400
    finally:
        db.svc_access_requests.delete_many({"organization_id": op_org})
        db.svc_engineers.delete_many({"organization_id": op_org})
        db.equipment.delete_many({"id": eq_id})
        db.svc_notifications.delete_many({"organization_id": op_org})
        db.organizations.delete_many({"id": {"$in": [op_org, eng_org]}})
        db.users.delete_many({"email": {"$in": [admin_email, eng_email]}})
        db.partner_engineers.delete_many({"email": eng_email})
