"""Iter 216h87 (UI follow-up #2) — Add-engineer trust fields + Preview
tracking endpoint.

Verifies:
  • POST /svc/engineers accepts the new trust fields at creation time
    (photo_url, qualifications, years_experience, verified).
  • GET /svc/engineers/{id}/preview-tracking-link returns an open-case
    tracking URL when one exists, falls back to a closed case, and
    returns a clear 404 when the engineer has no jobs at all.
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
    or "https://engineer-hub-114.preview.emergentagent.com"
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


class TestAddEngineerTrustFields:
    def test_post_accepts_trust_fields(self, admin_headers, db):
        admin = db.users.find_one(
            {"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1},
        )
        org = admin["organization_id"]
        # POST /svc/engineers requires an existing user in the org — seed one.
        new_user_id = f"trustadd-{uuid.uuid4()}"
        new_email = f"{new_user_id}@example.com"
        db.users.insert_one({
            "id": new_user_id,
            "email": new_email,
            "full_name": "Trust Add Test",
            "organization_id": org,
            "role": "engineer",
            "password": "x",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        try:
            r = requests.post(
                f"{BASE_URL}/api/svc/engineers",
                json={
                    "email": new_email,
                    "full_name": "Trust Add Test",
                    "mobile": "07700900000",
                    "vehicle_reg": "TR11 ABC",
                    "skills": ["cardio", "electrical"],
                    "photo_url": "https://example.com/p.jpg",
                    "qualifications": ["IOSH Working Safely", "PAT Tester"],
                    "years_experience": 5,
                    "verified": True,
                },
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            doc = db.svc_engineers.find_one({"id": new_user_id}, {"_id": 0})
            assert doc["photo_url"] == "https://example.com/p.jpg"
            assert doc["qualifications"] == ["IOSH Working Safely", "PAT Tester"]
            assert doc["years_experience"] == 5
            assert doc["verified"] is True
        finally:
            db.users.delete_many({"id": new_user_id})
            db.svc_engineers.delete_many({"id": new_user_id})

    def test_post_blank_years_experience_persists_as_none(self, admin_headers, db):
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1})
        org = admin["organization_id"]
        uid = f"trustadd-blank-{uuid.uuid4()}"
        email = f"{uid}@example.com"
        db.users.insert_one({
            "id": uid, "email": email, "full_name": "No Yrs",
            "organization_id": org, "role": "engineer", "password": "x",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        try:
            r = requests.post(
                f"{BASE_URL}/api/svc/engineers",
                json={"email": email, "full_name": "No Yrs"},
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            doc = db.svc_engineers.find_one({"id": uid}, {"_id": 0, "years_experience": 1})
            assert doc.get("years_experience") in (None,)
        finally:
            db.users.delete_many({"id": uid})
            db.svc_engineers.delete_many({"id": uid})


class TestPreviewTrackingLink:
    def test_returns_open_case_url(self, admin_headers, db):
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1})
        org = admin["organization_id"]
        eng_id = f"preview-eng-{uuid.uuid4()}"
        db.svc_engineers.insert_one({
            "id": eng_id, "organization_id": org,
            "email": f"{eng_id}@example.com", "full_name": "Preview Eng",
            "active": True,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        now = dt.datetime.now(dt.timezone.utc)
        # Closed case + newer open case → open should win.
        cclosed = f"preview-closed-{uuid.uuid4()}"
        copen = f"preview-open-{uuid.uuid4()}"
        db.svc_cases.insert_many([
            {"id": cclosed, "organization_id": org, "assigned_engineer_id": eng_id,
             "status": "closed", "priority": "p3", "title": "Old",
             "closed_at": (now - dt.timedelta(days=5)).isoformat(),
             "updated_at": (now - dt.timedelta(days=5)).isoformat(),
             "created_at": (now - dt.timedelta(days=7)).isoformat()},
            {"id": copen, "organization_id": org, "assigned_engineer_id": eng_id,
             "status": "en_route", "priority": "p2", "title": "Live",
             "updated_at": now.isoformat(),
             "created_at": (now - dt.timedelta(hours=2)).isoformat()},
        ])
        try:
            r = requests.get(
                f"{BASE_URL}/api/svc/engineers/{eng_id}/preview-tracking-link",
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["case_id"] == copen
            assert body["case_status"] == "en_route"
            assert body["url"].endswith(f"/track/{body['token']}")
            # The public URL must resolve.
            r2 = requests.get(f"{BASE_URL}/api/svc/public/track/{body['token']}", timeout=10)
            assert r2.status_code == 200
        finally:
            db.svc_engineers.delete_many({"id": eng_id})
            db.svc_cases.delete_many({"id": {"$in": [cclosed, copen]}})

    def test_falls_back_to_closed_case(self, admin_headers, db):
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1})
        org = admin["organization_id"]
        eng_id = f"preview-only-closed-{uuid.uuid4()}"
        db.svc_engineers.insert_one({
            "id": eng_id, "organization_id": org,
            "email": f"{eng_id}@example.com", "full_name": "Closed Only",
            "active": True,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        now = dt.datetime.now(dt.timezone.utc)
        cid = f"preview-onlyclosed-{uuid.uuid4()}"
        db.svc_cases.insert_one({
            "id": cid, "organization_id": org, "assigned_engineer_id": eng_id,
            "status": "closed", "priority": "p3", "title": "Old",
            "closed_at": now.isoformat(), "updated_at": now.isoformat(),
            "created_at": (now - dt.timedelta(days=2)).isoformat(),
        })
        try:
            r = requests.get(
                f"{BASE_URL}/api/svc/engineers/{eng_id}/preview-tracking-link",
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            assert r.json()["case_status"] == "closed"
        finally:
            db.svc_engineers.delete_many({"id": eng_id})
            db.svc_cases.delete_many({"id": cid})

    def test_404_when_no_jobs(self, admin_headers, db):
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1})
        eng_id = f"preview-nojobs-{uuid.uuid4()}"
        db.svc_engineers.insert_one({
            "id": eng_id, "organization_id": admin["organization_id"],
            "email": f"{eng_id}@example.com", "full_name": "No Jobs",
            "active": True,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        try:
            r = requests.get(
                f"{BASE_URL}/api/svc/engineers/{eng_id}/preview-tracking-link",
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 404, r.text
            assert "no jobs" in r.json()["detail"].lower()
        finally:
            db.svc_engineers.delete_many({"id": eng_id})

    def test_404_when_unknown_engineer(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/svc/engineers/does-not-exist-xyz/preview-tracking-link",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 404
