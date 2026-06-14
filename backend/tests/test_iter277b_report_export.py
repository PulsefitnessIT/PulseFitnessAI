"""Iter 277b — Export / email the engineer performance report (PDF)."""
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


def test_engineer_report_pdf_and_email_validation():
    db = _db()
    org = f"rep-org-{uuid.uuid4().hex}"
    email = f"rep.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"repeng-{uuid.uuid4().hex}"
    pw = "RepEng123!"
    try:
        db.organizations.insert_one({"id": org, "name": "Pulse Bromley", "account_type": "pulse_pro"})
        db.users.insert_one({
            "id": uid, "email": email, "password": _hash(pw),
            "role": "engineer", "account_type": "engineer", "organization_id": org,
            "full_name": "Report Engineer", "active": True,
        })
        db.svc_engineers.insert_one({"id": uid, "organization_id": org, "full_name": "Report Engineer", "active": True})

        tok = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw},
                            headers=rate_limit_bypass_headers(), timeout=15).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}

        # PDF download → real PDF bytes.
        pdf = requests.get(f"{BASE}/api/svc/engineer/analytics/reports.pdf?range=90d", headers=h, timeout=30)
        assert pdf.status_code == 200, pdf.text[:200]
        assert pdf.headers.get("content-type") == "application/pdf"
        assert pdf.content[:4] == b"%PDF"
        assert len(pdf.content) > 800

        # Email with an invalid recipient → 400 (guard runs before send).
        bad = requests.post(f"{BASE}/api/svc/engineer/analytics/reports/email",
                            json={"range": "90d", "to": "not-an-email"}, headers=h, timeout=30)
        assert bad.status_code == 400, bad.text[:200]
    finally:
        db.svc_engineers.delete_many({"organization_id": org})
        db.organizations.delete_one({"id": org})
        db.users.delete_many({"email": email})
