"""Iter 220ea·40 — Operator dispatch confirmation + readiness report.

- The faults list/detail now carries `supplier_case.supplier_name` so the
  UI can show a "✓ Sent to <supplier>" badge.
- `GET /api/suppliers/dispatch-readiness` reports which machines won't
  auto-dispatch a fault (supplier has no email / not in directory).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import rate_limit_bypass_headers

load_dotenv("/app/backend/.env")

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://platform-doctor.preview.emergentagent.com").rstrip("/")
OPERATOR_EMAIL = "jack.ottey@thirdspace.london"
OPERATOR_PW = "Test123!"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.fixture()
def mongo():
    c = MongoClient(MONGO_URL)
    try:
        yield c[DB_NAME]
    finally:
        c.close()


@pytest.fixture()
def operator():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": OPERATOR_EMAIL, "password": OPERATOR_PW},
                      headers=rate_limit_bypass_headers(), timeout=30)
    r.raise_for_status()
    b = r.json()
    return {"token": b["token"], "org": b["user"]["organization_id"], "h": {"Authorization": f"Bearer {b['token']}"}}


def test_fault_list_exposes_supplier_name_for_badge(mongo, operator):
    org, tag = operator["org"], uuid.uuid4().hex[:8]
    serial, sname, semail = f"PYSN-{tag}", f"PYTEST Sup {tag}", f"pytest-{tag}@example.com"
    mongo.suppliers.insert_one({"id": f"pysup-{tag}", "organization_id": org, "name": sname,
                                "email": semail, "created_at": datetime.now(timezone.utc).isoformat()})
    mongo.equipment.insert_one({"id": f"pyeq-{tag}", "organization_id": org, "name": "PY Tread",
                                "serial_number": serial, "supplier": sname, "machine_type": "Treadmill"})
    issue_id = None
    try:
        r = requests.post(f"{BASE}/api/issues", json={
            "serial_number": serial, "machine_type": "Treadmill",
            "issue_description": "Belt slipping", "severity": "high", "resolution_type": "engineer",
        }, headers=operator["h"], timeout=30)
        assert r.status_code == 200, r.text
        issue_id = r.json()["id"]

        lst = requests.get(f"{BASE}/api/issues", headers=operator["h"], timeout=30).json()
        rows = lst if isinstance(lst, list) else lst.get("issues", [])
        mine = next((i for i in rows if i["id"] == issue_id), None)
        assert mine is not None, "logged fault not in list"
        # The badge data must be present on the list payload.
        assert (mine.get("supplier_case") or {}).get("supplier_name") == sname
    finally:
        if issue_id:
            sc = mongo.supplier_cases.find_one({"issue_id": issue_id}) or {}
            mongo.supplier_case_comments.delete_many({"case_id": sc.get("id", "x")})
            mongo.supplier_cases.delete_many({"issue_id": issue_id})
            mongo.issues.delete_one({"id": issue_id})
        mongo.equipment.delete_many({"serial_number": serial})
        mongo.suppliers.delete_many({"name": sname})


def test_dispatch_readiness_flags_blocked_machines(mongo, operator):
    org, tag = operator["org"], uuid.uuid4().hex[:8]
    sname = f"PYTEST NoEmail {tag}"
    mongo.suppliers.insert_one({"id": f"pyblk-{tag}", "organization_id": org, "name": sname,
                                "email": "", "created_at": datetime.now(timezone.utc).isoformat()})
    mongo.equipment.insert_one({"id": f"pyblkeq1-{tag}", "organization_id": org, "name": "B1",
                                "serial_number": f"PYBLK1-{tag}", "supplier": sname})
    mongo.equipment.insert_one({"id": f"pyblkeq2-{tag}", "organization_id": org, "name": "B2",
                                "serial_number": f"PYBLK2-{tag}", "supplier": sname})
    try:
        r = requests.get(f"{BASE}/api/suppliers/dispatch-readiness", headers=operator["h"], timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["machines_blocked"] >= 2
        assert d["suppliers_missing_email_count"] >= 1
        blk = next((b for b in d["blocked_suppliers"] if b["name"] == sname), None)
        assert blk is not None and blk["machine_count"] == 2 and blk["reason"] == "no_email"
        assert any(s["name"] == sname for s in d["suppliers_missing_email"])
    finally:
        mongo.equipment.delete_many({"serial_number": {"$in": [f"PYBLK1-{tag}", f"PYBLK2-{tag}"]}})
        mongo.suppliers.delete_many({"name": sname})


def test_readiness_and_badge_wiring_present():
    iss = open("/app/backend/routes/issues.py").read()
    assert '"supplier_name": 1' in iss  # list enrichment carries it
    faults = open("/app/frontend/src/pages/Dashboard/FaultsTab.js").read()
    assert "issue-supplier-sent-" in faults and "Sent to" in faults
    sup = open("/app/frontend/src/components/shared/AccountSettings/suppliers.js").read()
    assert "dispatch-readiness" in sup and "won" in sup  # warning banner
