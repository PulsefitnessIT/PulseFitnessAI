"""Iter 216h165 — Single-refund detail endpoint with audit timeline."""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://staffing-ops-preview.preview.emergentagent.com").rstrip("/")
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
def admin():
    return _login("admin@gymaxisai.com", "MasterAdmin123!")


@pytest.fixture
def engineer():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


def _seed_refund_event(db, **overrides) -> str:
    rid = f"re_test_{uuid.uuid4().hex[:10]}"
    doc = {
        "id": rid,
        "charge_id": f"ch_{uuid.uuid4().hex[:14]}",
        "payment_intent": None,
        "status": "succeeded",
        "amount_pence": 2500,
        "currency": "gbp",
        "reason": "requested_by_customer",
        "internal_notes": "regression test",
        "organization_id": "org-test-216h165",
        "organization_name": "ACME Test Gym",
        "issued_by_user_id": "u-test",
        "issued_by_email": "admin@gymaxisai.com",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["refund_events"].insert_one(doc)
    return rid


def _seed_audit(db, refund_id: str, *, action="refund_issued", details="test entry"):
    db["audit_logs"].insert_one({
        "action": action,
        "user_id": "u-test",
        "user_email": "admin@gymaxisai.com",
        "resource_type": "refund",
        "resource_id": refund_id,
        "details": details,
        "ip_address": "127.0.0.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── 404 / auth ───────────────────────────────────────────────────

def test_detail_404_for_unknown_id(admin):
    r = requests.get(f"{API}/api/admin/refunds/re_bogus_xxx",
                     headers=_hdr(admin["token"]), timeout=20)
    assert r.status_code == 404


def test_detail_requires_master_admin(engineer):
    """A non-master-admin caller must be rejected even before the lookup."""
    r = requests.get(f"{API}/api/admin/refunds/re_anything",
                     headers=_hdr(engineer["token"]), timeout=20)
    assert r.status_code == 403


def test_detail_requires_auth():
    r = requests.get(f"{API}/api/admin/refunds/re_anything", timeout=20)
    assert r.status_code in (401, 403)


# ── Happy path ───────────────────────────────────────────────────

def test_detail_returns_event_and_audit_timeline(admin):
    db = _mongo()
    rid = _seed_refund_event(db)
    _seed_audit(db, rid, action="refund_issued", details="initial event")
    _seed_audit(db, rid, action="refund_review",  details="manual review")
    try:
        r = requests.get(f"{API}/api/admin/refunds/{rid}",
                         headers=_hdr(admin["token"]), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["refund"]["id"] == rid
        assert body["refund"]["organization_name"] == "ACME Test Gym"
        assert body["refund"]["amount_pence"] == 2500
        assert isinstance(body["audit"], list)
        assert len(body["audit"]) == 2
        actions = [a["action"] for a in body["audit"]]
        assert "refund_issued" in actions and "refund_review" in actions
        # Timeline must be sorted ascending by timestamp.
        ts = [a["timestamp"] for a in body["audit"]]
        assert ts == sorted(ts)
        # live snapshot key is always present; value may be None on test refunds.
        assert "live" in body
    finally:
        db["audit_logs"].delete_many({"resource_id": rid})
        db["refund_events"].delete_one({"id": rid})


def test_detail_backfills_org_name_when_missing(admin):
    """Pre-iter 215d0 rows only have organization_id. The detail
    endpoint must resolve `organization_name` on the fly."""
    db = _mongo()
    org_id = f"org-{uuid.uuid4().hex[:8]}"
    db["organizations"].insert_one({
        "id": org_id, "name": "Legacy Org 216h165",
    })
    rid = _seed_refund_event(
        db, organization_id=org_id, organization_name=None,
    )
    try:
        r = requests.get(f"{API}/api/admin/refunds/{rid}",
                         headers=_hdr(admin["token"]), timeout=20)
        assert r.status_code == 200
        assert r.json()["refund"]["organization_name"] == "Legacy Org 216h165"
    finally:
        db["refund_events"].delete_one({"id": rid})
        db["organizations"].delete_one({"id": org_id})


def test_lookup_endpoint_not_shadowed_by_detail(admin):
    """Regression: ensure `/admin/refunds/lookup` is not routed to the
    detail handler with refund_id=lookup."""
    r = requests.get(f"{API}/api/admin/refunds/lookup",
                     headers=_hdr(admin["token"]),
                     params={"query": "noop@example.com"}, timeout=20)
    # Lookup must succeed and return {"matches": [...]}.
    assert r.status_code == 200, r.text
    assert "matches" in r.json()
