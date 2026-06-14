"""Iter 276 — Cross-org machine history from an Operations-portal QR scan.

A field engineer scans an operator's `/scan/{id}` sticker and (read-only)
sees the machine's jobs, parts fitted and who worked on it. Access rule
"d": own org OR registered engineer of the machine's org OR has been
assigned a job on that machine. Everyone else → 403.
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


def _seed_engineer(db, name="History Engineer"):
    email = f"hist.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"histeng-{uuid.uuid4().hex}"
    pw = "HistEng123!"
    org_id = f"histeng-org-{uuid.uuid4().hex}"
    db.users.insert_one({
        "id": uid, "email": email, "password": _hash(pw),
        "role": "engineer_partner", "account_type": "partner_engineer",
        "is_partner_engineer": True, "organization_id": org_id,
        "full_name": name, "active": True,
    })
    db.organizations.insert_one({
        "id": org_id, "name": f"{name} (Engineer)",
        "account_type": "partner_engineer", "is_engineer_personal_org": True,
    })
    return email, uid, pw, org_id


def test_machine_history_access_rule_d():
    db = _db()
    # Operator org + a machine with one completed job (parts fitted).
    op_org = f"op-org-{uuid.uuid4().hex}"
    eq_id = f"op-eq-{uuid.uuid4().hex}"
    worked_email, worked_uid, worked_pw, worked_org = _seed_engineer(db, "Alice Worked")
    other_email, other_uid, other_pw, other_org = _seed_engineer(db, "Bob Other")
    try:
        db.organizations.insert_one({"id": op_org, "name": "Pulse Carshalton", "account_type": "pulse_pro"})
        db.equipment.insert_one({
            "id": eq_id, "organization_id": op_org, "name": "Leg Press",
            "equipment_type": "Strength", "manufacturer": "Technogym",
            "model": "Selection", "serial_number": "TG-LP-9",
        })
        db.svc_cases.insert_one({
            "id": f"case-{uuid.uuid4().hex}", "organization_id": op_org,
            "reference": "SVC-OPS-1", "title": "Hydraulics serviced",
            "status": "closed", "priority": "p3",
            "asset_id": eq_id, "equipment_ids": [eq_id],
            "assigned_engineer_id": worked_uid, "assigned_engineer_name": "Alice Worked",
            "fault_description": "Seat post seized", "source": "manual",
            "created_at": "2026-04-01T10:00:00+00:00",
            "allocated_parts": [
                {"part_name": "Seat post bush", "part_sku": "SP-22", "qty": 1,
                 "case_reference": "SVC-OPS-1", "allocated_at": "2026-04-01T11:00:00+00:00",
                 "allocated_by_name": "Alice Worked"},
            ],
        })

        # (a) engineer who worked on it → access=worked, sees history.
        s = requests.Session()
        s.post(f"{BASE}/api/auth/login", json={"email": worked_email, "password": worked_pw},
               headers=rate_limit_bypass_headers(), timeout=15)
        tok = s.post(f"{BASE}/api/auth/login", json={"email": worked_email, "password": worked_pw},
                     headers=rate_limit_bypass_headers(), timeout=15).json()["token"]
        r = requests.get(f"{BASE}/api/svc/engineer/machine-history/{eq_id}",
                         headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["access"] == "worked"
        assert body["operator_name"] == "Pulse Carshalton"
        assert body["stats"]["total_jobs"] == 1
        assert body["stats"]["total_parts"] == 1
        assert any(e["name"] == "Alice Worked" for e in body["engineers"])
        assert body["parts"][0]["part_name"] == "Seat post bush"

        # (c) unrelated engineer → 403.
        tok2 = requests.post(f"{BASE}/api/auth/login",
                             json={"email": other_email, "password": other_pw},
                             headers=rate_limit_bypass_headers(), timeout=15).json()["token"]
        r2 = requests.get(f"{BASE}/api/svc/engineer/machine-history/{eq_id}",
                          headers={"Authorization": f"Bearer {tok2}"}, timeout=15)
        assert r2.status_code == 403, r2.text[:200]

        # (b) make Bob a registered engineer of the operator → now 200.
        db.svc_engineers.insert_one({
            "id": other_uid, "organization_id": op_org, "name": "Bob Other", "active": True,
        })
        r3 = requests.get(f"{BASE}/api/svc/engineer/machine-history/{eq_id}",
                          headers={"Authorization": f"Bearer {tok2}"}, timeout=15)
        assert r3.status_code == 200, r3.text[:200]
        assert r3.json()["access"] == "operator_engineer"

        # Unknown machine → 404.
        r4 = requests.get(f"{BASE}/api/svc/engineer/machine-history/does-not-exist",
                          headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        assert r4.status_code == 404
    finally:
        db.svc_cases.delete_many({"organization_id": op_org})
        db.equipment.delete_many({"id": eq_id})
        db.svc_engineers.delete_many({"organization_id": op_org})
        db.organizations.delete_many({"id": {"$in": [op_org, worked_org, other_org]}})
        db.users.delete_many({"email": {"$in": [worked_email, other_email]}})
