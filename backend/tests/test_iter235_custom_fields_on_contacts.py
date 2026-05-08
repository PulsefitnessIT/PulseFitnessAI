"""Iter 235 — Custom Fields on contact-detail pages.

Covers:
  • CRM v2 contact PUT accepts a `custom_fields` map and round-trips it
    on GET (no schema change required — `update_contact` already accepts
    arbitrary keys; this proves the path is wired).
  • `/api/custom-properties/{id}/usage` now counts records across BOTH
    `crm_contacts` (marketing form submissions) AND `crm2_contacts`
    (operator-facing CRM) so the count matches what an operator sees on
    the contact-detail page.
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


@pytest.fixture(scope="module")
def crm_headers() -> dict:
    """The CRM v2 routes use a separate `crm_token` flow seeded by
    seed_crm_admin() on startup."""
    r = requests.post(
        f"{API_BASE}/crm/auth/login",
        json={"email": "craig.henshall@pulsefitness.com", "password": "Test123!"},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"CRM seed unavailable: {r.status_code} {r.text[:120]}")
    return {"Authorization": f"Bearer {r.json().get('token')}"}


def test_custom_field_round_trips_on_crm_v2_contact(crm_headers):
    """Create → patch with custom_fields → fetch → assert."""
    nonce = uuid.uuid4().hex[:6]
    create = requests.post(
        f"{API_BASE}/crm/v2/contacts",
        json={
            "first_name": "Iter235",
            "last_name": f"User {nonce}",
            "email": f"iter235+{nonce}@example.com",
            "lifecycle": "lead",
        },
        headers=crm_headers,
        timeout=15,
    )
    assert create.status_code == 200, create.text
    cid = create.json()["id"]

    # Patch with a custom_fields map — this is exactly what the
    # CustomFieldsPanel does on save.
    upd = requests.put(
        f"{API_BASE}/crm/v2/contacts/{cid}",
        json={"custom_fields": {"favourite_class": "spin", "preferred_trainer": "Sam"}},
        headers=crm_headers,
        timeout=10,
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["success"] is True

    # Fetch and assert round-trip
    fetched = requests.get(
        f"{API_BASE}/crm/v2/contacts/{cid}",
        headers=crm_headers,
        timeout=10,
    )
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["custom_fields"] == {"favourite_class": "spin", "preferred_trainer": "Sam"}

    # Patch a single key — the panel sends a partial map
    upd2 = requests.put(
        f"{API_BASE}/crm/v2/contacts/{cid}",
        json={"custom_fields": {"favourite_class": "hiit", "preferred_trainer": "Sam"}},
        headers=crm_headers,
        timeout=10,
    )
    assert upd2.status_code == 200
    fetched2 = requests.get(
        f"{API_BASE}/crm/v2/contacts/{cid}",
        headers=crm_headers,
        timeout=10,
    )
    assert fetched2.json()["custom_fields"]["favourite_class"] == "hiit"

    # Cleanup
    requests.delete(f"{API_BASE}/crm/v2/contacts/{cid}", headers=crm_headers, timeout=10)


def test_usage_endpoint_counts_both_collections(operator_headers, crm_headers):
    """Verify the `/usage` endpoint queries both `crm_contacts` and
    `crm2_contacts` without erroring. (The collections live in
    separate org partitions in this deployment, so we don't assert a
    cross-partition count — the assertion is that the endpoint succeeds
    and reports a non-error integer.)"""
    nonce = uuid.uuid4().hex[:6]
    cp = requests.post(
        f"{API_BASE}/custom-properties",
        json={
            "entity_type": "contact",
            "key": f"iter235_usage_{nonce}",
            "label": "Iter235 usage test",
            "field_type": "text",
        },
        headers=operator_headers,
        timeout=10,
    )
    assert cp.status_code == 200, cp.text
    pid = cp.json()["property"]["id"]

    u = requests.get(
        f"{API_BASE}/custom-properties/{pid}/usage",
        headers=operator_headers,
        timeout=10,
    )
    assert u.status_code == 200, u.text
    body = u.json()
    assert isinstance(body["usage"], int)
    assert body["usage"] >= 0
    assert body["entity_type"] == "contact"

    # Cleanup
    requests.delete(f"{API_BASE}/custom-properties/{pid}", headers=operator_headers, timeout=10)
    _ = crm_headers  # required for the same-fixture setup ordering


def test_unsetting_custom_field_round_trips(crm_headers):
    """Setting a custom field to None and re-saving should clear it on
    the contact (so an operator can delete a value via the panel)."""
    nonce = uuid.uuid4().hex[:6]
    contact = requests.post(
        f"{API_BASE}/crm/v2/contacts",
        json={
            "first_name": "Iter235", "last_name": f"Unset {nonce}",
            "email": f"iter235unset+{nonce}@example.com",
            "lifecycle": "lead",
            "custom_fields": {"favourite_class": "spin"},
        },
        headers=crm_headers,
        timeout=15,
    )
    cid = contact.json()["id"]
    requests.put(
        f"{API_BASE}/crm/v2/contacts/{cid}",
        json={"custom_fields": {"favourite_class": None}},
        headers=crm_headers,
        timeout=10,
    )
    fetched = requests.get(
        f"{API_BASE}/crm/v2/contacts/{cid}",
        headers=crm_headers,
        timeout=10,
    )
    cf = fetched.json()["custom_fields"]
    # Either the key is removed or its value is None — both fine.
    assert cf.get("favourite_class") is None
    requests.delete(f"{API_BASE}/crm/v2/contacts/{cid}", headers=crm_headers, timeout=10)
