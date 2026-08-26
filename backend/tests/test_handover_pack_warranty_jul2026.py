"""CRM · Equipment Sales — Warranty tiers + branded Handover Pack PDF.

Covers:
  GET  /api/crm/v2/warranty-tiers
  POST /api/crm/v2/quotes                       (sale line w/ warranty_tier)
  GET  /api/crm/v2/quotes/{id}/fulfilment       (warranty_tier preserved)
  POST /api/crm/v2/quotes/{id}/purchase-orders  (raise PO)
  POST /api/crm/v2/quotes/{id}/purchase-orders/{po}/receive  (GRN stamps warranty)
  GET  /api/crm/v2/quotes/{id}/handover/pack    (PDF 200 / 400 when no equipment)
"""
import os
from datetime import datetime

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
SUPPLIER = "TEST_Pulse Supplier"
NOTE = "TEST_handover_pack_warranty_jul2026"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/crm/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"CRM login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token: {r.text[:300]}"
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
        sdb.issues.delete_many({"quote_id": qid})
        sdb.svc_cases.delete_many({"quote_id": qid})
    mc.close()


def _make_quote(client, created_quote_ids, tier="extended_3yr", qty=2):
    payload = {
        "notes": NOTE, "vat_rate": 0,
        "company_name": "TEST_Handover Pack Co",
        "lines": [{
            "description": "TEST_Treadmill X1", "line_type": "sale", "quantity": qty,
            "unit_price": 2000, "cost_price": 1200, "manufacturer": "Pulse",
            "model": "TX-1", "discount": 0, "warranty_tier": tier,
        }],
    }
    r = client.post(f"{V2}/quotes", json=payload, timeout=60)
    assert r.status_code in (200, 201), f"create quote {r.status_code}: {r.text[:400]}"
    q = r.json().get("quote") or r.json()
    created_quote_ids.append(q["id"])
    return q


# ── Warranty tiers endpoint ────────────────────────────────────────
class TestWarrantyTiers:
    def test_tiers_endpoint(self, client):
        r = client.get(f"{V2}/warranty-tiers", timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        tiers = r.json().get("tiers")
        assert isinstance(tiers, list) and len(tiers) == 3, tiers
        codes = [t["code"] for t in tiers]
        assert codes == ["standard", "extended_3yr", "premium_5yr"], codes
        months = {t["code"]: t["months"] for t in tiers}
        assert months == {"standard": 12, "extended_3yr": 36, "premium_5yr": 60}
        for t in tiers:
            assert t.get("label"), t
            assert t.get("summary"), t

    def test_tiers_requires_auth(self):
        r = requests.get(f"{V2}/warranty-tiers", timeout=60)
        assert r.status_code in (401, 403), f"unauthenticated got {r.status_code}"


# ── Warranty flows through quote → fulfilment → GRN → equipment ────
class TestWarrantyThroughFulfilment:
    def test_quote_line_preserves_warranty_tier(self, client, created_quote_ids):
        q = _make_quote(client, created_quote_ids)
        r = client.get(f"{V2}/quotes/{q['id']}/fulfilment", timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        lines = data.get("procurable_lines") or []
        assert lines, f"no procurable lines: {data}"
        line = lines[0]
        assert line.get("warranty_tier") == "extended_3yr", line
        assert data["summary"]["equipment_units_expected"] == 2, data["summary"]

    def test_grn_stamps_warranty_on_equipment(self, client, created_quote_ids):
        q = _make_quote(client, created_quote_ids)
        qid = q["id"]

        ful = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
        line_id = ful["procurable_lines"][0]["line_id"]

        r = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                        json={"supplier_name": SUPPLIER}, timeout=60)
        assert r.status_code in (200, 201), f"raise PO {r.status_code}: {r.text[:400]}"
        po = r.json().get("purchase_order") or r.json().get("po") or r.json()
        po_id = po.get("id") or (r.json().get("purchase_orders") or [{}])[0].get("id")
        assert po_id, f"no PO id: {r.text[:400]}"

        serials = ["TEST-SER-A1", "TEST-SER-A2"]
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/receive",
                        json={"items": [{"line_id": line_id, "received_qty": 2,
                                         "serials": serials}]}, timeout=90)
        assert r.status_code == 200, f"receive {r.status_code}: {r.text[:400]}"

        ful = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
        assert ful["summary"]["equipment_created"] == 2, ful["summary"]
        eq = ful.get("equipment") or []
        assert len(eq) == 2, eq
        # verify warranty stamped via handover pack path data (equipment docs)
        from pymongo import MongoClient
        be = dotenv_values("/app/backend/.env")
        mc = MongoClient(be["MONGO_URL"])
        rows = list(mc[be["DB_NAME"]].equipment.find({"quote_id": qid}, {"_id": 0}))
        mc.close()
        assert len(rows) == 2, rows
        for row in rows:
            assert row.get("warranty_tier") == "extended_3yr", row
            assert row.get("warranty_months") == 36, row
            assert row.get("warranty_start"), row
            expiry = row.get("warranty_expiry")
            assert expiry, row
            start = datetime.strptime(str(row["warranty_start"])[:10], "%Y-%m-%d")
            end = datetime.strptime(str(expiry)[:10], "%Y-%m-%d")
            days = (end - start).days
            assert 1080 <= days <= 1115, f"expiry not ~3y: {days} days ({start}->{end})"
            assert row.get("serial_number") in serials, row

    def test_standard_tier_defaults_12_months(self, client, created_quote_ids):
        q = _make_quote(client, created_quote_ids, tier="standard", qty=1)
        qid = q["id"]
        ful = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
        line_id = ful["procurable_lines"][0]["line_id"]
        po = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                         json={"supplier_name": SUPPLIER}, timeout=60).json()
        po_id = (po.get("purchase_order") or po).get("id")
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/receive",
                        json={"items": [{"line_id": line_id, "received_qty": 1,
                                         "serials": ["TEST-SER-B1"]}]}, timeout=90)
        assert r.status_code == 200, r.text[:400]
        from pymongo import MongoClient
        be = dotenv_values("/app/backend/.env")
        mc = MongoClient(be["MONGO_URL"])
        row = mc[be["DB_NAME"]].equipment.find_one({"quote_id": qid}, {"_id": 0})
        mc.close()
        assert row and row.get("warranty_months") == 12, row


# ── Handover pack PDF ──────────────────────────────────────────────
class TestHandoverPack:
    def test_pack_400_when_no_equipment(self, client, created_quote_ids):
        q = _make_quote(client, created_quote_ids, qty=1)
        r = client.get(f"{V2}/quotes/{q['id']}/handover/pack", timeout=90)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
        assert "equipment" in r.text.lower()

    def test_pack_pdf_after_grn(self, client, created_quote_ids):
        q = _make_quote(client, created_quote_ids, tier="premium_5yr", qty=1)
        qid = q["id"]
        ful = client.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
        line_id = ful["procurable_lines"][0]["line_id"]
        po = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                         json={"supplier_name": SUPPLIER}, timeout=60).json()
        po_id = (po.get("purchase_order") or po).get("id")
        rr = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/receive",
                         json={"items": [{"line_id": line_id, "received_qty": 1,
                                          "serials": ["TEST-SER-C1"]}]}, timeout=90)
        assert rr.status_code == 200, rr.text[:400]

        r = client.get(f"{V2}/quotes/{qid}/handover/pack", timeout=120)
        assert r.status_code == 200, f"pack {r.status_code}: {r.text[:400]}"
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        assert r.content[:4] == b"%PDF", r.content[:20]
        assert len(r.content) > 1000, len(r.content)
        assert "attachment" in (r.headers.get("content-disposition") or "")

    def test_pack_404_unknown_quote(self, client):
        r = client.get(f"{V2}/quotes/does-not-exist-xyz/handover/pack", timeout=60)
        assert r.status_code == 404, f"{r.status_code}: {r.text[:200]}"

    def test_pack_requires_auth(self, client, created_quote_ids):
        q = _make_quote(client, created_quote_ids, qty=1)
        r = requests.get(f"{V2}/quotes/{q['id']}/handover/pack", timeout=60)
        assert r.status_code in (401, 403), r.status_code
