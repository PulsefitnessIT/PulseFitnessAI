"""Iter 216h78 — Engineer Roster (customer-side grants UI) sanity tests.

Frontend-driving E2E lives in Playwright tests; here we verify the
backend endpoints the panel calls still behave under the field shapes
the UI sends (`engineer_email`, `case_ids`, `scope`, `note`).
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://fitness-onboarding-3.preview.emergentagent.com"
).rstrip("/")

ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
    return client[os.environ.get("DB_NAME") or "test_database"]


class TestEngineerRosterEndpoints:
    def test_org_wide_grant(self, db, admin_headers):
        """Scope=org_wide → empty case_ids accepted."""
        r = requests.post(f"{BASE_URL}/api/customer-engineer-grants",
                          json={"engineer_email": "e1.agent@gymaxisai.com",
                                "case_ids": [], "scope": "org_wide",
                                "note": "Ad-hoc cardio repair contractor"},
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200
        g = r.json()["grant"]
        assert g["scope"] == "org_wide"
        assert g["active"] is True
        # cleanup
        db.partner_job_grants.delete_many({"id": g["id"]})

    def test_per_case_grant_with_ids(self, db, admin_headers):
        case_ids = [f"case-{uuid.uuid4()}", f"case-{uuid.uuid4()}"]
        r = requests.post(f"{BASE_URL}/api/customer-engineer-grants",
                          json={"engineer_email": "e1.agent@gymaxisai.com",
                                "case_ids": case_ids, "scope": "per_case", "note": ""},
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200
        g = r.json()["grant"]
        assert g["scope"] == "per_case"
        assert set(g["case_ids"]) == set(case_ids)
        db.partner_job_grants.delete_many({"id": g["id"]})

    def test_list_shows_active_and_revoked(self, db, admin_headers):
        # Create + revoke a grant
        cr = requests.post(f"{BASE_URL}/api/customer-engineer-grants",
                           json={"engineer_email": "e1.agent@gymaxisai.com",
                                 "case_ids": [], "scope": "org_wide", "note": ""},
                           headers=admin_headers, timeout=10)
        gid = cr.json()["grant"]["id"]
        requests.delete(f"{BASE_URL}/api/customer-engineer-grants/{gid}", headers=admin_headers, timeout=10)
        # List includes the revoked row
        lr = requests.get(f"{BASE_URL}/api/customer-engineer-grants", headers=admin_headers, timeout=10)
        rows = {r["id"]: r for r in lr.json()["grants"]}
        assert gid in rows
        assert rows[gid]["active"] is False
        assert rows[gid]["revoked_at"]
        db.partner_job_grants.delete_many({"id": gid})

    def test_revoking_unknown_id_returns_404(self, admin_headers):
        r = requests.delete(f"{BASE_URL}/api/customer-engineer-grants/no-such-id",
                            headers=admin_headers, timeout=10)
        assert r.status_code == 404
