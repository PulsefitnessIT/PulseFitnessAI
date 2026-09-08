"""Inventory & Distribution — Phase 1 backend smoke (iter: dealer_dist_phase1)."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://allocation-wizard-ai.preview.emergentagent.com").rstrip("/")
EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"

TAG = uuid.uuid4().hex[:6].upper()


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code == 429:
        time.sleep(35)
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_dashboard(H):
    r = requests.get(f"{BASE_URL}/api/inventory/dashboard", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    assert "cards" in r.json()


def test_field_ownership(H):
    r = requests.get(f"{BASE_URL}/api/inventory/field-ownership", headers=H, timeout=20)
    assert r.status_code == 200
    assert len(r.json()["matrix"]) > 5


def test_settings(H):
    r = requests.get(f"{BASE_URL}/api/inventory/settings", headers=H, timeout=20)
    assert r.status_code == 200
    r2 = requests.put(f"{BASE_URL}/api/inventory/settings", headers=H, json={"qc_required": False}, timeout=20)
    assert r2.status_code == 200
    assert r2.json()["qc_required"] is False


def test_sage(H):
    r = requests.get(f"{BASE_URL}/api/inventory/sage/connection", headers=H, timeout=20)
    assert r.status_code == 200
    r2 = requests.post(f"{BASE_URL}/api/inventory/sage/connection", headers=H,
                       json={"edition": "standard", "version": "2024", "company": f"TEST_{TAG}"}, timeout=20)
    assert r2.status_code == 200
    r3 = requests.get(f"{BASE_URL}/api/inventory/sage/capabilities/discover", headers=H, timeout=20)
    assert r3.status_code == 200
    assert "capabilities" in r3.json()


def test_warehouse_and_location(H):
    code = f"TWH{TAG}"
    r = requests.post(f"{BASE_URL}/api/inventory/warehouses", headers=H,
                      json={"code": code, "name": f"TEST WH {TAG}", "country": "GB"}, timeout=20)
    assert r.status_code == 200, r.text
    wh_id = r.json()["id"]
    lr = requests.post(f"{BASE_URL}/api/inventory/warehouses/{wh_id}/locations", headers=H,
                       json={"code": f"L{TAG}", "zone": "A"}, timeout=20)
    assert lr.status_code == 200
    pytest.wh_id = wh_id
    pytest.wh_code = code


def test_order_lifecycle(H):
    wh_id = pytest.wh_id
    product_code = f"PC{TAG}"
    order_body = {
        "dealer_name": f"TEST Dealer {TAG}",
        "dealer_country": "FR",
        "currency": "EUR",
        "customer_po": f"PO-{TAG}",
        "delivery_address": "10 Rue de Paris",
        "warehouse_id": wh_id,
        "lines": [{
            "product_code": product_code,
            "description": "Test Machine",
            "product_type": "serialised_machine",
            "quantity": 3,
            "unit_price": 100.0,
        }],
    }
    r = requests.post(f"{BASE_URL}/api/inventory/orders", headers=H, json=order_body, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    order_id = data["order"]["id"]
    assert data["provisional_units"] == 3

    # validate
    v = requests.post(f"{BASE_URL}/api/inventory/orders/{order_id}/validate", headers=H, timeout=20)
    assert v.status_code == 200
    assert "checks" in v.json()

    # receive 2 units
    rc = requests.post(f"{BASE_URL}/api/inventory/stock/receive", headers=H,
                       json={"warehouse_id": wh_id, "product_code": product_code, "quantity": 2}, timeout=20)
    assert rc.status_code == 200

    # reserve
    rv = requests.post(f"{BASE_URL}/api/inventory/orders/{order_id}/reserve", headers=H, timeout=20)
    assert rv.status_code == 200
    assert rv.json()["order_status"] == "partially_available"

    # get order detail
    od = requests.get(f"{BASE_URL}/api/inventory/orders/{order_id}", headers=H, timeout=20)
    assert od.status_code == 200
    units = od.json()["units"]
    assert len(units) == 3

    # assign serial to first
    serial = f"SN{TAG}001"
    a1 = requests.post(f"{BASE_URL}/api/inventory/units/{units[0]['id']}/assign-serial",
                       headers=H, json={"serial_number": serial}, timeout=20)
    assert a1.status_code == 200
    assert a1.json()["unit"]["status"] == "serial_assigned"

    # dedupe: same serial on 2nd unit → 409
    a2 = requests.post(f"{BASE_URL}/api/inventory/units/{units[1]['id']}/assign-serial",
                       headers=H, json={"serial_number": serial}, timeout=20)
    assert a2.status_code == 409, f"Expected 409, got {a2.status_code}: {a2.text}"


def test_stock_availability(H):
    r = requests.get(f"{BASE_URL}/api/inventory/stock/availability", headers=H, timeout=20)
    assert r.status_code == 200
