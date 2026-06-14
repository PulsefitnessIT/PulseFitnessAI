"""Iter 275 — Engineer QR fault-logging for off-platform customers.

An independent engineer prints a branded QR sticker for a customer's
machine. The customer (NOT on the operations portal) scans it, reports a
fault on the public `/api/public/r/{id}` endpoint, and a case is created
STRAIGHT in the engineer's queue (`svc_cases`, assigned to the engineer).
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


def _seed_engineer(db):
    email = f"qreng.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"qreng-{uuid.uuid4().hex}"
    pw = "QrEngPass123!"
    org_id = f"qreng-org-{uuid.uuid4().hex}"
    db.users.insert_one({
        "id": uid, "email": email, "password": _hash(pw),
        "role": "engineer_partner", "account_type": "partner_engineer",
        "is_partner_engineer": True, "organization_id": org_id,
        "full_name": "QR Engineer", "active": True,
    })
    db.organizations.insert_one({
        "id": org_id, "name": "QR Engineer (Engineer)",
        "account_type": "partner_engineer", "country_code": "GB",
        "currency": "GBP", "is_engineer_personal_org": True,
    })
    db.partner_engineers.insert_one({
        "id": f"pe-{uuid.uuid4().hex}", "email": email, "user_id": uid,
        "status": "approved", "company_name": "FitFix Ltd",
        "referral_code": f"QR{uuid.uuid4().hex[:6].upper()}",
        "country_code": "GB", "created_at": "2026-01-01T00:00:00+00:00",
    })
    return email, uid, pw, org_id


def test_qr_card_is_branded_and_public_fault_creates_assigned_case():
    db = _db()
    email, uid, pw, org_id = _seed_engineer(db)
    eq_id = f"qr-eq-{uuid.uuid4().hex}"
    try:
        # Customer-linked machine in the engineer's org.
        db.equipment.insert_one({
            "id": eq_id, "organization_id": org_id, "user_id": uid,
            "created_by_id": uid, "name": "Treadmill #1",
            "equipment_type": "Treadmill", "manufacturer": "Life Fitness",
            "model": "Integrity DX", "serial_number": "LF-QR-1",
            "customer_id": f"cust-{uuid.uuid4().hex}", "customer_name": "Riverside Gym",
        })

        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw},
                   headers=rate_limit_bypass_headers(), timeout=15)
        assert r.status_code == 200, r.text[:200]
        tok = r.json().get("token")
        h = {"Authorization": f"Bearer {tok}"}

        # qr-label: engineer's company name + /r/{id} scan URL.
        lbl = s.get(f"{BASE}/api/svc/engineer/equipment/{eq_id}/qr-label", headers=h, timeout=15)
        assert lbl.status_code == 200, lbl.text[:150]
        body = lbl.json()
        assert body["brand_name"] == "FitFix Ltd"
        assert body["scan_url"].endswith(f"/r/{eq_id}")

        # qr-card: a real PNG.
        card = s.get(f"{BASE}/api/svc/engineer/equipment/{eq_id}/qr-card?size=62x35", headers=h, timeout=20)
        assert card.status_code == 200
        assert card.headers.get("content-type") == "image/png"
        assert card.content[:8] == b"\x89PNG\r\n\x1a\n"

        # Public machine info (NO auth) — branded.
        pub = requests.get(f"{BASE}/api/public/r/{eq_id}", timeout=15)
        assert pub.status_code == 200
        assert pub.json()["brand_name"] == "FitFix Ltd"

        # Public fault report (NO auth) → assigned case in engineer's queue.
        rep = requests.post(
            f"{BASE}/api/public/r/{eq_id}/report-fault",
            data={"description": "Belt slipping under load", "severity": "critical",
                  "reporter_name": "Jane Customer", "reporter_phone": "07700900111"},
            timeout=45,
        )
        assert rep.status_code == 200, rep.text[:200]
        ref = rep.json()["reference"]
        assert ref

        case = db.svc_cases.find_one({"organization_id": org_id, "reference": ref}, {"_id": 0})
        assert case is not None
        assert case["assigned_engineer_id"] == uid
        assert case["status"] == "assigned"
        assert case["priority"] == "p1"  # critical → p1
        assert case["asset_id"] == eq_id
        assert case["source"] == "qr_scan"
        assert case["source_meta"]["reporter_name"] == "Jane Customer"
    finally:
        db.svc_cases.delete_many({"organization_id": org_id})
        db.svc_case_events.delete_many({"organization_id": org_id})
        db.equipment.delete_many({"id": eq_id})
        db.organizations.delete_one({"id": org_id})
        db.users.delete_many({"email": email})
        db.partner_engineers.delete_many({"email": email})


def test_public_report_requires_description_and_name():
    db = _db()
    email, uid, pw, org_id = _seed_engineer(db)
    eq_id = f"qr-eq-{uuid.uuid4().hex}"
    try:
        db.equipment.insert_one({
            "id": eq_id, "organization_id": org_id, "user_id": uid,
            "created_by_id": uid, "name": "Bike", "equipment_type": "Exercise Bike",
            "customer_id": "c1", "customer_name": "Gym",
        })
        # Missing name → rejected (my 400, or FastAPI 422).
        r1 = requests.post(f"{BASE}/api/public/r/{eq_id}/report-fault",
                           data={"description": "broken", "reporter_name": ""}, timeout=20)
        assert r1.status_code in (400, 422)
        # Missing description → 422 (Form required) or 400.
        r2 = requests.post(f"{BASE}/api/public/r/{eq_id}/report-fault",
                           data={"reporter_name": "Bob"}, timeout=20)
        assert r2.status_code in (400, 422)
        # Unknown equipment → 404.
        r3 = requests.post(f"{BASE}/api/public/r/does-not-exist/report-fault",
                           data={"description": "x", "reporter_name": "Bob"}, timeout=20)
        assert r3.status_code == 404
    finally:
        db.equipment.delete_many({"id": eq_id})
        db.organizations.delete_one({"id": org_id})
        db.users.delete_many({"email": email})
        db.partner_engineers.delete_many({"email": email})
