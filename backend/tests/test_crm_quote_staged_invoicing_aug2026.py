"""CRM · CPQ v2 staged invoicing (Equipment Sales Phase 2).

Covers routes/crm_quote_invoicing.py:
  GET  /api/crm/v2/quotes/{id}/invoicing
  PUT  /api/crm/v2/quotes/{id}/schedule
  POST /api/crm/v2/quotes/{id}/schedule/auto
  POST /api/crm/v2/quotes/{id}/stages/{sid}/invoice | pay | credit-note
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
        sdb.crm2_invoices.delete_many({"quote_id": qid})
    mc.close()


def _new_quote(client, created_quote_ids, total=10000):
    r = client.post(f"{V2}/quotes", json={
        "notes": "TEST_staged_invoicing",
        "vat_rate": 0,
        "lines": [{"description": "TEST_ Equipment package", "line_type": "sale",
                   "quantity": 1, "unit_price": total, "discount": 0}],
    }, timeout=60)
    assert r.status_code in (200, 201), f"create quote failed {r.status_code}: {r.text[:400]}"
    q = r.json().get("quote") or r.json()
    qid = q.get("id")
    assert qid
    created_quote_ids.append(qid)
    assert q.get("total") == total, f"quote total {q.get('total')} != {total}"
    return qid


# ── Full lifecycle ────────────────────────────────────────────────
class TestStagedInvoicingLifecycle:
    def test_full_lifecycle(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)

        # auto schedule 25/75
        r = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 25, "final_percent": 75}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        assert len(v["stages"]) == 2, v["stages"]
        dep, fin = v["stages"][0], v["stages"][1]
        assert dep["kind"] == "deposit" and dep["amount"] == 2500.0
        assert fin["kind"] == "final" and fin["amount"] == 7500.0
        s = v["summary"]
        assert s["total"] == 10000.0
        assert s["scheduled"] == 10000.0
        assert s["balance"] == 10000.0
        assert s["remaining_to_invoice"] == 10000.0
        assert s["invoiced"] == 0 and s["paid"] == 0

        # GET read-back
        g = client.get(f"{V2}/quotes/{qid}/invoicing", timeout=60)
        assert g.status_code == 200, g.text[:300]
        gv = g.json()
        assert len(gv["stages"]) == 2
        assert gv["invoices"] == []
        assert gv["summary"]["balance"] == 10000.0
        assert all("_id" not in st for st in gv["stages"])

        # invoice the deposit
        r = client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/invoice", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        assert v["invoice"]["number"].startswith("INV-"), v["invoice"]["number"]
        assert v["invoice"]["amount"] == 2500.0
        assert v["invoice"]["doc_type"] == "invoice"
        s = v["summary"]
        assert s["invoiced"] == 2500.0
        assert s["balance"] == 10000.0, "unpaid invoice must not reduce balance"
        assert s["outstanding"] == 2500.0
        assert s["remaining_to_invoice"] == 7500.0
        assert v["stages"][0]["status"] == "invoiced"

        # pay deposit in full
        r = client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/pay", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        s = r.json()["summary"]
        assert s["paid"] == 2500.0
        assert s["balance"] == 7500.0
        assert s["outstanding"] == 0.0
        assert r.json()["stages"][0]["status"] == "paid"

        # invoice the final
        r = client.post(f"{V2}/quotes/{qid}/stages/{fin['id']}/invoice", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        s = r.json()["summary"]
        assert s["invoiced"] == 10000.0
        assert s["remaining_to_invoice"] == 0.0
        assert s["fully_invoiced"] is True
        assert s["balance"] == 7500.0

        # part-pay the final 5000
        r = client.post(f"{V2}/quotes/{qid}/stages/{fin['id']}/pay", json={"amount": 5000}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        s = v["summary"]
        assert s["paid"] == 7500.0
        assert s["outstanding"] == 2500.0
        assert s["balance"] == 2500.0
        assert v["stages"][1]["status"] == "part_paid"

        # credit note 1000 on the final
        r = client.post(f"{V2}/quotes/{qid}/stages/{fin['id']}/credit-note",
                        json={"amount": 1000, "reason": "Goodwill"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        assert v["credit_note"]["number"].startswith("CN-")
        assert v["credit_note"]["doc_type"] == "credit_note"
        assert v["credit_note"]["reason"] == "Goodwill"
        s = v["summary"]
        assert s["credited"] == 1000.0
        assert s["invoiced"] == 9000.0, "net invoiced must be gross minus credits"
        assert s["invoiced_gross"] == 10000.0
        assert s["balance"] == 1500.0
        assert s["outstanding"] == 1500.0

        # persistence via GET
        g = client.get(f"{V2}/quotes/{qid}/invoicing", timeout=60).json()
        assert g["summary"]["balance"] == 1500.0
        assert g["summary"]["credited"] == 1000.0
        assert g["summary"]["paid"] == 7500.0
        assert len(g["invoices"]) == 3
        assert g["stages"][1]["credited_amount"] == 1000.0
        assert g["stages"][1]["outstanding"] == 1500.0


# ── Guards / validation ───────────────────────────────────────────
class TestGuards:
    def test_auto_percent_must_total_100(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        r = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 30, "interim_percent": 30, "final_percent": 30}, timeout=60)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:300]}"

    def test_cannot_drop_invoiced_stage(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        v = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 25, "final_percent": 75}, timeout=60).json()
        dep, fin = v["stages"]
        client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/invoice", json={}, timeout=60)
        # PUT schedule omitting the invoiced deposit
        r = client.put(f"{V2}/quotes/{qid}/schedule", json={"stages": [
            {"id": fin["id"], "kind": "final", "basis": "percent", "percent": 100},
        ]}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
        assert "already been invoiced" in r.text

    def test_overpay_rejected(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        v = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 25, "final_percent": 75}, timeout=60).json()
        dep = v["stages"][0]
        client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/invoice", json={}, timeout=60)
        r = client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/pay", json={"amount": 9999}, timeout=60)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:300]}"

    def test_pay_before_invoice_rejected(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        v = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 25, "final_percent": 75}, timeout=60).json()
        dep = v["stages"][0]
        r = client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/pay", json={}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_double_invoice_rejected(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        v = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 50, "final_percent": 50}, timeout=60).json()
        dep = v["stages"][0]
        assert client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/invoice", json={}, timeout=60).status_code == 200
        r = client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/invoice", json={}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_credit_before_invoice_rejected(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        v = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 25, "final_percent": 75}, timeout=60).json()
        r = client.post(f"{V2}/quotes/{qid}/stages/{v['stages'][0]['id']}/credit-note",
                        json={"amount": 100, "reason": "x"}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_credit_over_invoiced_rejected(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        v = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 25, "final_percent": 75}, timeout=60).json()
        dep = v["stages"][0]
        client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/invoice", json={}, timeout=60)
        r = client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/credit-note",
                        json={"amount": 5000, "reason": "too much"}, timeout=60)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:300]}"

    def test_unknown_stage_404(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        r = client.post(f"{V2}/quotes/{qid}/stages/nope-123/invoice", json={}, timeout=60)
        assert r.status_code == 404, r.status_code

    def test_unknown_quote_404(self, client):
        r = client.get(f"{V2}/quotes/does-not-exist-xyz/invoicing", timeout=60)
        assert r.status_code == 404, r.status_code

    def test_unauthenticated_rejected(self):
        r = requests.get(f"{V2}/quotes/abc/invoicing", timeout=60)
        assert r.status_code in (401, 403), r.status_code


# ── Custom schedule editor path ───────────────────────────────────
class TestCustomSchedule:
    def test_put_custom_amount_stages(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        r = client.put(f"{V2}/quotes/{qid}/schedule", json={"stages": [
            {"kind": "deposit", "basis": "amount", "amount": 3000, "label": "TEST_Deposit"},
            {"kind": "interim", "basis": "amount", "amount": 2000},
            {"kind": "final", "basis": "percent", "percent": 50},
        ]}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        assert [st["amount"] for st in v["stages"]] == [3000.0, 2000.0, 5000.0]
        assert v["summary"]["scheduled"] == 10000.0
        assert v["summary"]["unscheduled"] == 0.0
        # persisted
        g = client.get(f"{V2}/quotes/{qid}/invoicing", timeout=60).json()
        assert [st["label"] for st in g["stages"]][0] == "TEST_Deposit"
        assert len(g["stages"]) == 3

    def test_reschedule_keeps_lifecycle_state(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)
        v = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 25, "final_percent": 75}, timeout=60).json()
        dep, fin = v["stages"]
        client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/invoice", json={}, timeout=60)
        client.post(f"{V2}/quotes/{qid}/stages/{dep['id']}/pay", json={}, timeout=60)
        r = client.put(f"{V2}/quotes/{qid}/schedule", json={"stages": [
            {"id": dep["id"], "kind": "deposit", "basis": "percent", "percent": 25},
            {"id": fin["id"], "kind": "final", "basis": "percent", "percent": 75},
            {"kind": "interim", "basis": "amount", "amount": 500},
        ]}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        kept = next(st for st in v["stages"] if st["id"] == dep["id"])
        assert kept["status"] == "paid"
        assert kept["paid_amount"] == 2500.0
        assert v["summary"]["paid"] == 2500.0
        assert v["summary"]["balance"] == 7500.0
