"""Iter 216h82 — Service Report PDF + email-to-customer.

Endpoints under test:
  GET  /api/svc/cases/{case_id}/service-report.pdf
  POST /api/svc/cases/{case_id}/service-report/email
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
OPERATOR_EMAIL = "e1.agent@gymaxisai.com"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
    return client[os.environ.get("DB_NAME") or "test_database"]


@pytest.fixture
def operator_user_id(db):
    return db.users.find_one({"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1})["id"]


@pytest.fixture
def seeded_case(db, operator_user_id):
    admin = db.users.find_one(
        {"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1},
    )
    case_id = f"svcrep-{uuid.uuid4()}"
    now = dt.datetime.now(dt.timezone.utc)
    db.svc_cases.insert_one({
        "id": case_id,
        "reference": "CASE-SVCREP-1",
        "organization_id": admin["organization_id"],
        "assigned_engineer_id": operator_user_id,
        "status": "closed",
        "priority": "p2",
        "title": "Treadmill #3 — belt slipping",
        "description": "Member reports the belt slips at 12 km/h.",
        "site_name": "Test Gym",
        "site_address": "1 Test St",
        "site_postcode": "TE5 1NG",
        "asset_name": "Life Fitness 95T",
        "customer_name": "Jane Customer",
        "customer_email": "jane.customer@example.com",
        "closed_at": now.isoformat(),
        "sla_resolve_at": (now - dt.timedelta(hours=2)).isoformat(),
        "created_at": (now - dt.timedelta(days=1)).isoformat(),
        "updated_at": now.isoformat(),
        "customer_rating": 5,
        "customer_rating_comment": "Quick, friendly, sorted.",
        "allocated_parts": [
            {
                "id": str(uuid.uuid4()),
                "part_sku": "BELT-001",
                "part_name": "Running belt 95T",
                "qty": 1,
                "source": "van",
            },
        ],
    })
    # one time entry per category so the report includes a Time section
    db.svc_time_entries.insert_many([
        {
            "id": str(uuid.uuid4()),
            "organization_id": admin["organization_id"],
            "case_id": case_id,
            "engineer_id": operator_user_id,
            "category": "travel",
            "duration_minutes": 25,
            "start_at": (now - dt.timedelta(hours=2)).isoformat(),
            "end_at": (now - dt.timedelta(hours=1, minutes=35)).isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "organization_id": admin["organization_id"],
            "case_id": case_id,
            "engineer_id": operator_user_id,
            "category": "on_site",
            "duration_minutes": 40,
            "start_at": (now - dt.timedelta(hours=1, minutes=30)).isoformat(),
            "end_at": (now - dt.timedelta(minutes=50)).isoformat(),
        },
    ])
    # one signature
    sig_id = str(uuid.uuid4())
    db.svc_signatures.insert_one({
        "id": sig_id,
        "organization_id": admin["organization_id"],
        "case_id": case_id,
        "signed_by_name": "Jane Customer",
        "signed_by_role": "Manager",
        "signed_at": now.isoformat(),
        # 1x1 transparent PNG as a data URL
        "image_data": (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        ),
        "summary": "Job done.",
    })
    # one fix_summary event so the Work Completed section populates
    db.svc_case_events.insert_one({
        "id": str(uuid.uuid4()),
        "case_id": case_id,
        "organization_id": admin["organization_id"],
        "type": "note",
        "body": "Replaced belt and re-tensioned. Tested at 14 km/h for 5 min.",
        "extra": {"kind": "fix_summary"},
        "at": now.isoformat(),
    })
    yield case_id
    db.svc_cases.delete_many({"id": case_id})
    db.svc_time_entries.delete_many({"case_id": case_id})
    db.svc_signatures.delete_many({"case_id": case_id})
    db.svc_case_events.delete_many({"case_id": case_id})


class TestServiceReportPDF:
    def test_pdf_returns_200_and_is_pdf(self, admin_headers, seeded_case):
        r = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/service-report.pdf",
            headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content.startswith(b"%PDF"), "PDF magic header missing"
        assert len(r.content) > 1500, "PDF unexpectedly small"

    def test_pdf_unknown_case_404(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/svc/cases/does-not-exist-svcrep/service-report.pdf",
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 404

    def test_pdf_requires_auth(self, seeded_case):
        r = requests.get(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/service-report.pdf",
            timeout=10,
        )
        assert r.status_code in (401, 403)


class TestServiceReportEmail:
    def test_email_missing_recipient_returns_400(self, admin_headers, db, operator_user_id):
        admin = db.users.find_one(
            {"email": ADMIN_EMAIL}, {"_id": 0, "organization_id": 1},
        )
        cid = f"svcrep-noemail-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid,
            "organization_id": admin["organization_id"],
            "assigned_engineer_id": operator_user_id,
            "status": "closed", "priority": "p3",
            "closed_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "title": "Noemail test",
        })
        try:
            r = requests.post(
                f"{BASE_URL}/api/svc/cases/{cid}/service-report/email",
                json={}, headers=admin_headers, timeout=10,
            )
            assert r.status_code == 400, r.text
        finally:
            db.svc_cases.delete_many({"id": cid})

    def test_email_persists_sent_metadata_on_success(self, admin_headers, seeded_case, db):
        """The endpoint may return 502 in preview (sender domain not verified)
        but on success (200) it must persist `service_report_sent_at` +
        `service_report_sent_to` so the UI can show the "Sent" pill.
        """
        r = requests.post(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/service-report/email",
            json={"to": "ops+test@example.com", "note": "Cheers!"},
            headers=admin_headers, timeout=20,
        )
        assert r.status_code in (200, 502), r.text
        if r.status_code == 200:
            doc = db.svc_cases.find_one(
                {"id": seeded_case},
                {"_id": 0, "service_report_sent_at": 1, "service_report_sent_to": 1},
            )
            assert doc["service_report_sent_to"] == "ops+test@example.com"
            assert "T" in doc["service_report_sent_at"]

    def test_email_requires_auth(self, seeded_case):
        r = requests.post(
            f"{BASE_URL}/api/svc/cases/{seeded_case}/service-report/email",
            json={"to": "a@b.com"}, timeout=10,
        )
        assert r.status_code in (401, 403)
