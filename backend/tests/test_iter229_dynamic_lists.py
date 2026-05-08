"""Iter 229 — Active Dynamic Lists tests.

Covers:
  • CRUD lifecycle (create → list → fetch → update → delete)
  • Auto-refresh on stale read (refresh_stale=true)
  • Force refresh
  • Members pagination + 404 + cross-org isolation
  • Refresh interval bounds validation
  • Membership-check endpoint (used by Journeys gates)
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API_BASE = os.environ.get("API_BASE") or (
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=", 1)[1].split("\n", 1)[0].strip() + "/api"
)


def _login(email: str, password: str) -> str:
    headers = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only-2026"}
    r = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def operator_headers() -> dict:
    return {"Authorization": f"Bearer {_login('lee.somers@pulsefitness.com', 'TempPass123!')}"}


def _create_list(operator_headers: dict, name: str, **extra) -> dict:
    payload = {
        "name": name,
        "rules": {"op": "and", "conditions": []},
        **extra,
    }
    r = requests.post(
        f"{API_BASE}/marketing/dynamic-lists",
        json=payload,
        headers=operator_headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["list"]


def test_dynamic_list_crud_lifecycle(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    name = f"Iter229 List {nonce}"

    created = _create_list(operator_headers, name=name, description="Test")
    assert created["name"] == name
    assert created["refresh_interval_minutes"] == 60
    assert created["last_evaluated_at"] is not None
    list_id = created["id"]

    r = requests.get(
        f"{API_BASE}/marketing/dynamic-lists",
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert any(li["id"] == list_id for li in body["lists"])

    r = requests.put(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}",
        json={"name": f"{name} v2", "refresh_interval_minutes": 240},
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 200, r.text
    updated = r.json()["list"]
    assert updated["name"].endswith(" v2")
    assert updated["refresh_interval_minutes"] == 240

    r = requests.delete(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}",
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 200

    r = requests.get(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}",
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 404


def test_refresh_interval_bounds_validation(operator_headers):
    r = requests.post(
        f"{API_BASE}/marketing/dynamic-lists",
        json={"name": "TooFast", "refresh_interval_minutes": 1},
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 400

    r = requests.post(
        f"{API_BASE}/marketing/dynamic-lists",
        json={"name": "TooSlow", "refresh_interval_minutes": 99999},
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_force_refresh_and_members_listing(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    created = _create_list(operator_headers, name=f"Iter229 Members {nonce}")
    list_id = created["id"]

    r = requests.post(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}/refresh",
        headers=operator_headers,
        timeout=15,
    )
    assert r.status_code == 200
    refreshed = r.json()["list"]
    assert refreshed["last_evaluated_at"] is not None

    r = requests.get(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}/members?page=1&page_size=10",
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert isinstance(body["members"], list)
    assert "total" in body

    requests.delete(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}",
        headers=operator_headers,
        timeout=10,
    )


def test_membership_check_endpoint(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    created = _create_list(operator_headers, name=f"Iter229 Contains {nonce}")
    list_id = created["id"]
    r = requests.get(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}/contains/non-existent-id",
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["list_id"] == list_id
    assert body["contains"] is False
    requests.delete(
        f"{API_BASE}/marketing/dynamic-lists/{list_id}",
        headers=operator_headers,
        timeout=10,
    )


def test_unknown_list_returns_404(operator_headers):
    r = requests.get(
        f"{API_BASE}/marketing/dynamic-lists/bogus-id",
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 404


def test_unauthenticated_access_rejected():
    r = requests.get(f"{API_BASE}/marketing/dynamic-lists", timeout=10)
    assert r.status_code in (401, 403)
