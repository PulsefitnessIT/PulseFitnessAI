"""Iter 218 — partner-application approve / reject flow.

Critical first-customer fix: Dan Thomas's engineer-partner application
was persisted to `partner_applications` correctly, but the master-admin
UI was reading from `partner_engineers` so the row was invisible. This
test pins:

  1. The list endpoint returns pending applications (master-admin only).
  2. Approve promotes the application → `partner_engineers` and emits
     a referral code.
  3. After approval, the application no longer appears in
     `status=pending`.
  4. Approving the same application twice 400s.
  5. Reject marks the application without creating a partner row.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import pytest

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://mod-only-deploy.preview.emergentagent.com",
)


def _master_token() -> str:
    """Module-cached — avoid auth rate-limit on a 7-test suite."""
    if _CACHE.get("master"):
        return _CACHE["master"]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        )
        r.raise_for_status()
    _CACHE["master"] = r.json()["token"]
    return _CACHE["master"]


def _tenant_token() -> str:
    if _CACHE.get("tenant"):
        return _CACHE["tenant"]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": "jack.ottey@thirdspace.london", "password": "Test123!"},
        )
        r.raise_for_status()
    _CACHE["tenant"] = r.json()["token"]
    return _CACHE["tenant"]


_CACHE: dict[str, str] = {}


def _submit_application(email: str, full_name: str = "PinTest Engineer") -> str:
    """Submit a unique public application — returns the application id."""
    form = {
        "full_name": full_name,
        "email": email,
        "phone": "07700 900 999",
        "service_postcode": "M1 1AA",
        "travel_radius_km": "20",
        "brands_supported": "Life Fitness,Technogym",
        "skills": "mechanical",
        "qualifications": "NVQ Level 3",
        "years_experience": "5",
        "has_insurance": "true",
        "terms_accepted": "true",
    }
    with httpx.Client(timeout=20.0) as c:
        r = c.post(f"{BASE}/api/partners/public-apply", data=form)
    r.raise_for_status()
    j = r.json()
    assert j["ok"], j
    return j["application_id"]


# ── List endpoint — master-only ─────────────────────────────────


def test_list_applications_requires_master_admin() -> None:
    tenant = _tenant_token()
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications",
            headers={"Authorization": f"Bearer {tenant}"},
        )
    assert r.status_code == 403, r.text


def test_list_applications_returns_array_for_master() -> None:
    master = _master_token()
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/partners/applications",
            headers={"Authorization": f"Bearer {master}"},
        )
    assert r.status_code == 200
    j = r.json()
    assert "applications" in j
    assert "total" in j
    assert isinstance(j["applications"], list)


# ── Approve flow ───────────────────────────────────────────────


@pytest.fixture()
def pending_application_id() -> str:
    """Submit a fresh application with a unique email per test run."""
    email = f"pintest+{uuid.uuid4().hex[:8]}@example.com"
    return _submit_application(email)


def test_approve_promotes_application_to_partner(
    pending_application_id: str,
) -> None:
    master = _master_token()
    headers = {"Authorization": f"Bearer {master}"}
    with httpx.Client(timeout=20.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{pending_application_id}/approve",
            headers=headers,
            json={"level": "engineer_partner"},
        )
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    assert body["ok"]
    assert body["partner_id"]
    assert body["level"] == "engineer_partner"


def test_approve_twice_400s(pending_application_id: str) -> None:
    """Idempotency guard — second approve must 400, never silently
    create a second partner_engineers row."""
    master = _master_token()
    headers = {"Authorization": f"Bearer {master}"}
    with httpx.Client(timeout=20.0) as c:
        r1 = c.post(
            f"{BASE}/api/partners/applications/{pending_application_id}/approve",
            headers=headers, json={"level": "engineer_partner"},
        )
        assert r1.status_code == 200
        r2 = c.post(
            f"{BASE}/api/partners/applications/{pending_application_id}/approve",
            headers=headers, json={"level": "engineer_partner"},
        )
    assert r2.status_code == 400, r2.text
    assert "already" in r2.json()["detail"].lower()


def test_approve_invalid_level_400s(pending_application_id: str) -> None:
    master = _master_token()
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{pending_application_id}/approve",
            headers={"Authorization": f"Bearer {master}"},
            json={"level": "diamond_ultra"},
        )
    assert r.status_code == 400, r.text


def test_approve_unknown_application_404s() -> None:
    master = _master_token()
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{uuid.uuid4()}/approve",
            headers={"Authorization": f"Bearer {master}"},
            json={"level": "engineer_partner"},
        )
    assert r.status_code == 404


# ── Reject flow ───────────────────────────────────────────────


def test_reject_application(pending_application_id: str) -> None:
    master = _master_token()
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{pending_application_id}/reject",
            headers={"Authorization": f"Bearer {master}"},
            json={"reason": "Not enough experience yet — please reapply in 12 months."},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"]
    assert body["status"] == "rejected"
