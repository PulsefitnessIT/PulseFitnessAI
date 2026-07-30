"""Iter 219 — Partner application full-detail drawer endpoints.

Covers the three new master-admin endpoints that let the master
admin click into a pending engineer application and review every
field + paperwork the applicant uploaded:

  • GET   /api/partners/applications/{id}                 (full detail)
  • PATCH /api/partners/applications/{id}/notes           (reviewer notes)
  • GET   /api/partners/applications/{id}/attachments/{aid}  (auth-gated
    streaming download for a single CV / cert attachment).

Follows the same live-preview httpx pattern used by iter 218 — the
TestClient pathway races with the Motor event loop, so we drive the
running server instead.
"""
from __future__ import annotations

import io
import os
import uuid

import httpx
import pytest


BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://mod-hq-email.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _bypass_headers() -> dict[str, str]:
    """Optional rate-limit bypass — see iter 219d test file for context."""
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": secret} if secret else {}


def _login(email: str, password: str) -> str:
    key = f"login::{email}"
    if _CACHE.get(key):
        return _CACHE[key]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
            headers=_bypass_headers(),
        )
        r.raise_for_status()
    _CACHE[key] = r.json()["token"]
    return _CACHE[key]


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


def _non_admin_headers() -> dict[str, str]:
    # `engineer.smoke` is a partner_engineer with no master-admin flag,
    # so it's perfect to assert the 403 boundary.
    return {"Authorization": f"Bearer {_login('engineer.smoke@gymaxisai.com', 'EngTest123!')}"}


@pytest.fixture()
def fresh_application_id() -> str:
    """Public-apply a brand-new application with a CV + cert attachment
    so we have rich data to inspect."""
    cv_bytes = b"%PDF-1.4\nFake CV body for iter 219 tests.\n%%EOF"
    cert_bytes = b"%PDF-1.4\nFake cert body for iter 219 tests.\n%%EOF"
    files = {
        "cv_file":   ("cv.pdf",   io.BytesIO(cv_bytes),   "application/pdf"),
        "cert_file": ("cert.pdf", io.BytesIO(cert_bytes), "application/pdf"),
    }
    email = f"iter219-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "full_name": "Iter 219 Test Engineer",
        "email": email,
        "phone": "07123456789",
        "company_name": "Test Engineering Co",
        "service_postcode": "SW1A 1AA",
        "travel_radius_km": "50",
        "brands_supported": "Life Fitness,Technogym,Precor",
        "skills": "cardio,strength,electrical",
        "qualifications": "C&G Level 3,IPAF,IOSH",
        "years_experience": "7",
        "has_insurance": "true",
        "insurance_provider": "Hiscox",
        "insurance_expires_at": "2026-12-31",
        "qualifications_expires_at": "2027-06-30",
        "referral_source": "Google search",
        "cover_letter": "I have 7 years of UK gym equipment service experience.",
        "terms_accepted": "true",
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.post(f"{BASE}/api/partners/public-apply", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()["application_id"]


# ───────────────── GET /partners/applications/{id} ─────────────────


def test_get_application_full_detail_returns_every_submitted_field(fresh_application_id: str):
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications/{fresh_application_id}",
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"application", "referrer"}
    app_doc = body["application"]
    assert app_doc["full_name"] == "Iter 219 Test Engineer"
    assert app_doc["phone"] == "07123456789"
    assert app_doc["company_name"] == "Test Engineering Co"
    assert app_doc["service_postcode"] == "SW1A 1AA"
    assert app_doc["travel_radius_km"] == 50
    assert "Life Fitness" in app_doc["brands_supported"]
    assert "electrical" in app_doc["skills"]
    assert "IPAF" in app_doc["qualifications"]
    assert app_doc["years_experience"] == "7"
    assert app_doc["has_insurance"] is True
    assert app_doc["insurance_provider"] == "Hiscox"
    assert app_doc["insurance_expires_at"]
    assert app_doc["qualifications_expires_at"]
    assert app_doc["terms_accepted_at"]
    assert app_doc["cover_letter"].startswith("I have 7 years")
    assert app_doc["status"] == "pending"


def test_get_application_rewrites_attachment_urls_to_auth_endpoint(fresh_application_id: str):
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications/{fresh_application_id}",
            headers=_admin_headers(),
        )
    assert r.status_code == 200
    attachments = r.json()["application"]["attachments"]
    assert len(attachments) == 2
    for att in attachments:
        assert att["download_url"].startswith(
            f"/api/partners/applications/{fresh_application_id}/attachments/"
        )
        assert att["id"]
        assert att["original_filename"] in {"cv.pdf", "cert.pdf"}


def test_get_application_404_when_missing():
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications/does-not-exist-{uuid.uuid4().hex[:8]}",
            headers=_admin_headers(),
        )
    assert r.status_code == 404


def test_get_application_403_for_non_admin(fresh_application_id: str):
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications/{fresh_application_id}",
            headers=_non_admin_headers(),
        )
    assert r.status_code == 403


# ─────────────── PATCH /partners/applications/{id}/notes ───────────────


def test_reviewer_notes_round_trip(fresh_application_id: str):
    note = "Spoke to candidate — references look strong."
    with httpx.Client(timeout=15.0) as c:
        r = c.patch(
            f"{BASE}/api/partners/applications/{fresh_application_id}/notes",
            json={"notes": note},
            headers=_admin_headers(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["reviewer_notes"] == note
        r2 = c.get(
            f"{BASE}/api/partners/applications/{fresh_application_id}",
            headers=_admin_headers(),
        )
    assert r2.json()["application"]["reviewer_notes"] == note


def test_reviewer_notes_empty_clears(fresh_application_id: str):
    with httpx.Client(timeout=15.0) as c:
        c.patch(
            f"{BASE}/api/partners/applications/{fresh_application_id}/notes",
            json={"notes": "draft"},
            headers=_admin_headers(),
        )
        r = c.patch(
            f"{BASE}/api/partners/applications/{fresh_application_id}/notes",
            json={"notes": "   "},
            headers=_admin_headers(),
        )
    assert r.status_code == 200
    assert r.json()["reviewer_notes"] is None


# ───── GET /partners/applications/{id}/attachments/{attachment_id} ─────


def test_attachment_download_streams_the_original_bytes(fresh_application_id: str):
    with httpx.Client(timeout=30.0) as c:
        det = c.get(
            f"{BASE}/api/partners/applications/{fresh_application_id}",
            headers=_admin_headers(),
        )
        attachments = det.json()["application"]["attachments"]
        cv = next(a for a in attachments if a["original_filename"] == "cv.pdf")
        r = c.get(f"{BASE}{cv['download_url']}", headers=_admin_headers())
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF-1.4")
    cd = r.headers.get("content-disposition", "")
    assert "cv.pdf" in cd


def test_attachment_download_404_for_unknown_attachment(fresh_application_id: str):
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications/{fresh_application_id}/attachments/nope-{uuid.uuid4().hex[:8]}",
            headers=_admin_headers(),
        )
    assert r.status_code == 404


def test_attachment_download_403_for_non_admin(fresh_application_id: str):
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications/{fresh_application_id}/attachments/anything",
            headers=_non_admin_headers(),
        )
    assert r.status_code == 403
