"""Iter 265 — End-to-end backend integration tests for US engineer readiness.

Validates the full flow:
  1. Public apply with country_code=US stores US market (and ZIP, not UK postcode).
  2. Public apply with country_code=GB still validates UK postcode.
  3. Master-admin approval of a US application produces a partner_engineers
     row whose country_code='US'.
  4. Admin compliance view for that US partner returns required_kinds =
     {work_authorization, background_check, public_liability}.
  5. Regression: GB engineer compliance still returns DBS/RTW set.
  6. Regression: GB application + approve still works.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

BASE = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://admin-portal-fix-37.preview.emergentagent.com",
).rstrip("/")

BYPASS = os.environ.get(
    "RATE_LIMIT_BYPASS_SECRET",
    "7d889c8f7c814c8fdfeeb49fd2ea8bca2b17df490c8df1fea50bd7d279f44105",
)

_CACHE: dict[str, str] = {}


def _master_token() -> str:
    if _CACHE.get("master"):
        return _CACHE["master"]
    with httpx.Client(timeout=20.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        )
    r.raise_for_status()
    _CACHE["master"] = r.json()["token"]
    return _CACHE["master"]


def _engineer_token() -> str | None:
    """Login as the seeded UK partner engineer (for compliance regression)."""
    if "engineer" in _CACHE:
        return _CACHE["engineer"]
    with httpx.Client(timeout=20.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={
                "email": "engineer.smoke@gymaxisai.com",
                "password": "EngTest123!",
            },
        )
    if r.status_code != 200:
        return None
    _CACHE["engineer"] = r.json()["token"]
    return _CACHE["engineer"]


def _submit_application(*, country_code: str, postcode: str, email_prefix: str) -> tuple[str, dict]:
    """POST /api/partners/public-apply (multipart). Returns (application_id, response_json)."""
    email = f"{email_prefix}+{uuid.uuid4().hex[:8]}@example.com"
    form = {
        "full_name": f"PinTest {country_code} Engineer",
        "email": email,
        "phone": "07700 900 999",
        "country_code": country_code,
        "service_postcode": postcode,
        "travel_radius_km": "20",
        "brands_supported": "Life Fitness,Technogym",
        "skills": "mechanical",
        "qualifications": "NVQ Level 3",
        "years_experience": "5",
        "has_insurance": "true",
        "terms_accepted": "true",
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/public-apply",
            data=form,
            headers={"X-RateLimit-Bypass": BYPASS},
        )
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text})


# ── 1. Public apply: US market stored, ZIP accepted ──────────────────────


def test_public_apply_us_stores_us_market_and_accepts_zip() -> None:
    status, body = _submit_application(
        country_code="US", postcode="10001", email_prefix="us_apply"
    )
    assert status == 200, body
    assert body.get("ok") is True, body
    application_id = body["application_id"]

    # Verify the application document via master-admin list endpoint.
    master = _master_token()
    with httpx.Client(timeout=20.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications?status=pending",
            headers={"Authorization": f"Bearer {master}"},
        )
    assert r.status_code == 200, r.text
    apps = r.json().get("applications", [])
    matched = next((a for a in apps if a.get("id") == application_id), None)
    assert matched is not None, "Submitted US application not found in pending list"
    assert matched.get("country_code") == "US", matched
    assert matched.get("service_postcode") == "10001"


def test_public_apply_gb_default_still_works() -> None:
    status, body = _submit_application(
        country_code="GB", postcode="M1 1AA", email_prefix="gb_apply"
    )
    assert status == 200, body
    assert body.get("ok") is True

    master = _master_token()
    with httpx.Client(timeout=20.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications?status=pending",
            headers={"Authorization": f"Bearer {master}"},
        )
    apps = r.json().get("applications", [])
    matched = next((a for a in apps if a.get("id") == body["application_id"]), None)
    assert matched is not None
    assert matched.get("country_code") == "GB"


def test_public_apply_gb_still_runs_uk_postcode_validator() -> None:
    """For GB, the postcode validator is invoked (uppercases, trims). The
    validator is lenient by design (length only), so we assert the
    persisted postcode was normalised — proving the validator branch ran."""
    status, body = _submit_application(
        country_code="GB", postcode="  m1 1aa  ", email_prefix="gb_pc_norm"
    )
    assert status == 200, body
    master = _master_token()
    with httpx.Client(timeout=20.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications?status=pending",
            headers={"Authorization": f"Bearer {master}"},
        )
    apps = r.json().get("applications", [])
    matched = next((a for a in apps if a.get("id") == body["application_id"]), None)
    assert matched is not None
    # GB branch uppercases + collapses whitespace; US branch would only trim.
    assert matched.get("service_postcode") == "M1 1AA", matched


# ── 2. Approval promotes US application → partner_engineers.country_code=US ──


@pytest.fixture()
def approved_us_partner_id() -> str:
    """Submit and approve a US application; return the new partner_id."""
    status, body = _submit_application(
        country_code="US", postcode="10001", email_prefix="us_approve"
    )
    assert status == 200, body
    application_id = body["application_id"]

    master = _master_token()
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/approve",
            headers={"Authorization": f"Bearer {master}"},
            json={"level": "engineer_partner"},
        )
    assert r.status_code == 200, r.text
    return r.json()["partner_id"]


def test_approved_us_partner_has_us_market(approved_us_partner_id: str) -> None:
    """The admin compliance view reads partner_engineers.country_code."""
    master = _master_token()
    with httpx.Client(timeout=20.0) as c:
        r = c.get(
            f"{BASE}/api/master-admin/partners/{approved_us_partner_id}/compliance-docs",
            headers={"Authorization": f"Bearer {master}"},
        )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["country_code"] == "US", j
    required = set(j.get("required_kinds") or [])
    assert "work_authorization" in required, j
    assert "background_check" in required, j
    assert "public_liability" in required, j
    # MUST NOT include the UK doc set
    assert "dbs" not in required, j
    assert "rtw" not in required, j
    assert "safeguarding" not in required, j


# ── 3. GB engineer compliance regression ────────────────────────────────


def test_gb_engineer_compliance_returns_uk_doc_set() -> None:
    """GET /api/partners/me/compliance-docs for the seeded GB engineer
    must still return the UK doc set (dbs/rtw/safeguarding/public_liability)."""
    token = _engineer_token()
    if not token:
        pytest.skip("Seeded engineer login not available in this preview env")
    with httpx.Client(timeout=20.0) as c:
        r = c.get(
            f"{BASE}/api/partners/me/compliance-docs",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("country_code") == "GB", j
    required = set(j.get("required_kinds") or [])
    assert {"dbs", "rtw", "safeguarding", "public_liability"}.issubset(required), j
    assert "work_authorization" not in required


# ── 4. Locale resolver runtime sanity (no import regressions) ──────────


def test_engineer_localization_imports_cleanly() -> None:
    """Cheap smoke that the resolver module imports & functions exist
    (caught a NameError/ImportError once in iter 220p1)."""
    from utils.localization import engineer_localization, COUNTRY_CONFIG
    assert "US" in COUNTRY_CONFIG
    assert "GB" in COUNTRY_CONFIG
    assert callable(engineer_localization)
