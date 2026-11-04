"""Iter 216h144 — Engineer independence (self-create + supplier card) tests."""
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


def test_self_create_returns_case_and_self_assigns(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    db = _mongo()
    idempo = f"test-216h144-{uuid.uuid4()}"
    r = requests.post(
        f"{API}/api/svc/engineer/jobs/self-create",
        headers={**_hdr(tok), "Idempotency-Key": idempo},
        json={"title": "QA self-create", "priority": "P2",
              "intake_channel": "manual",
              "customer_name": "QA Customer"},
        timeout=10,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    case_id = body["case_id"]
    try:
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["assigned_engineer_id"] == user_id
        assert case["self_allocated"] is True
        assert case["reference"].startswith("SELF-")
        # Replay with same idempotency key returns same row
        r2 = requests.post(
            f"{API}/api/svc/engineer/jobs/self-create",
            headers={**_hdr(tok), "Idempotency-Key": idempo},
            json={"title": "QA self-create (replay)", "priority": "P2",
                  "intake_channel": "manual"},
            timeout=10,
        )
        assert r2.status_code in (200, 201)
        assert r2.json()["case_id"] == case_id
    finally:
        db["svc_cases"].delete_one({"id": case_id})


def test_intake_card_returns_slug_and_share_url(sess):
    tok = sess["token"]
    r = requests.get(f"{API}/api/svc/engineer/intake-card",
                     headers=_hdr(tok), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"]
    assert body["share_url"]
    # Calling again should return the same slug (stable)
    r2 = requests.get(f"{API}/api/svc/engineer/intake-card",
                      headers=_hdr(tok), timeout=10)
    assert r2.json()["slug"] == body["slug"]


def test_public_card_get_and_submit_then_accept(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    db = _mongo()
    # Ensure intake slug
    info = requests.get(f"{API}/api/svc/engineer/intake-card",
                        headers=_hdr(tok), timeout=10).json()
    slug = info["slug"]

    # Public GET — no auth required
    rg = requests.get(f"{API}/api/r/{slug}", timeout=10)
    assert rg.status_code == 200
    assert rg.json()["slug"] == slug
    # Public POST submit
    rs = requests.post(
        f"{API}/api/r/{slug}/request",
        json={"customer_name": "Public QA",
               "customer_email": "qa@example.com",
               "title": "Treadmill belt slipping",
               "description": "Slip under load",
               "priority": "P3",
               "consent": True},
        timeout=10,
    )
    assert rs.status_code == 201, rs.text
    req_id = rs.json()["request_id"]
    try:
        # Engineer sees it in inbox
        rl = requests.get(f"{API}/api/svc/engineer/job-requests",
                          headers=_hdr(tok), timeout=10)
        assert rl.status_code == 200
        ids = [x["id"] for x in rl.json()["requests"]]
        assert req_id in ids
        # Accept
        ra = requests.post(
            f"{API}/api/svc/engineer/job-requests/{req_id}/accept",
            headers=_hdr(tok),
            json={"estimated_minutes": 90},
            timeout=10,
        )
        assert ra.status_code == 200, ra.text
        case_id = ra.json()["case_id"]
        case = db["svc_cases"].find_one({"id": case_id})
        try:
            assert case["assigned_engineer_id"] == user_id
            assert case["intake_channel"] == "supplier_card"
            assert case["customer_email"] == "qa@example.com"
            assert case["job_request_id"] == req_id
            # Notification fired
            n = db["svc_notifications"].find_one(
                {"user_id": user_id, "source_type": "job_request", "source_id": req_id},
            )
            assert n is not None, "Supplier-card submit should fire a notification"
        finally:
            db["svc_cases"].delete_one({"id": case_id})
            db["svc_notifications"].delete_many({"source_id": req_id})
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})


def test_public_consent_required():
    """Submit without consent should 400."""
    # Use a fresh login to fetch a slug
    sess = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    info = requests.get(f"{API}/api/svc/engineer/intake-card",
                        headers=_hdr(sess["token"]), timeout=10).json()
    r = requests.post(
        f"{API}/api/r/{info['slug']}/request",
        json={"customer_name": "X", "customer_email": "x@x.com",
               "title": "No consent", "consent": False, "priority": "P3"},
        timeout=10,
    )
    assert r.status_code == 400


def test_decline_request(sess):
    tok = sess["token"]
    db = _mongo()
    info = requests.get(f"{API}/api/svc/engineer/intake-card",
                        headers=_hdr(tok), timeout=10).json()
    rs = requests.post(
        f"{API}/api/r/{info['slug']}/request",
        json={"customer_name": "Decliner",
               "customer_email": "d@example.com",
               "title": "Decline me", "consent": True, "priority": "P4"},
        timeout=10,
    )
    req_id = rs.json()["request_id"]
    try:
        rd = requests.post(
            f"{API}/api/svc/engineer/job-requests/{req_id}/decline",
            headers=_hdr(tok),
            json={"reason": "Out of area"},
            timeout=10,
        )
        assert rd.status_code == 200
        # Cannot accept after decline
        ra = requests.post(
            f"{API}/api/svc/engineer/job-requests/{req_id}/accept",
            headers=_hdr(tok), json={}, timeout=10,
        )
        assert ra.status_code == 409
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})


def test_parse_email_returns_shape(sess):
    """We can't always guarantee a real LLM response in CI, but the
    endpoint should at least return the expected shape (502 OR a parsed
    dict). If EMERGENT_LLM_KEY is absent the endpoint returns 503."""
    tok = sess["token"]
    r = requests.post(
        f"{API}/api/svc/engineer/jobs/parse-email",
        headers=_hdr(tok),
        json={"email_body": "Hi, our treadmill #2 at PureGym Soho is broken — belt slips. "
                            "Please call John on 07900 000111 (john@example.com). Thanks.",
               "subject": "Broken treadmill"},
        timeout=30,
    )
    # The LLM might not be configured in the preview environment — accept
    # success, 502 (LLM error) or 503 (key missing).
    assert r.status_code in (200, 502, 503), r.text
    if r.status_code == 200:
        data = r.json()
        assert "parsed" in data
        assert set(data["parsed"].keys()) >= {
            "customer_name", "customer_email", "site_name", "title",
            "description", "priority",
        }
