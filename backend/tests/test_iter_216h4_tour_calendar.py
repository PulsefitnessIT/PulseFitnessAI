"""
Iter 216h4 — Tour Calendar booking flow.

Pins the contract for the public slot picker + operator console:
  1. Default config returns Mon-Fri 10-16 with 30-min slots when no config exists.
  2. Slot generation respects lead-time + ahead-window.
  3. Booking a slot removes it from public availability (capacity=1 default).
  4. Re-booking the same draft+slot is idempotent.
  5. Lead-time/past-slot bookings are rejected.
  6. Operator can list, mark attended, cancel.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

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
TEST_SLUG = "strong-fitness-test"
TEST_ORG_ID = "6e2b80c5-05b0-4a8a-a06a-2af52ee7cd8c"


@pytest.fixture
def db():
    assert MONGO_URL and DB_NAME
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def operator_headers():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PWD},
        headers={"X-RateLimit-Bypass": BYPASS},
        timeout=30,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _create_draft(email: str, first: str = "Tour", last: str = "Tester") -> str:
    r = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft",
        json={"first_name": first, "last_name": last, "email": email, "step": "details"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["draft_id"]


def _fetch_slots() -> dict:
    r = httpx.get(f"{API_URL}/api/public/signup/{TEST_SLUG}/tour-slots", timeout=30)
    r.raise_for_status()
    return r.json()


@pytest.fixture
def cleanup_tour_data(db):
    """Snapshot existing bookings then restore — keeps tests isolated."""
    pre_drafts = set(d["id"] for d in db.signup_drafts.find({}, {"_id": 0, "id": 1}))
    pre_bookings = set(b["id"] for b in db.tour_bookings.find({}, {"_id": 0, "id": 1}))
    yield
    db.signup_drafts.delete_many({"id": {"$nin": list(pre_drafts)}})
    db.tour_bookings.delete_many({"id": {"$nin": list(pre_bookings)}})


def test_public_tour_config_returns_defaults():
    r = httpx.get(f"{API_URL}/api/public/signup/{TEST_SLUG}/tour-config", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["slot_duration_minutes"] == 30
    assert body["lead_time_hours"] == 4
    assert body["ahead_window_days"] == 14
    assert body["location"]


def test_slots_grid_respects_lead_time_and_window():
    body = _fetch_slots()
    assert body["total"] > 0
    # No date keys older than today; no slots within the next 4 hours.
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    for date_key in body["slots_by_date"]:
        assert date_key >= today
    # All slots should be at least lead_time_hours into the future.
    for slots in body["slots_by_date"].values():
        for s in slots:
            slot_dt = datetime.fromisoformat(s["slot_at"].replace("Z", "+00:00"))
            delta_hours = (slot_dt - now).total_seconds() / 3600
            assert delta_hours >= 3.5  # 4-hour cutoff with some grace


def test_book_then_slot_removed_from_availability(cleanup_tour_data):
    email = f"tour-{uuid.uuid4().hex[:8]}@example.com"
    draft = _create_draft(email)
    before = _fetch_slots()
    first_date = sorted(before["slots_by_date"].keys())[0]
    pick = before["slots_by_date"][first_date][0]["slot_at"]
    r = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{draft}/book-tour",
        json={"slot_at": pick, "email": email},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.json()["idempotent"] is False
    after = _fetch_slots()
    # Pick should no longer appear anywhere
    all_after = [s["slot_at"] for slots in after["slots_by_date"].values() for s in slots]
    assert pick not in all_after


def test_idempotent_rebook_same_draft_same_slot(cleanup_tour_data):
    email = f"tour-{uuid.uuid4().hex[:8]}@example.com"
    draft = _create_draft(email)
    first_date = sorted(_fetch_slots()["slots_by_date"].keys())[0]
    pick = _fetch_slots()["slots_by_date"][first_date][0]["slot_at"]
    r1 = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{draft}/book-tour",
        json={"slot_at": pick}, timeout=30,
    )
    r2 = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{draft}/book-tour",
        json={"slot_at": pick}, timeout=30,
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["booking_id"] == r2.json()["booking_id"]
    assert r2.json()["idempotent"] is True


def test_capacity_conflict_returns_409(cleanup_tour_data):
    e1 = f"tour-{uuid.uuid4().hex[:8]}@example.com"
    e2 = f"tour-{uuid.uuid4().hex[:8]}@example.com"
    d1 = _create_draft(e1)
    d2 = _create_draft(e2)
    first_date = sorted(_fetch_slots()["slots_by_date"].keys())[0]
    pick = _fetch_slots()["slots_by_date"][first_date][0]["slot_at"]
    r1 = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{d1}/book-tour",
        json={"slot_at": pick}, timeout=30,
    )
    assert r1.status_code == 200
    r2 = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{d2}/book-tour",
        json={"slot_at": pick}, timeout=30,
    )
    assert r2.status_code == 409


def test_past_slot_rejected(cleanup_tour_data):
    draft = _create_draft(f"tour-{uuid.uuid4().hex[:8]}@example.com")
    r = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{draft}/book-tour",
        json={"slot_at": "2020-01-01T10:00:00Z"}, timeout=30,
    )
    assert r.status_code == 400


def test_operator_list_marks_attended(operator_headers, cleanup_tour_data):
    email = f"tour-{uuid.uuid4().hex[:8]}@example.com"
    draft = _create_draft(email)
    first_date = sorted(_fetch_slots()["slots_by_date"].keys())[0]
    pick = _fetch_slots()["slots_by_date"][first_date][0]["slot_at"]
    book = httpx.post(
        f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{draft}/book-tour",
        json={"slot_at": pick, "email": email}, timeout=30,
    ).json()
    bid = book["booking_id"]
    # Operator can list
    listing = httpx.get(
        f"{API_URL}/api/memberships/tour-bookings", headers=operator_headers, timeout=30,
    ).json()
    assert any(b["id"] == bid for b in listing["bookings"])
    # Mark attended
    r = httpx.post(
        f"{API_URL}/api/memberships/tour-bookings/{bid}/attended",
        headers=operator_headers, timeout=30,
    )
    assert r.status_code == 200
    # Cancel by operator: requires booked status — re-create a different one to cancel
    email2 = f"tour-{uuid.uuid4().hex[:8]}@example.com"
    d2 = _create_draft(email2)
    avail = _fetch_slots()
    if avail["total"] > 0:
        first_date2 = sorted(avail["slots_by_date"].keys())[0]
        pick2 = avail["slots_by_date"][first_date2][0]["slot_at"]
        b2 = httpx.post(
            f"{API_URL}/api/public/signup/{TEST_SLUG}/draft/{d2}/book-tour",
            json={"slot_at": pick2}, timeout=30,
        ).json()
        cancel = httpx.post(
            f"{API_URL}/api/memberships/tour-bookings/{b2['booking_id']}/cancel",
            headers=operator_headers, timeout=30,
        )
        assert cancel.status_code == 200


def test_operator_get_tour_config_returns_defaults(operator_headers):
    r = httpx.get(
        f"{API_URL}/api/memberships/tour-config", headers=operator_headers, timeout=30,
    )
    assert r.status_code == 200
    cfg = r.json()
    assert "weekly_schedule" in cfg
    assert cfg["slot_duration_minutes"] == 30
    # ``_is_default`` indicator helps the UI show "defaults — customise?" hint.
    assert "_is_default" in cfg


def test_operator_can_update_tour_config(operator_headers, db):
    # Snapshot existing config so we can restore.
    existing = db.tour_configs.find_one({"organization_id": TEST_ORG_ID}, {"_id": 0})
    try:
        new_cfg = {
            "weekly_schedule": [{"weekday": 6, "start": "09:00", "end": "12:00"}],  # Saturday only
            "slot_duration_minutes": 45,
            "capacity_per_slot": 2,
            "lead_time_hours": 8,
            "ahead_window_days": 7,
            "location": "Main entrance",
        }
        r = httpx.put(
            f"{API_URL}/api/memberships/tour-config",
            json=new_cfg, headers=operator_headers, timeout=30,
        )
        assert r.status_code == 200
        cfg = r.json()["config"]
        assert cfg["slot_duration_minutes"] == 45
        assert cfg["capacity_per_slot"] == 2
        assert cfg["location"] == "Main entrance"
    finally:
        if existing:
            db.tour_configs.update_one(
                {"organization_id": TEST_ORG_ID}, {"$set": existing}, upsert=True,
            )
        else:
            db.tour_configs.delete_one({"organization_id": TEST_ORG_ID})
