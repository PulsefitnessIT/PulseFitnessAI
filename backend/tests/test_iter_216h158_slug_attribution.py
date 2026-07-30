"""Iter 216h158 — Public-card slug attribution + conversion analytics.

Closes the marketing-analytics gap from the Feb 2026 process audit:
every case created via the supplier-card flow (manual accept OR
inbound-email auto-accept) now carries `source_card_slug` +
`source_engineer_id` so marketing / ops can answer "which engineer's
QR card converted best this month".

Audits:
  • accept_job_request copies `intake_slug` → case.source_card_slug.
  • engineer self_allocate writes source_engineer_id on the case.
  • Inbound-email auto-accept writes both source_card_slug + engineer_id.
  • `GET /api/svc/engineer/independence/card-conversions` returns a
    per-slug rollup with requests, cases, revenue and rate, sorted by
    revenue desc.
  • Window param `?days=` clamps to 1–365.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://mod-hq-email.preview.emergentagent.com").rstrip("/")
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


def _seed_request(db, org_id, *, slug, engineer_id, engineer_name="QA Eng"):
    rid = str(uuid.uuid4())
    db["svc_job_requests"].insert_one({
        "id": rid,
        "engineer_id": engineer_id,
        "engineer_name": engineer_name,
        "organization_id": org_id,
        "intake_slug": slug,
        "intake_channel": "supplier_card",
        "status": "pending",
        "customer_name": "QA Customer",
        "customer_email": "qa@example.com",
        "site_name": "QA Site",
        "site_postcode": "N1 1AA",
        "title": "Attribution QA",
        "description": "Test description",
        "priority": "P3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return rid


def _seed_case(db, org_id, *, slug, engineer_id, status="closed",
               intake_channel="supplier_card"):
    case_id = str(uuid.uuid4())
    db["svc_cases"].insert_one({
        "id": case_id,
        "organization_id": org_id,
        "reference": f"ATR-{case_id[:5]}",
        "title": "Attribution QA case",
        "status": status,
        "priority": "P3",
        "intake_channel": intake_channel,
        "source_card_slug": slug,
        "source_engineer_id": engineer_id,
        "assigned_engineer_id": engineer_id,
        "assigned_engineer_name": "QA Eng",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return case_id


def _seed_quote(db, org_id, case_id, *, net, status="invoiced"):
    qid = str(uuid.uuid4())
    db["svc_quotes"].insert_one({
        "id": qid,
        "organization_id": org_id,
        "case_id": case_id,
        "status": status,
        "net": net,
        "subtotal": net,
        "gross": round(net * 1.2, 2),
        "total": round(net * 1.2, 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return qid


# ── accept_job_request copies slug onto case ────────────────────

def test_accept_job_request_writes_source_slug(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    slug = f"qa-slug-{uuid.uuid4().hex[:6]}"
    req_id = _seed_request(db, org_id, slug=slug, engineer_id=user_id)
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/job-requests/{req_id}/accept",
            headers=_hdr(tok), json={}, timeout=15,
        )
        assert r.status_code == 200, r.text
        case_id = r.json()["case_id"]
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["source_card_slug"] == slug
        assert case["source_engineer_id"] == user_id
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["audit_logs"].delete_many({"resource_id": case_id})
        db["svc_sicon_outbox"].delete_many(
            {"$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id}]},
        )
    finally:
        db["svc_job_requests"].delete_one({"id": req_id})


# ── self_allocate stamps source_engineer_id ─────────────────────

def test_self_allocate_writes_source_engineer_id(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    db = _mongo()
    r = requests.post(
        f"{API}/api/svc/engineer/jobs/self-create",
        headers=_hdr(tok),
        json={
            "title": "Slug attribution self-allocate",
            "description": "QA",
            "priority": "P3",
            "customer_name": "QA",
            "site_name": "QA",
            "intake_channel": "phone",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201)
    case_id = r.json()["case_id"]
    try:
        db = _mongo()
        case = db["svc_cases"].find_one({"id": case_id})
        assert case["source_engineer_id"] == user_id
        # No slug attribution for phone walk-ups.
        assert case.get("source_card_slug") is None
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["audit_logs"].delete_many({"resource_id": case_id})
        db["svc_sicon_outbox"].delete_many(
            {"$or": [{"payload.OurReference": case_id},
                     {"payload.ServiceCallReference": case_id}]},
        )


# ── card-conversions analytics ──────────────────────────────────

def test_card_conversions_aggregates_correctly(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    slug_a = f"qa-a-{uuid.uuid4().hex[:6]}"
    slug_b = f"qa-b-{uuid.uuid4().hex[:6]}"
    # Slug A: 3 requests (2 accepted, 1 pending), 2 closed cases £400+£600
    a_reqs = [_seed_request(db, org_id, slug=slug_a, engineer_id=user_id)
              for _ in range(3)]
    db["svc_job_requests"].update_many(
        {"id": {"$in": a_reqs[:2]}}, {"$set": {"status": "accepted"}},
    )
    case_a1 = _seed_case(db, org_id, slug=slug_a, engineer_id=user_id)
    case_a2 = _seed_case(db, org_id, slug=slug_a, engineer_id=user_id)
    q1 = _seed_quote(db, org_id, case_a1, net=400.0)
    q2 = _seed_quote(db, org_id, case_a2, net=600.0)
    # Slug B: 1 request, 1 case, £100 — should sort below A.
    b_req = _seed_request(db, org_id, slug=slug_b, engineer_id=user_id)
    case_b1 = _seed_case(db, org_id, slug=slug_b, engineer_id=user_id,
                         intake_channel="inbound_email")
    q3 = _seed_quote(db, org_id, case_b1, net=100.0)
    try:
        r = requests.get(
            f"{API}/api/svc/engineer/independence/card-conversions",
            headers=_hdr(tok), timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Find our seeded rows in the response (ignore other test debris).
        rows = {row["slug"]: row for row in body["rows"]
                if row["slug"] in (slug_a, slug_b)}
        assert slug_a in rows and slug_b in rows
        a = rows[slug_a]
        assert a["requests_total"] == 3
        assert a["requests_accepted"] == 2
        assert a["requests_pending"] == 1
        assert a["cases_total"] == 2
        assert a["cases_closed"] == 2
        assert a["revenue_total"] == 1000.0
        # Conversion = accepted / total = 2/3 ≈ 0.667
        assert a["conversion_rate"] == 0.667
        b = rows[slug_b]
        assert b["cases_inbound_email"] == 1
        assert b["revenue_total"] == 100.0
        # Sort order: A appears before B because revenue desc.
        order = [r["slug"] for r in body["rows"] if r["slug"] in (slug_a, slug_b)]
        assert order.index(slug_a) < order.index(slug_b)
    finally:
        db["svc_job_requests"].delete_many({"id": {"$in": a_reqs + [b_req]}})
        db["svc_cases"].delete_many({"id": {"$in": [case_a1, case_a2, case_b1]}})
        db["svc_quotes"].delete_many({"id": {"$in": [q1, q2, q3]}})


def test_card_conversions_days_window_clamped(sess):
    tok = sess["token"]
    # Below 1
    r = requests.get(
        f"{API}/api/svc/engineer/independence/card-conversions?days=0",
        headers=_hdr(tok), timeout=15,
    )
    assert r.status_code == 422
    # Above 365
    r2 = requests.get(
        f"{API}/api/svc/engineer/independence/card-conversions?days=500",
        headers=_hdr(tok), timeout=15,
    )
    assert r2.status_code == 422


def test_card_conversions_excludes_old_data(sess):
    """A case older than the window must NOT appear in totals."""
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    slug = f"qa-old-{uuid.uuid4().hex[:6]}"
    old_case_id = str(uuid.uuid4())
    db["svc_cases"].insert_one({
        "id": old_case_id,
        "organization_id": org_id,
        "reference": f"OLD-{old_case_id[:5]}",
        "title": "Aged case",
        "status": "closed",
        "intake_channel": "supplier_card",
        "source_card_slug": slug,
        "source_engineer_id": user_id,
        # Way outside the default 90-day window.
        "created_at": (datetime.now(timezone.utc)
                       - timedelta(days=400)).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        r = requests.get(
            f"{API}/api/svc/engineer/independence/card-conversions?days=30",
            headers=_hdr(tok), timeout=15,
        )
        assert r.status_code == 200
        rows = {row["slug"]: row for row in r.json()["rows"]}
        assert slug not in rows or rows[slug]["cases_total"] == 0
    finally:
        db["svc_cases"].delete_one({"id": old_case_id})
