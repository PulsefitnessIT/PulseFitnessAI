"""Iter 216h140 — Engineer Diary & Dispatch tests."""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://mod-only-deploy.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def admin_session():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


def _ensure_engineer(db, org_id, user_id, name):
    eng = db["svc_engineers"].find_one({"organization_id": org_id, "id": user_id})
    if not eng:
        db["svc_engineers"].insert_one({
            "id": user_id, "organization_id": org_id, "full_name": name,
            "email": "", "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })


def _seed_case(db, org_id):
    case_id = str(uuid.uuid4())
    db["svc_cases"].insert_one({
        "id": case_id,
        "organization_id": org_id,
        "reference": f"TEST-{case_id[:6]}",
        "title": "Diary integration test",
        "status": "open",
        "priority": "P2",
        "site_name": "Test Gym",
        "customer_name": "Test Customer",
        "scheduled_at": None,
        "assigned_engineer_id": None,
        "estimated_minutes": 90,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return case_id


def test_engineer_diary_empty_range(admin_session):
    tok = admin_session["token"]
    r = requests.get(f"{API}/api/svc/engineer/diary", headers=_hdr(tok), timeout=10)
    assert r.status_code == 200
    assert "slots" in r.json()


def test_engineer_create_and_delete_block(admin_session):
    tok = admin_session["token"]
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).replace(microsecond=0).isoformat()
    r = requests.post(
        f"{API}/api/svc/engineer/diary/blocks",
        headers=_hdr(tok),
        json={"title": "Annual leave", "kind": "holiday",
              "start_at": start, "end_at": end, "note": "QA test"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    block = r.json()["block"]
    bid = block["source_id"]

    # Should appear in diary
    rg = requests.get(
        f"{API}/api/svc/engineer/diary",
        params={"from": start, "to": end},
        headers=_hdr(tok), timeout=10,
    )
    assert rg.status_code == 200
    found = [s for s in rg.json()["slots"] if s["source_id"] == bid]
    assert found, "Created block not in diary"

    # Delete it
    rd = requests.delete(
        f"{API}/api/svc/engineer/diary/blocks/{bid}",
        headers=_hdr(tok), timeout=10,
    )
    assert rd.status_code == 200


def test_admin_dispatch_assign_flow(admin_session):
    """Owner can assign an unscheduled case to themselves (they're also
    an engineer profile via auto-mirror) and it appears in the diary."""
    tok = admin_session["token"]
    user_id = admin_session["user"]["id"]
    org_id = admin_session["user"]["organization_id"]
    db = _mongo()
    _ensure_engineer(db, org_id, user_id, admin_session["user"].get("full_name") or "Owner")
    case_id = _seed_case(db, org_id)
    try:
        # Verify it shows up in unassigned
        ru = requests.get(
            f"{API}/api/svc/admin/diary/unassigned",
            headers=_hdr(tok), timeout=10,
        )
        assert ru.status_code == 200
        unassigned_ids = [j["id"] for j in ru.json()["jobs"]]
        assert case_id in unassigned_ids

        # Assign
        when = (datetime.now(timezone.utc) + timedelta(hours=4)).replace(microsecond=0).isoformat()
        ra = requests.post(
            f"{API}/api/svc/admin/diary/case/{case_id}/assign",
            headers=_hdr(tok),
            json={"engineer_id": user_id, "scheduled_at": when},
            timeout=10,
        )
        assert ra.status_code == 200, ra.text

        # It should now appear in the engineer's diary
        from_ = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        to_ = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        rd = requests.get(
            f"{API}/api/svc/engineer/diary",
            params={"from": from_, "to": to_},
            headers=_hdr(tok), timeout=10,
        )
        assert rd.status_code == 200
        cases = [s for s in rd.json()["slots"] if s["source_id"] == case_id]
        assert cases, "Assigned case not in diary"
        assert cases[0]["kind"] == "job"
    finally:
        db["svc_cases"].delete_one({"id": case_id})


def test_engineer_reschedule_own_job(admin_session):
    tok = admin_session["token"]
    user_id = admin_session["user"]["id"]
    org_id = admin_session["user"]["organization_id"]
    db = _mongo()
    _ensure_engineer(db, org_id, user_id, "QA Eng")
    case_id = _seed_case(db, org_id)
    db["svc_cases"].update_one(
        {"id": case_id},
        {"$set": {"assigned_engineer_id": user_id,
                   "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()}},
    )
    try:
        new_when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        r = requests.post(
            f"{API}/api/svc/engineer/diary/case/{case_id}/reschedule",
            headers=_hdr(tok),
            json={"scheduled_at": new_when}, timeout=10,
        )
        assert r.status_code == 200
        # Persisted
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["scheduled_at"].startswith(new_when[:13])
    finally:
        db["svc_cases"].delete_one({"id": case_id})


def test_engineer_cannot_reschedule_others_job(admin_session):
    tok = admin_session["token"]
    org_id = admin_session["user"]["organization_id"]
    db = _mongo()
    other = str(uuid.uuid4())
    _ensure_engineer(db, org_id, other, "Other Eng")
    case_id = _seed_case(db, org_id)
    db["svc_cases"].update_one(
        {"id": case_id},
        {"$set": {"assigned_engineer_id": other,
                   "scheduled_at": datetime.now(timezone.utc).isoformat()}},
    )
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/diary/case/{case_id}/reschedule",
            headers=_hdr(tok),
            json={"scheduled_at": datetime.now(timezone.utc).isoformat()},
            timeout=10,
        )
        assert r.status_code == 403
    finally:
        db["svc_cases"].delete_one({"id": case_id})
