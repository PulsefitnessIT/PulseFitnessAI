"""Iter 216h155 — SVC compliance audit-log coverage.

Closes the audit gap identified in the Feb 2026 process review: before
this iter the SVC module had **zero** `audit_log()` calls while CRM
and Master Admin had dozens. Every money-bearing or legally-binding
mutation must now leave an immutable row in `audit_logs` so SOC2 /
GDPR / ISO 27001 paths have a tamper-evident "who did what, when, to
which case" answer.

Audits:
  • svc.case.transition.{state} — every state change
  • svc.case.self_claim         — engineer self-allocates from queue
  • svc.case.self_allocate      — engineer creates case from phone/email
  • svc.case.accept_job_request — supplier-card public intake accepted
  • svc.case.dispatch           — admin schedules to engineer
  • svc.case.signature_captured — customer sign-off (legal binding)
  • svc.invoice.finalise        — money committed
  • svc.parts.approve           — parts chain-of-custody
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://pulse-mod-estate--6ncsuzra.preview.emergentagent.com").rstrip("/")
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


def _seed_case(db, org_id, **overrides):
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "organization_id": org_id,
        "reference": f"AUD-{case_id[:5]}",
        "title": "Audit-log test",
        "status": "new",
        "priority": "P3",
        "site_name": "Audit Site",
        "assigned_engineer_id": None,
        "estimated_minutes": 60,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["svc_cases"].insert_one(doc)
    return case_id


def _last_audit(db, *, user_id: str, action: str, resource_id: str):
    """Return the most recent `audit_logs` row matching the tuple."""
    return db["audit_logs"].find_one(
        {"user_id": user_id, "action": action, "resource_id": resource_id},
        sort=[("timestamp", -1)],
    )


# ── State transitions ──────────────────────────────────────────

def test_transition_close_writes_audit_row(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    user_id = sess["user"]["id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="repaired")
    try:
        r = requests.post(
            f"{API}/api/svc/cases/{case_id}/transition",
            headers=_hdr(tok), json={"to": "closed"}, timeout=15,
        )
        assert r.status_code == 200, r.text
        row = _last_audit(db, user_id=user_id,
                          action="svc.case.transition.closed",
                          resource_id=case_id)
        assert row is not None, "transition.closed must write audit row"
        assert row["resource_type"] == "svc_case"
        assert "→ closed" in row["details"]
        assert row["user_email"] == "e1.agent@gymaxisai.com"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["audit_logs"].delete_many({"resource_id": case_id})


# ── Self-claim ─────────────────────────────────────────────────

def test_self_claim_writes_audit_row(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="new")
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/queue/{case_id}/claim",
            headers=_hdr(tok), json={}, timeout=15,
        )
        assert r.status_code == 200, r.text
        row = _last_audit(db, user_id=user_id, action="svc.case.self_claim",
                          resource_id=case_id)
        assert row is not None
        assert "new→assigned" in row["details"]
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})
        db["audit_logs"].delete_many({"resource_id": case_id})


# ── Self-allocate ──────────────────────────────────────────────

def test_self_allocate_writes_audit_row(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    db = _mongo()
    r = requests.post(
        f"{API}/api/svc/engineer/jobs/self-create",
        headers=_hdr(tok),
        json={
            "title": "Audit-log self-allocate", "description": "QA",
            "priority": "P3", "customer_name": "Audit QA",
            "site_name": "Audit Site", "intake_channel": "phone",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    case_id = r.json()["case_id"]
    try:
        row = _last_audit(db, user_id=user_id,
                          action="svc.case.self_allocate",
                          resource_id=case_id)
        assert row is not None
        assert "channel=phone" in row["details"]
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["audit_logs"].delete_many({"resource_id": case_id})


# ── Dispatch via admin diary ───────────────────────────────────

def test_diary_dispatch_writes_audit_row(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    eng = db["svc_engineers"].find_one({"organization_id": org_id})
    if not eng:
        pytest.skip("No svc_engineer profile in org")
    case_id = _seed_case(db, org_id, status="new")
    try:
        when = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        r = requests.post(
            f"{API}/api/svc/admin/diary/case/{case_id}/assign",
            headers=_hdr(tok),
            json={"engineer_id": eng["id"], "scheduled_at": when,
                  "estimated_minutes": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        row = _last_audit(db, user_id=user_id, action="svc.case.dispatch",
                          resource_id=case_id)
        assert row is not None
        assert eng["id"] in row["details"]
        assert "new→assigned" in row["details"]
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})
        db["audit_logs"].delete_many({"resource_id": case_id})


# ── Invoice finalise (money commit) ────────────────────────────

def test_invoice_finalise_writes_audit_row(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="closed",
                         customer_name="Audit Invoice Co")
    qid = str(uuid.uuid4())
    db["svc_quotes"].insert_one({
        "id": qid,
        "organization_id": org_id,
        "case_id": case_id,
        "reference": f"AQ-{qid[:5]}",
        "status": "approved",
        "net": 500.0,
        "subtotal": 500.0,
        "vat": 100.0,
        "gross": 600.0,
        "total": 600.0,
        "lines": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        r = requests.post(
            f"{API}/api/svc/billing/{case_id}/invoice/finalise",
            headers=_hdr(tok), timeout=20,
        )
        assert r.status_code == 200, r.text
        row = _last_audit(db, user_id=user_id, action="svc.invoice.finalise",
                          resource_id=qid)
        assert row is not None
        assert row["resource_type"] == "svc_invoice"
        assert "net=£500" in row["details"]
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_quotes"].delete_many({"id": qid})
        db["svc_sage_invoice_outbox"].delete_many({"case_id": case_id})
        db["crm2_activities"].delete_many({"case_id": case_id})
        db["audit_logs"].delete_many({"resource_id": case_id})
        db["audit_logs"].delete_many({"resource_id": qid})


# ── Signature capture (legal binding) ──────────────────────────

def test_signature_writes_audit_row(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="awaiting_sign_off",
                         assigned_engineer_id=user_id)
    try:
        # 1x1 transparent PNG dataURL — minimum valid signature image.
        png_b64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
                   "2mNgAAIAAAUAAen63NgAAAAASUVORK5CYII=")
        data_url = f"data:image/png;base64,{png_b64}"
        r = requests.post(
            f"{API}/api/svc/engineer/signature",
            headers=_hdr(tok),
            json={
                "case_id": case_id,
                "signed_by_name": "Audit Signer",
                "signed_by_role": "Site Manager",
                "image_data": data_url,
                "summary": "Repair signed off",
            },
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        sig_id = r.json()["id"]
        row = _last_audit(db, user_id=user_id,
                          action="svc.case.signature_captured",
                          resource_id=sig_id)
        assert row is not None
        assert "signed_by=Audit Signer" in row["details"]
        # Cleanup
        db["svc_signatures"].delete_one({"id": sig_id})
        db["audit_logs"].delete_many({"resource_id": sig_id})
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})


# ── Parts approval (chain-of-custody) ──────────────────────────

def test_parts_approve_writes_audit_row(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="assigned",
                         assigned_engineer_id=user_id)
    r1 = requests.post(
        f"{API}/api/svc/engineer/parts-requests",
        headers=_hdr(tok),
        json={
            "case_id": case_id, "part_sku": "PT-AUDIT-QA",
            "part_name": "Audit QA part", "qty": 1,
            "urgency": "normal", "notes": "audit test",
        },
        timeout=15,
    )
    assert r1.status_code in (200, 201), r1.text
    req_id = r1.json().get("id") or r1.json().get("request_id")
    try:
        r2 = requests.post(
            f"{API}/api/admin/parts-requests/{req_id}/approve",
            headers=_hdr(tok), json={"ship_from": "warehouse"}, timeout=15,
        )
        assert r2.status_code == 200, r2.text
        row = _last_audit(db, user_id=user_id, action="svc.parts.approve",
                          resource_id=req_id)
        assert row is not None
        assert "sku=PT-AUDIT-QA" in row["details"]
        assert "qty=1" in row["details"]
        assert "from=warehouse" in row["details"]
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_parts_requests"].delete_one({"id": req_id})
        db["svc_part_movements"].delete_many({"case_id": case_id})
        db["svc_sicon_outbox"].delete_many(
            {"$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id}]},
        )
        db["audit_logs"].delete_many({"resource_id": req_id})
        db["audit_logs"].delete_many({"resource_id": case_id})
