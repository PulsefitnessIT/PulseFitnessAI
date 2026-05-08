"""
Phase 6 Billing API Tests — iter 215dt

Tests the Quoting & Billing endpoints:
- GET /api/svc/billing?status=ready|quoted|invoiced|all
- GET /api/svc/billing/{case_id}/quote
- POST /api/svc/billing/{case_id}/quote/auto-fill
- PUT /api/svc/billing/{case_id}/quote (create/update draft)
- POST /api/svc/billing/{case_id}/quote/approve
- POST /api/svc/billing/{case_id}/quote/void
- GET /api/svc/billing/{case_id}/invoice/preview
- POST /api/svc/billing/{case_id}/invoice/finalise
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for master admin"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
    )
    if resp.status_code != 200:
        pytest.skip("Login failed - cannot run billing tests")
    return resp.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


def _create_chargeable_case(auth_headers, title_prefix="TEST_Billing"):
    """Helper to create a chargeable case via intake endpoint"""
    case_resp = requests.post(
        f"{BASE_URL}/api/svc/intake/phone",
        headers=auth_headers,
        json={
            "title": f"{title_prefix}_{uuid.uuid4().hex[:8]}",
            "description": "Test case for billing API",
            "priority": "p3",
            "cover_type": "chargeable",
            "customer_name": "Test Customer",
            "site_name": "Test Site",
        },
    )
    if case_resp.status_code != 200:
        return None
    case_id = case_resp.json()["id"]
    # Close the case to make it billable
    requests.put(f"{BASE_URL}/api/svc/cases/{case_id}", headers=auth_headers, json={"status": "closed"})
    return case_id


@pytest.fixture(scope="module")
def test_case_id(auth_headers):
    """Get a chargeable case without a quote for testing"""
    resp = requests.get(f"{BASE_URL}/api/svc/billing?status=ready", headers=auth_headers)
    if resp.status_code == 200 and resp.json().get("rows"):
        return resp.json()["rows"][0]["id"]
    # Create a test case
    case_id = _create_chargeable_case(auth_headers)
    if case_id:
        return case_id
    pytest.skip("No ready cases and cannot create one")


class TestBillingQueue:
    """Tests for GET /api/svc/billing endpoint"""

    def test_billing_queue_all(self, auth_headers):
        """GET /api/svc/billing?status=all returns chargeable cases"""
        resp = requests.get(f"{BASE_URL}/api/svc/billing?status=all", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "count" in data
        # Verify structure of rows
        if data["rows"]:
            row = data["rows"][0]
            assert "id" in row
            assert "reference" in row
            assert "billing_state" in row
            assert row["billing_state"] in ["ready", "quoted", "invoiced"]

    def test_billing_queue_ready_filter(self, auth_headers):
        """GET /api/svc/billing?status=ready returns only ready cases"""
        resp = requests.get(f"{BASE_URL}/api/svc/billing?status=ready", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for row in data.get("rows", []):
            assert row["billing_state"] == "ready"
            assert row.get("quote") is None

    def test_billing_queue_invoiced_filter(self, auth_headers):
        """GET /api/svc/billing?status=invoiced returns only invoiced cases"""
        resp = requests.get(f"{BASE_URL}/api/svc/billing?status=invoiced", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for row in data.get("rows", []):
            assert row["billing_state"] == "invoiced"
            assert row.get("quote") is not None
            assert row["quote"]["status"] == "invoiced"


class TestQuoteOperations:
    """Tests for quote CRUD operations"""

    def test_get_quote_for_case(self, auth_headers, test_case_id):
        """GET /api/svc/billing/{case_id}/quote returns case and quote"""
        resp = requests.get(f"{BASE_URL}/api/svc/billing/{test_case_id}/quote", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "case" in data
        assert "quote" in data
        assert data["case"]["id"] == test_case_id

    def test_get_quote_nonexistent_case(self, auth_headers):
        """GET /api/svc/billing/{case_id}/quote returns 404 for non-existent case"""
        resp = requests.get(f"{BASE_URL}/api/svc/billing/nonexistent-case-id/quote", headers=auth_headers)
        assert resp.status_code == 404

    def test_auto_fill_returns_structure(self, auth_headers, test_case_id):
        """POST /api/svc/billing/{case_id}/quote/auto-fill returns expected structure"""
        resp = requests.post(f"{BASE_URL}/api/svc/billing/{test_case_id}/quote/auto-fill", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "case_id" in data
        assert "proposed_lines" in data
        assert "proposed_totals" in data
        assert "labour_rate" in data
        assert data["labour_rate"] == 65.0  # Default labour rate
        # Verify totals structure
        totals = data["proposed_totals"]
        assert "subtotal" in totals
        assert "discount" in totals
        assert "net" in totals
        assert "vat" in totals
        assert "gross" in totals


class TestQuoteLifecycle:
    """Tests for the full quote lifecycle: create → update → approve → finalise"""

    @pytest.fixture
    def fresh_case_id(self, auth_headers):
        """Create a fresh case for lifecycle testing"""
        case_id = _create_chargeable_case(auth_headers, "TEST_Lifecycle")
        if not case_id:
            pytest.skip("Cannot create test case")
        yield case_id
        # Cleanup: void any quote
        requests.post(f"{BASE_URL}/api/svc/billing/{case_id}/quote/void", headers=auth_headers)

    def test_create_draft_quote(self, auth_headers, fresh_case_id):
        """PUT /api/svc/billing/{case_id}/quote creates a draft quote"""
        resp = requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={
                "lines": [
                    {"kind": "labour", "qty": 2, "unit_amount": 65, "description": "Onsite labour"},
                    {"kind": "part", "qty": 1, "unit_amount": 100, "description": "Test part", "part_sku": "TEST-001"},
                ],
                "vat_rate": 0.20,
                "discount_pct": 10,
                "notes": "Test quote",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["reference"].startswith("Q-")
        assert data["version"] == 1
        assert len(data["lines"]) == 2
        # Verify totals calculation
        assert data["subtotal"] == 230.0  # 2*65 + 1*100
        assert data["discount"] == 23.0  # 10% of 230
        assert data["net"] == 207.0  # 230 - 23
        assert data["vat"] == 41.4  # 20% of 207
        assert data["gross"] == 248.4  # 207 + 41.4

    def test_update_draft_increments_version(self, auth_headers, fresh_case_id):
        """PUT /api/svc/billing/{case_id}/quote on existing draft increments version"""
        # Create initial draft
        requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={"lines": [{"kind": "labour", "qty": 1, "unit_amount": 65, "description": "Initial"}]},
        )
        # Update it
        resp = requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={"lines": [{"kind": "labour", "qty": 2, "unit_amount": 65, "description": "Updated"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        assert len(data["history"]) == 2

    def test_approve_draft_quote(self, auth_headers, fresh_case_id):
        """POST /api/svc/billing/{case_id}/quote/approve flips draft to approved"""
        # Create draft
        requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={"lines": [{"kind": "labour", "qty": 1, "unit_amount": 65, "description": "To approve"}]},
        )
        # Approve
        resp = requests.post(f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote/approve", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["approved_at"] is not None

    def test_cannot_edit_approved_quote(self, auth_headers, fresh_case_id):
        """PUT /api/svc/billing/{case_id}/quote returns 409 for approved quote"""
        # Create and approve
        requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={"lines": [{"kind": "labour", "qty": 1, "unit_amount": 65, "description": "Approved"}]},
        )
        requests.post(f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote/approve", headers=auth_headers)
        # Try to edit
        resp = requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={"lines": [{"kind": "labour", "qty": 2, "unit_amount": 100, "description": "Should fail"}]},
        )
        assert resp.status_code == 409
        assert "Cannot edit" in resp.json()["detail"]

    def test_void_draft_quote(self, auth_headers, fresh_case_id):
        """POST /api/svc/billing/{case_id}/quote/void voids a draft quote"""
        # Create draft
        requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={"lines": [{"kind": "labour", "qty": 1, "unit_amount": 65, "description": "To void"}]},
        )
        # Void
        resp = requests.post(f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote/void", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # Verify voided
        get_resp = requests.get(f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote", headers=auth_headers)
        assert get_resp.json()["quote"] is None

    def test_void_approved_quote(self, auth_headers, fresh_case_id):
        """POST /api/svc/billing/{case_id}/quote/void works on approved quote"""
        # Create and approve
        requests.put(
            f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote",
            headers=auth_headers,
            json={"lines": [{"kind": "labour", "qty": 1, "unit_amount": 65, "description": "Approved to void"}]},
        )
        requests.post(f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote/approve", headers=auth_headers)
        # Void
        resp = requests.post(f"{BASE_URL}/api/svc/billing/{fresh_case_id}/quote/void", headers=auth_headers)
        assert resp.status_code == 200


class TestInvoiceOperations:
    """Tests for invoice preview and finalise"""

    @pytest.fixture
    def approved_case_id(self, auth_headers):
        """Create a case with an approved quote"""
        case_id = _create_chargeable_case(auth_headers, "TEST_Invoice")
        if not case_id:
            pytest.skip("Cannot create test case")
        # Create and approve quote
        requests.put(
            f"{BASE_URL}/api/svc/billing/{case_id}/quote",
            headers=auth_headers,
            json={
                "lines": [
                    {"kind": "labour", "qty": 2, "unit_amount": 65, "description": "Labour for invoice"},
                    {"kind": "part", "qty": 1, "unit_amount": 50, "description": "Part for invoice", "part_sku": "INV-001"},
                ],
            },
        )
        requests.post(f"{BASE_URL}/api/svc/billing/{case_id}/quote/approve", headers=auth_headers)
        return case_id

    def test_invoice_preview_structure(self, auth_headers, approved_case_id):
        """GET /api/svc/billing/{case_id}/invoice/preview returns Sage payload structure"""
        resp = requests.get(f"{BASE_URL}/api/svc/billing/{approved_case_id}/invoice/preview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "case_id" in data
        assert "quote" in data
        assert "payload" in data
        # Verify Sage payload structure
        payload = data["payload"]
        assert "OurReference" in payload
        assert "Reference" in payload
        assert "Lines" in payload
        assert "QuoteReference" in payload
        assert "QuoteTotal" in payload
        # Verify lines have Sage fields
        for line in payload["Lines"]:
            assert "NominalCode" in line
            assert "Description" in line
            assert "Quantity" in line
            assert "UnitNetAmount" in line
            assert "TaxCode" in line

    def test_finalise_invoice(self, auth_headers, approved_case_id):
        """POST /api/svc/billing/{case_id}/invoice/finalise pushes to outbox"""
        resp = requests.post(f"{BASE_URL}/api/svc/billing/{approved_case_id}/invoice/finalise", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["quote"]["status"] == "invoiced"
        assert data["outbox"]["status"] == "ready"
        assert "QuoteReference" in data["outbox"]["payload"]

    def test_finalise_without_approved_quote_fails(self, auth_headers):
        """POST /api/svc/billing/{case_id}/invoice/finalise returns 409 without approved quote"""
        # Create case without quote
        case_id = _create_chargeable_case(auth_headers, "TEST_NoQuote")
        if not case_id:
            pytest.skip("Cannot create test case")
        # Try to finalise
        resp = requests.post(f"{BASE_URL}/api/svc/billing/{case_id}/invoice/finalise", headers=auth_headers)
        assert resp.status_code == 409
        assert "No approved quote" in resp.json()["detail"]


class TestLineNormalisation:
    """Tests for line normalisation and totals calculation"""

    @pytest.fixture
    def test_case(self, auth_headers):
        """Create a test case for line tests"""
        case_id = _create_chargeable_case(auth_headers, "TEST_Lines")
        if not case_id:
            pytest.skip("Cannot create test case")
        yield case_id
        requests.post(f"{BASE_URL}/api/svc/billing/{case_id}/quote/void", headers=auth_headers)

    def test_invalid_kind_dropped(self, auth_headers, test_case):
        """Lines with invalid kind are dropped during normalisation"""
        resp = requests.put(
            f"{BASE_URL}/api/svc/billing/{test_case}/quote",
            headers=auth_headers,
            json={
                "lines": [
                    {"kind": "labour", "qty": 1, "unit_amount": 65, "description": "Valid"},
                    {"kind": "invalid_kind", "qty": 1, "unit_amount": 100, "description": "Should be dropped"},
                ],
            },
        )
        assert resp.status_code == 200
        assert len(resp.json()["lines"]) == 1
        assert resp.json()["lines"][0]["kind"] == "labour"

    def test_adjustment_line_allowed(self, auth_headers, test_case):
        """Adjustment lines are allowed and can have negative amounts"""
        resp = requests.put(
            f"{BASE_URL}/api/svc/billing/{test_case}/quote",
            headers=auth_headers,
            json={
                "lines": [
                    {"kind": "labour", "qty": 2, "unit_amount": 65, "description": "Labour"},
                    {"kind": "adjustment", "qty": 1, "unit_amount": -30, "description": "Discount"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 2
        assert data["subtotal"] == 100.0  # 130 - 30

    def test_totals_with_discount_pct(self, auth_headers, test_case):
        """Discount percentage is applied correctly to totals"""
        resp = requests.put(
            f"{BASE_URL}/api/svc/billing/{test_case}/quote",
            headers=auth_headers,
            json={
                "lines": [{"kind": "labour", "qty": 2, "unit_amount": 50, "description": "Labour"}],
                "discount_pct": 20,
                "vat_rate": 0.20,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["subtotal"] == 100.0
        assert data["discount"] == 20.0  # 20% of 100
        assert data["net"] == 80.0  # 100 - 20
        assert data["vat"] == 16.0  # 20% of 80
        assert data["gross"] == 96.0  # 80 + 16


class TestApproveEdgeCases:
    """Edge case tests for approve endpoint"""

    def test_approve_nonexistent_draft_returns_404(self, auth_headers):
        """POST /api/svc/billing/{case_id}/quote/approve returns 404 for non-existent draft"""
        resp = requests.post(f"{BASE_URL}/api/svc/billing/nonexistent-case/quote/approve", headers=auth_headers)
        assert resp.status_code == 404
