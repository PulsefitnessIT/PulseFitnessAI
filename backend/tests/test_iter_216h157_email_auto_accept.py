"""Iter 216h157 — Inbound email auto-accept on high AI confidence.

When the GPT-5.2 parser returns a high-confidence extraction (≥0.9)
AND deterministic gates pass (customer + site + substantial title),
the inbound webhook skips the triage inbox and creates the svc_case
directly. The pending path remains the fallback for low-confidence
or sparse parses.

Audits:
  • High-confidence parse → svc_cases row (ASSIGNED), NO job_request row.
  • Low-confidence parse → svc_job_requests (pending) as before.
  • Hallucinated `confidence: 0.99` but missing site → falls back.
  • Auto-accepted case carries intake_channel + confidence metadata,
    fires audit_log + Sicon outbox + CRM activity (via state).
"""
import os
import uuid

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://admin-setup-portal.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"
SECRET = os.environ.get("INBOUND_EMAIL_WEBHOOK_SECRET")


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
    if not SECRET:
        pytest.skip("INBOUND_EMAIL_WEBHOOK_SECRET not configured")
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


@pytest.fixture
def inbox(sess):
    r = requests.get(f"{API}/api/svc/engineer/inbound-address",
                     headers=_hdr(sess["token"]), timeout=10)
    assert r.status_code == 200
    return r.json()


def _cleanup_case(db, case_id):
    db["svc_cases"].delete_one({"id": case_id})
    db["svc_case_events"].delete_many({"case_id": case_id})
    db["svc_notifications"].delete_many({"source_id": case_id})
    db["svc_sicon_outbox"].delete_many(
        {"$or": [{"payload.OurReference": case_id},
                 {"payload.ServiceCallReference": case_id}]},
    )
    db["audit_logs"].delete_many({"resource_id": case_id})
    db["svc_inbound_email_log"].delete_many({"case_id": case_id})


# ── High-confidence parse → auto-accept ─────────────────────────

def test_high_confidence_auto_creates_case(inbox):
    db = _mongo()
    payload = {
        "to": inbox["email"],
        "from": "ops@acme-gyms.example",
        "subject": "Urgent: treadmill 7 down at Acme HQ",
        "text": "Treadmill 7 has stopped — error code E03. Please attend ASAP.",
        "parsed_override": {
            "customer_name": "Acme Gyms",
            "customer_email": "ops@acme-gyms.example",
            "customer_phone": "020 1234 5678",
            "site_name": "Acme Gyms HQ",
            "site_address": "1 Acme Way, London",
            "site_postcode": "N1 7AB",
            "title": "Treadmill 7 down at Acme HQ — E03",
            "description": "Treadmill 7 stopped with error code E03.",
            "priority": "P2",
            "confidence": 0.95,
        },
    }
    r = requests.post(
        f"{API}/api/inbound/email/test?secret={SECRET}",
        json=payload, timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "case_auto_created"
    case_id = body["case_id"]
    try:
        case = db["svc_cases"].find_one({"id": case_id})
        assert case is not None
        assert case["status"] == "assigned"
        assert case["intake_channel"] == "inbound_email"
        assert case["intake_subchannel"] == "auto_accepted"
        assert case["intake_confidence"] >= 0.9
        assert case["priority"] == "P2"
        assert case["site_postcode"] == "N1 7AB"
        # No pending request row should exist for this inbound.
        pending = db["svc_job_requests"].count_documents(
            {"source.subject": payload["subject"]},
        )
        assert pending == 0
        # Audit row written.
        audit = db["audit_logs"].find_one(
            {"action": "svc.case.auto_accept_email",
             "resource_id": case_id},
        )
        assert audit is not None
        # Inbound log carries outcome + confidence.
        log = db["svc_inbound_email_log"].find_one({"case_id": case_id})
        assert log is not None
        assert log["outcome"] == "case_auto_created"
        assert log["confidence"] >= 0.9
    finally:
        _cleanup_case(db, case_id)


# ── Low-confidence → fallback to pending ────────────────────────

def test_low_confidence_falls_back_to_pending(inbox):
    db = _mongo()
    payload = {
        "to": inbox["email"],
        "from": "customer@example.com",
        "subject": "Help please",
        "text": "Hi can someone call me back about my gym?",
        "parsed_override": {
            "customer_name": None,
            "site_name": None,
            "site_postcode": None,
            "title": "Help",
            "description": None,
            "priority": "P3",
            "confidence": 0.4,
        },
    }
    r = requests.post(
        f"{API}/api/inbound/email/test?secret={SECRET}",
        json=payload, timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "request_created"
    req_id = body["request_id"]
    try:
        req = db["svc_job_requests"].find_one({"id": req_id})
        assert req is not None
        assert req["status"] == "pending"
        assert req.get("confidence", 0) < 0.9
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})
        db["svc_notifications"].delete_many({"source_id": req_id})


def test_hallucinated_high_confidence_without_site_falls_back(inbox):
    """Defence-in-depth — the AI sometimes claims confidence: 0.99 but
    every required field is missing. The deterministic min() floor
    must prevent auto-accept."""
    db = _mongo()
    payload = {
        "to": inbox["email"],
        "from": "vague@example.com",
        "subject": "stuff broken",
        "text": "things are broken",
        "parsed_override": {
            "customer_name": "Vague Customer",
            "site_name": None,          # ← deterministic gate fails here
            "site_postcode": None,
            "title": "Things broken",   # < 12 chars — title_substantial fails
            "priority": "P3",
            "confidence": 0.99,         # AI claims very high
        },
    }
    r = requests.post(
        f"{API}/api/inbound/email/test?secret={SECRET}",
        json=payload, timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "request_created", \
        f"hallucinated 0.99 must NOT auto-accept, got {body}"
    req_id = body["request_id"]
    try:
        # Stored confidence is floored by missing site (gate)
        # but title is long enough to score the title-bit, so the
        # deterministic confidence floor may equal 0.9. The point is
        # `outcome == request_created` — confidence is stored verbatim.
        req = db["svc_job_requests"].find_one({"id": req_id})
        assert req["confidence"] <= 0.9
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})
        db["svc_notifications"].delete_many({"source_id": req_id})


def test_auto_accept_threshold_can_be_disabled_via_short_title(inbox):
    """A 6-char title is below the deterministic floor — even with
    AI confidence 0.95 and full site/customer, we fall back."""
    db = _mongo()
    payload = {
        "to": inbox["email"],
        "from": "ops@acme-gyms.example",
        "subject": "Fix",
        "text": "Fix it",
        "parsed_override": {
            "customer_name": "Acme Gyms",
            "site_name": "Acme HQ",
            "site_postcode": "N1 7AB",
            "title": "Fix",         # < 12 chars
            "priority": "P3",
            "confidence": 0.95,
        },
    }
    r = requests.post(
        f"{API}/api/inbound/email/test?secret={SECRET}",
        json=payload, timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["outcome"] == "request_created"
    req_id = r.json()["request_id"]
    try:
        # Still recorded with a confidence value.
        req = db["svc_job_requests"].find_one({"id": req_id})
        assert "confidence" in req
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})
        db["svc_notifications"].delete_many({"source_id": req_id})
