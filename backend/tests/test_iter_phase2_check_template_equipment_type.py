"""Phase 2 Task 2 backend - maintenance template equipment_type persistence."""
import os
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "owner@apexfitness.group",
        "password": "ApexDemo2026!"
    }, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_create_template_with_equipment_type_persists(auth_headers):
    payload = {
        "name": "TEST_Phase2_Treadmill_Template",
        "category": "Cardio",
        "equipment_type": "Treadmill",
        "items": ["Check belt", "Lubricate deck", "E-stop test"]
    }
    r = requests.post(f"{BASE_URL}/api/maintenance/templates", json=payload, headers=auth_headers, timeout=20)
    assert r.status_code in (200, 201), f"Create failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["equipment_type"] == "Treadmill"
    assert data["name"] == payload["name"]
    assert data["items"] == payload["items"]
    tid = data["id"]

    # GET verifies persistence
    g = requests.get(f"{BASE_URL}/api/maintenance/templates", headers=auth_headers, timeout=20)
    assert g.status_code == 200
    templates = g.json().get("templates", [])
    found = next((t for t in templates if t.get("id") == tid), None)
    assert found is not None, "Template not in GET list"
    assert found["equipment_type"] == "Treadmill"

    # Cleanup
    requests.delete(f"{BASE_URL}/api/maintenance/templates/{tid}", headers=auth_headers, timeout=10)


def test_create_template_without_equipment_type_stores_empty(auth_headers):
    payload = {
        "name": "TEST_Phase2_General",
        "category": "General",
        "items": ["Generic check 1", "Generic check 2"]
    }
    r = requests.post(f"{BASE_URL}/api/maintenance/templates", json=payload, headers=auth_headers, timeout=20)
    assert r.status_code in (200, 201), f"Create failed: {r.text}"
    data = r.json()
    assert data.get("equipment_type", None) == "", f"Expected empty string, got {data.get('equipment_type')!r}"
    tid = data["id"]

    g = requests.get(f"{BASE_URL}/api/maintenance/templates", headers=auth_headers, timeout=20)
    assert g.status_code == 200
    found = next((t for t in g.json().get("templates", []) if t.get("id") == tid), None)
    assert found is not None
    assert found.get("equipment_type", "") == ""

    requests.delete(f"{BASE_URL}/api/maintenance/templates/{tid}", headers=auth_headers, timeout=10)


def test_create_template_with_existing_equipment_type_from_org(auth_headers):
    # Pull an existing equipment type from the org
    eq = requests.get(f"{BASE_URL}/api/equipment", headers=auth_headers, timeout=20)
    assert eq.status_code == 200
    items = eq.json() if isinstance(eq.json(), list) else eq.json().get("equipment", [])
    types = sorted({(e.get("equipment_type") or "").strip() for e in items if e.get("equipment_type")})
    assert types, "Apex demo org should have equipment types"
    chosen = types[0]

    payload = {
        "name": f"TEST_Assigned_{chosen}",
        "category": "Custom",
        "equipment_type": chosen,
        "items": ["Custom item A", "Custom item B"]
    }
    r = requests.post(f"{BASE_URL}/api/maintenance/templates", json=payload, headers=auth_headers, timeout=20)
    assert r.status_code in (200, 201)
    data = r.json()
    assert data["equipment_type"] == chosen
    tid = data["id"]
    requests.delete(f"{BASE_URL}/api/maintenance/templates/{tid}", headers=auth_headers, timeout=10)


def test_spec_sheet_pdf_endpoint_public(auth_headers):
    """Task 1 - verify /api/spec-sheets/pdf/{id} is reachable; we don't have a known id but list endpoint should work."""
    # Try to list equipment with spec_sheet_id
    eq = requests.get(f"{BASE_URL}/api/equipment", headers=auth_headers, timeout=20)
    assert eq.status_code == 200
    items = eq.json() if isinstance(eq.json(), list) else eq.json().get("equipment", [])
    with_spec = [e for e in items if e.get("spec_sheet_id")]
    # OK if none — equip-manufacturer-manual card is conditional. Just log.
    print(f"Equipment with spec_sheet_id in apex-demo-org: {len(with_spec)} / {len(items)}")
    if with_spec:
        spec_id = with_spec[0]["spec_sheet_id"]
        r = requests.get(f"{BASE_URL}/api/spec-sheets/pdf/{spec_id}", timeout=20, allow_redirects=False)
        # Public endpoint - expect 200 or redirect, not 401
        assert r.status_code != 401, "spec sheet PDF endpoint should be public"
        print(f"Spec PDF status: {r.status_code}")
