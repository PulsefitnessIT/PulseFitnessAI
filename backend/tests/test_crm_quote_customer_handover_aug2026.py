"""CRM · CPQ v2 "Customer Register Handover" (cross-org equipment push).

Covers routes/crm_quote_handover.py:
  GET  /api/crm/v2/quotes/{id}/handover           -> customer_portal block
  POST /api/crm/v2/quotes/{id}/handover/register  -> cross-org copy (idempotent)

Seeded fixture (left in place): crm2_companies 'HANDOVER-TEST-CO' (iso-demo-org)
-> tenant_org_id 'handover-test-portal' (org 'Handover Test Gym').
"""
import os

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
_be = dotenv_values("/app/backend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"
V2 = f"{BASE}/api/crm/v2"
ORG = "iso-demo-org"
LINKED_COMPANY = "HANDOVER-TEST-CO"
TENANT_ORG = "handover-test-portal"


def _db():
    from pymongo import MongoClient
    mc = MongoClient(_be["MONGO_URL"])
    return mc, mc[_be["DB_NAME"]]


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
    mc, sdb = _db()
    for qid in created_quote_ids:
        sdb.crm2_quotes.delete_many({"id": qid})
        sdb.purchase_orders.delete_many({"quote_id": qid})
        sdb.equipment.delete_many({"quote_id": qid})  # both orgs
        sdb.crm2_invoices.delete_many({"quote_id": qid})
        sdb.issues.delete_many({"quote_id": qid})
        sdb.svc_cases.delete_many({"quote_id": qid})
    mc.close()


def _new_quote(client, created_quote_ids, company_id, company_name=""):
    payload = {
        "notes": "TEST_customer_handover",
        "vat_rate": 0,
        "company_id": company_id,
        "lines": [
            {"description": "TEST_ Handover Treadmill", "line_type": "sale", "quantity": 2,
             "unit_price": 1500, "cost_price": 900, "manufacturer": "Pulse",
             "model": "HT-1", "discount": 0},
        ],
    }
    if company_name:
        payload["company_name"] = company_name
    r = client.post(f"{V2}/quotes", json=payload, timeout=60)
    assert r.status_code in (200, 201), f"create quote failed {r.status_code}: {r.text[:400]}"
    q = r.json().get("quote") or r.json()
    qid = q.get("id")
    assert qid
    created_quote_ids.append(qid)
    assert q.get("company_id") == company_id, f"company_id not persisted: {q.get('company_id')}"
    return qid


def _deliver(client, qid, serials):
    r = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                    json={"supplier_name": "ACME", "vat_rate": 0}, timeout=60)
    assert r.status_code in (200, 201), r.text[:400]
    po = r.json()["purchase_order"]
    eq_line = next(i["line_id"] for i in po["items"] if i["is_equipment"])
    r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po['id']}/receive",
                    json={"items": [{"line_id": eq_line, "received_qty": len(serials),
                                     "serials": serials}]}, timeout=60)
    assert r.status_code in (200, 201), r.text[:400]
    return r.json()


# ── Seed sanity ─────────────────────────────────────────────────────
def test_seeded_linked_company_present():
    mc, sdb = _db()
    try:
        co = sdb.crm2_companies.find_one({"id": LINKED_COMPANY, "organization_id": ORG})
        assert co, "seeded HANDOVER-TEST-CO missing"
        assert co.get("tenant_org_id") == TENANT_ORG, co.get("tenant_org_id")
        org = sdb.organizations.find_one({"id": TENANT_ORG})
        assert org and org.get("name") == "Handover Test Gym", org
    finally:
        mc.close()


# ── Happy path: view → register → idempotent re-register → cross-org rows ──
class TestCustomerHandover:
    def test_end_to_end(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids, LINKED_COMPANY, "Handover Test Gym")

        # Before delivery: linked, nothing registered
        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        assert r.status_code == 200, r.text[:400]
        cp = r.json()["customer_portal"]
        assert cp["linked"] is True, cp
        assert cp["tenant_org_id"] == TENANT_ORG
        assert cp["tenant_org_name"] == "Handover Test Gym", cp
        assert cp["equipment_registered"] == 0 and cp["pending_handover"] == 0, cp

        # Register before goods received -> nothing to push (but allowed)
        r = client.post(f"{V2}/quotes/{qid}/handover/register", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["handed_over"] == []

        # Deliver 2 units with serials
        _deliver(client, qid, ["H-1", "H-2"])

        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        cp = r.json()["customer_portal"]
        assert cp["equipment_registered"] == 2, cp
        assert cp["pending_handover"] == 2, cp
        assert cp["equipment_handed_over"] == 0, cp

        # Push into the customer's portal
        r = client.post(f"{V2}/quotes/{qid}/handover/register", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert len(body["handed_over"]) == 2, body["handed_over"]
        assert sorted(x["serial_number"] for x in body["handed_over"]) == ["H-1", "H-2"]
        cp = body["customer_portal"]
        assert cp["pending_handover"] == 0 and cp["equipment_handed_over"] == 2, cp

        # Idempotent second push
        r = client.post(f"{V2}/quotes/{qid}/handover/register", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert len(r.json()["handed_over"]) == 0, r.json()["handed_over"]

        # GET reflects persisted state
        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        cp = r.json()["customer_portal"]
        assert cp["equipment_handed_over"] == 2 and cp["pending_handover"] == 0, cp

        # Cross-org equipment rows exist in the CUSTOMER org with provenance
        mc, sdb = _db()
        try:
            rows = list(sdb.equipment.find({"quote_id": qid, "organization_id": TENANT_ORG}))
            assert len(rows) == 2, f"expected 2 customer rows, got {len(rows)}"
            assert sorted(r["serial_number"] for r in rows) == ["H-1", "H-2"]
            for row in rows:
                assert row["source"] == "deal_handover", row.get("source")
                assert row["origin_org_id"] == ORG
                assert row["origin_equipment_id"]
                assert row["status"] == "active"
            # seller rows stamped
            sellers = list(sdb.equipment.find({"quote_id": qid, "organization_id": ORG}))
            assert len(sellers) == 2
            for s in sellers:
                assert s.get("handed_over_at"), "seller row not stamped handed_over_at"
                assert s.get("customer_org_id") == TENANT_ORG
                assert s.get("customer_equipment_id")
        finally:
            mc.close()


# ── Guard: company with no tenant_org_id -> 400 ─────────────────────
class TestUnlinkedCompany:
    def test_register_unlinked_returns_400(self, client, created_quote_ids):
        mc, sdb = _db()
        try:
            co = sdb.crm2_companies.find_one(
                {"organization_id": ORG, "tenant_org_id": {"$in": [None, ""]}}, {"id": 1, "name": 1})
            if not co:
                co = sdb.crm2_companies.find_one(
                    {"organization_id": ORG, "tenant_org_id": {"$exists": False}}, {"id": 1, "name": 1})
        finally:
            mc.close()
        assert co, "no unlinked company in iso-demo-org to test with"
        qid = _new_quote(client, created_quote_ids, co["id"], co.get("name", ""))

        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        assert r.status_code == 200, r.text[:300]
        cp = r.json()["customer_portal"]
        assert cp["linked"] is False, cp
        assert cp["tenant_org_id"] in (None, ""), cp

        r = client.post(f"{V2}/quotes/{qid}/handover/register", json={}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
        assert "portal" in (r.json().get("detail") or "").lower(), r.text[:300]


    def test_register_no_company_returns_400(self, client, created_quote_ids):
        """Quote with NO company_id at all -> guard still fires (no crash)."""
        payload = {
            "notes": "TEST_customer_handover", "vat_rate": 0,
            "lines": [{"description": "TEST_ No-company Bike", "line_type": "sale",
                       "quantity": 1, "unit_price": 500, "cost_price": 300, "discount": 0}],
        }
        r = client.post(f"{V2}/quotes", json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        qid = (r.json().get("quote") or r.json())["id"]
        created_quote_ids.append(qid)

        g = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        assert g.status_code == 200, g.text[:300]
        assert g.json()["customer_portal"]["linked"] is False

        r = client.post(f"{V2}/quotes/{qid}/handover/register", json={}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
        assert "portal" in (r.json().get("detail") or "").lower(), r.text[:300]


# ── Auth guard ──────────────────────────────────────────────────────
def test_register_requires_auth():
    r = requests.post(f"{V2}/quotes/whatever/handover/register", json={}, timeout=60)
    assert r.status_code in (401, 403), r.status_code
