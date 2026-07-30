"""Iter 216h89 — Pre-job H&S / RAMS checklist.

Endpoints under test:
  GET    /api/svc/safety/template
  PUT    /api/svc/safety/template
  GET    /api/svc/engineer/jobs/{id}/safety
  POST   /api/svc/engineer/jobs/{id}/safety/signoff
  POST   /api/svc/engineer/time/start  (now gated on safety signoff)
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
    or "https://mod-hq-email.preview.emergentagent.com"
).rstrip("/")

ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"

PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


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


@pytest.fixture
def seeded_case(db, admin_user):
    cid = f"safety-{uuid.uuid4()}"
    now = dt.datetime.now(dt.timezone.utc)
    db.svc_cases.insert_one({
        "id": cid,
        "organization_id": admin_user["organization_id"],
        "assigned_engineer_id": admin_user["id"],
        "status": "en_route",
        "priority": "p2",
        "title": "Safety test",
        "site_name": "Test Gym",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    })
    yield cid
    db.svc_cases.delete_many({"id": cid})
    db.svc_case_safety_signoffs.delete_many({"case_id": cid})
    db.svc_time_entries.delete_many({"case_id": cid})


class TestSafetyTemplate:
    def test_get_template_lazy_seeds_default(self, admin_headers, db, admin_user):
        # Wipe any prior template to test the seed
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})
        r = requests.get(f"{BASE_URL}/api/svc/safety/template", headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text
        tpl = r.json()
        assert tpl["items"]
        # Standard 8-item default
        assert len(tpl["items"]) == 8
        assert any(i["id"] == "ppe" for i in tpl["items"])
        # Cleanup for downstream tests
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})

    def test_put_template_validates_and_persists(self, admin_headers, db, admin_user):
        r = requests.put(
            f"{BASE_URL}/api/svc/safety/template",
            json={"items": [
                {"id": "site_in",   "label": "Signed in at site", "required": True},
                {"id": "ppe",       "label": "PPE worn", "required": True},
                {"id": "tools_pat", "label": "Tools PAT-tested in last 12 months", "required": False},
            ]},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        tpl = r.json()
        assert len(tpl["items"]) == 3
        assert {i["id"] for i in tpl["items"]} == {"site_in", "ppe", "tools_pat"}
        # Cleanup
        db.svc_safety_templates.delete_many({"organization_id": admin_user["organization_id"]})

    def test_put_template_rejects_empty(self, admin_headers):
        r = requests.put(
            f"{BASE_URL}/api/svc/safety/template",
            json={"items": []},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400


class TestSafetySignoffGate:
    def test_get_safety_state_for_case(self, admin_headers, seeded_case):
        r = requests.get(
            f"{BASE_URL}/api/svc/engineer/jobs/{seeded_case}/safety",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["completed"] is False
        assert body["signoff"] is None
        assert body["template"]["items"]

    def test_on_site_timer_blocked_until_signoff(self, admin_headers, seeded_case):
        # Step 1: attempt to start on-site timer without signoff → 412
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": seeded_case, "category": "on_site"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 412, r.text
        assert r.json()["detail"]["code"] == "safety_signoff_required"

        # Step 2: travel timer is NOT gated
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": seeded_case, "category": "travel"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text

        # Step 3: complete the signoff with all required items
        tpl = requests.get(f"{BASE_URL}/api/svc/safety/template", headers=admin_headers, timeout=10).json()
        required_ids = [i["id"] for i in tpl["items"] if i["required"]]
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/jobs/{seeded_case}/safety/signoff",
            json={
                "ticked_item_ids": required_ids,
                "signature_image": PNG_DATA_URL,
                "remarks": "All clear",
            },
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        signoff = r.json()
        assert set(signoff["ticked_item_ids"]) >= set(required_ids)

        # Step 4: now on-site timer succeeds
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": seeded_case, "category": "on_site"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text

    def test_signoff_rejects_missing_required(self, admin_headers, seeded_case):
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/jobs/{seeded_case}/safety/signoff",
            json={
                "ticked_item_ids": ["sign_in"],  # missing other required items
                "signature_image": PNG_DATA_URL,
            },
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400
        assert "Required items not ticked" in r.json()["detail"]

    def test_signoff_requires_signature(self, admin_headers, seeded_case):
        tpl = requests.get(f"{BASE_URL}/api/svc/safety/template", headers=admin_headers, timeout=10).json()
        all_required = [i["id"] for i in tpl["items"] if i["required"]]
        r = requests.post(
            f"{BASE_URL}/api/svc/engineer/jobs/{seeded_case}/safety/signoff",
            json={"ticked_item_ids": all_required, "signature_image": ""},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400
        assert "signature" in r.json()["detail"].lower()


class TestSafetyOnReport:
    def test_pdf_includes_safety_section(self, admin_headers, db, admin_user):
        # Seed a closed case + signoff so the PDF section renders
        cid = f"safety-pdf-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid,
            "organization_id": admin_user["organization_id"],
            "assigned_engineer_id": admin_user["id"],
            "status": "closed", "priority": "p2",
            "title": "PDF safety test",
            "closed_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        })
        db.svc_case_safety_signoffs.insert_one({
            "id": str(uuid.uuid4()),
            "case_id": cid,
            "organization_id": admin_user["organization_id"],
            "engineer_id": admin_user["id"],
            "engineer_name": "Test Engineer",
            "template_snapshot": [
                {"id": "sign_in", "label": "Signed in at reception", "required": True},
                {"id": "ppe", "label": "PPE worn", "required": True},
            ],
            "ticked_item_ids": ["sign_in", "ppe"],
            "signature_image": PNG_DATA_URL,
            "remarks": "All clear",
            "signed_at": now.isoformat(),
        })
        try:
            r = requests.get(
                f"{BASE_URL}/api/svc/cases/{cid}/service-report.pdf",
                headers=admin_headers, timeout=15,
            )
            assert r.status_code == 200, r.text
            assert r.headers.get("content-type", "").startswith("application/pdf")
            assert r.content.startswith(b"%PDF")
        finally:
            db.svc_cases.delete_many({"id": cid})
            db.svc_case_safety_signoffs.delete_many({"case_id": cid})
