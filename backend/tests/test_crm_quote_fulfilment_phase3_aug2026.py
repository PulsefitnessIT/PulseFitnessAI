"""CRM · CPQ v2 Fulfilment (Equipment Sales Phase 3).

Covers routes/crm_quote_fulfilment.py:
  GET  /api/crm/v2/quotes/{id}/fulfilment
  POST /api/crm/v2/quotes/{id}/purchase-orders
  POST /api/crm/v2/quotes/{id}/purchase-orders/{poId}/status
  POST /api/crm/v2/quotes/{id}/purchase-orders/{poId}/receive  (GRN -> db.equipment)
"""
import os

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"
V2 = f"{BASE}/api/crm/v2"
SUPPLIER = "Pulse Fitness Ltd"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/crm/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"CRM login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token in login response: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def app_client():
    """Normal app token (for GET /api/equipment cross-check)."""
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"App login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no app token: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_quote_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(created_quote_ids):
    yield
    from pymongo import MongoClient
    be = dotenv_values("/app/backend/.env")
    mc = MongoClient(be["MONGO_URL"])
    sdb = mc[be["DB_NAME"]]
    for qid in created_quote_ids:
        sdb.crm2_quotes.delete_many({"id": qid})
        sdb.purchase_orders.delete_many({"quote_id": qid})
        sdb.equipment.delete_many({"quote_id": qid})
        sdb.crm2_invoices.delete_many({"quote_id": qid})
    mc.close()


def _new_equipment_quote(client, created_quote_ids):
    r = client.post(f"{V2}/quotes", json={
        "notes": "TEST_fulfilment_phase3",
        "vat_rate": 0,
        "lines": [
            {"description": "TEST_ Treadmill X1", "line_type": "sale", "quantity": 2,
             "unit_price": 10000, "cost_price": 7000, "manufacturer": "Pulse", "model": "X1",
             "discount": 0},
            {"description": "TEST_ Belt", "line_type": "spare_part", "quantity": 5,
             "unit_price": 50, "cost_price": 30, "discount": 0},
            {"description": "TEST_ Old treadmill trade-in", "line_type": "trade_in",
             "quantity": 1, "unit_price": 2000, "discount": 0},
        ],
    }, timeout=60)
    assert r.status_code in (200, 201), f"create quote failed {r.status_code}: {r.text[:500]}"
    q = r.json().get("quote") or r.json()
    qid = q.get("id")
    assert qid
    created_quote_ids.append(qid)
    return qid


# ── Fulfilment read view ─────────────────────────────────────────
class TestFulfilmentLifecycle:
    def test_full_lifecycle(self, client, app_client, created_quote_ids):
        qid = _new_equipment_quote(client, created_quote_ids)

        # 1. GET fulfilment — procurable excludes trade_in
        r = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        types = sorted(l["line_type"] for l in v["procurable_lines"])
        assert types == ["sale", "spare_part"], f"procurable line types {types}"
        assert v["summary"]["equipment_units_expected"] == 2, v["summary"]
        assert v["summary"]["po_count"] == 0
        assert v["summary"]["equipment_created"] == 0
        eq_line = next(l for l in v["procurable_lines"] if l["is_equipment"])
        assert eq_line["cost_price"] == 7000 and eq_line["sell_price"] == 10000
        assert eq_line["manufacturer"] == "Pulse" and eq_line["model"] == "X1"

        # 2. Raise PO — priced at cost
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                        json={"supplier_name": SUPPLIER, "vat_rate": 0}, timeout=60)
        assert r.status_code in (200, 201), r.text[:500]
        body = r.json()
        po = body["purchase_order"]
        assert po["supplier_name"] == SUPPLIER
        assert po["quote_id"] == qid
        assert po["status"] == "draft"
        assert po["subtotal"] == 14150, f"subtotal {po['subtotal']} != 14150"
        prices = {i["name"]: i["unit_price"] for i in po["items"]}
        assert prices["TEST_ Treadmill X1"] == 7000
        assert prices["TEST_ Belt"] == 30
        assert body["summary"]["po_count"] == 1
        po_id = po["id"]
        # NOTE: quote lines are stored WITHOUT a stable id, so the ids returned by
        # GET /fulfilment are regenerated per request. The PO's persisted item ids
        # are the only reliable handles for the GRN.
        po_eq_line_id = next(i["line_id"] for i in po["items"] if i["is_equipment"])
        po_spare_line_id = next(i["line_id"] for i in po["items"] if not i["is_equipment"])

        # 3. Guard — receive more than outstanding => 422
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/receive",
                        json={"items": [{"line_id": po_eq_line_id, "received_qty": 5}]}, timeout=60)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:300]}"

        # 4. GRN — receive 2 equipment units with serials
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/receive",
                        json={"items": [{"line_id": po_eq_line_id, "received_qty": 2,
                                         "serials": ["TEST_SN-AAA", "TEST_SN-BBB"]}]}, timeout=60)
        assert r.status_code == 200, r.text[:500]
        g = r.json()
        assert len(g["created_equipment"]) == 2, g["created_equipment"]
        assert sorted(e["serial_number"] for e in g["created_equipment"]) == ["TEST_SN-AAA", "TEST_SN-BBB"]
        assert g["po_status"] == "part_received", g["po_status"]
        assert g["summary"]["equipment_created"] == 2

        # 5. Second GET confirms persistence
        r = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60)
        assert r.status_code == 200
        v2 = r.json()
        assert v2["summary"]["equipment_created"] == 2
        assert v2["purchase_orders"][0]["status"] == "part_received"
        eq_item = next(i for i in v2["purchase_orders"][0]["items"] if i["is_equipment"])
        assert eq_item["received_qty"] == 2

        # 6. Equipment visible via normal app equipment list, valued at SELL price
        r = app_client.get(f"{BASE}/api/equipment", timeout=60)
        assert r.status_code == 200, r.text[:300]
        payload = r.json()
        rows = payload if isinstance(payload, list) else (payload.get("equipment") or payload.get("items") or [])
        mine = [e for e in rows if e.get("quote_id") == qid]
        assert len(mine) == 2, f"expected 2 equipment rows in /api/equipment, got {len(mine)}"
        for e in mine:
            assert e.get("purchase_cost") == 10000, e.get("purchase_cost")
            assert e.get("supplier") == SUPPLIER
            assert e.get("source") == "deal_grn"
            assert e.get("po_number") == po["po_number"]
            assert "_id" not in e

        # 7. Receive the spare line -> fully received
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/receive",
                        json={"items": [{"line_id": po_spare_line_id, "received_qty": 5}]}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["po_status"] == "received", d["po_status"]
        assert d["summary"]["equipment_created"] == 2, "spare part must NOT create equipment"


# ── Guards ────────────────────────────────────────────────────────
class TestGuards:
    def test_po_requires_supplier_name(self, client, created_quote_ids):
        qid = _new_equipment_quote(client, created_quote_ids)
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders", json={"supplier_name": "  "}, timeout=60)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:300]}"
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders", json={}, timeout=60)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:300]}"

    def test_unknown_quote_404(self, client):
        r = client.get(f"{V2}/quotes/does-not-exist-xyz/fulfilment", timeout=60)
        assert r.status_code == 404, r.status_code

    def test_unknown_po_404(self, client, created_quote_ids):
        qid = _new_equipment_quote(client, created_quote_ids)
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/nope/receive",
                        json={"items": []}, timeout=60)
        assert r.status_code == 404, r.status_code

    def test_unauthenticated_rejected(self, created_quote_ids):
        r = requests.get(f"{V2}/quotes/anything/fulfilment", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_procurable_line_ids_are_stable_across_requests(self, client, created_quote_ids):
        """BUG (iter phase3): quote lines are persisted WITHOUT an `id`, so
        `_procurable_lines` mints a fresh uuid on every call. The UI reads the ids
        from GET /fulfilment and posts them back as `line_ids` → always 400."""
        qid = _new_equipment_quote(client, created_quote_ids)
        a = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
        b = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
        ids_a = [l["line_id"] for l in a["procurable_lines"]]
        ids_b = [l["line_id"] for l in b["procurable_lines"]]
        assert ids_a == ids_b, f"line_ids not stable: {ids_a} vs {ids_b}"

    def test_raise_po_with_line_ids_from_fulfilment_view(self, client, created_quote_ids):
        """Exact request the frontend PO dialog makes."""
        qid = _new_equipment_quote(client, created_quote_ids)
        v = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
        ids = [l["line_id"] for l in v["procurable_lines"]]
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                        json={"supplier_name": SUPPLIER, "line_ids": ids}, timeout=60)
        assert r.status_code in (200, 201), f"frontend PO payload rejected: {r.status_code} {r.text[:200]}"

    def test_grn_with_unknown_line_id_is_rejected(self, client, created_quote_ids):
        """A receipt whose line_id matches nothing silently returns 200 and does
        nothing — should be a 4xx so the operator knows the GRN was not applied."""
        qid = _new_equipment_quote(client, created_quote_ids)
        po = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                         json={"supplier_name": SUPPLIER}, timeout=60).json()["purchase_order"]
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po['id']}/receive",
                        json={"items": [{"line_id": "no-such-line", "received_qty": 1}]}, timeout=60)
        assert r.status_code in (400, 404, 422), f"silent no-op: {r.status_code} {r.text[:200]}"

    def test_po_status_transition_and_validation(self, client, created_quote_ids):
        qid = _new_equipment_quote(client, created_quote_ids)
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders", json={"supplier_name": SUPPLIER}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        po_id = r.json()["purchase_order"]["id"]

        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/status",
                        json={"status": "bogus"}, timeout=60)
        assert r.status_code == 422, r.status_code

        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/status",
                        json={"status": "ordered"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["purchase_orders"][0]["status"] == "ordered"
