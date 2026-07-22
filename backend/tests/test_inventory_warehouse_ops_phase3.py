"""Inventory & Distribution — Phase 3 Warehouse Operations backend E2E.

Flow: create warehouse → order (2 serialised units) → assign serials → release
→ pick (wrong serial 409, correct ok) → QC (pass + quarantine) → package
(picked ok, quarantined 409) → seal → dispatch → queues.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://platform-doctor.preview.emergentagent.com").rstrip("/")
EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"
TAG = uuid.uuid4().hex[:6].upper()


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code == 429:
        time.sleep(35)
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def ctx(H):
    # warehouse
    code = f"P3WH{TAG}"
    r = requests.post(f"{BASE_URL}/api/inventory/warehouses", headers=H,
                      json={"code": code, "name": f"P3 WH {TAG}", "country": "GB"}, timeout=20)
    assert r.status_code == 200, r.text
    wh_id = r.json()["id"]

    # order (1 serialised line, qty=2)
    product_code = f"P3PC{TAG}"
    body = {
        "dealer_name": f"TEST P3 Dealer {TAG}",
        "dealer_country": "GB",
        "currency": "GBP",
        "customer_po": f"P3PO-{TAG}",
        "warehouse_id": wh_id,
        "lines": [{
            "product_code": product_code,
            "description": "P3 Test Machine",
            "product_type": "serialised_machine",
            "quantity": 2,
            "unit_price": 100.0,
        }],
    }
    r = requests.post(f"{BASE_URL}/api/inventory/orders", headers=H, json=body, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    order_id = data["order"]["id"]
    assert data["provisional_units"] == 2

    # get units and assign serials
    od = requests.get(f"{BASE_URL}/api/inventory/orders/{order_id}", headers=H, timeout=20).json()
    units = od["units"]
    assert len(units) == 2
    ser_a = f"SER-A-{TAG}"
    ser_b = f"SER-B-{TAG}"
    r1 = requests.post(f"{BASE_URL}/api/inventory/units/{units[0]['id']}/assign-serial",
                       headers=H, json={"serial_number": ser_a}, timeout=20)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{BASE_URL}/api/inventory/units/{units[1]['id']}/assign-serial",
                       headers=H, json={"serial_number": ser_b}, timeout=20)
    assert r2.status_code == 200, r2.text

    return {"wh_id": wh_id, "order_id": order_id, "unit_a": units[0]["id"], "unit_b": units[1]["id"],
            "ser_a": ser_a, "ser_b": ser_b}


def test_release(H, ctx):
    r = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{ctx['order_id']}/release", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["pick_tasks"] == 2
    assert r.json()["status"] == "released_to_warehouse"


def test_release_idempotent_rejected(H, ctx):
    r = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{ctx['order_id']}/release", headers=H, timeout=20)
    assert r.status_code == 400


def test_pick_wrong_serial_rejected(H, ctx):
    ful = requests.get(f"{BASE_URL}/api/inventory/ops/orders/{ctx['order_id']}/fulfilment", headers=H, timeout=20).json()
    task_a = next(t for t in ful["pick_tasks"] if t["unit_id"] == ctx["unit_a"])
    r = requests.post(f"{BASE_URL}/api/inventory/ops/pick-tasks/{task_a['id']}/pick",
                      headers=H, json={"serial": "NOPE"}, timeout=20)
    assert r.status_code == 409, r.text
    detail = r.json().get("detail", {})
    assert (isinstance(detail, dict) and detail.get("error") == "wrong_serial"), r.text


def test_pick_correct(H, ctx):
    ful = requests.get(f"{BASE_URL}/api/inventory/ops/orders/{ctx['order_id']}/fulfilment", headers=H, timeout=20).json()
    task_a = next(t for t in ful["pick_tasks"] if t["unit_id"] == ctx["unit_a"])
    task_b = next(t for t in ful["pick_tasks"] if t["unit_id"] == ctx["unit_b"])
    r1 = requests.post(f"{BASE_URL}/api/inventory/ops/pick-tasks/{task_a['id']}/pick",
                       headers=H, json={"serial": ctx["ser_a"]}, timeout=20)
    assert r1.status_code == 200 and r1.json()["ok"]
    r2 = requests.post(f"{BASE_URL}/api/inventory/ops/pick-tasks/{task_b['id']}/pick",
                       headers=H, json={"serial": ctx["ser_b"]}, timeout=20)
    assert r2.status_code == 200 and r2.json()["order_fully_picked"] is True


def test_qc_pass_and_quarantine(H, ctx):
    # unit A pass
    r1 = requests.post(f"{BASE_URL}/api/inventory/ops/units/{ctx['unit_a']}/qc",
                       headers=H, json={"result": "pass"}, timeout=20)
    assert r1.status_code == 200 and r1.json()["passed"] is True
    # unit B quarantine
    r2 = requests.post(f"{BASE_URL}/api/inventory/ops/units/{ctx['unit_b']}/qc",
                       headers=H, json={"result": "quarantine"}, timeout=20)
    assert r2.status_code == 200 and r2.json()["passed"] is False


def test_pack_and_seal(H, ctx):
    p = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{ctx['order_id']}/packages",
                      headers=H, json={"type": "pallet"}, timeout=20)
    assert p.status_code == 200, p.text
    pkg_id = p.json()["id"]
    ctx["pkg_id"] = pkg_id
    # add picked unit A → ok
    ra = requests.post(f"{BASE_URL}/api/inventory/ops/packages/{pkg_id}/add-unit",
                       headers=H, json={"serial": ctx["ser_a"]}, timeout=20)
    assert ra.status_code == 200, ra.text
    # add quarantined unit B → 409
    rb = requests.post(f"{BASE_URL}/api/inventory/ops/packages/{pkg_id}/add-unit",
                      headers=H, json={"serial": ctx["ser_b"]}, timeout=20)
    assert rb.status_code == 409, rb.text
    detail = rb.json().get("detail", {})
    assert isinstance(detail, dict) and detail.get("error") == "quarantined"
    # seal
    s = requests.post(f"{BASE_URL}/api/inventory/ops/packages/{pkg_id}/seal",
                     headers=H, json={"weight": 55.5}, timeout=20)
    assert s.status_code == 200


def test_dispatch(H, ctx):
    r = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{ctx['order_id']}/dispatch",
                     headers=H, json={"carrier": "DHL", "tracking": f"TRK{TAG}"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["units_dispatched"] == 1  # only unit A, not quarantined B
    assert data["order_status"] == "dispatched"
    assert data["shipment"]["reference"].startswith("SHP-")
    assert data["shipment"]["status"] == "in_transit"
    assert data["shipment"]["carrier"] == "DHL"


def test_fulfilment_view(H, ctx):
    r = requests.get(f"{BASE_URL}/api/inventory/ops/orders/{ctx['order_id']}/fulfilment", headers=H, timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d["order"]["status"] == "dispatched"
    assert d["shipment"] is not None
    assert len(d["packages"]) == 1
    assert len(d["units"]) == 2


def test_queues_all_stages(H):
    for stage in ["receiving", "picking", "qc", "packing", "dispatch"]:
        r = requests.get(f"{BASE_URL}/api/inventory/ops/queues/{stage}", headers=H, timeout=20)
        assert r.status_code == 200, f"{stage}: {r.text}"
        assert r.json()["stage"] == stage
        assert "orders" in r.json()


def test_qc_templates(H):
    r = requests.get(f"{BASE_URL}/api/inventory/ops/qc/templates", headers=H, timeout=20)
    assert r.status_code == 200
    assert len(r.json()["templates"]) >= 1
