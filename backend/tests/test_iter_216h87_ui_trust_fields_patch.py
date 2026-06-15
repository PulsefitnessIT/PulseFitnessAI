"""Iter 216h87 (UI follow-up) — Verify operator-side engineer edit accepts
and persists the new trust card fields (photo_url, qualifications,
years_experience, verified) via the existing PATCH endpoint.
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
    or "https://staffing-ops-preview.preview.emergentagent.com"
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


class TestEngineerTrustFieldsPersistence:
    def test_patch_persists_trust_fields(self, admin_headers, db):
        admin = db.users.find_one(
            {"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1, "id": 1},
        )
        org = admin["organization_id"]
        # Seed an engineer to edit
        eng_id = f"trustui-{uuid.uuid4()}"
        db.svc_engineers.insert_one({
            "id": eng_id,
            "organization_id": org,
            "email": f"{eng_id}@example.com",
            "full_name": "Trust Test",
            "active": True,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        try:
            payload = {
                "photo_url": "https://example.com/eng.jpg",
                "qualifications": ["IOSH Working Safely", "18th Edition"],
                "years_experience": 9,
                "verified": True,
            }
            r = requests.patch(
                f"{BASE_URL}/api/svc/engineers/{eng_id}",
                json=payload, headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            doc = db.svc_engineers.find_one({"id": eng_id}, {"_id": 0})
            assert doc["photo_url"] == "https://example.com/eng.jpg"
            assert doc["qualifications"] == ["IOSH Working Safely", "18th Edition"]
            assert doc["years_experience"] == 9
            assert doc["verified"] is True
            # And the listing also surfaces them
            r = requests.get(
                f"{BASE_URL}/api/svc/engineers",
                headers=admin_headers, timeout=10,
            )
            row = next(e for e in r.json()["engineers"] if e["id"] == eng_id)
            assert row["photo_url"] == "https://example.com/eng.jpg"
            assert row["verified"] is True
            assert "IOSH Working Safely" in row["qualifications"]
        finally:
            db.svc_engineers.delete_many({"id": eng_id})

    def test_null_years_experience_clears_field(self, admin_headers, db):
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1})
        eng_id = f"clearyrs-{uuid.uuid4()}"
        db.svc_engineers.insert_one({
            "id": eng_id,
            "organization_id": admin["organization_id"],
            "email": f"{eng_id}@example.com",
            "full_name": "Clear Yrs",
            "active": True,
            "years_experience": 8,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        try:
            r = requests.patch(
                f"{BASE_URL}/api/svc/engineers/{eng_id}",
                json={"years_experience": None},
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            doc = db.svc_engineers.find_one({"id": eng_id}, {"_id": 0, "years_experience": 1})
            # Either explicitly None or removed entirely is acceptable
            assert doc.get("years_experience") in (None,)
        finally:
            db.svc_engineers.delete_many({"id": eng_id})
