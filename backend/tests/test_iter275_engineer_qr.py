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
        assert body["scan_url"].endswith(f"/r/eq/{eq_id}")

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


def test_link_pre_printed_sticker_code_and_resolve_publicly():
    """Iter 275b — engineers bind a pre-printed code to a machine; the
    public `/r/c/{code}` resolver + in-app scanner then find it; duplicate
    codes are rejected."""
    db = _db()
    email, uid, pw, org_id = _seed_engineer(db)
    eq1 = f"qr-eq-{uuid.uuid4().hex}"
    eq2 = f"qr-eq-{uuid.uuid4().hex}"
    code = f"FITFIX-{uuid.uuid4().hex[:6].upper()}"
    try:
        for eid, name in ((eq1, "Treadmill"), (eq2, "Rower")):
            db.equipment.insert_one({
                "id": eid, "organization_id": org_id, "user_id": uid,
                "created_by_id": uid, "name": name, "equipment_type": name,
                "customer_id": f"cust-{uuid.uuid4().hex}", "customer_name": "Gym",
            })

        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw},
                   headers=rate_limit_bypass_headers(), timeout=15)
        assert r.status_code == 200
        h = {"Authorization": f"Bearer {r.json()['token']}"}

        # Link the code to machine 1.
        set1 = s.post(f"{BASE}/api/svc/engineer/equipment/{eq1}/sticker-code",
                      json={"code": code}, headers=h, timeout=15)
        assert set1.status_code == 200, set1.text[:200]
        assert set1.json()["code_scan_url"].endswith(f"/r/c/{code}")

        # Public resolve by code (case-insensitive, no auth) → machine 1.
        pub = requests.get(f"{BASE}/api/public/r/c/{code.lower()}", timeout=15)
        assert pub.status_code == 200, pub.text[:200]
        assert pub.json()["id"] == eq1
        assert pub.json()["brand_name"] == "FitFix Ltd"

        # In-app scanner resolves the sticker code too.
        byc = s.get(f"{BASE}/api/svc/engineer/equipment/by-code/{code}", headers=h, timeout=15)
        assert byc.status_code == 200
        assert byc.json()["equipment"]["id"] == eq1

        # Same code on machine 2 → 409 (globally unique).
        dup = s.post(f"{BASE}/api/svc/engineer/equipment/{eq2}/sticker-code",
                     json={"code": code.lower()}, headers=h, timeout=15)
        assert dup.status_code == 409, dup.text[:200]

        # Unlink machine 1 → public resolver 404.
        clr = s.post(f"{BASE}/api/svc/engineer/equipment/{eq1}/sticker-code",
                     json={"code": ""}, headers=h, timeout=15)
        assert clr.status_code == 200
        assert requests.get(f"{BASE}/api/public/r/c/{code}", timeout=15).status_code == 404
    finally:
        db.equipment.delete_many({"id": {"$in": [eq1, eq2]}})
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
