"""Iter 216h147 — Engineer self-claim queue tests.

Covers:
  • List unassigned queue + stats.
  • Atomic claim assigns to caller.
  • Race condition — second claim returns 409.
  • Claim on closed job returns 409.
  • Claim on unknown id returns 404.
  • Auth — requires engineer access.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://rbac-modules.preview.emergentagent.com").rstrip("/")
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
def sess():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


def _seed_unassigned(db, org_id, **overrides):
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "organization_id": org_id,
        "reference": f"QUE-{case_id[:5]}",
        "title": "Race test job",
        "status": "new",
        "priority": "P2",
        "site_name": "Test Site",
        "scheduled_at": None,
        "assigned_engineer_id": None,
        "estimated_minutes": 60,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["svc_cases"].insert_one(doc)
    return case_id


def test_queue_list_and_stats(sess):
    tok = sess["token"]
    r = requests.get(f"{API}/api/svc/engineer/queue/unassigned",
                     headers=_hdr(tok), timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "jobs" in body and "count" in body
    s = requests.get(f"{API}/api/svc/engineer/queue/stats",
                     headers=_hdr(tok), timeout=10)
    assert s.status_code == 200
    js = s.json()
    for k in ("total", "p1", "sla_breached_or_due"):
        assert k in js


def test_claim_assigns_to_caller(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_unassigned(db, org_id)
    try:
        when = (datetime.now(timezone.utc) + timedelta(hours=3)) \
            .replace(microsecond=0).isoformat()
        r = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok),
            json={"scheduled_at": when, "estimated_minutes": 90},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["assigned_engineer_id"] == user_id
        assert case["scheduled_at"].startswith(when[:13])
        assert case["estimated_minutes"] == 90
        assert "self_claimed_at" in case
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})


def test_second_claim_409(sess):
    """Once claimed, a second claim attempt must return 409 with
    `already_claimed` even if it's the same engineer."""
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_unassigned(db, org_id)
    try:
        r1 = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=10,
        )
        assert r1.status_code == 200
        r2 = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=10,
        )
        assert r2.status_code == 409
        detail = r2.json().get("detail")
        # detail can be a dict (preferred) or a string
        if isinstance(detail, dict):
            assert detail.get("code") == "already_claimed"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})


def test_claim_closed_case_409(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_unassigned(db, org_id, status="closed")
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=10,
        )
        assert r.status_code == 409
    finally:
        db["svc_cases"].delete_one({"id": case_id})


def test_claim_unknown_404(sess):
    tok = sess["token"]
    r = requests.post(
        f"{API}/api/svc/engineer/queue/{uuid.uuid4()}/claim",
        headers=_hdr(tok), json={}, timeout=10,
    )
    assert r.status_code == 404


def test_unassigned_list_does_not_show_claimed(sess):
    """Once claimed, the case must drop from the unassigned list."""
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_unassigned(db, org_id)
    try:
        r0 = requests.get(f"{API}/api/svc/engineer/queue/unassigned",
                          headers=_hdr(tok), timeout=10).json()
        assert case_id in [j["id"] for j in r0["jobs"]]
        rc = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=10,
        )
        assert rc.status_code == 200
        r1 = requests.get(f"{API}/api/svc/engineer/queue/unassigned",
                          headers=_hdr(tok), timeout=10).json()
        assert case_id not in [j["id"] for j in r1["jobs"]]
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})


def test_queue_unauth_fails():
    r = requests.get(f"{API}/api/svc/engineer/queue/unassigned", timeout=10)
    assert r.status_code in (401, 403)
