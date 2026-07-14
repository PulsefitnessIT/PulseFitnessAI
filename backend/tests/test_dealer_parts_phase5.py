"""Backend tests for Dealer Warranty Parts Phase 5.

Covers:
- AI parse-invoice + AI dealer-summary (real LLM; retry once on transient available:false)
- CSV report exports (allocations/stock/usage/failures + 404 for unknown)
- Dealer portal overview + replenishment request lifecycle
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"

SAMPLE_INVOICE = """PulseFit GmbH — Sales Order Confirmation
Order Reference: PO-2026-DE-00421
Currency: EUR
Total Order Value: 12,450.00

Line 1: Treadmill T-9000 — Qty 3 — Unit 2,300.00 — Line total 6,900.00
Line 2: Elliptical E-500 — Qty 2 — Unit 1,275.00 — Line total 2,550.00
Line 3: Bike B-200 — Qty 3 — Unit 1,000.00 — Line total 3,000.00
"""


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def dealer_id(h):
    """Find Fitline Deutschland dealer id."""
    r = requests.get(f"{BASE_URL}/api/dealer-parts/dealers", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    dealers = r.json().get("dealers") or r.json()
    if isinstance(dealers, dict):
        dealers = dealers.get("dealers") or []
    fit = next((d for d in dealers if "fitline" in (d.get("name") or "").lower()), None)
    assert fit, f"Fitline Deutschland not found among {[d.get('name') for d in dealers]}"
    return fit["id"]


# ── AI: parse-invoice ─────────────────────────────────────────────
class TestAIParseInvoice:
    def test_parse_invoice(self, h):
        payload = {"text": SAMPLE_INVOICE}
        result = None
        for attempt in range(2):
            r = requests.post(f"{BASE_URL}/api/dealer-parts/ai/parse-invoice", json=payload, headers=h, timeout=90)
            assert r.status_code == 200, r.text
            result = r.json()
            if result.get("available"):
                break
            time.sleep(2)
        assert result.get("available") is True, f"AI unavailable after retry: {result}"
        assert isinstance(result.get("lines"), list)
        assert len(result["lines"]) >= 1, "AI must extract at least one line"
        # Should NOT invent — max 3 lines from sample
        assert len(result["lines"]) <= 5
        for line in result["lines"]:
            assert "machine_model" in line
            assert "quantity" in line
        # order_value should be present and roughly correct
        assert result.get("order_value") is not None
        ov = float(result["order_value"])
        assert 10000 <= ov <= 15000, f"order_value {ov} out of expected range"

    def test_parse_invoice_too_short(self, h):
        r = requests.post(f"{BASE_URL}/api/dealer-parts/ai/parse-invoice", json={"text": "short"}, headers=h, timeout=30)
        assert r.status_code == 400


# ── AI: dealer-summary ────────────────────────────────────────────
class TestAIDealerSummary:
    def test_dealer_summary(self, h, dealer_id):
        result = None
        for attempt in range(2):
            r = requests.post(f"{BASE_URL}/api/dealer-parts/ai/dealer-summary",
                              json={"dealer_id": dealer_id}, headers=h, timeout=90)
            assert r.status_code == 200, r.text
            result = r.json()
            if result.get("available"):
                break
            time.sleep(2)
        assert result.get("available") is True, f"AI unavailable after retry: {result}"
        assert isinstance(result.get("summary"), str) and len(result["summary"]) > 10
        assert isinstance(result.get("highlights"), list)
        assert "dealer_note" in result


# ── CSV reports ───────────────────────────────────────────────────
class TestReports:
    @pytest.mark.parametrize("report", ["allocations", "stock", "usage", "failures"])
    def test_report_csv(self, h, report):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/reports/{report}.csv", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "").lower()
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower(), f"missing attachment header: {cd}"
        assert "filename" in cd.lower()
        # Must have header row
        first_line = r.text.splitlines()[0] if r.text else ""
        assert "," in first_line, f"header row not comma-separated: {first_line!r}"

    def test_unknown_report_404(self, h):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/reports/nonsense.csv", headers=h, timeout=30)
        assert r.status_code == 404


# ── Dealer portal ────────────────────────────────────────────────
class TestDealerPortal:
    def test_overview(self, h, dealer_id):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/portal/{dealer_id}/overview", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("dealer", "stock", "stock_value", "incoming", "recent_usage", "requests"):
            assert k in d, f"missing key {k}"
        assert d["dealer"]["id"] == dealer_id
        # stock_status computed
        for s in d["stock"]:
            assert s.get("stock_status") in ("in_stock", "low_stock", "out_of_stock")
        # incoming must only be dispatched/partially_received
        for a in d["incoming"]:
            assert a.get("status") in ("dispatched", "partially_received")

    def test_overview_unknown_dealer_404(self, h):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/portal/does-not-exist/overview", headers=h, timeout=30)
        assert r.status_code == 404

    def test_replenishment_request_lifecycle(self, h, dealer_id):
        # Create
        payload = {"part_sku": "TEST_SKU_P5", "part_name": "TEST Phase5 Part", "quantity": 2, "note": "TEST_ phase5 automated"}
        r = requests.post(f"{BASE_URL}/api/dealer-parts/portal/{dealer_id}/request-replenishment",
                          json=payload, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        req = r.json()
        assert req["status"] == "requested"
        assert req["part_sku"] == "TEST_SKU_P5"
        assert req["quantity"] == 2
        req_id = req["id"]

        # List includes it
        r = requests.get(f"{BASE_URL}/api/dealer-parts/replenishment-requests", headers=h, timeout=30)
        assert r.status_code == 200
        listed = r.json()["requests"]
        assert any(x["id"] == req_id for x in listed)

        # Invalid status → 400
        r = requests.patch(f"{BASE_URL}/api/dealer-parts/replenishment-requests/{req_id}",
                           json={"status": "banana"}, headers=h, timeout=30)
        assert r.status_code == 400

        # Approve
        r = requests.patch(f"{BASE_URL}/api/dealer-parts/replenishment-requests/{req_id}",
                           json={"status": "approved"}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

        # Missing part_sku → 400
        r = requests.post(f"{BASE_URL}/api/dealer-parts/portal/{dealer_id}/request-replenishment",
                          json={"quantity": 1}, headers=h, timeout=30)
        assert r.status_code == 400

        # 404 on nonexistent
        r = requests.patch(f"{BASE_URL}/api/dealer-parts/replenishment-requests/nope-id",
                           json={"status": "approved"}, headers=h, timeout=30)
        assert r.status_code == 404
