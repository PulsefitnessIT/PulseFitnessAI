"""Iter 216h146 — Inbound email webhook tests."""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://fitness-ai-migrate.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def sess():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


def _secret():
    # The backend .env value — read from server env via /api/svc/engineer/inbound-address
    # we know it's set if "enabled" is true on that response.
    return os.environ.get("INBOUND_EMAIL_WEBHOOK_SECRET")


def test_inbound_address_returns_email(sess):
    tok = sess["token"]
    r = requests.get(f"{API}/api/svc/engineer/inbound-address",
                     headers=_hdr(tok), timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "@" in body["email"]
    assert body["domain"]
    assert body["slug"]
    assert body["enabled"] is True


def test_webhook_rejects_missing_secret(sess):
    tok = sess["token"]
    info = requests.get(f"{API}/api/svc/engineer/inbound-address",
                        headers=_hdr(tok), timeout=10).json()
    r = requests.post(
        f"{API}/api/inbound/email/test",
        json={"to": info["email"], "from": "qa@example.com",
              "subject": "Test", "text": "Hello"},
        timeout=15,
    )
    assert r.status_code == 401


def test_webhook_creates_request_with_valid_secret(sess):
    secret = _secret()
    if not secret:
        pytest.skip("INBOUND_EMAIL_WEBHOOK_SECRET not in test env")
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    info = requests.get(f"{API}/api/svc/engineer/inbound-address",
                        headers=_hdr(tok), timeout=10).json()
    r = requests.post(
        f"{API}/api/inbound/email/test?secret={secret}",
        json={"to": info["email"],
              "from": "Jane Customer <jane@example.com>",
              "subject": "Bike #3 broken at PureGym Soho",
              "text": "Hi - bike 3 belt slipping under load. Phone 07900000111."},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["outcome"] == "request_created"
    req_id = body["request_id"]
    try:
        doc = db["svc_job_requests"].find_one({"id": req_id})
        assert doc["engineer_id"] == user_id
        assert doc["organization_id"] == org_id
        assert doc["intake_channel"] == "inbound_email"
        assert doc["customer_email"] == "jane@example.com"
        assert doc["status"] == "pending"
        # Notification fired
        n = db["svc_notifications"].find_one(
            {"user_id": user_id, "source_type": "job_request", "source_id": req_id},
        )
        assert n is not None
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})
        db["svc_notifications"].delete_many({"source_id": req_id})


def test_webhook_unknown_recipient(sess):
    secret = _secret()
    if not secret:
        pytest.skip("INBOUND_EMAIL_WEBHOOK_SECRET not in test env")
    r = requests.post(
        f"{API}/api/inbound/email/test?secret={secret}",
        json={"to": f"nonexistent-{uuid.uuid4()}@in.gymaxis.com",
              "from": "x@y.com", "subject": "Lost", "text": "X"},
        timeout=15,
    )
    assert r.status_code == 404


def test_webhook_rejects_high_spam_score(sess):
    secret = _secret()
    if not secret:
        pytest.skip("INBOUND_EMAIL_WEBHOOK_SECRET not in test env")
    tok = sess["token"]
    info = requests.get(f"{API}/api/svc/engineer/inbound-address",
                        headers=_hdr(tok), timeout=10).json()
    db = _mongo()
    r = requests.post(
        f"{API}/api/inbound/email/test?secret={secret}",
        json={"to": info["email"], "from": "spam@x.com",
              "subject": "x", "text": "x", "spam_score": 9.5},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["outcome"] == "rejected_spam"
    # No job request created
    assert db["svc_job_requests"].count_documents({
        "source.from": "spam@x.com",
    }) == 0


def test_webhook_accepts_multipart_form_data(sess):
    """SendGrid Inbound Parse sends multipart/form-data, not JSON.
    Our webhook (the live /email path) must accept that too."""
    secret = _secret()
    if not secret:
        pytest.skip("INBOUND_EMAIL_WEBHOOK_SECRET not in test env")
    tok = sess["token"]
    info = requests.get(f"{API}/api/svc/engineer/inbound-address",
                        headers=_hdr(tok), timeout=10).json()
    db = _mongo()
    user_id = sess["user"]["id"]
    r = requests.post(
        f"{API}/api/inbound/email?secret={secret}",
        data={
            "to": info["email"],
            "from": "Multipart Customer <multi@example.com>",
            "subject": "Treadmill not powering on",
            "text": "Hi, treadmill 5 won't power on. Site: FitOne Camden.",
            "spam_score": "0.2",
        },
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "request_created"
    req_id = body["request_id"]
    try:
        doc = db["svc_job_requests"].find_one({"id": req_id})
        assert doc["customer_email"] == "multi@example.com"
        assert doc["intake_channel"] == "inbound_email"
        assert doc["engineer_id"] == user_id
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})
        db["svc_notifications"].delete_many({"source_id": req_id})
