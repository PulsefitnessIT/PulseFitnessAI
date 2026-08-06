"""Iter 216h86 + h87 — Pulse engineer bypass + Engineer profile public card.

h86: Internal engineers (direct tenant employees with a `svc_engineers`
     row in their org) bypass the partner subscription requirement —
     they're employees, not contractors.

h87: Public tracking endpoint surfaces a richer engineer card —
     photo_url, avg_rating, ratings_count, jobs_completed_90d,
     qualifications, verified pill — for trust signalling.
"""
from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://pulse-tender-system.preview.emergentagent.com"
).rstrip("/")

ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
    return client[os.environ.get("DB_NAME") or "test_database"]


def _make_user_token(db, *, account_type: str = "trial", is_pulse_admin: bool = False) -> tuple[dict, dict]:
    """Create a transient regular user + return its bearer headers.

    Direct DB insert + login via the standard JWT endpoint by exploiting
    the password we set. Uses the same hash logic as the real backend.
    """
    import bcrypt
    raw = "InternalEng2026!"
    pw = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    org_id = f"pulseorg-{uuid.uuid4()}"
    user_id = f"pulseeng-{uuid.uuid4()}"
    email = f"{user_id}@example.com"
    db.organizations.insert_one({
        "id": org_id,
        "name": "Test Pulse Gym",
        "account_type": account_type,
        "brand": "pulse" if account_type.startswith("pulse") else "gymaxis",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    db.users.insert_one({
        "id": user_id,
        "email": email,
        "password": pw,
        "full_name": "Pulse Engineer",
        "organization_id": org_id,
        "account_type": account_type,
        "is_pulse_admin": is_pulse_admin,
        "role": "engineer",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": raw}, timeout=10,
    )
    assert r.status_code == 200, r.text
    return (
        {"id": user_id, "organization_id": org_id, "email": email},
        {"Authorization": f"Bearer {r.json()['token']}"},
    )


class TestInternalEngineerBypass:
    def test_pulse_engineer_without_partner_profile_blocked_until_added_to_svc_engineers(self, db):
        """Phase 1: a brand new Pulse user (no partner, no svc_engineers row) is
        blocked from /svc/engineer/me with the same 402 as any other unauth.

        Phase 2: after the manager adds them to `svc_engineers`, the same
        request returns 200 with their engineer profile.
        """
        user, hdr = _make_user_token(db, account_type="pulse_pro")
        try:
            # Phase 1 — no svc_engineers row → 402 (or similar block)
            r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=hdr, timeout=10)
            assert r.status_code in (402, 403), r.text
            # Phase 2 — manager seeds a svc_engineers row
            db.svc_engineers.insert_one({
                "id": user["id"],
                "organization_id": user["organization_id"],
                "email": user["email"],
                "full_name": "Pulse Engineer",
                "active": True,
                "skills": ["cardio", "strength"],
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            })
            r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=hdr, timeout=10)
            assert r.status_code == 200, r.text
            # And the access endpoint reports the new reason
            r2 = requests.get(f"{BASE_URL}/api/partners/me/engineer-access", headers=hdr, timeout=10)
            assert r2.status_code == 200, r2.text
            assert r2.json().get("allowed") is True
            assert r2.json().get("reason") == "internal_engineer"
        finally:
            db.users.delete_many({"id": user["id"]})
            db.organizations.delete_many({"id": user["organization_id"]})
            db.svc_engineers.delete_many({"id": user["id"]})

    def test_pulse_engineer_does_not_need_partner_subscription(self, db):
        """An internal employee with NO partner enrolment uses the engineer
        app freely. Enrolling as a partner is an opt-in commercial choice
        and its rules take precedence once opted in (covered by h77)."""
        user, hdr = _make_user_token(db, account_type="pulse_pro")
        db.svc_engineers.insert_one({
            "id": user["id"],
            "organization_id": user["organization_id"],
            "email": user["email"],
            "full_name": "Pulse Engineer",
            "active": True,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        try:
            r = requests.get(f"{BASE_URL}/api/partners/me/engineer-access", headers=hdr, timeout=10)
            assert r.status_code == 200
            body = r.json()
            assert body["allowed"] is True
            assert body["reason"] == "internal_engineer"
            # And the engineer endpoint itself returns 200
            r2 = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=hdr, timeout=10)
            assert r2.status_code == 200
        finally:
            db.users.delete_many({"id": user["id"]})
            db.organizations.delete_many({"id": user["organization_id"]})
            db.svc_engineers.delete_many({"id": user["id"]})


class TestEngineerProfileCard:
    """Iter 216h87 — Public tracking returns the rich engineer card with
    trust signals (rating, job count, qualifications, verified flag,
    photo URL when present)."""
    def test_engineer_card_returns_stats(self, admin_headers, db):
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1, "id": 1})
        org = admin["organization_id"]
        eng_id = f"trustcard-{uuid.uuid4()}"
        # Seed an engineer profile with new h87 trust fields.
        db.svc_engineers.insert_one({
            "id": eng_id,
            "organization_id": org,
            "full_name": "Verified Vinny",
            "email": f"{eng_id}@example.com",
            "active": True,
            "skills": ["cardio", "strength", "electrical"],
            "qualifications": ["IOSH Working Safely", "PAT Tester"],
            "photo_url": "https://example.com/engineer-vinny.jpg",
            "years_experience": 8,
            "verified": True,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        # Seed 3 closed cases all rated 5★ in the last 30 days.
        now = dt.datetime.now(dt.timezone.utc)
        cids = []
        for i in range(3):
            cid = f"trust-closed-{uuid.uuid4()}"
            cids.append(cid)
            db.svc_cases.insert_one({
                "id": cid, "organization_id": org,
                "assigned_engineer_id": eng_id,
                "status": "closed", "priority": "p2",
                "closed_at": (now - dt.timedelta(days=i + 1)).isoformat(),
                "customer_rating": 5,
                "title": f"Test {i}",
                "created_at": (now - dt.timedelta(days=i + 3)).isoformat(),
            })
        # Now the live case with this engineer assigned.
        live_case = f"trust-live-{uuid.uuid4()}"
        db.svc_cases.insert_one({
            "id": live_case, "organization_id": org,
            "assigned_engineer_id": eng_id,
            "status": "en_route", "priority": "p2",
            "reference": "TRUST-CARD-1",
            "title": "Live tracking trust test",
            "site_name": "Test Site",
            "customer_name": "Carol Customer",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        })
        try:
            # Mint the tracking link.
            r = requests.get(
                f"{BASE_URL}/api/svc/cases/{live_case}/tracking-link",
                headers=admin_headers, timeout=10,
            )
            token = r.json()["token"]
            r = requests.get(f"{BASE_URL}/api/svc/public/track/{token}", timeout=10)
            assert r.status_code == 200
            body = r.json()
            eng = body["engineer"]
            assert eng["first_name"] == "Verified"
            assert eng["verified"] is True
            assert eng["photo_url"] == "https://example.com/engineer-vinny.jpg"
            assert eng["jobs_completed_90d"] == 3
            assert eng["avg_rating"] == 5.0
            assert eng["ratings_count"] == 3
            assert "IOSH Working Safely" in eng["qualifications"]
            assert "cardio" in eng["skills"]
            assert eng["years_experience"] == 8
            # Must still never leak email / mobile / full_name
            assert "email" not in eng
            assert "mobile" not in eng
            assert "full_name" not in eng
        finally:
            db.svc_engineers.delete_many({"id": eng_id})
            db.svc_cases.delete_many({"id": {"$in": cids + [live_case]}})

    def test_engineer_card_no_history(self, admin_headers, db):
        """An engineer with zero closed cases returns a card with first
        name + skills only (no rating / job count blocks)."""
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1})
        org = admin["organization_id"]
        eng_id = f"newgrad-{uuid.uuid4()}"
        db.svc_engineers.insert_one({
            "id": eng_id, "organization_id": org,
            "full_name": "Newgrad Nikki", "email": f"{eng_id}@example.com",
            "active": True, "skills": ["electrical"],
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        cid = f"newgrad-live-{uuid.uuid4()}"
        db.svc_cases.insert_one({
            "id": cid, "organization_id": org,
            "assigned_engineer_id": eng_id,
            "status": "assigned", "priority": "p3",
            "reference": "NEWGRAD-1",
            "title": "First job", "site_name": "Test", "customer_name": "Sam",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        try:
            token = requests.get(
                f"{BASE_URL}/api/svc/cases/{cid}/tracking-link",
                headers=admin_headers, timeout=10,
            ).json()["token"]
            r = requests.get(f"{BASE_URL}/api/svc/public/track/{token}", timeout=10)
            assert r.status_code == 200
            eng = r.json()["engineer"]
            assert eng["first_name"] == "Newgrad"
            assert eng["jobs_completed_90d"] == 0
            assert eng["avg_rating"] is None
            assert eng["ratings_count"] == 0
        finally:
            db.svc_engineers.delete_many({"id": eng_id})
            db.svc_cases.delete_many({"id": cid})
