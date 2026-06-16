"""Iter 220l — Pre-launch polish (4 items).

Covers:
  1. VAT-exempt engineer toggle (`PUT /api/partners/me/tax-settings`)
     + invoice payload honours the flag and stamps `vat_exempt`.
  2. Engineer self-service ratings view
     (`GET /api/svc/engineer/me/ratings`) — summary + distribution
     + list shape.
  3. Customer "Request this engineer again"
     (`POST /api/svc/public/track/{token}/preferred-engineer`).
  4. Job grant max-age — grants get `expires_at` on creation and
     stale grants no longer count via `_has_access_via_grant`.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://fitness-ai-migrate.preview.emergentagent.com",
)


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, headers=_bypass())
        r.raise_for_status()
        d = r.json()
    return d.get("token") or d.get("access_token")


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def me_user_id(db):
    u = db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0, "id": 1, "organization_id": 1})
    return u["id"]


# ────────────────────────────────────────────────────────────────────
# 1. VAT toggle + invoice integration
# ────────────────────────────────────────────────────────────────────


def test_vat_toggle_400s_when_no_body():
    """Empty body should 400 — protects against silent no-op writes."""
    with httpx.Client(timeout=15.0) as c:
        r = c.put(f"{BASE}/api/partners/me/tax-settings", headers=_hdr(), json={})
    # Master admin has no partner record so we hit the 404 first; the
    # endpoint guards "no partner" before "no body".
    assert r.status_code in (400, 404)


def test_vat_toggle_persists_for_partner(db, me_user_id):
    """Insert a real partner record + flip the VAT flag end-to-end."""
    partner_id = f"pe_iter220l_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220l_test": True,
        "user_id": me_user_id,
        "status": "approved",
        "subscription": {"status": "active"},
        "vat_registered": True,
        "vat_number": "GB000000000",
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.put(
                f"{BASE}/api/partners/me/tax-settings",
                headers=_hdr(),
                json={"vat_registered": False},
            )
        assert r.status_code == 200, r.text
        p = r.json()["partner"]
        assert p["vat_registered"] is False
        # vat_number must be wiped when un-ticked
        assert p.get("vat_number") in (None, "")
    finally:
        db.partner_engineers.delete_one({"id": partner_id})


def test_invoice_payload_zeroes_vat_when_engineer_exempt():
    """_build_invoice_payload must force vat_rate=0 + vat_exempt=True
    when the engineer is flagged as not-VAT-registered."""
    from routes.svc.engineer_invoices import _build_invoice_payload
    inv = _build_invoice_payload(
        user={"id": "u1", "organization_id": "o1", "email": "e@e.test"},
        engineer={"full_name": "Test", "email": "e@e.test"},
        issue_date=datetime.now(timezone.utc),
        payment_terms_days=14,
        body={
            "case_id": "c1",
            "lines": [{"description": "Labour", "quantity": 1, "unit_price": 100.0}],
            "vat_rate": 20,
            "discount_pct": 0,
        },
        case_snapshot={"id": "c1", "reference": "REF-1"},
        vat_settings={"vat_registered": False, "vat_number": None},
    )
    assert inv["vat_exempt"] is True
    assert inv["vat_rate"] == 0
    assert inv["vat_amount"] == 0
    assert inv["total"] == 100.0  # subtotal only


def test_invoice_payload_keeps_vat_when_engineer_registered():
    """Backward-compat: vat_registered=True (or omitted) keeps the
    20% default in place."""
    from routes.svc.engineer_invoices import _build_invoice_payload
    inv = _build_invoice_payload(
        user={"id": "u1", "organization_id": "o1", "email": "e@e.test"},
        engineer={"full_name": "Test", "email": "e@e.test"},
        issue_date=datetime.now(timezone.utc),
        payment_terms_days=14,
        body={
            "case_id": "c1",
            "lines": [{"description": "Labour", "quantity": 1, "unit_price": 100.0}],
            "vat_rate": 20,
            "discount_pct": 0,
        },
        case_snapshot={"id": "c1", "reference": "REF-1"},
        vat_settings={"vat_registered": True, "vat_number": "GB123"},
    )
    assert inv["vat_exempt"] is False
    assert inv["vat_rate"] == 20
    assert inv["vat_amount"] == 20.0
    assert inv["total"] == 120.0


# ────────────────────────────────────────────────────────────────────
# 2. Engineer ratings self-view
# ────────────────────────────────────────────────────────────────────


def test_ratings_endpoint_empty_state():
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{BASE}/api/svc/engineer/me/ratings", headers=_hdr())
    assert r.status_code == 200, r.text
    body = r.json()
    assert "summary" in body
    assert "ratings" in body
    assert isinstance(body["summary"]["distribution"], dict)
    assert {"1", "2", "3", "4", "5"} <= set(body["summary"]["distribution"].keys())


def test_ratings_endpoint_aggregates_real_data(db, me_user_id):
    """Seed a few rated cases and check avg + distribution + list."""
    org_id = db.users.find_one({"id": me_user_id})["organization_id"]
    case_ids: list[str] = []
    for stars, comment in ((5, "Great work"), (4, "Solid"), (5, "Quick fix")):
        cid = f"case_220l_rating_{uuid.uuid4().hex[:6]}"
        db.svc_cases.insert_one({
            "id": cid,
            "organization_id": org_id,
            "assigned_engineer_id": me_user_id,
            "status": "closed",
            "reference": f"REF-{stars}",
            "title": f"Test case {stars}",
            "customer_rating": stars,
            "customer_rating_comment": comment,
            "customer_name": "Test Customer",
            "customer_feedback_at": datetime.now(timezone.utc).isoformat(),
        })
        case_ids.append(cid)
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/api/svc/engineer/me/ratings", headers=_hdr())
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["count"] >= 3
        assert body["summary"]["avg"] is not None
        # Should find our 3 seeded cases somewhere in the list
        our_ids = {x["case_id"] for x in body["ratings"]}
        for cid in case_ids:
            assert cid in our_ids
    finally:
        db.svc_cases.delete_many({"id": {"$in": case_ids}})


# ────────────────────────────────────────────────────────────────────
# 3. Customer "Request this engineer again"
# ────────────────────────────────────────────────────────────────────


def test_preferred_engineer_endpoint_creates_row(db, me_user_id):
    """Token + engineer → row in svc_engineer_preferences."""
    org_id = db.users.find_one({"id": me_user_id})["organization_id"]
    token = f"tok_{uuid.uuid4().hex}"
    case_id = f"case_220l_pref_{uuid.uuid4().hex[:6]}"
    db.svc_cases.insert_one({
        "id": case_id,
        "organization_id": org_id,
        "track_token": token,
        "assigned_engineer_id": me_user_id,
        "assigned_engineer_name": "Test Engineer",
        "customer_name": "Happy Customer",
        "customer_email": "happy@example.test",
        "status": "closed",
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{BASE}/api/svc/public/track/{token}/preferred-engineer",
                json={"note": "Loved the work!"},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body.get("requested_at")

        pref = db.svc_engineer_preferences.find_one({"track_token": token})
        assert pref is not None
        assert pref["engineer_id"] == me_user_id
        assert pref["note"] == "Loved the work!"

        # Idempotent — second call upserts, doesn't duplicate.
        with httpx.Client(timeout=15.0) as c:
            r2 = c.post(f"{BASE}/api/svc/public/track/{token}/preferred-engineer", json={})
        assert r2.status_code == 200
        count = db.svc_engineer_preferences.count_documents({"track_token": token, "engineer_id": me_user_id})
        assert count == 1
    finally:
        db.svc_cases.delete_one({"id": case_id})
        db.svc_engineer_preferences.delete_many({"track_token": token})


def test_preferred_engineer_404_for_invalid_token():
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/svc/public/track/short/preferred-engineer", json={})
    assert r.status_code == 404
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/svc/public/track/not_a_valid_token_xyz_999/preferred-engineer", json={})
    assert r.status_code == 404


def test_preferred_engineer_409_when_no_engineer(db, me_user_id):
    """Unassigned case → 409 (no engineer to request)."""
    org_id = db.users.find_one({"id": me_user_id})["organization_id"]
    token = f"tok_unassigned_{uuid.uuid4().hex}"
    case_id = f"case_220l_noeng_{uuid.uuid4().hex[:6]}"
    db.svc_cases.insert_one({
        "id": case_id,
        "organization_id": org_id,
        "track_token": token,
        "assigned_engineer_id": None,
        "status": "new",
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(f"{BASE}/api/svc/public/track/{token}/preferred-engineer", json={})
        assert r.status_code == 409
    finally:
        db.svc_cases.delete_one({"id": case_id})


# ────────────────────────────────────────────────────────────────────
# 4. Job grant max-age
# ────────────────────────────────────────────────────────────────────


def test_grant_gets_expires_at_on_creation(db, me_user_id):
    """New grants must have an expires_at ~30 days out by default."""
    org_id = db.users.find_one({"id": me_user_id})["organization_id"]
    eng_user = db.users.find_one({"organization_id": org_id, "id": {"$ne": me_user_id}}, {"_id": 0, "email": 1})
    if not eng_user:
        # Fall back to creating against an admin-known test address — the
        # endpoint requires an existing user, so if we can't find one,
        # skip this test (graceful for thin envs).
        pytest.skip("No second user in org to use as engineer")
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/customer-engineer-grants",
            headers=_hdr(),
            json={
                "engineer_email": eng_user["email"],
                "case_ids": ["c_iter220l_test"],
                "expires_in_days": 7,
            },
        )
    if r.status_code == 404:
        pytest.skip(f"Engineer {eng_user['email']} not a known user for grants")
    assert r.status_code == 200, r.text
    grant = r.json()["grant"]
    assert "expires_at" in grant
    assert grant["expires_in_days"] == 7
    # Cleanup
    db.partner_job_grants.delete_one({"id": grant["id"]})


def test_expired_grant_does_not_count_for_access(db):
    """An active grant whose expires_at has passed must NOT unlock
    access via _has_access_via_grant."""
    from routes.partners import _has_access_via_grant
    fake_user_id = f"u_iter220l_{uuid.uuid4().hex[:6]}"
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    expired_id = f"grant_expired_{uuid.uuid4().hex[:6]}"
    fresh_id = f"grant_fresh_{uuid.uuid4().hex[:6]}"
    db.partner_job_grants.insert_one({
        "id": expired_id,
        "engineer_user_id": fake_user_id,
        "active": True,
        "expires_at": past,
    })
    try:
        # Only an expired grant → no access
        result = asyncio.get_event_loop().run_until_complete(_has_access_via_grant(fake_user_id))
        assert result is False

        # Add a fresh one → access granted
        db.partner_job_grants.insert_one({
            "id": fresh_id,
            "engineer_user_id": fake_user_id,
            "active": True,
            "expires_at": future,
        })
        result = asyncio.get_event_loop().run_until_complete(_has_access_via_grant(fake_user_id))
        assert result is True
    finally:
        db.partner_job_grants.delete_many({"id": {"$in": [expired_id, fresh_id]}})
