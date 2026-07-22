"""Phase 2 — Sage 200 order sync (Simulate path)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _wipe(headers):
    """Best-effort clean state: not exposed via API; rely on idempotency instead."""
    # Directly wipe via mongo would need db access; test relies on idempotency guarantees.
    return


def test_field_map(headers):
    r = requests.get(f"{BASE_URL}/api/inventory/sage/field-map", headers=headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "field_map" in data
    assert any(f["pulse"] == "sage_order_id" for f in data["field_map"]["header"])


def test_simulate_idempotent_10x(headers):
    # Run 10 times, ensure only 2 mirrors remain
    for i in range(10):
        r = requests.post(f"{BASE_URL}/api/inventory/sage/sync/run", headers=headers, json={"simulate": True}, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "simulated"
    orders = requests.get(f"{BASE_URL}/api/inventory/sage/orders", headers=headers, timeout=30).json()["orders"]
    sage_ids = {o["sage_order_id"] for o in orders}
    assert "SAGE-1001" in sage_ids and "SAGE-1002" in sage_ids
    # There should be exactly the 2 sample orders (no duplicates)
    dup_1001 = [o for o in orders if o["sage_order_id"] == "SAGE-1001"]
    dup_1002 = [o for o in orders if o["sage_order_id"] == "SAGE-1002"]
    assert len(dup_1001) == 1 and len(dup_1002) == 1

    status = requests.get(f"{BASE_URL}/api/inventory/sage/sync/status", headers=headers, timeout=30).json()
    assert status["health"] in ("warning", "healthy")


def test_exceptions_populated(headers):
    r = requests.get(f"{BASE_URL}/api/inventory/sage/exceptions", headers=headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    unmapped_products = {p["sage_stock_code"] for p in data["unmapped_products"]}
    # DELIVERY should NOT be in unmapped list
    assert "DELIVERY" not in unmapped_products
    # These need mapping
    for code in ("TREAD-900", "BIKE-500", "ROWER-300", "SPARE-BELT"):
        assert code in unmapped_products, f"{code} missing"


def test_map_dealer_and_products_then_retry(headers):
    # iso-demo-org has seeded 'iso-cA' AlphaCo (Site A)
    company_id = "iso-cA"

    r = requests.post(f"{BASE_URL}/api/inventory/sage/mappings/dealer", headers=headers,
                      json={"sage_account": "FITFR01", "crm_company_id": company_id}, timeout=30)
    assert r.status_code == 200, r.text

    for code in ("TREAD-900", "BIKE-500"):
        r = requests.post(f"{BASE_URL}/api/inventory/sage/mappings/product", headers=headers,
                          json={"sage_stock_code": code, "product_code": code}, timeout=30)
        assert r.status_code == 200

    # Find SO-1001 mirror id
    orders = requests.get(f"{BASE_URL}/api/inventory/sage/orders", headers=headers, timeout=30).json()["orders"]
    m1001 = next(o for o in orders if o["sage_order_id"] == "SAGE-1001")

    # Retry
    r = requests.post(f"{BASE_URL}/api/inventory/sage/orders/{m1001['id']}/retry", headers=headers, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] in ("imported", "updated")


def test_distribution_order_created_with_5_units(headers):
    # Find DO from sage source
    r = requests.get(f"{BASE_URL}/api/inventory/orders", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    orders = r.json().get("orders", [])
    sage_orders = [o for o in orders if o.get("source") == "sage" and o.get("sage_order_id") == "SAGE-1001"]
    assert len(sage_orders) == 1, f"Expected 1 sage-sourced DO for SAGE-1001, got {len(sage_orders)}"
    order_id = sage_orders[0]["id"]

    # Verify lines + equipment units
    detail = requests.get(f"{BASE_URL}/api/inventory/orders/{order_id}", headers=headers, timeout=30)
    assert detail.status_code == 200
    d = detail.json()
    units_r = requests.get(f"{BASE_URL}/api/inventory/orders/{order_id}/units", headers=headers, timeout=30)
    assert units_r.status_code == 200
    units = units_r.json().get("units", [])
    assert len(units) == 5, f"Expected 5 provisional units, got {len(units)}"


def test_idempotency_after_import(headers):
    # Re-run simulate; SO-1001 should be skipped (duplicates_prevented), no new DO
    before = requests.get(f"{BASE_URL}/api/inventory/orders", headers=headers, timeout=30).json().get("orders", [])
    sage_count_before = len([o for o in before if o.get("sage_order_id") == "SAGE-1001"])

    r = requests.post(f"{BASE_URL}/api/inventory/sage/sync/run", headers=headers, json={"simulate": True}, timeout=60)
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["duplicates_prevented"] >= 1
    assert run["needs_mapping"] >= 1  # SO-1002 still unmapped

    after = requests.get(f"{BASE_URL}/api/inventory/orders", headers=headers, timeout=30).json().get("orders", [])
    sage_count_after = len([o for o in after if o.get("sage_order_id") == "SAGE-1001"])
    assert sage_count_after == sage_count_before == 1


def test_live_run_without_connection(headers):
    r = requests.post(f"{BASE_URL}/api/inventory/sage/sync/run", headers=headers, json={"simulate": False}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    # If Sage not connected: authentication_required
    if not data.get("run"):
        assert data.get("health") == "authentication_required"
