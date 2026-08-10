"""Backend tests for Dealer Warranty Parts (Phase 1) — Jan 2026."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://multi-eng-booking.preview.emergentagent.com"
API = f"{BASE_URL}/api/dealer-parts"

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"No token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Dashboard ─────────────────────────────────────────────
def test_dashboard(h):
    r = requests.get(f"{API}/dashboard", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "cards" in d
    for k in ("dealers", "stores", "allowance_total", "stock_value"):
        assert k in d["cards"], f"missing card {k}"
    assert "allowance_by_country" in d
    assert "recent_allocations" in d


# ── Settings ──────────────────────────────────────────────
def test_settings_get_and_put(h):
    r = requests.get(f"{API}/settings", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    s = r.json()
    orig = s.get("default_percentage")
    assert orig is not None

    r2 = requests.put(f"{API}/settings", headers=h, json={"default_percentage": 3.5}, timeout=30)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("default_percentage") == 3.5

    # revert
    requests.put(f"{API}/settings", headers=h, json={"default_percentage": orig}, timeout=30)


# ── Dealers ───────────────────────────────────────────────
def test_dealer_create_get_and_dedup(h):
    name = "TEST_DealerA_Jan26"
    payload = {"name": name, "country": "United Kingdom"}
    r = requests.post(f"{API}/dealers", headers=h, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d1 = r.json()
    assert d1["name"] == name
    dealer_id = d1["id"]

    # dedup — same name should return existing (no new id)
    r2 = requests.post(f"{API}/dealers", headers=h, json=payload, timeout=30)
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == dealer_id, "Duplicate dealer not deduped"

    # get detail with rollup
    r3 = requests.get(f"{API}/dealers/{dealer_id}", headers=h, timeout=30)
    assert r3.status_code == 200, r3.text
    detail = r3.json()
    assert "rollup" in detail
    for k in ("allowance_total", "approved_value", "stock_value"):
        assert k in detail["rollup"], f"missing rollup key {k}"
    return dealer_id


@pytest.fixture(scope="module")
def dealer_id(h):
    r = requests.post(f"{API}/dealers", headers=h,
                      json={"name": "TEST_DealerFlow_Jan26", "country": "Germany"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ── Orders + allowance calc ───────────────────────────────
def test_order_import_allowance_and_dedup(h, dealer_id):
    payload = {
        "dealer_id": dealer_id,
        "order_reference": "TEST-ORD-JAN26-001",
        "order_value": 100000,
        "spare_parts_percentage": 3,
    }
    r = requests.post(f"{API}/orders", headers=h, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["allowance"] == 3000.0, f"expected allowance 3000.0 got {o['allowance']}"
    assert o["order_value"] == 100000
    order_id = o["id"]

    # dedup — same order_reference for same dealer
    r2 = requests.post(f"{API}/orders", headers=h, json=payload, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["id"] == order_id, "Duplicate order not deduped"


@pytest.fixture(scope="module")
def order_id(h, dealer_id):
    r = requests.post(f"{API}/orders", headers=h, json={
        "dealer_id": dealer_id, "order_reference": "TEST-ORD-JAN26-FLOW",
        "order_value": 50000, "spare_parts_percentage": 4,
    }, timeout=30)
    return r.json()["id"]


# ── Allocation lifecycle ──────────────────────────────────
def test_allocation_full_lifecycle(h, dealer_id, order_id):
    # create draft
    payload = {
        "dealer_id": dealer_id,
        "order_id": order_id,
        "items": [
            {"part_sku": "TESTPART-A", "part_name": "Belt", "quantity": 2, "unit_value": 100},
            {"part_sku": "TESTPART-B", "part_name": "Motor", "quantity": 1, "unit_value": 500},
        ],
    }
    r = requests.post(f"{API}/allocations", headers=h, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["status"] == "draft"
    assert a["recommended_value"] == 700.0
    aid = a["id"]

    # submit
    r = requests.post(f"{API}/allocations/{aid}/submit", headers=h, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "awaiting_approval", r.text

    # approve
    r = requests.post(f"{API}/allocations/{aid}/approve", headers=h, json={"reason": "test"}, timeout=30)
    assert r.status_code == 200, r.text
    ap = r.json()
    assert ap["status"] == "approved"
    assert ap["approved_value"] == 700.0

    # dispatch (auto-creates Main Dealer Store if none)
    r = requests.post(f"{API}/allocations/{aid}/dispatch", headers=h, json={}, timeout=30)
    assert r.status_code == 200, r.text
    disp = r.json()
    assert disp["status"] == "dispatched"
    assert disp.get("store_id")

    # receive
    r = requests.post(f"{API}/allocations/{aid}/receive", headers=h, json={}, timeout=30)
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["status"] == "completed"

    # movements check
    r = requests.get(f"{API}/movements", headers=h, params={"dealer_id": dealer_id}, timeout=30)
    assert r.status_code == 200
    mvs = r.json()["movements"]
    types = {m["movement_type"] for m in mvs if m.get("allocation_id") == aid}
    assert "dispatched_to_dealer" in types
    assert "received_by_dealer" in types

    # store stock reflects received qty
    r = requests.get(f"{API}/stores/{disp['store_id']}/stock", headers=h, timeout=30)
    assert r.status_code == 200
    stock = r.json()["stock"]
    part_a = next((s for s in stock if s["part_sku"] == "TESTPART-A"), None)
    assert part_a and part_a["qty_on_hand"] >= 2, f"expected qty_on_hand >=2 for TESTPART-A, got {part_a}"


# ── Over-allowance approval ───────────────────────────────
def test_over_allowance_approval(h, dealer_id):
    # small order → allowance small
    r = requests.post(f"{API}/orders", headers=h, json={
        "dealer_id": dealer_id, "order_reference": "TEST-ORD-JAN26-OVER",
        "order_value": 1000, "spare_parts_percentage": 1,  # allowance = 10
    }, timeout=30)
    assert r.status_code == 200
    small_order = r.json()
    assert small_order["allowance"] == 10.0

    # allocation value 500 > allowance 10 → over_allowance=true
    r = requests.post(f"{API}/allocations", headers=h, json={
        "dealer_id": dealer_id, "order_id": small_order["id"],
        "items": [{"part_sku": "TESTPART-OVER", "part_name": "X", "quantity": 5, "unit_value": 100}],
    }, timeout=30)
    assert r.status_code == 200
    alloc = r.json()
    assert alloc["over_allowance"] is True

    # submit + approve as owner (manager) should succeed
    aid = alloc["id"]
    requests.post(f"{API}/allocations/{aid}/submit", headers=h, timeout=30)
    r = requests.post(f"{API}/allocations/{aid}/approve", headers=h, json={"reason": "override"}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
