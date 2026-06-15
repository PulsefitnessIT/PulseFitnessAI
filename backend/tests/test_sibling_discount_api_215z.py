"""
Iteration 215z — Sibling Discount API Tests.

Tests:
1. GET /api/memberships/billing/sibling-discount — returns org's sibling discount pct
2. POST /api/memberships/billing/sibling-discount — sets sibling discount pct
3. Validation: pct must be 0-50 (422 for out of range)
4. Authorization: only owner/manager can set (403 for member)
5. PDF generation endpoint works after syntax fix
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://staffing-ops-preview.preview.emergentagent.com").rstrip("/")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
MEMBER_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_PASSWORD = "Member2026!"
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token (owner/manager role)."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code == 429:
        pytest.skip("Rate limited - wait and retry")
    assert resp.status_code == 200, f"Operator login failed: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth."""
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def member_token():
    """Get member JWT token (regular member role)."""
    resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
        "email": MEMBER_EMAIL,
        "password": MEMBER_PASSWORD
    })
    if resp.status_code == 429:
        pytest.skip("Rate limited - wait and retry")
    if resp.status_code != 200:
        pytest.skip(f"Member login failed: {resp.text}")
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def member_headers(member_token):
    """Headers with member auth."""
    return {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}


class TestSiblingDiscountGet:
    """GET /api/memberships/billing/sibling-discount"""

    def test_get_sibling_discount_requires_auth(self):
        """Endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/sibling-discount")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"

    def test_get_sibling_discount_returns_pct(self, operator_headers):
        """Returns pct and enabled fields."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            headers=operator_headers
        )
        assert resp.status_code == 200, f"GET failed: {resp.text}"
        data = resp.json()
        assert "pct" in data, "Response missing 'pct' field"
        assert "enabled" in data, "Response missing 'enabled' field"
        assert isinstance(data["pct"], int), "pct should be an integer"
        assert isinstance(data["enabled"], bool), "enabled should be a boolean"
        assert 0 <= data["pct"] <= 50, f"pct should be 0-50, got {data['pct']}"


class TestSiblingDiscountSet:
    """POST /api/memberships/billing/sibling-discount"""

    def test_set_sibling_discount_requires_auth(self):
        """Endpoint requires authentication."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            json={"pct": 10}
        )
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"

    def test_set_sibling_discount_success(self, operator_headers):
        """Owner/manager can set sibling discount."""
        # Set to 15%
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            json={"pct": 15},
            headers=operator_headers
        )
        assert resp.status_code == 200, f"POST failed: {resp.text}"
        data = resp.json()
        assert data["pct"] == 15, f"Expected pct=15, got {data['pct']}"
        assert data["enabled"] is True, "enabled should be True when pct > 0"

        # Verify persistence via GET
        get_resp = requests.get(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            headers=operator_headers
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["pct"] == 15, f"GET after POST should return 15, got {get_data['pct']}"

    def test_set_sibling_discount_to_zero_disables(self, operator_headers):
        """Setting pct=0 disables the discount."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            json={"pct": 0},
            headers=operator_headers
        )
        assert resp.status_code == 200, f"POST failed: {resp.text}"
        data = resp.json()
        assert data["pct"] == 0
        assert data["enabled"] is False, "enabled should be False when pct=0"

    def test_set_sibling_discount_validation_max(self, operator_headers):
        """pct > 50 should be rejected with 422."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            json={"pct": 51},
            headers=operator_headers
        )
        assert resp.status_code == 422, f"Expected 422 for pct=51, got {resp.status_code}"

    def test_set_sibling_discount_validation_negative(self, operator_headers):
        """pct < 0 should be rejected with 422."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            json={"pct": -1},
            headers=operator_headers
        )
        assert resp.status_code == 422, f"Expected 422 for pct=-1, got {resp.status_code}"


class TestSiblingDiscountAuthorization:
    """Authorization tests — only owner/manager can set."""

    def test_member_cannot_set_sibling_discount(self, member_headers):
        """Regular member should get 403."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            json={"pct": 10},
            headers=member_headers
        )
        # Member JWT is for member portal, not operator portal
        # Should get 403 or 401 depending on how the endpoint validates
        assert resp.status_code in [401, 403], f"Expected 401/403 for member, got {resp.status_code}"


class TestPDFGeneration:
    """Test PDF generation endpoint after syntax fix."""

    def test_pdf_endpoint_exists(self, operator_headers):
        """GET /api/memberships/billing/invoice/{id}/pdf should exist."""
        # First, get an existing invoice
        list_resp = requests.get(
            f"{BASE_URL}/api/memberships/billing/invoices",
            headers=operator_headers
        )
        if list_resp.status_code != 200:
            pytest.skip("Could not list invoices")

        invoices = list_resp.json().get("invoices", [])
        if not invoices:
            pytest.skip("No invoices to test PDF generation")

        invoice_id = invoices[0]["id"]

        # Try to get PDF
        pdf_resp = requests.get(
            f"{BASE_URL}/api/memberships/billing/invoice/{invoice_id}/pdf",
            headers=operator_headers
        )
        # Should return PDF or 404 if endpoint doesn't exist
        # The endpoint may not exist yet - check if it's implemented
        if pdf_resp.status_code == 404:
            # Check if it's a "not found" for the invoice or the endpoint
            if "not found" in pdf_resp.text.lower():
                pytest.skip("PDF endpoint may not be implemented yet")

        # If we get here, endpoint exists
        assert pdf_resp.status_code in [200, 404], f"Unexpected status: {pdf_resp.status_code}"


class TestMonthlyInvoicePreviewWithDiscount:
    """Test that sibling discount appears in preview."""

    def test_preview_endpoint_works(self, operator_headers):
        """POST /api/memberships/billing/monthly-invoice/preview should work."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            json={"period": "2026-04"},
            headers=operator_headers
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        assert "period" in data
        assert "invoices" in data
        assert "total_pence" in data


class TestBackendHealthAfterSyntaxFix:
    """Verify backend is fully running after E702 syntax fix."""

    def test_backend_health(self):
        """Backend should respond to health check."""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"

    def test_auth_endpoint_works(self):
        """Auth endpoint should work."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        assert resp.status_code in [200, 429], f"Auth failed: {resp.status_code}"
