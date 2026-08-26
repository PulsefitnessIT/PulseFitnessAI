"""Iter 216h151 — Service Ops state-machine integrity tests.

Audits cross-module integrity gaps from the Feb 2026 process review:

  • Queue filter must use canonical OPEN_STATES (not the bogus
    `["closed", "invoiced", "cancelled", "void"]` literal which lets
    `rejected` cases leak into the engineer queue).
  • Self-claim from the queue must move NEW/TRIAGED → ASSIGNED and
    leave a `state_change` row in `svc_case_events` so the audit
    trail and case timeline reflect the dispatch.
  • Engineer self-allocate (independence.py) must insert a case in
    canonical ASSIGNED state (was `"open"` — not in the state graph)
    and append a `case_created` timeline event.
  • Admin diary schedule of a NEW case must transition it to
    ASSIGNED and append a `state_change` event.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://photo-fix-verify.preview.emergentagent.com").rstrip("/")
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
def eng_sess():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


def _seed(db, org_id, status, **overrides):
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "organization_id": org_id,
        "reference": f"S151-{case_id[:5]}",
        "title": "State machine audit",
        "status": status,
        "priority": "P3",
        "site_name": "Audit Site",
        "scheduled_at": None,
        "assigned_engineer_id": None,
        "estimated_minutes": 60,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["svc_cases"].insert_one(doc)
    return case_id


# ── Queue filter integrity ──────────────────────────────────────

def test_queue_excludes_rejected_cases(eng_sess):
    """Before iter 216h151 the queue filter used `$nin: ["closed",
    "invoiced", "cancelled", "void"]` — none of which match the real
    state machine. A REJECTED case with no engineer would leak in."""
    tok = eng_sess["token"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    rejected_id = _seed(db, org_id, "rejected")
    open_id = _seed(db, org_id, "new")
    try:
        r = requests.get(
            f"{API}/api/svc/engineer/queue/unassigned",
            headers=_hdr(tok), params={"limit": 500}, timeout=15,
        )
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()["jobs"]]
        assert rejected_id not in ids, "rejected case must not appear in queue"
        assert open_id in ids, "open NEW case must appear in queue"
    finally:
        db["svc_cases"].delete_many({"id": {"$in": [rejected_id, open_id]}})


def test_queue_excludes_closed_and_invoiced(eng_sess):
    tok = eng_sess["token"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    closed_id = _seed(db, org_id, "closed")
    invoiced_id = _seed(db, org_id, "invoiced")
    try:
        r = requests.get(
            f"{API}/api/svc/engineer/queue/unassigned",
            headers=_hdr(tok), params={"limit": 500}, timeout=15,
        )
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()["jobs"]]
        assert closed_id not in ids
        assert invoiced_id not in ids
    finally:
        db["svc_cases"].delete_many({"id": {"$in": [closed_id, invoiced_id]}})


# ── Claim transitions state + writes timeline ───────────────────

def test_self_claim_promotes_new_to_assigned_and_logs_event(eng_sess):
    tok = eng_sess["token"]
    user_id = eng_sess["user"]["id"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed(db, org_id, "new")
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=15,
        )
        assert r.status_code == 200, r.text
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["status"] == "assigned", "NEW must promote to ASSIGNED on claim"
        assert case["assigned_engineer_id"] == user_id
        assert "prev_status" not in case, "temp prev_status field must be stripped"
        # Timeline event present
        events = list(db["svc_case_events"].find({"case_id": case_id}))
        kinds = {e.get("type") for e in events}
        assert "state_change" in kinds, f"expected state_change event, got {kinds}"
        sc = next(e for e in events if e.get("type") == "state_change")
        assert sc["extra"]["from_state"] == "new"
        assert sc["extra"]["to_state"] == "assigned"
        assert sc["extra"]["via"] == "self_claim"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})


def test_self_claim_triaged_also_promotes(eng_sess):
    tok = eng_sess["token"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed(db, org_id, "triaged")
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=15,
        )
        assert r.status_code == 200
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["status"] == "assigned"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})


def test_self_claim_already_assigned_orphan_keeps_state(eng_sess):
    """An ASSIGNED case whose engineer was removed (e.g. left the org)
    must be re-claimable; state stays ASSIGNED (the state machine
    allows ASSIGNED→ASSIGNED for reassignment)."""
    tok = eng_sess["token"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed(db, org_id, "assigned")
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=15,
        )
        assert r.status_code == 200
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["status"] == "assigned"
        # A `self_claim` event should be recorded even without state change
        events = list(db["svc_case_events"].find({"case_id": case_id}))
        kinds = {e.get("type") for e in events}
        assert kinds & {"self_claim", "state_change"}
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})


# ── Engineer self-allocate inserts canonical state ──────────────

def test_self_allocate_inserts_canonical_assigned_with_event(eng_sess):
    """Before iter 216h151 this path inserted `status="open"` which
    isn't in the state graph at all."""
    tok = eng_sess["token"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    r = requests.post(
        f"{API}/api/svc/engineer/jobs/self-create",
        headers=_hdr(tok),
        json={
            "title": "State machine self-allocate test",
            "description": "A short description of the fault.",
            "priority": "P3",
            "customer_name": "QA Customer",
            "site_name": "QA Site",
            "intake_channel": "phone",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    case_id = r.json()["case_id"]
    try:
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["status"] == "assigned"
        events = list(db["svc_case_events"].find({"case_id": case_id}))
        kinds = {e.get("type") for e in events}
        assert "case_created" in kinds
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
