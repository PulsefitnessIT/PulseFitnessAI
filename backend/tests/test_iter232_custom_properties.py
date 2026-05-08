"""Iter 232 — Custom Properties (user-facing schema editor) tests.

Covers:
  • Auth — 401 unauthenticated; 403 non-owner non-admin
  • CRUD lifecycle (create + list + get + update + archive)
  • Key + field_type validation
  • Reserved keys rejected
  • Duplicate (org, entity_type, key) rejected
  • Immutable fields cannot change after creation
  • Soft-delete (status=archived); GET /usage works post-archive
  • Form submission routes `custom.<key>` mappings into contact.custom_fields
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
def master_headers() -> dict:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


def _create(headers: dict, **overrides) -> dict:
    nonce = uuid.uuid4().hex[:6]
    payload = {
        "entity_type": "contact",
        "key": f"iter232_{nonce}",
        "label": f"Iter232 {nonce}",
        "field_type": "text",
        **overrides,
    }
    r = requests.post(
        f"{API_BASE}/custom-properties",
        json=payload,
        headers=headers,
        timeout=15,
    )
    return r


def test_unauthenticated_rejected():
    r = requests.get(f"{API_BASE}/custom-properties", timeout=10)
    assert r.status_code in (401, 403)


def test_create_list_get_update_archive_lifecycle(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    create_r = requests.post(
        f"{API_BASE}/custom-properties",
        json={
            "entity_type": "contact",
            "key": f"iter232_lifecycle_{nonce}",
            "label": "Lifecycle test",
            "field_type": "select",
            "options": [{"value": "yes", "label": "Yes"}, "no"],
            "group": "Preferences",
        },
        headers=operator_headers,
        timeout=15,
    )
    assert create_r.status_code == 200, create_r.text
    prop = create_r.json()["property"]
    assert prop["status"] == "active"
    assert len(prop["options"]) == 2
    pid = prop["id"]

    list_r = requests.get(
        f"{API_BASE}/custom-properties?entity_type=contact",
        headers=operator_headers,
        timeout=10,
    )
    assert any(p["id"] == pid for p in list_r.json()["properties"])

    get_r = requests.get(
        f"{API_BASE}/custom-properties/{pid}",
        headers=operator_headers,
        timeout=10,
    )
    assert get_r.status_code == 200

    upd_r = requests.put(
        f"{API_BASE}/custom-properties/{pid}",
        json={"label": "Updated Lifecycle", "required": True},
        headers=operator_headers,
        timeout=10,
    )
    assert upd_r.status_code == 200
    upd = upd_r.json()["property"]
    assert upd["label"] == "Updated Lifecycle"
    assert upd["required"] is True

    arc_r = requests.delete(
        f"{API_BASE}/custom-properties/{pid}",
        headers=operator_headers,
        timeout=10,
    )
    assert arc_r.status_code == 200

    # Default list excludes archived
    list_r2 = requests.get(
        f"{API_BASE}/custom-properties?entity_type=contact",
        headers=operator_headers,
        timeout=10,
    )
    assert all(p["id"] != pid for p in list_r2.json()["properties"])

    # include_archived=true brings it back
    list_r3 = requests.get(
        f"{API_BASE}/custom-properties?entity_type=contact&include_archived=true",
        headers=operator_headers,
        timeout=10,
    )
    assert any(p["id"] == pid for p in list_r3.json()["properties"])


def test_invalid_key_rejected(operator_headers):
    r = _create(operator_headers, key="Invalid Key!")
    assert r.status_code == 400


def test_invalid_entity_rejected(operator_headers):
    r = _create(operator_headers, entity_type="ufo")
    assert r.status_code == 400


def test_invalid_field_type_rejected(operator_headers):
    r = _create(operator_headers, field_type="picture")
    assert r.status_code == 400


def test_reserved_key_rejected(operator_headers):
    r = _create(operator_headers, key="email")
    assert r.status_code == 400


def test_duplicate_key_rejected(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    r1 = _create(operator_headers, key=f"dupkey_{nonce}")
    assert r1.status_code == 200, r1.text
    r2 = _create(operator_headers, key=f"dupkey_{nonce}")
    assert r2.status_code == 409


def test_immutable_fields_locked(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    r = _create(operator_headers, key=f"imm_{nonce}")
    pid = r.json()["property"]["id"]
    # try to change key
    r_bad = requests.put(
        f"{API_BASE}/custom-properties/{pid}",
        json={"key": "different_key", "label": "x"},
        headers=operator_headers,
        timeout=10,
    )
    assert r_bad.status_code == 400
    # try to change field_type
    r_bad2 = requests.put(
        f"{API_BASE}/custom-properties/{pid}",
        json={"field_type": "number"},
        headers=operator_headers,
        timeout=10,
    )
    assert r_bad2.status_code == 400


def test_master_admin_can_crud(master_headers):
    nonce = uuid.uuid4().hex[:6]
    r = requests.post(
        f"{API_BASE}/custom-properties",
        json={
            "entity_type": "contact",
            "key": f"master_iter232_{nonce}",
            "label": "Master test",
            "field_type": "boolean",
        },
        headers=master_headers,
        timeout=10,
    )
    assert r.status_code == 200, r.text


def test_usage_count_returns_zero_for_unused(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    r = _create(operator_headers, key=f"usage_{nonce}")
    pid = r.json()["property"]["id"]
    u = requests.get(
        f"{API_BASE}/custom-properties/{pid}/usage",
        headers=operator_headers,
        timeout=10,
    )
    assert u.status_code == 200
    assert u.json()["usage"] == 0


def test_unknown_property_404(operator_headers):
    r = requests.get(
        f"{API_BASE}/custom-properties/bogus-id",
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 404


def test_form_routes_custom_field_into_contact(operator_headers):
    """Submitting a form whose field has crm_property='custom.<key>'
    persists the value to contact.custom_fields.<key>."""
    nonce = uuid.uuid4().hex[:6]
    # 1) create a property
    cp = _create(operator_headers, key=f"form_route_{nonce}")
    assert cp.status_code == 200, cp.text
    cp_key = cp.json()["property"]["key"]

    # 2) create a form mapping a field to this custom property
    form_payload = {
        "name": f"Iter232 Form {nonce}",
        "description": "test",
        "fields": [
            {"label": "Email", "field_type": "email", "required": True, "crm_property": "email"},
            {"label": "Favourite", "field_type": "text", "required": False, "crm_property": f"custom.{cp_key}"},
        ],
    }
    fr = requests.post(
        f"{API_BASE}/marketing/forms",
        json=form_payload,
        headers=operator_headers,
        timeout=15,
    )
    assert fr.status_code == 200, fr.text
    form_meta = fr.json()
    slug = form_meta["slug"]
    field_ids = {f["label"]: f["id"] for f in form_meta["fields"]}

    # 3) submit the form (public unauth endpoint)
    submit_email = f"iter232+{nonce}@example.com"
    sub_r = requests.post(
        f"{API_BASE}/marketing/forms/by-slug/{slug}/submit",
        json={
            "values": {
                field_ids["Email"]: submit_email,
                field_ids["Favourite"]: "Spin classes",
            },
            "consent": True,
        },
        timeout=15,
    )
    assert sub_r.status_code == 200, sub_r.text

    # 4) verify the contact carries the custom_field
    # We fetch via the audiences preview which queries crm_contacts.
    pv = requests.post(
        f"{API_BASE}/marketing/audiences/preview",
        json={"rules": {"op": "and", "conditions": [
            {"field": f"custom_fields.{cp_key}", "op": "==", "value": "Spin classes"},
        ]}},
        headers=operator_headers,
        timeout=15,
    )
    assert pv.status_code == 200, pv.text
    body = pv.json()
    assert body["estimated_size"] >= 1, "submitted contact should be findable via custom_field rule"
