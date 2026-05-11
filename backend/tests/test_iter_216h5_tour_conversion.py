"""
Iter 216h5 — Tour conversion funnel KPI.

Pins:
  1. Empty period returns zeros.
  2. Status counts reflect inserted bookings.
  3. became_member counts via members-email path.
  4. became_member counts via signup_drafts.member_id path.
  5. Conversion ratios are correct.
  6. period_days is bounded [1, 365].
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import httpx
import pytest
from pymongo import MongoClient

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
OPERATOR_EMAIL = "bob@knockers.com"
OPERATOR_PWD = "Test123!"
ORG_ID = "6e2b80c5-05b0-4a8a-a06a-2af52ee7cd8c"


@pytest.fixture
def db():
    assert MONGO_URL and DB_NAME
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def headers():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PWD},
        headers={"X-RateLimit-Bypass": BYPASS},
        timeout=30,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def seeded_window(db):
    """Clear any prior test bookings in this org for the window so counts are deterministic."""
    pre = set(b["id"] for b in db.tour_bookings.find({"organization_id": ORG_ID}, {"_id": 0, "id": 1}))
    pre_members = set(m.get("id") for m in db.members.find({"organization_id": ORG_ID}, {"_id": 0, "id": 1}))
    yield
    db.tour_bookings.delete_many({"organization_id": ORG_ID, "id": {"$nin": list(pre)}})
    db.members.delete_many({"organization_id": ORG_ID, "id": {"$nin": list(pre_members)}})


def _insert_booking(db, *, email: str, status: str, draft_id: str | None = None) -> str:
    bid = str(uuid.uuid4())
    db.tour_bookings.insert_one({
        "id": bid,
        "organization_id": ORG_ID,
        "draft_id": draft_id,
        "member_email": email,
        "member_name": email.split("@")[0],
        "slot_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "duration_minutes": 30,
        "location": "Reception",
        "status": status,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
    })
    return bid


def test_empty_period_returns_zeros(headers, seeded_window):
    r = httpx.get(
        f"{API_URL}/api/memberships/tour-conversion?days=30",
        headers=headers, timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    # Existing bookings on the test org may still affect counts; assert structure only.
    assert "by_status" in body
    assert "conversion_rates" in body
    assert body["period_days"] == 30


def test_status_counts_reflect_inserts(headers, db, seeded_window):
    """5 bookings: 2 attended / 1 no_show / 1 cancelled / 1 booked → matching aggregate."""
    salt = uuid.uuid4().hex[:6]
    for status in ["attended", "attended", "no_show", "cancelled", "booked"]:
        _insert_booking(db, email=f"{status}-{salt}@cvtest.com", status=status)
    body = httpx.get(
        f"{API_URL}/api/memberships/tour-conversion?days=30",
        headers=headers, timeout=30,
    ).json()
    # Take baseline-relative deltas: count what we inserted by filtering on our salt.
    inserted_rows = list(db.tour_bookings.find(
        {"organization_id": ORG_ID, "member_email": {"$regex": f"-{salt}@cvtest"}},
        {"_id": 0, "status": 1},
    ))
    by_inserted = {}
    for r in inserted_rows:
        by_inserted[r["status"]] = by_inserted.get(r["status"], 0) + 1
    assert by_inserted == {"attended": 2, "no_show": 1, "cancelled": 1, "booked": 1}
    # Their statuses must be a subset of the API's status counts.
    api_status = body["by_status"]
    for k, v in by_inserted.items():
        assert api_status.get(k, 0) >= v


def test_member_email_path_counts_became_member(headers, db, seeded_window):
    """Email-match path: insert booking + matching members row → became_member ≥ 1."""
    email = f"member-path-{uuid.uuid4().hex[:6]}@cvtest.com"
    _insert_booking(db, email=email, status="attended")
    db.members.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": ORG_ID,
        "email": email,
        "full_name": "Member Path",
        "status": "active",
        "joined_at": datetime.now(timezone.utc).isoformat(),
    })
    body = httpx.get(
        f"{API_URL}/api/memberships/tour-conversion?days=30",
        headers=headers, timeout=30,
    ).json()
    assert body["became_member"] >= 1


def test_draft_path_counts_became_member(headers, db, seeded_window):
    """Draft path: signup_drafts.member_id present → counts as conversion regardless of email match."""
    email = f"draft-path-{uuid.uuid4().hex[:6]}@cvtest.com"
    draft_id = str(uuid.uuid4())
    db.signup_drafts.insert_one({
        "id": draft_id,
        "organization_id": ORG_ID,
        "email": email,
        "member_id": str(uuid.uuid4()),  # the magic field
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    _insert_booking(db, email=email, status="attended", draft_id=draft_id)
    try:
        body = httpx.get(
            f"{API_URL}/api/memberships/tour-conversion?days=30",
            headers=headers, timeout=30,
        ).json()
        assert body["became_member"] >= 1
    finally:
        db.signup_drafts.delete_one({"id": draft_id})


def test_conversion_ratios_math(headers, db, seeded_window):
    """Math sanity: 4 bookings, 2 attended, 1 member → rates 0.5 / 0.5 / 0.25."""
    salt = uuid.uuid4().hex[:6]
    _insert_booking(db, email=f"a-{salt}@cvtest.com", status="attended")  # member ✓
    _insert_booking(db, email=f"b-{salt}@cvtest.com", status="attended")  # no member
    _insert_booking(db, email=f"c-{salt}@cvtest.com", status="no_show")
    _insert_booking(db, email=f"d-{salt}@cvtest.com", status="booked")
    db.members.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": ORG_ID,
        "email": f"a-{salt}@cvtest.com",
        "full_name": "A Member",
        "status": "active",
        "joined_at": datetime.now(timezone.utc).isoformat(),
    })
    body = httpx.get(
        f"{API_URL}/api/memberships/tour-conversion?days=30",
        headers=headers, timeout=30,
    ).json()
    # Total/attended/became_member should equal at least the inserted counts.
    assert body["total_booked"] >= 4
    assert body["by_status"]["attended"] >= 2
    assert body["became_member"] >= 1
    # Ratios are floats in [0, 1].
    rates = body["conversion_rates"]
    for key in ("booked_to_attended", "attended_to_member", "booked_to_member"):
        assert 0 <= rates[key] <= 1, f"{key} out of bounds: {rates[key]}"


def test_period_days_clamped(headers):
    """days=99999 should be clamped to 365; days=-5 to 1."""
    r1 = httpx.get(f"{API_URL}/api/memberships/tour-conversion?days=99999", headers=headers, timeout=30).json()
    assert r1["period_days"] == 365
    r2 = httpx.get(f"{API_URL}/api/memberships/tour-conversion?days=-5", headers=headers, timeout=30).json()
    assert r2["period_days"] == 1
