"""Iter 283 — Failed email Resend (single + Resend-all) contract tests."""
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
BYPASS = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
TAG = "TEST_iter283"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, headers=BYPASS, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin():
    return {"Authorization": f"Bearer {_login('admin@pulsefitness.com', 'C2s9yJ3YAhydB4d34-Bykg')}"}


@pytest.fixture(scope="module")
def std():
    return {"Authorization": f"Bearer {_login('portal@pulsefitness.ltd', 'PulseFleet123!')}"}


def _seed(status="failed", payload=True, retried=False, sender="Pulse Fitness <service@pulsefitness.com>", age_days=0):
    eid = f"{TAG}-{uuid.uuid4()}"
    doc = {"id": eid, "to": "test+iter283@example.com", "subject": f"{TAG} {status}",
           "sender": sender, "status": status, "error": "fixture", "tag": TAG,
           "created_at": datetime.now(timezone.utc) - timedelta(days=age_days)}
    if payload:
        doc["payload"] = {"from": sender, "to": ["test+iter283@example.com"],
                          "subject": f"{TAG} {status}", "html": "<p>x</p>"}
    if retried:
        doc["retried_at"] = datetime.now(timezone.utc)
    mdb.email_send_events.insert_one(doc)
    return eid


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    ids = [d["id"] for d in mdb.email_send_events.find({"tag": TAG}, {"id": 1})]
    mdb.email_send_events.delete_many({"$or": [{"tag": TAG}, {"retry_of": {"$in": ids}}]})


# --- unit: sender repair
def test_repair_from():
    from routes.email_health import _repair_from
    assert _repair_from("Pulse <service@pulsefitness.com>") == "Pulse <service@modservice.pulsefitness.com>"
    assert _repair_from("service@pulsefitness.com") == "service@modservice.pulsefitness.com"
    assert _repair_from("x@modservice.pulsefitness.com") == "x@modservice.pulsefitness.com"
    assert _repair_from("a@other.com") == "a@other.com"


# --- GET endpoints include retryable_count
def test_health_and_emails_retryable_count(admin):
    _seed()
    h = requests.get(f"{API}/master-admin/email-health", headers=admin, timeout=20)
    assert h.status_code == 200
    assert isinstance(h.json()["retryable_count"], int) and h.json()["retryable_count"] >= 1
    e = requests.get(f"{API}/master-admin/emails", headers=admin, timeout=20)
    assert e.status_code == 200
    assert e.json()["retryable_count"] == h.json()["retryable_count"]
    assert all("payload" not in i for i in e.json()["items"])


# --- 403 for non-master
@pytest.mark.parametrize("method,path", [
    ("get", "/master-admin/email-health"), ("get", "/master-admin/emails"),
    ("post", "/master-admin/email-events/retry-failed"), ("post", "/master-admin/email-events/xyz/retry")])
def test_non_master_403(std, method, path):
    r = getattr(requests, method)(f"{API}{path}", headers=std, timeout=20)
    assert r.status_code == 403, r.text


def test_retry_unknown_404(admin):
    r = requests.post(f"{API}/master-admin/email-events/nope-{uuid.uuid4()}/retry", headers=admin, timeout=20)
    assert r.status_code == 404


def test_retry_sent_409(admin):
    r = requests.post(f"{API}/master-admin/email-events/{_seed(status='sent')}/retry", headers=admin, timeout=20)
    assert r.status_code == 409


def test_retry_already_retried_409(admin):
    r = requests.post(f"{API}/master-admin/email-events/{_seed(retried=True)}/retry", headers=admin, timeout=20)
    assert r.status_code == 409


def test_retry_no_payload_409(admin):
    r = requests.post(f"{API}/master-admin/email-events/{_seed(payload=False)}/retry", headers=admin, timeout=20)
    assert r.status_code == 409


def test_retry_rejected_422_json_and_marks_retried(admin):
    eid = _seed()
    r = requests.post(f"{API}/master-admin/email-events/{eid}/retry", headers=admin, timeout=40)
    assert r.status_code in (200, 422), r.text
    assert r.headers.get("content-type", "").startswith("application/json")
    if r.status_code == 422:
        assert "Resend rejected it again" in r.json()["detail"]
    orig = mdb.email_send_events.find_one({"id": eid})
    assert orig.get("retried_at") and orig.get("retry_event_id")
    new = mdb.email_send_events.find_one({"retry_of": eid})
    assert new is not None
    assert new["sender"].endswith("@modservice.pulsefitness.com>"), new["sender"]
    # second retry → 409
    r2 = requests.post(f"{API}/master-admin/email-events/{eid}/retry", headers=admin, timeout=20)
    assert r2.status_code == 409


def test_retry_all_shape_and_no_double_replay(admin):
    a, b = _seed(), _seed()
    old = _seed(age_days=9)
    r = requests.post(f"{API}/master-admin/email-events/retry-failed", headers=admin, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("attempted", "sent", "failed", "errors"):
        assert k in d
    assert d["attempted"] == d["sent"] + d["failed"] and d["attempted"] <= 60
    assert len(d["errors"]) <= 10
    for eid in (a, b):
        assert mdb.email_send_events.find_one({"id": eid}).get("retried_at")
    assert not mdb.email_send_events.find_one({"id": old}).get("retried_at"), "old (>7d) row should not be replayed"
    # the failures created by this run are themselves retryable (new rows) — but originals must not replay again
    r2 = requests.post(f"{API}/master-admin/email-events/retry-failed", headers=admin, timeout=120)
    assert r2.status_code == 200
    assert mdb.email_send_events.count_documents({"retry_of": a}) == 1
