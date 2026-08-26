"""Iter 294 — CPQ v2 line-type-aware quote totals (sale / spare_part / service_contract / trade_in).

Covers POST /api/crm/v2/quotes totals + GET /api/crm/v2/quotes/{id}/pdf with a trade-in line.
CRM uses a SEPARATE token via POST /api/crm/auth/login.
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def crm_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/crm/auth/login", json={"email": CRM_EMAIL, "password": CRM_PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"CRM login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("token") or r.json().get("access_token")
    if not token:
        pytest.fail(f"No token in CRM login response: {r.text[:400]}")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


MIXED_LINES = [
    {"description": "TEST_ Series 3 Treadmill", "line_type": "sale", "quantity": 1,
     "unit_price": 10000, "cost_price": 7000, "discount": 0},
    {"description": "TEST_ Drive belt", "line_type": "spare_part", "quantity": 4,
     "unit_price": 50, "cost_price": 30, "discount": 0},
    {"description": "TEST_ 12mo service contract", "line_type": "service_contract", "quantity": 1,
     "unit_price": 1200, "cost_price": 400, "discount": 0},
    {"description": "TEST_ Trade-in old treadmill", "line_type": "trade_in", "quantity": 1,
     "unit_price": 2500, "cost_price": 0, "discount": 0},
]


@pytest.fixture(scope="module")
def created_quote(crm_client):
    r = crm_client.post(f"{BASE_URL}/api/crm/v2/quotes",
                        json={"lines": MIXED_LINES, "vat_rate": 20, "notes": "TEST_ line types"}, timeout=60)
    if r.status_code not in (200, 201):
        pytest.fail(f"create quote failed {r.status_code}: {r.text[:500]}")
    return r.json()


class TestQuoteLineTypeTotals:
    def test_totals_are_line_type_aware(self, created_quote):
        q = created_quote
        assert q["equipment_subtotal"] == 10000
        assert q["parts_subtotal"] == 200
        assert q["contract_subtotal"] == 1200
        assert q["trade_in_total"] == -2500
        assert q["subtotal"] == 8900
        assert q["cost_total"] == 7520
        assert q["gross_profit"] == 1380
        assert round(q["gross_margin_percent"], 2) == 15.51
        assert q["vat_amount"] == 1780
        assert q["total"] == 10680
        assert "_id" not in q

    def test_line_net_subtotals(self, created_quote):
        by_type = {ln["line_type"]: ln for ln in created_quote["lines"]}
        assert set(by_type) == {"sale", "spare_part", "service_contract", "trade_in"}
        assert by_type["sale"]["net_subtotal"] == 10000
        assert by_type["spare_part"]["net_subtotal"] == 200
        assert by_type["service_contract"]["net_subtotal"] == 1200
        assert by_type["trade_in"]["net_subtotal"] == -2500

    def test_persisted_via_list(self, crm_client, created_quote):
        # No GET /quotes/{id} endpoint exists in CPQ v2; list is the read path.
        r = crm_client.get(f"{BASE_URL}/api/crm/v2/quotes?limit=50", timeout=60)
        assert r.status_code == 200
        match = [x for x in r.json()["quotes"] if x["id"] == created_quote["id"]]
        assert match, "created quote not returned by list endpoint"
        q = match[0]
        assert q["subtotal"] == 8900
        assert q["trade_in_total"] == -2500
        assert q["total"] == 10680
        assert "_id" not in q

    def test_pdf_renders_with_trade_in(self, crm_client, created_quote):
        r = crm_client.get(f"{BASE_URL}/api/crm/v2/quotes/{created_quote['id']}/pdf", timeout=120)
        assert r.status_code == 200, r.text[:400]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1000

    def test_unknown_line_type_falls_back_to_sale(self, crm_client):
        r = crm_client.post(f"{BASE_URL}/api/crm/v2/quotes",
                            json={"lines": [{"description": "TEST_ bogus", "line_type": "nonsense",
                                             "quantity": 2, "unit_price": 100, "cost_price": 50}],
                                  "vat_rate": 20}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        q = r.json()
        assert q["lines"][0]["line_type"] == "sale"
        assert q["equipment_subtotal"] == 200
        assert q["subtotal"] == 200

    def test_trade_in_only_quote_does_not_crash(self, crm_client):
        r = crm_client.post(f"{BASE_URL}/api/crm/v2/quotes",
                            json={"lines": [{"description": "TEST_ trade only", "line_type": "trade_in",
                                             "quantity": 1, "unit_price": 500}], "vat_rate": 20}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        q = r.json()
        assert q["subtotal"] == -500
        assert q["trade_in_total"] == -500
        # margin guard: negative subtotal must not blow up
        assert isinstance(q["gross_margin_percent"], (int, float))

    def test_discount_applies_to_trade_in_allowance(self, crm_client):
        r = crm_client.post(f"{BASE_URL}/api/crm/v2/quotes",
                            json={"lines": [
                                {"description": "TEST_ sale", "line_type": "sale", "quantity": 1,
                                 "unit_price": 1000, "cost_price": 500},
                                {"description": "TEST_ ti neg entered", "line_type": "trade_in", "quantity": 1,
                                 "unit_price": -300},
                            ], "vat_rate": 20}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        q = r.json()
        # negative unit_price on a trade-in must still be treated as a credit
        assert q["trade_in_total"] == -300
        assert q["subtotal"] == 700


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    """No DELETE endpoint for CPQ v2 quotes — clean TEST_ quotes straight from Mongo."""
    yield
    try:
        import asyncio
        from utils.database import db as mongo

        async def _rm():
            await mongo.crm2_quotes.delete_many({"lines.description": {"$regex": "^TEST_"}})

        asyncio.run(_rm())
    except Exception as exc:
        print(f"cleanup skipped: {exc}")
