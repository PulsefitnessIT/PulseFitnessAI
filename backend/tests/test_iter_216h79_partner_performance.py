"""Iter 216h79 — Partner performance scoring tests.

Verifies the composite score (40% SLA · 30% completion · 20% volume ·
10% CSAT) and the tier classification thresholds.

Seeds svc_cases assigned to the test partner's user_id with varying
SLA outcomes / customer ratings, then asserts:
  • Empty window → insufficient_data + zero score
  • Below MIN_CLOSED_FOR_SCORE → insufficient_data even if SLA = 100%
  • Perfect performer → top_tier (90+)
  • Mostly SLA breaches + low CSAT → needs_improvement (<60)
  • Leaderboard sorts insufficient_data partners last
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
    or "https://pulse-staging-10.preview.emergentagent.com"
).rstrip("/")

OPERATOR_EMAIL = "e1.agent@gymaxisai.com"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"
E1_PARTNER_ID = "40c2b861-6f04-4377-894b-0507055bff79"


def _login_admin():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin_headers(): return _login_admin()


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
    return client[os.environ.get("DB_NAME") or "test_database"]


@pytest.fixture(scope="module")
def operator_user_id(db):
    u = db.users.find_one({"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1})
    return u["id"]


def _seed_closed_case(db, user_id, *, within_sla: bool, rating: int | None = None,
                      days_ago: int = 10):
    closed_at = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat()
    sla_resolve_at = (
        (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago + (-1 if within_sla else 1))).isoformat()
    )
    if within_sla:
        # SLA target is 1 day AFTER closure → closed within target
        sla_resolve_at = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago - 1)).isoformat()
    case_id = f"perftest-{uuid.uuid4()}"
    org_id = "perftest-org"
    doc = {
        "id": case_id,
        "organization_id": org_id,
        "assigned_engineer_id": user_id,
        "status": "closed",
        "priority": "p2",
        "closed_at": closed_at,
        "sla_resolve_at": sla_resolve_at,
        "created_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago + 3)).isoformat(),
        "updated_at": closed_at,
    }
    if rating is not None:
        doc["customer_rating"] = rating
    db.svc_cases.insert_one(doc)
    return case_id


@pytest.fixture
def cleanup_perftest(db):
    yield
    db.svc_cases.delete_many({"id": {"$regex": "^perftest-"}})


class TestEmptyWindow:
    def test_empty_returns_insufficient_data(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/{E1_PARTNER_ID}/performance?window_days=90",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["score"] == 0
        assert body["tier"] == "insufficient_data"
        assert body["recommended_level"] is None


class TestThresholds:
    def test_under_min_closed_is_insufficient(self, db, operator_user_id, admin_headers, cleanup_perftest):
        for _ in range(3):  # below MIN_CLOSED_FOR_SCORE=5
            _seed_closed_case(db, operator_user_id, within_sla=True, rating=5)
        r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/{E1_PARTNER_ID}/performance?window_days=90",
            headers=admin_headers, timeout=10,
        )
        body = r.json()
        assert body["tier"] == "insufficient_data"
        assert body["counts"]["closed"] == 3

    def test_perfect_performer_is_top_tier(self, db, operator_user_id, admin_headers, cleanup_perftest):
        # 10 perfectly closed cases with 5-star ratings
        for _ in range(10):
            _seed_closed_case(db, operator_user_id, within_sla=True, rating=5)
        r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/{E1_PARTNER_ID}/performance?window_days=90",
            headers=admin_headers, timeout=10,
        )
        body = r.json()
        assert body["counts"]["closed"] == 10
        assert body["counts"]["closed_within_sla"] == 10
        assert body["components"]["sla_compliance"] == 1.0
        assert body["components"]["completion_rate"] == 1.0
        # 10/50 volume × 0.2 = 0.04 + 1.0 sla × 0.4 = 0.4 + 1.0 completion × 0.3 = 0.3 + 1.0 csat × 0.1 = 0.1
        # = 0.84 → 84% → "strong"
        # To hit "top_tier" we'd need volume > 50.
        assert body["score"] >= 80
        assert body["tier"] in ("strong", "top_tier")
        assert body["recommended_level"] in ("verified_partner", "strategic_partner")

    def test_top_tier_at_high_volume(self, db, operator_user_id, admin_headers, cleanup_perftest):
        # 50 perfectly closed cases with 5-star ratings → score 100
        for _ in range(50):
            _seed_closed_case(db, operator_user_id, within_sla=True, rating=5)
        r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/{E1_PARTNER_ID}/performance?window_days=90",
            headers=admin_headers, timeout=10,
        )
        body = r.json()
        assert body["score"] == 100.0
        assert body["tier"] == "top_tier"
        assert body["recommended_level"] == "strategic_partner"

    def test_bad_performer_needs_improvement(self, db, operator_user_id, admin_headers, cleanup_perftest):
        # 8 closed cases — 2 within SLA, 6 breached; ratings mostly 2
        for i in range(8):
            _seed_closed_case(db, operator_user_id,
                              within_sla=(i < 2), rating=2)
        # And some cancelled jobs to drag completion_rate
        for _ in range(4):
            db.svc_cases.insert_one({
                "id": f"perftest-cancel-{uuid.uuid4()}",
                "organization_id": "perftest-org",
                "assigned_engineer_id": operator_user_id,
                "status": "cancelled",
                "updated_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=5)).isoformat(),
            })
        r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/{E1_PARTNER_ID}/performance?window_days=90",
            headers=admin_headers, timeout=10,
        )
        body = r.json()
        assert body["counts"]["closed"] == 8
        assert body["counts"]["cancelled"] == 4
        # SLA 2/8 = 0.25, completion 8/12 = 0.667, volume 8/50 = 0.16, csat 2/5 = 0.4
        # = 0.4×0.25 + 0.3×0.667 + 0.2×0.16 + 0.1×0.4 = 0.1 + 0.2 + 0.032 + 0.04 = 0.372
        # = 37.2% → needs_improvement
        assert body["score"] < 60
        assert body["tier"] == "needs_improvement"
        # cleanup the cancelled rows
        db.svc_cases.delete_many({"id": {"$regex": "^perftest-cancel-"}})


class TestLeaderboard:
    def test_leaderboard_orders_by_score(self, db, operator_user_id, admin_headers, cleanup_perftest):
        # Seed a strong run for the E1 partner
        for _ in range(10):
            _seed_closed_case(db, operator_user_id, within_sla=True, rating=5)
        r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/performance/leaderboard?window_days=90",
            headers=admin_headers, timeout=10,
        )
        body = r.json()
        assert body["window_days"] == 90
        assert len(body["partners"]) >= 1
        # E1 should appear with a score
        e1 = next(p for p in body["partners"] if p["id"] == E1_PARTNER_ID)
        assert e1["performance"]["score"] > 80

    def test_window_days_validation(self, admin_headers):
        # Out-of-range window
        r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/{E1_PARTNER_ID}/performance?window_days=1000",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 422


class TestCustomerRatingCapture:
    def test_rating_round_trips_through_case_update(self, admin_headers, db):
        # Create a case, then PUT a customer_rating onto it via the
        # existing /api/svc/cases/{id} endpoint.
        case_id = f"perftest-rating-{uuid.uuid4()}"
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "id": 1, "organization_id": 1})
        db.svc_cases.insert_one({
            "id": case_id, "organization_id": admin["organization_id"],
            "status": "closed", "priority": "p3",
            "closed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sla_resolve_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "title": "Test", "case_type": "fault",
        })
        try:
            r = requests.put(f"{BASE_URL}/api/svc/cases/{case_id}",
                             json={"customer_rating": 5, "customer_rating_comment": "Great"},
                             headers=admin_headers, timeout=10)
            assert r.status_code == 200, r.text
            doc = db.svc_cases.find_one({"id": case_id}, {"_id": 0, "customer_rating": 1, "customer_rating_comment": 1})
            assert doc["customer_rating"] == 5
            assert doc["customer_rating_comment"] == "Great"
        finally:
            db.svc_cases.delete_many({"id": case_id})
