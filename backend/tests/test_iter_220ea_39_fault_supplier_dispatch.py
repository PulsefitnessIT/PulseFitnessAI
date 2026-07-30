"""Iter 220ea·39 — Auto-dispatch a logged fault to the machine's supplier.

When a gym logs a fault, the supplier card ("log the job") is created and
emailed automatically. Supplier resolution is machine-first (option C):
the supplier set against the faulted machine → the supplier named on the
fault → the org's primary auto_dispatch supplier. Only fires for open
(unresolved) faults, and only when the resolved supplier has an email.
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

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://mod-hq-email.preview.emergentagent.com").rstrip("/")
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
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PW},
        headers=rate_limit_bypass_headers(), timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    return {"token": body["token"], "org": body["user"]["organization_id"]}


def _log_fault(token: str, serial: str, supplier: str | None = None) -> dict:
    payload = {
        "serial_number": serial, "machine_type": "Treadmill",
        "issue_description": "Belt slipping badly under load", "severity": "high",
        "resolution_type": "engineer",
    }
    if supplier is not None:
        payload["supplier"] = supplier
    r = requests.post(f"{BASE}/api/issues", json=payload,
                      headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_fault_auto_dispatches_to_machine_supplier(mongo, operator):
    org = operator["org"]
    tag = uuid.uuid4().hex[:8]
    serial = f"PYTEST-SN-{tag}"
    supplier_name = f"PYTEST Supplier {tag}"
    supplier_email = f"pytest-sup-{tag}@example.com"

    mongo.suppliers.insert_one({
        "id": f"pysup-{tag}", "organization_id": org, "name": supplier_name,
        "email": supplier_email, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.equipment.insert_one({
        "id": f"pyeq-{tag}", "organization_id": org, "name": "PYTEST Treadmill",
        "serial_number": serial, "supplier": supplier_name, "machine_type": "Treadmill",
    })

    issue_id = None
    try:
        # No supplier on the payload → must resolve from the machine.
        issue = _log_fault(operator["token"], serial)
        issue_id = issue["id"]

        doc = mongo.issues.find_one({"id": issue_id})
        assert doc["status"] == "open"
        assert doc.get("auto_dispatched_supplier_email") == supplier_email
        assert doc.get("auto_dispatched_supplier_name") == supplier_name
        assert doc.get("supplier_case_token")

        # The supplier "card to log the job" was created.
        sc = mongo.supplier_cases.find_one({"issue_id": issue_id})
        assert sc is not None
        assert sc["supplier_email"] == supplier_email
        # …with a first message that triggers the supplier email.
        assert mongo.supplier_case_comments.count_documents({"case_id": sc["id"]}) >= 1
    finally:
        if issue_id:
            sc = mongo.supplier_cases.find_one({"issue_id": issue_id}) or {}
            mongo.supplier_case_comments.delete_many({"case_id": sc.get("id", "x")})
            mongo.supplier_cases.delete_many({"issue_id": issue_id})
            mongo.issues.delete_one({"id": issue_id})
        mongo.equipment.delete_many({"serial_number": serial})
        mongo.suppliers.delete_many({"name": supplier_name})


def test_self_fixed_fault_does_not_dispatch(mongo, operator):
    org = operator["org"]
    tag = uuid.uuid4().hex[:8]
    serial = f"PYTEST-SN-SELF-{tag}"
    supplier_name = f"PYTEST Supplier Self {tag}"

    mongo.suppliers.insert_one({
        "id": f"pysup-self-{tag}", "organization_id": org, "name": supplier_name,
        "email": f"pytest-self-{tag}@example.com", "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.equipment.insert_one({
        "id": f"pyeq-self-{tag}", "organization_id": org, "name": "PYTEST Bike",
        "serial_number": serial, "supplier": supplier_name, "machine_type": "Bike",
    })
    issue_id = None
    try:
        r = requests.post(f"{BASE}/api/issues", json={
            "serial_number": serial, "machine_type": "Bike",
            "issue_description": "Loose pedal, tightened on the spot", "severity": "low",
            "resolution_type": "self_fix",
        }, headers={"Authorization": f"Bearer {operator['token']}"}, timeout=30)
        assert r.status_code == 200, r.text
        issue_id = r.json()["id"]
        # Self-fixed → resolved → no supplier dispatch.
        assert mongo.supplier_cases.find_one({"issue_id": issue_id}) is None
        assert mongo.issues.find_one({"id": issue_id}).get("auto_dispatched_supplier_email") is None
    finally:
        if issue_id:
            mongo.issues.delete_one({"id": issue_id})
        mongo.equipment.delete_many({"serial_number": serial})
        mongo.suppliers.delete_many({"name": supplier_name})


def test_dispatch_helpers_present():
    src = open("/app/backend/routes/issues.py").read()
    assert "_resolve_fault_supplier" in src
    assert "equipment" in src and "auto_dispatch" in src  # machine-first + org fallback
    # Wired into both single and batch fault submit.
    assert src.count("_auto_dispatch_to_primary_supplier(") >= 2
