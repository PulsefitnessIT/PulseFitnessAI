"""Inventory & Distribution — Phase 4 Dealer Distribution backend E2E.

Setup (reuses Phase-3 fulfilment): warehouse → French dealer order (EUR, 1 line qty=3, serialised)
→ assign 3 serials → release → pick all → QC pass all → pack all → seal → dispatch (SHP-*).

Phase 4 tests:
- list & get shipment
- shipment status update
- customs (incoterm, hs, declared value, currency)
- documents: generate packing_list twice (rev1, rev2), delivery_note
- dealer receive: 2 confirmed + 1 damaged → discrepancy_reported / delivery_discrepancy
- unknown serial → 409 serial_not_in_shipment
- dealer inventory: 2 available holdings
- transfer orders: create → approve → dispatch → receive
- summary endpoint
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
    for _ in range(3):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
        if r.status_code == 429:
            time.sleep(35)
            continue
        break
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ─── Setup: full order → dispatch to get an SHP ───
@pytest.fixture(scope="module")
def ship(H):
    # warehouse A
    wh_a = requests.post(f"{BASE_URL}/api/inventory/warehouses", headers=H,
                        json={"code": f"P4WHA{TAG}", "name": f"P4 WHA {TAG}", "country": "GB"},
                        timeout=20).json()["id"]
    # warehouse B (for transfer test)
    wh_b = requests.post(f"{BASE_URL}/api/inventory/warehouses", headers=H,
                        json={"code": f"P4WHB{TAG}", "name": f"P4 WHB {TAG}", "country": "GB"},
                        timeout=20).json()["id"]

    # French dealer order, EUR, qty 3 serialised
    body = {
        "dealer_name": f"TEST P4 FR Dealer {TAG}",
        "dealer_country": "France",
        "currency": "EUR",
        "customer_po": f"P4PO-{TAG}",
        "warehouse_id": wh_a,
        "lines": [{
            "product_code": f"P4PC{TAG}",
            "description": "P4 Test Machine",
            "product_type": "serialised_machine",
            "quantity": 3,
            "unit_price": 500.0,
        }],
    }
    r = requests.post(f"{BASE_URL}/api/inventory/orders", headers=H, json=body, timeout=30)
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["id"]

    # units + serials
    od = requests.get(f"{BASE_URL}/api/inventory/orders/{order_id}", headers=H, timeout=20).json()
    units = od["units"]
    assert len(units) == 3
    serials = [f"P4S{TAG}-{i}" for i in range(3)]
    for u, s in zip(units, serials):
        rr = requests.post(f"{BASE_URL}/api/inventory/units/{u['id']}/assign-serial",
                           headers=H, json={"serial_number": s}, timeout=20)
        assert rr.status_code == 200, rr.text

    # release → pick → QC → pack → seal → dispatch
    rr = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/release", headers=H, timeout=20)
    assert rr.status_code == 200, rr.text

    ful = requests.get(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/fulfilment", headers=H, timeout=20).json()
    for t in ful["pick_tasks"]:
        u_serial = next(s for u_id, s in zip([u["id"] for u in units], serials) if u_id == t["unit_id"])
        rr = requests.post(f"{BASE_URL}/api/inventory/ops/pick-tasks/{t['id']}/pick",
                          headers=H, json={"serial": u_serial}, timeout=20)
        assert rr.status_code == 200, rr.text

    for u in units:
        rr = requests.post(f"{BASE_URL}/api/inventory/ops/units/{u['id']}/qc",
                          headers=H, json={"result": "pass"}, timeout=20)
        assert rr.status_code == 200

    pkg = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/packages",
                       headers=H, json={"type": "pallet"}, timeout=20).json()
    pkg_id = pkg["id"]
    for s in serials:
        rr = requests.post(f"{BASE_URL}/api/inventory/ops/packages/{pkg_id}/add-unit",
                          headers=H, json={"serial": s}, timeout=20)
        assert rr.status_code == 200, rr.text
    requests.post(f"{BASE_URL}/api/inventory/ops/packages/{pkg_id}/seal", headers=H, json={"weight": 100}, timeout=20)

    dsp = requests.post(f"{BASE_URL}/api/inventory/ops/orders/{order_id}/dispatch",
                       headers=H, json={"carrier": "DHL", "tracking": f"P4TRK{TAG}"}, timeout=20).json()
    shipment_id = dsp["shipment"]["id"]
    shipment_ref = dsp["shipment"]["reference"]

    return {
        "wh_a": wh_a, "wh_b": wh_b, "order_id": order_id,
        "shipment_id": shipment_id, "shipment_ref": shipment_ref,
        "unit_ids": [u["id"] for u in units], "serials": serials,
    }


# ─── Phase 4 tests ───
def test_list_shipments(H, ship):
    r = requests.get(f"{BASE_URL}/api/inventory/dist/shipments", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    refs = [s["reference"] for s in r.json()["shipments"]]
    assert ship["shipment_ref"] in refs


def test_get_shipment_detail(H, ship):
    r = requests.get(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["shipment"]["reference"] == ship["shipment_ref"]
    assert len(d["units"]) == 3
    assert d["receipt"] is None
    assert d["documents"] == []


def test_shipment_status_update(H, ship):
    r = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/status",
                     headers=H, json={"status": "in_transit"}, timeout=20)
    assert r.status_code == 200 and r.json()["status"] == "in_transit"
    # persistence
    d = requests.get(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}", headers=H, timeout=20).json()
    assert d["shipment"]["status"] == "in_transit"


def test_shipment_status_invalid(H, ship):
    r = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/status",
                     headers=H, json={"status": "BOGUS"}, timeout=20)
    assert r.status_code == 400


def test_customs_set(H, ship):
    body = {"incoterm": "DAP", "hs_code": "9506.91", "declared_value": 1500, "currency": "EUR",
            "country_of_origin": "GB"}
    r = requests.put(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/customs",
                    headers=H, json=body, timeout=20)
    assert r.status_code == 200, r.text
    c = r.json()["customs"]
    assert c["incoterm"] == "DAP"
    assert c["currency"] == "EUR"
    # persistence
    d = requests.get(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}", headers=H, timeout=20).json()
    assert d["shipment"]["customs"]["hs_code"] == "9506.91"


def test_documents_versioning(H, ship):
    # rev 1
    r1 = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/documents",
                      headers=H, json={"type": "packing_list"}, timeout=20)
    assert r1.status_code == 200, r1.text
    assert r1.json()["document"]["revision"] == 1
    assert r1.json()["document"]["currency"] == "EUR"
    # rev 2
    r2 = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/documents",
                      headers=H, json={"type": "packing_list"}, timeout=20)
    assert r2.status_code == 200 and r2.json()["document"]["revision"] == 2
    # delivery note (rev 1)
    r3 = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/documents",
                      headers=H, json={"type": "delivery_note"}, timeout=20)
    assert r3.status_code == 200 and r3.json()["document"]["revision"] == 1
    # list
    dl = requests.get(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/documents", headers=H, timeout=20)
    assert dl.status_code == 200
    docs = dl.json()["documents"]
    assert len(docs) == 3
    packing_docs = [d for d in docs if d["type"] == "packing_list"]
    assert sorted([d["revision"] for d in packing_docs]) == [1, 2]


def test_document_unknown_type(H, ship):
    r = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/documents",
                    headers=H, json={"type": "not_a_type"}, timeout=20)
    assert r.status_code == 400


def test_receive_unknown_serial_409(H, ship):
    r = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/receive",
                    headers=H, json={"confirmed_serials": ["DEFINITELY-NOT-IN-SHIP"]}, timeout=20)
    assert r.status_code == 409, r.text
    detail = r.json().get("detail", {})
    assert isinstance(detail, dict) and detail.get("error") == "serial_not_in_shipment"


def test_dealer_receive_with_discrepancy(H, ship):
    # 2 confirmed, 1 damaged
    body = {
        "confirmed_serials": ship["serials"][:2],
        "damaged_serials": [ship["serials"][2]],
    }
    r = requests.post(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}/receive",
                     headers=H, json=body, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["confirmed"] == 2
    assert d["damaged"] == 1
    assert d["receipt_status"] == "discrepancy_reported"
    assert d["shipment_status"] == "delivery_discrepancy"

    # persistence: receipt & shipment status
    sd = requests.get(f"{BASE_URL}/api/inventory/dist/shipments/{ship['shipment_id']}", headers=H, timeout=20).json()
    assert sd["shipment"]["status"] == "delivery_discrepancy"
    assert sd["receipt"] is not None
    assert set(sd["receipt"]["confirmed"]) == set(ship["serials"][:2])
    assert sd["receipt"]["damaged"] == [ship["serials"][2]]


def test_dealer_inventory_holdings(H, ship):
    r = requests.get(f"{BASE_URL}/api/inventory/dist/dealer-inventory", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    serials_held = [h["serial_number"] for h in r.json()["holdings"]]
    # 2 confirmed serials should appear
    for s in ship["serials"][:2]:
        assert s in serials_held, f"Missing {s} in dealer inventory"
    # damaged must NOT appear
    assert ship["serials"][2] not in serials_held


def test_transfer_flow(H, ship):
    # create
    r = requests.post(f"{BASE_URL}/api/inventory/dist/transfers", headers=H,
                    json={"source_warehouse_id": ship["wh_a"], "dest_warehouse_id": ship["wh_b"], "unit_ids": []},
                    timeout=20)
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["status"] == "awaiting_approval"
    assert t["reference"].startswith("TRF-")
    tid = t["id"]

    # approve → dispatch → receive
    for action, expected in [("approve", "approved"), ("dispatch", "in_transit"), ("receive", "received")]:
        rr = requests.post(f"{BASE_URL}/api/inventory/dist/transfers/{tid}/{action}", headers=H, timeout=20)
        assert rr.status_code == 200, rr.text
        assert rr.json()["status"] == expected

    # persistence
    ls = requests.get(f"{BASE_URL}/api/inventory/dist/transfers", headers=H, timeout=20).json()
    row = next(x for x in ls["transfers"] if x["id"] == tid)
    assert row["status"] == "received"


def test_transfer_same_source_dest_400(H, ship):
    r = requests.post(f"{BASE_URL}/api/inventory/dist/transfers", headers=H,
                    json={"source_warehouse_id": ship["wh_a"], "dest_warehouse_id": ship["wh_a"], "unit_ids": []},
                    timeout=20)
    assert r.status_code == 400


def test_summary(H, ship):
    r = requests.get(f"{BASE_URL}/api/inventory/dist/summary", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("shipments_in_transit", "shipments_delivered", "delivery_discrepancies",
              "dealer_held_units", "open_transfers"):
        assert k in d
    assert d["delivery_discrepancies"] >= 1
    assert d["dealer_held_units"] >= 2
