"""Iter 216h90 + h91 + h92 — NPS feedback · Live tracking · CSV-importable H&S.

Endpoints under test:
  POST   /api/svc/public/track/{token}/feedback             — h90 NPS
  POST   /api/svc/engineer/location                          — h91 ping
  GET    /api/svc/public/track/{token}                       — h91 ETA in payload
  GET    /api/svc/safety/template/export.csv                 — h92 export
  POST   /api/svc/safety/template/import-csv                 — h92 import
"""
from __future__ import annotations

import datetime as dt
import io
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://aftersales-engine.preview.emergentagent.com"
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


@pytest.fixture(scope="module")
def admin_user(db):
    return db.users.find_one(
        {"email": ADMIN_EMAIL}, {"_id": 0, "id": 1, "organization_id": 1},
    )


# ─────────────────────────────────────────────────────────────────
# h90 — NPS public feedback
# ─────────────────────────────────────────────────────────────────
class TestPublicFeedback:
    def test_feedback_accepts_rating_nps_and_comment(self, admin_headers, db, admin_user):
        cid = f"nps-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid, "organization_id": admin_user["organization_id"],
            "status": "closed", "priority": "p2",
            "title": "NPS test",
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        })
        try:
            # Mint a tracking link
            token = requests.get(
                f"{BASE_URL}/api/svc/cases/{cid}/tracking-link",
                headers=admin_headers, timeout=10,
            ).json()["token"]
            # Submit feedback (no auth)
            r = requests.post(
                f"{BASE_URL}/api/svc/public/track/{token}/feedback",
                json={"rating": 5, "nps_score": 10, "comment": "Top service!"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            doc = db.svc_cases.find_one({"id": cid}, {"_id": 0})
            assert doc["customer_rating"] == 5
            assert doc["customer_nps"] == 10
            assert doc["customer_rating_comment"] == "Top service!"
            assert "T" in doc["customer_feedback_at"]
            # Tracking endpoint reports feedback_captured = True
            payload = requests.get(f"{BASE_URL}/api/svc/public/track/{token}", timeout=10).json()
            assert payload["feedback_captured"] is True
            assert payload["rating_captured"] is True
        finally:
            db.svc_cases.delete_many({"id": cid})

    def test_feedback_rejects_empty_payload(self, admin_headers, db, admin_user):
        cid = f"nps-empty-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid, "organization_id": admin_user["organization_id"],
            "status": "closed", "priority": "p3",
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        })
        try:
            token = requests.get(
                f"{BASE_URL}/api/svc/cases/{cid}/tracking-link",
                headers=admin_headers, timeout=10,
            ).json()["token"]
            r = requests.post(
                f"{BASE_URL}/api/svc/public/track/{token}/feedback",
                json={}, timeout=10,
            )
            assert r.status_code == 400
            assert "leave a rating" in r.json()["detail"].lower()
        finally:
            db.svc_cases.delete_many({"id": cid})

    def test_feedback_validates_ranges(self, admin_headers, db, admin_user):
        cid = f"nps-range-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid, "organization_id": admin_user["organization_id"],
            "status": "closed", "priority": "p3",
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        })
        try:
            token = requests.get(
                f"{BASE_URL}/api/svc/cases/{cid}/tracking-link",
                headers=admin_headers, timeout=10,
            ).json()["token"]
            r = requests.post(
                f"{BASE_URL}/api/svc/public/track/{token}/feedback",
                json={"rating": 9}, timeout=10,
            )
            assert r.status_code == 400
            r = requests.post(
                f"{BASE_URL}/api/svc/public/track/{token}/feedback",
                json={"nps_score": 11}, timeout=10,
            )
            assert r.status_code == 400
        finally:
            db.svc_cases.delete_many({"id": cid})

    def test_feedback_404_on_bad_token(self):
        r = requests.post(
            f"{BASE_URL}/api/svc/public/track/bogus-token-x/feedback",
            json={"comment": "Hello"}, timeout=10,
        )
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────
# h91 — Engineer location pings + ETA in tracking payload
# ─────────────────────────────────────────────────────────────────
class TestEngineerLocation:
    def test_post_location_persists(self, admin_headers, db, admin_user):
        # Wipe any previous ping
        db.svc_engineer_locations.delete_many({"engineer_id": admin_user["id"]})
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/location",
            json={"lat": 52.4862, "lng": -1.8904, "accuracy_m": 8.0},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        doc = db.svc_engineer_locations.find_one(
            {"engineer_id": admin_user["id"]}, {"_id": 0},
        )
        assert doc["lat"] == 52.4862
        assert doc["lng"] == -1.8904

    def test_post_location_rejects_bad_coords(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/location",
            json={"lat": 999, "lng": 0},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400

    def test_public_track_surfaces_eta_when_en_route(self, admin_headers, db, admin_user):
        # Birmingham coords for the engineer + site 5 km away
        db.svc_engineer_locations.update_one(
            {"engineer_id": admin_user["id"]},
            {"$set": {
                "engineer_id": admin_user["id"],
                "organization_id": admin_user["organization_id"],
                "lat": 52.4862, "lng": -1.8904, "accuracy_m": 8.0,
                "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        cid = f"eta-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid, "organization_id": admin_user["organization_id"],
            "assigned_engineer_id": admin_user["id"],
            "status": "en_route", "priority": "p2",
            "title": "ETA test", "customer_name": "Pat",
            "site_lat": 52.5374, "site_lng": -1.8920,  # ~5.7 km north
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        })
        try:
            token = requests.get(
                f"{BASE_URL}/api/svc/cases/{cid}/tracking-link",
                headers=admin_headers, timeout=10,
            ).json()["token"]
            body = requests.get(
                f"{BASE_URL}/api/svc/public/track/{token}", timeout=10,
            ).json()
            assert body["engineer_location"]["lat"] == 52.4862
            assert body["site_location"]["lat"] == 52.5374
            assert body["eta"]["minutes"] is not None
            assert body["eta"]["minutes"] > 0
            assert "min away" in body["eta"]["label"]
        finally:
            db.svc_cases.delete_many({"id": cid})

    def test_public_track_no_location_when_status_closed(self, admin_headers, db, admin_user):
        """Privacy: do not leak engineer location when the case is closed."""
        db.svc_engineer_locations.update_one(
            {"engineer_id": admin_user["id"]},
            {"$set": {
                "engineer_id": admin_user["id"],
                "organization_id": admin_user["organization_id"],
                "lat": 52.4862, "lng": -1.8904,
                "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        cid = f"eta-closed-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid, "organization_id": admin_user["organization_id"],
            "assigned_engineer_id": admin_user["id"],
            "status": "closed", "priority": "p3",
            "site_lat": 52.5, "site_lng": -1.9,
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        })
        try:
            token = requests.get(
                f"{BASE_URL}/api/svc/cases/{cid}/tracking-link",
                headers=admin_headers, timeout=10,
            ).json()["token"]
            body = requests.get(
                f"{BASE_URL}/api/svc/public/track/{token}", timeout=10,
            ).json()
            assert body["engineer_location"] is None
            assert body["eta"] is None
        finally:
            db.svc_cases.delete_many({"id": cid})


# ─────────────────────────────────────────────────────────────────
# h92 — Safety template CSV import / export
# ─────────────────────────────────────────────────────────────────
class TestSafetyCsv:
    def test_export_returns_csv(self, admin_headers, db, admin_user):
        # Clear template so we get a known shape
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})
        r = requests.get(
            f"{BASE_URL}/api/svc/safety/template/export.csv",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("text/csv")
        body = r.text
        first = body.splitlines()[0].strip().lower()
        assert first == "label,required,id"
        assert "ppe" in body.lower()
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})

    def test_import_csv_appends_by_default(self, admin_headers, db, admin_user):
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})
        # Seed with one item first
        requests.put(
            f"{BASE_URL}/api/svc/safety/template",
            json={"items": [{"id": "site_in", "label": "Signed in", "required": True}]},
            headers=admin_headers, timeout=10,
        )
        csv_body = (
            "label,required\n"
            "Toolbox talk completed,yes\n"
            "Spotter present,yes\n"
            "Lighting adequate,no\n"
        )
        r = requests.post(
            f"{BASE_URL}/api/svc/safety/template/import-csv",
            files={"file": ("custom.csv", csv_body, "text/csv")},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported_count"] == 3
        assert body["total_count"] == 4
        tpl = db.svc_safety_templates.find_one(
            {"organization_id": admin_user["organization_id"], "active": True},
            {"_id": 0, "items": 1},
        )
        labels = [i["label"] for i in tpl["items"]]
        assert "Signed in" in labels
        assert "Toolbox talk completed" in labels
        # `required` parsed correctly
        toolbox = next(i for i in tpl["items"] if i["label"] == "Toolbox talk completed")
        assert toolbox["required"] is True
        lighting = next(i for i in tpl["items"] if i["label"] == "Lighting adequate")
        assert lighting["required"] is False
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})

    def test_import_csv_replace_wipes_existing(self, admin_headers, db, admin_user):
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})
        requests.put(
            f"{BASE_URL}/api/svc/safety/template",
            json={"items": [{"id": "old", "label": "Old item", "required": True}]},
            headers=admin_headers, timeout=10,
        )
        csv_body = "label,required\nBrand new,yes\n"
        r = requests.post(
            f"{BASE_URL}/api/svc/safety/template/import-csv?replace=true",
            files={"file": ("c.csv", csv_body, "text/csv")},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200
        tpl = db.svc_safety_templates.find_one(
            {"organization_id": admin_user["organization_id"], "active": True},
            {"_id": 0, "items": 1},
        )
        assert len(tpl["items"]) == 1
        assert tpl["items"][0]["label"] == "Brand new"
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})

    def test_import_rejects_missing_label_column(self, admin_headers):
        csv_body = "name,required\nFoo,yes\n"
        r = requests.post(
            f"{BASE_URL}/api/svc/safety/template/import-csv",
            files={"file": ("bad.csv", csv_body, "text/csv")},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400
        assert "label" in r.json()["detail"].lower()

    def test_import_rejects_empty_file(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/svc/safety/template/import-csv",
            files={"file": ("empty.csv", b"", "text/csv")},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400
