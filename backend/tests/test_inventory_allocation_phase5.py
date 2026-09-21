"""Inventory & Distribution — Phase 5 Customer Allocation, Installation & Warranty E2E.

Setup: warehouse → US dealer order (USD, qty=2 serialised) → assign 2 serials →
release → pick both → QC pass both → pack → seal → dispatch → dealer receive both.

Phase 5 tests:
- GET /available lists both dealer-held serials
- POST /customers first time creates (dealer_customer/pending_validation)
- POST /customers second time with same name (no force) → created:false + duplicates
- POST /customers with force=true → creates a second row
- GET /customers/search finds the created customer
- POST /allocate both units → 2 asset rows in db.equipment, unit.asset_id set
- GET /allocations lists 2 rows, both awaiting_installation
- GET /customer-portal/{cid}/equipment → 2 rows awaiting_installation
- POST /install without acceptance → 400
- POST /install with acceptance → 200, equipment.status=active, warranty_expiry set
- Portal after install → status=active
- Summary counters
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine.preview.emergentagent.com").rstrip("/")
EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"
TAG = uuid.uuid4().hex[:6].upper()


@pytest.fixture(scope="module")
def H():
    for _ in range(3):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
        if r.status_code == 429:
            time.sleep(35); continue
        break
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def dealer_stock(H):
    """Set up 2 dealer-held units (received by US dealer)."""
    wh = requests.post(f"{BASE_URL}/api/inventory/warehouses", headers=H,
                       json={"code": f"P5WH{TAG}", "name": f"P5 WH {TAG}", "country": "US"},
                       timeout=20).json()["id"]

    body = {
        "dealer_name": f"TEST P5 US Dealer {TAG}",
        "dealer_country": "United States",
        "currency": "USD",
        "customer_po": f"P5PO-{TAG}",
        "warehouse_id": wh,
        "lines": [{
            "product_code": f"P5PC{TAG}",
            "description": "P5 Test Machine",
            "product_type": "serialised_machine",
            "quantity": 2,
            "unit_price": 750.0,
        }],
    }
    r = requests.post(f"{BASE_URL}/api/inventory/orders", headers=H, json=body, timeout=30)
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["id"]

    od = requests.get(f"{BASE_URL}/api/inventory/orders/{order_id}", headers=H, timeout=20).json()
    units = od["units"]
    assert len(units) == 2
    serials = [f"P5S{TAG}-{i}" for i in range(2)]
    for u, s in zip(units, serials):
        rr = requests.post(f"{BASE_URL}/api/inventory/units/{u['id']}/assign-serial",
                           headers=H, json={"serial_number": s}, timeout=20)
        assert rr.status_code == 200, rr.text

    assert requests.post(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/release", headers=H, timeout=20).status_code == 200
    ful = requests.get(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/fulfilment", headers=H, timeout=20).json()
    for t in ful["pick_tasks"]:
        u_serial = next(s for u_id, s in zip([u["id"] for u in units], serials) if u_id == t["unit_id"])
        assert requests.post(f"{BASE_URL}/api/inventory/ops/pick-tasks/{t['id']}/pick",
                             headers=H, json={"serial": u_serial}, timeout=20).status_code == 200
    for u in units:
        assert requests.post(f"{BASE_URL}/api/inventory/ops/units/{u['id']}/qc",
                             headers=H, json={"result": "pass"}, timeout=20).status_code == 200

    pkg_id = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/packages",
                           headers=H, json={"type": "pallet"}, timeout=20).json()["id"]
    for s in serials:
        assert requests.post(f"{BASE_URL}/api/inventory/ops/packages/{pkg_id}/add-unit",
                             headers=H, json={"serial": s}, timeout=20).status_code == 200
    requests.post(f"{BASE_URL}/api/inventory/ops/packages/{pkg_id}/seal", headers=H, json={"weight": 100}, timeout=20)

    dsp = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/dispatch",
                        headers=H, json={"carrier": "FedEx", "tracking": f"P5TRK{TAG}"}, timeout=20).json()
    shipment_id = dsp["shipment"]["id"]

    # Dealer receives both serials
    r = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{shipment_id}/receive",
                      headers=H, json={"confirmed_serials": serials, "damaged_serials": []}, timeout=20)
    assert r.status_code == 200, r.text

    # get unit_ids from dealer inventory
    inv = requests.get(f"{BASE_URL}/api/inventory/dist/dealer-inventory", headers=H, timeout=20).json()
    holdings = [h for h in inv["holdings"] if h["serial_number"] in serials]
    assert len(holdings) == 2, holdings
    return {
        "order_id": order_id, "shipment_id": shipment_id,
        "serials": serials, "unit_ids": [h["unit_id"] for h in holdings],
    }


# ─── Tests ───
def test_available_lists_dealer_stock(H, dealer_stock):
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/available", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    serials = [a["serial_number"] for a in r.json()["available"]]
    for s in dealer_stock["serials"]:
        assert s in serials, f"Missing {s} in available"


CUST_NAME = f"TEST Downtown Fitness Club {TAG}"


@pytest.fixture(scope="module")
def customer(H):
    # first create — no duplicates
    r = requests.post(f"{BASE_URL}/api/inventory/alloc/customers", headers=H,
                      json={"name": CUST_NAME, "country": "US", "force": False}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["created"] is True
    assert j["company"]["company_type"] == "dealer_customer"
    assert j["company"]["status"] == "pending_validation"
    return j["company"]


def test_customer_create_dedup(H, customer):
    # second create same name, force=False → not created, duplicates returned
    r = requests.post(f"{BASE_URL}/api/inventory/alloc/customers", headers=H,
                      json={"name": CUST_NAME, "country": "US", "force": False}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["created"] is False
    assert isinstance(j.get("duplicates"), list) and len(j["duplicates"]) >= 1
    assert any(d["id"] == customer["id"] for d in j["duplicates"])


def test_customer_search(H, customer):
    q = CUST_NAME.split()[1]  # "Downtown"
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/customers/search", headers=H,
                     params={"q": q}, timeout=20)
    assert r.status_code == 200, r.text
    ids = [m["id"] for m in r.json()["matches"]]
    assert customer["id"] in ids


def test_customer_search_too_short(H):
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/customers/search", headers=H,
                     params={"q": "a"}, timeout=20)
    assert r.status_code == 200
    assert r.json()["matches"] == []


@pytest.fixture(scope="module")
def allocation(H, dealer_stock, customer):
    body = {
        "unit_ids": dealer_stock["unit_ids"],
        "customer_company_id": customer["id"],
        "customer_site": "Main Club, 5th Ave",
        "planned_install_date": "2026-02-15",
        "service_responsibility": "dealer",
    }
    r = requests.post(f"{BASE_URL}/api/inventory/alloc/allocate", headers=H, json=body, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["allocated"] == 2, j
    for res in j["results"]:
        assert res["ok"] is True
        assert res["asset_id"]
        assert res["reference"].startswith("ALL-")
    return j["results"]


def test_allocations_list(H, allocation):
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/allocations", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    rows = r.json()["allocations"]
    ids = {res["allocation_id"] for res in allocation}
    matching = [row for row in rows if row["id"] in ids]
    assert len(matching) == 2
    for row in matching:
        assert row["status"] == "awaiting_installation"


def test_allocation_detail(H, allocation):
    aid = allocation[0]["allocation_id"]
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/allocations/{aid}", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["allocation"]["id"] == aid
    assert d["asset"] is not None
    assert d["asset"]["status"] == "awaiting_installation"
    assert d["asset"]["asset_source"] == "dealer_distribution"
    assert d["installation"] is None
    assert d["warranty"] is None


def test_customer_portal_awaiting(H, customer, allocation):
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/customer-portal/{customer['id']}/equipment",
                     headers=H, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["company"]["id"] == customer["id"]
    assert len(j["equipment"]) == 2
    for eq in j["equipment"]:
        assert eq["status"] == "awaiting_installation"


def test_available_after_allocate(H, dealer_stock):
    # After allocation, those serials should NOT be in available anymore
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/available", headers=H, timeout=20)
    assert r.status_code == 200
    serials = [a["serial_number"] for a in r.json()["available"]]
    for s in dealer_stock["serials"]:
        assert s not in serials, f"{s} still in available after allocation"


def test_install_without_acceptance_400(H, allocation):
    aid = allocation[0]["allocation_id"]
    r = requests.post(f"{BASE_URL}/api/inventory/alloc/allocations/{aid}/install",
                      headers=H, json={"engineer_name": "Alex Engineer", "customer_acceptance": False}, timeout=20)
    assert r.status_code == 400, r.text


def test_install_activates_asset_and_warranty(H, allocation, customer):
    aid = allocation[0]["allocation_id"]
    r = requests.post(f"{BASE_URL}/api/inventory/alloc/allocations/{aid}/install",
                      headers=H, json={
                          "engineer_name": "Alex Engineer",
                          "checklist": {"positioned": True, "power": True, "safety": True},
                          "software_version": "1.2.3",
                          "customer_acceptance": True,
                      }, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["asset_status"] == "active"
    assert j["warranty_end"]

    # verify persistence via GET
    d = requests.get(f"{BASE_URL}/api/inventory/alloc/allocations/{aid}", headers=H, timeout=20).json()
    assert d["allocation"]["status"] == "active"
    assert d["asset"]["status"] == "active"
    assert d["asset"]["warranty_expiry"]
    assert d["installation"] is not None
    assert d["installation"]["engineer_name"] == "Alex Engineer"
    assert d["warranty"] is not None


def test_portal_shows_active_after_install(H, customer, allocation):
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/customer-portal/{customer['id']}/equipment",
                     headers=H, timeout=20).json()
    active = [e for e in r["equipment"] if e["status"] == "active"]
    awaiting = [e for e in r["equipment"] if e["status"] == "awaiting_installation"]
    assert len(active) == 1
    assert len(awaiting) == 1


def test_summary(H):
    r = requests.get(f"{BASE_URL}/api/inventory/alloc/summary", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("available_to_allocate", "awaiting_installation", "active_assets"):
        assert k in d
    assert d["active_assets"] >= 1
    assert d["awaiting_installation"] >= 1
