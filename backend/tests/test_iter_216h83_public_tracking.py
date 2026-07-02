"""Iter 216h83 — Customer Live Tracking (public, tokenised).

Endpoints under test:
  GET  /api/svc/cases/{case_id}/tracking-link             (operator, mint+fetch)
  POST /api/svc/cases/{case_id}/tracking-link/regenerate  (operator)
  GET  /api/svc/public/track/{token}                      (public, no auth)
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
    or "https://comms-email-hub.preview.emergentagent.com"
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


@pytest.fixture
def seeded_case(db):
    admin = db.users.find_one(
        {"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1},
    )
    case_id = f"track-{uuid.uuid4()}"
    now = dt.datetime.now(dt.timezone.utc)
    db.svc_cases.insert_one({
        "id": case_id,
        "reference": "CASE-TRK-1",
        "organization_id": admin["organization_id"],
        "status": "en_route",
        "priority": "p2",
        "title": "Tracking smoke test",
        "site_name": "Trackable Gym",
        "site_postcode": "TR1 1NG",
        "customer_name": "Pat Customer",
        "customer_email": "pat@example.com",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    })
    yield case_id
    db.svc_cases.delete_many({"id": case_id})


class TestTrackingLinkMint:
    def test_mint_returns_token_and_url(self, admin_headers, seeded_case):
        r = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/tracking-link",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["token"]) >= 18
        assert body["url"].endswith(f"/track/{body['token']}")

    def test_mint_idempotent(self, admin_headers, seeded_case):
        r1 = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/tracking-link",
            headers=admin_headers, timeout=10,
        ).json()
        r2 = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/tracking-link",
            headers=admin_headers, timeout=10,
        ).json()
        assert r1["token"] == r2["token"], "Same case should return same token"

    def test_regenerate_swaps_token(self, admin_headers, seeded_case):
        first = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/tracking-link",
            headers=admin_headers, timeout=10,
        ).json()["token"]
        second = requests.post(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/tracking-link/regenerate",
            headers=admin_headers, timeout=10,
        ).json()["token"]
        assert first != second
        # Old token now resolves to 404
        old = requests.get(f"{BASE_URL}/api/svc/public/track/{first}", timeout=10)
        assert old.status_code == 404

    def test_mint_unknown_case_404(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/svc/cases/does-not-exist-track/tracking-link",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 404


class TestPublicTracking:
    def test_public_view_no_auth(self, admin_headers, seeded_case):
        link = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/tracking-link",
            headers=admin_headers, timeout=10,
        ).json()
        token = link["token"]
        r = requests.get(f"{BASE_URL}/api/svc/public/track/{token}", timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reference"] == "CASE-TRK-1"
        assert body["status"] == "en_route"
        assert body["status_label"] == "On the way"
        assert body["status_stage"] == 3
        assert body["organization"]["name"]
        assert "logo_url" in body["organization"]
        # Must NOT leak commercial / internal fields
        forbidden = {"customer_email", "assigned_engineer_id", "allocated_parts",
                     "track_token", "_id", "organization_id"}
        assert not (set(body.keys()) & forbidden)
        # Customer first name surfaces, full name does not
        assert body["customer_first_name"] == "Pat"

    def test_public_view_bad_token_404(self):
        r = requests.get(f"{BASE_URL}/api/svc/public/track/bogus-token-xx", timeout=10)
        assert r.status_code == 404

    def test_public_view_strips_internal_engineer_fields(self, admin_headers, db, seeded_case):
        # Bind an engineer with PII so we can assert it doesn't leak.
        eng = db.svc_engineers.find_one({}, {"_id": 0, "id": 1, "organization_id": 1})
        if not eng:
            pytest.skip("No engineer profile seeded in this environment")
        db.svc_cases.update_one(
            {"id": seeded_case},
            {"$set": {"assigned_engineer_id": eng["id"]}},
        )
        token = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/tracking-link",
            headers=admin_headers, timeout=10,
        ).json()["token"]
        r = requests.get(f"{BASE_URL}/api/svc/public/track/{token}", timeout=10)
        assert r.status_code == 200
        body = r.json()
        if body.get("engineer"):
            # First name surfaces, email/full-name/mobile NEVER
            assert "email" not in body["engineer"]
            assert "mobile" not in body["engineer"]
            assert "full_name" not in body["engineer"]
            assert "first_name" in body["engineer"]
