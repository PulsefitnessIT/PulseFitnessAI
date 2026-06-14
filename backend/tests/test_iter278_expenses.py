"""Iter 278 — Expenses Tracker & Receipt Scanner backend regression.

Covers: config seeding (country rules + categories), the solo-engineer
auto-approve path, the operator submit→approve→reimburse workflow, mileage
amount on create, grouped reports, and the finance CSV export + lock.
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


def _mk_org_user(db, *, role, account_type, solo=False, country="United Kingdom"):
    org = f"exp-org-{uuid.uuid4().hex}"
    email = f"exp.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"expu-{uuid.uuid4().hex}"
    pw = "ExpTest123!"
    org_doc = {"id": org, "name": "Expense Test Co", "account_type": account_type, "country": country}
    if solo:
        org_doc["is_engineer_personal_org"] = True
    db.organizations.insert_one(org_doc)
    db.users.insert_one({
        "id": uid, "email": email, "password": _hash(pw),
        "role": role, "account_type": account_type, "organization_id": org,
        "full_name": "Expense Tester", "active": True,
    })
    return org, uid, email, pw


def test_config_seeds_rules_and_categories():
    db = _db()
    org, uid, email, pw = _mk_org_user(db, role="owner", account_type="service_provider")
    try:
        h = {"Authorization": f"Bearer {_login(email, pw)}"}
        cfg = requests.get(f"{BASE}/api/expenses/config", headers=h, timeout=15).json()
        assert cfg["can_review"] is True                      # owner reviews
        assert cfg["approval_mode"] == "on"                   # operator org
        assert len(cfg["country_rules"]) >= 3
        assert len(cfg["categories"]) >= 10
        assert cfg["default_country_code"] == "GB"
    finally:
        for c in ("expenses", "expense_country_rules", "expense_categories", "expense_events"):
            db[c].delete_many({"organization_id": org})
        db.organizations.delete_one({"id": org})
        db.users.delete_many({"email": email})


def test_solo_engineer_autoapproves():
    db = _db()
    org, uid, email, pw = _mk_org_user(db, role="engineer", account_type="partner_engineer", solo=True)
    try:
        h = {"Authorization": f"Bearer {_login(email, pw)}"}
        cfg = requests.get(f"{BASE}/api/expenses/config", headers=h, timeout=15).json()
        assert cfg["approval_mode"] == "off"
        assert cfg["can_review"] is False
        # submit=True on a solo org → auto-approved.
        r = requests.post(f"{BASE}/api/expenses", headers=h, timeout=15, json={
            "expense_type": "manual", "category_name": "Parking", "merchant": "NCP",
            "transaction_date": "2026-06-10", "gross_amount": 12.0, "submit": True})
        assert r.status_code == 200, r.text[:200]
        assert r.json()["status"] == "approved"
    finally:
        for c in ("expenses", "expense_country_rules", "expense_categories", "expense_events"):
            db[c].delete_many({"organization_id": org})
        db.organizations.delete_one({"id": org})
        db.users.delete_many({"email": email})


def test_operator_workflow_and_mileage_and_export():
    db = _db()
    org, uid, email, pw = _mk_org_user(db, role="owner", account_type="service_provider")
    try:
        h = {"Authorization": f"Bearer {_login(email, pw)}"}

        # mileage amount computed on create (45p/mi UK personal car × 10mi).
        ml = requests.post(f"{BASE}/api/expenses", headers=h, timeout=15, json={
            "expense_type": "mileage",
            "mileage": {"distance": 10, "unit": "mi", "vehicle_type": "personal_car",
                        "rate": 0.45, "calculated_amount": 4.5}}).json()
        assert ml["gross_amount"] == 4.5

        # manual draft → submit → approve → reimburse.
        e = requests.post(f"{BASE}/api/expenses", headers=h, timeout=15, json={
            "expense_type": "manual", "category_name": "Fuel", "merchant": "BP",
            "transaction_date": "2026-06-09", "gross_amount": 50.0, "tax_amount": 8.33}).json()
        eid = e["id"]
        assert requests.post(f"{BASE}/api/expenses/{eid}/submit", headers=h, timeout=15).json()["status"] == "submitted"
        rev = requests.post(f"{BASE}/api/expenses/{eid}/review", headers=h, timeout=15,
                            json={"action": "approve", "note": "ok"}).json()
        assert rev["status"] == "approved"

        # report groups by category.
        rep = requests.get(f"{BASE}/api/expenses/reports?group_by=category", headers=h, timeout=15).json()
        assert rep["totals"]["count"] >= 2

        # CSV export of approved → marks them exported + locked.
        csv = requests.get(f"{BASE}/api/expenses/export.csv?status=approved", headers=h, timeout=15)
        assert csv.status_code == 200
        assert "Expense ID" in csv.text and "BP" in csv.text
        after = requests.get(f"{BASE}/api/expenses/{eid}", headers=h, timeout=15).json()
        assert after["status"] == "exported" and after["locked"] is True

        # reimburse the exported claim.
        rb = requests.post(f"{BASE}/api/expenses/{eid}/reimburse", headers=h, timeout=15, json={}).json()
        assert rb["status"] == "reimbursed"
    finally:
        for c in ("expenses", "expense_country_rules", "expense_categories", "expense_events"):
            db[c].delete_many({"organization_id": org})
        db.organizations.delete_one({"id": org})
        db.users.delete_many({"email": email})
