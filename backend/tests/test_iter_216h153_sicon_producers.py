"""Iter 216h153 — Sicon outbox producer coverage on Phase 5 paths.

Audits the producer-side gap identified in the Feb 2026 process review:
every case mutation that flows through the new engineer-independence
paths (claim, self-allocate, accept_job_request, diary schedule) AND
every parts movement (request approval, PO receipt) must enqueue an
outbound payload to `svc_sicon_outbox` so the upstream service-call /
stock ledger stays in sync.

These tests do NOT exercise the Sicon worker (that's covered elsewhere
in test_sicon_outbox_worker.py). They only assert that the producer
sites enqueue the right `kind`s + payload shape.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://fitness-onboarding-3.preview.emergentagent.com").rstrip("/")
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


def _seed_case(db, org_id, **overrides):
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "organization_id": org_id,
        "reference": f"SI-{case_id[:5]}",
        "title": "Sicon producer test",
        "status": "new",
        "priority": "P3",
        "site_name": "Test Site",
        "assigned_engineer_id": None,
        "estimated_minutes": 60,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["svc_cases"].insert_one(doc)
    return case_id


# ── Self-claim → push_case + push_event (state_change) ─────────

def test_self_claim_enqueues_case_and_state_change(eng_sess):
    tok = eng_sess["token"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="new")
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=15,
        )
        assert r.status_code == 200, r.text
        # Look up the case's human reference to query the tracking note.
        case = db["svc_cases"].find_one({"id": case_id}, {"reference": 1})
        ref = case.get("reference")
        # Sicon outbox: one `case` row, one `tracking_note` row.
        kinds = list(db["svc_sicon_outbox"].find(
            {"organization_id": org_id,
             "$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id},
                     {"payload.ServiceCallReference": ref}]},
            {"_id": 0, "kind": 1, "payload": 1},
        ))
        kind_set = {k["kind"] for k in kinds}
        assert "case" in kind_set, f"missing case kind, got {kind_set}"
        assert "tracking_note" in kind_set, f"missing tracking_note, got {kind_set}"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})
        db["svc_sicon_outbox"].delete_many(
            {"$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id}]},
        )


# ── Self-allocate (engineer creates a fresh case) ───────────────

def test_self_allocate_enqueues_case_and_created_note(eng_sess):
    tok = eng_sess["token"]
    org_id = eng_sess["user"]["organization_id"]
    db = _mongo()
    r = requests.post(
        f"{API}/api/svc/engineer/jobs/self-create",
        headers=_hdr(tok),
        json={
            "title": "Sicon producer self-allocate",
            "description": "QA description for outbox check.",
            "priority": "P3",
            "customer_name": "Sicon QA Customer",
            "site_name": "Sicon QA Site",
            "intake_channel": "phone",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    case_id = r.json()["case_id"]
    try:
        case = db["svc_cases"].find_one({"id": case_id}, {"reference": 1})
        ref = (case or {}).get("reference")
        outbox = list(db["svc_sicon_outbox"].find(
            {"organization_id": org_id,
             "$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id},
                     {"payload.ServiceCallReference": ref}]},
            {"_id": 0, "kind": 1},
        ))
        kinds = {x["kind"] for x in outbox}
        assert "case" in kinds, f"self-allocate did not enqueue case row: {kinds}"
        assert "tracking_note" in kinds, f"self-allocate did not enqueue case_created tracking note: {kinds}"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_sicon_outbox"].delete_many(
            {"$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id}]},
        )


# ── Dispatcher diary schedule ───────────────────────────────────

def test_admin_diary_schedule_enqueues_case_and_state_change():
    """Admin dispatcher scheduling a NEW case must promote it to
    ASSIGNED and push both an updated case + state_change tracking
    note."""
    admin_sess = _login("admin@gymaxisai.com", "MasterAdmin123!")
    tok = admin_sess["token"]
    org_id = admin_sess["user"]["organization_id"]
    db = _mongo()
    # Resolve an engineer in the org for the assignment.
    eng = db["svc_engineers"].find_one({"organization_id": org_id})
    if not eng:
        pytest.skip("No svc_engineer profile in org to dispatch to")
    case_id = _seed_case(db, org_id, status="new")
    try:
        when = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat()
        r = requests.post(
            f"{API}/api/svc/admin/diary/case/{case_id}/assign",
            headers=_hdr(tok),
            json={"engineer_id": eng["id"], "scheduled_at": when,
                  "estimated_minutes": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        case = db["svc_cases"].find_one({"id": case_id}, {"reference": 1})
        ref = (case or {}).get("reference")
        outbox = list(db["svc_sicon_outbox"].find(
            {"organization_id": org_id,
             "$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id},
                     {"payload.ServiceCallReference": ref}]},
            {"_id": 0, "kind": 1},
        ))
        kinds = {x["kind"] for x in outbox}
        assert "case" in kinds
        assert "tracking_note" in kinds
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})
        db["svc_sicon_outbox"].delete_many(
            {"$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id}]},
        )


# ── Parts-request approval enqueues stock movement ─────────────

def test_parts_request_approval_enqueues_part_movement():
    """When admin approves an engineer's parts request the resulting
    allocation must push a `part_movement` row to the Sicon outbox.

    Uses `e1.agent@gymaxisai.com` for both actors — that account is
    the canonical org `owner` so it can both raise an engineer parts
    request AND approve it as admin (role=owner clears _is_admin)."""
    sess = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    eng_id = sess["user"]["id"]
    case_id = _seed_case(db, org_id, status="assigned",
                         assigned_engineer_id=eng_id)
    case = db["svc_cases"].find_one({"id": case_id}, {"reference": 1})
    ref = case.get("reference")
    r1 = requests.post(
        f"{API}/api/svc/engineer/parts-requests",
        headers=_hdr(tok),
        json={
            "case_id": case_id,
            "part_sku": "PT-SICON-QA",
            "part_name": "Sicon producer QA part",
            "qty": 2,
            "urgency": "normal",
            "notes": "test",
        },
        timeout=15,
    )
    assert r1.status_code in (200, 201), r1.text
    req_id = r1.json().get("id") or r1.json().get("request_id")
    assert req_id, f"could not extract request id from {r1.text}"
    try:
        r2 = requests.post(
            f"{API}/api/admin/parts-requests/{req_id}/approve",
            headers=_hdr(tok),
            json={"ship_from": "warehouse"},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        movements = list(db["svc_sicon_outbox"].find(
            {"organization_id": org_id, "kind": "part_movement",
             "$or": [{"payload.ServiceCallReference": case_id},
                     {"payload.ServiceCallReference": ref}]},
            {"_id": 0, "payload": 1},
        ))
        assert movements, "approve did not enqueue a Sicon part_movement"
        assert movements[0]["payload"]["MovementTypeID"] == "AllocateToCall"
        assert movements[0]["payload"]["PartCode"] == "PT-SICON-QA"
        assert movements[0]["payload"]["Quantity"] == 2
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_parts_requests"].delete_one({"id": req_id})
        db["svc_part_movements"].delete_many({"case_id": case_id})
        db["svc_sicon_outbox"].delete_many(
            {"$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id}]},
        )
