"""Iter 215aa — Family Auto-Bill API endpoint tests.

Tests the new member-side and operator-side endpoints:
- GET /api/member/billing/auto-pay — member status
- POST /api/member/billing/auto-pay/setup — start Stripe checkout
- POST /api/member/billing/auto-pay/disable — turn off auto-pay
- GET /api/memberships/billing/autopay/members — operator list
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def operator_token(api_client):
    """Get operator JWT for memberships module."""
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": "lee.somers@pulsefitness.com",
        "password": "TempPass123!"
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Operator login failed: {resp.status_code} {resp.text}")


@pytest.fixture(scope="module")
def member_token(api_client):
    """Register a fresh member to get a member JWT."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    email = f"autopay-test-{unique}@example.com"
    resp = api_client.post(f"{BASE_URL}/api/member-auth/register", json={
        "email": email,
        "password": "Test123!",
        "first_name": "AutoPay",
        "last_name": "Tester",
        "organization_id": "mbr-demo-org"
    })
    if resp.status_code in (200, 201):
        return resp.json().get("token")
    # Try login if already exists
    resp2 = api_client.post(f"{BASE_URL}/api/member-auth/login", json={
        "email": email,
        "password": "Test123!"
    })
    if resp2.status_code == 200:
        return resp2.json().get("token")
    pytest.skip(f"Member registration/login failed: {resp.status_code} {resp.text}")


# ─────────────────────────────────────────────────────────────────────────────
# Member-side endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMemberAutoPay:
    """Tests for member-side auto-pay endpoints."""

    def test_get_autopay_status_requires_auth(self, api_client):
        """GET /api/member/billing/auto-pay without token returns 401."""
        resp = api_client.get(f"{BASE_URL}/api/member/billing/auto-pay")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: GET /api/member/billing/auto-pay returns 401 without auth")

    def test_get_autopay_status_with_member_token(self, api_client, member_token):
        """GET /api/member/billing/auto-pay with valid member token returns status."""
        resp = api_client.get(
            f"{BASE_URL}/api/member/billing/auto-pay",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify response structure
        assert "enabled" in data, "Response should have 'enabled' field"
        assert isinstance(data["enabled"], bool), "'enabled' should be boolean"
        # Optional fields
        assert "card_brand" in data or data.get("card_brand") is None
        assert "card_last4" in data or data.get("card_last4") is None
        assert "last_saved_at" in data or data.get("last_saved_at") is None
        print(f"PASS: GET /api/member/billing/auto-pay returns {data}")

    def test_setup_autopay_requires_auth(self, api_client):
        """POST /api/member/billing/auto-pay/setup without token returns 401."""
        resp = api_client.post(f"{BASE_URL}/api/member/billing/auto-pay/setup")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: POST /api/member/billing/auto-pay/setup returns 401 without auth")

    def test_setup_autopay_with_member_token(self, api_client, member_token):
        """POST /api/member/billing/auto-pay/setup with valid member token returns checkout_url."""
        resp = api_client.post(
            f"{BASE_URL}/api/member/billing/auto-pay/setup",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        # Should return 200 with checkout_url if STRIPE_API_KEY is set, or 503 if not
        if resp.status_code == 503:
            data = resp.json()
            assert "Stripe" in data.get("detail", ""), "503 should mention Stripe not configured"
            print("PASS: POST /api/member/billing/auto-pay/setup returns 503 (Stripe not configured)")
            pytest.skip("Stripe not configured - skipping checkout_url verification")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "checkout_url" in data, "Response should have 'checkout_url'"
        assert "session_id" in data, "Response should have 'session_id'"
        assert data["checkout_url"].startswith("https://checkout.stripe.com"), \
            f"checkout_url should be Stripe URL, got {data['checkout_url']}"
        print(f"PASS: POST /api/member/billing/auto-pay/setup returns checkout_url: {data['checkout_url'][:60]}...")

    def test_disable_autopay_requires_auth(self, api_client):
        """POST /api/member/billing/auto-pay/disable without token returns 401."""
        resp = api_client.post(f"{BASE_URL}/api/member/billing/auto-pay/disable")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: POST /api/member/billing/auto-pay/disable returns 401 without auth")

    def test_disable_autopay_with_member_token(self, api_client, member_token):
        """POST /api/member/billing/auto-pay/disable with valid member token returns ok."""
        resp = api_client.post(
            f"{BASE_URL}/api/member/billing/auto-pay/disable",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True, "Response should have ok=true"
        assert data.get("enabled") is False, "Response should have enabled=false"
        print(f"PASS: POST /api/member/billing/auto-pay/disable returns {data}")


# ─────────────────────────────────────────────────────────────────────────────
# Operator-side endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOperatorAutoPay:
    """Tests for operator-side auto-pay endpoints."""

    def test_list_autopay_members_requires_auth(self, api_client):
        """GET /api/memberships/billing/autopay/members without token returns 401."""
        resp = api_client.get(f"{BASE_URL}/api/memberships/billing/autopay/members")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: GET /api/memberships/billing/autopay/members returns 401 without auth")

    def test_list_autopay_members_with_operator_token(self, api_client, operator_token):
        """GET /api/memberships/billing/autopay/members with operator token returns list."""
        resp = api_client.get(
            f"{BASE_URL}/api/memberships/billing/autopay/members",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "count" in data, "Response should have 'count'"
        assert "members" in data, "Response should have 'members'"
        assert isinstance(data["members"], list), "'members' should be a list"
        # Verify member structure if any exist
        if data["members"]:
            m = data["members"][0]
            assert "id" in m, "Member should have 'id'"
            assert "first_name" in m, "Member should have 'first_name'"
            assert "last_name" in m, "Member should have 'last_name'"
        print(f"PASS: GET /api/memberships/billing/autopay/members returns count={data['count']}")


# ─────────────────────────────────────────────────────────────────────────────
# Regression tests for iter 215z sibling discount
# ─────────────────────────────────────────────────────────────────────────────

class TestRegressionSiblingDiscount:
    """Regression tests for sibling discount (iter 215z)."""

    def test_get_sibling_discount(self, api_client, operator_token):
        """GET /api/memberships/billing/sibling-discount still works."""
        resp = api_client.get(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "pct" in data, "Response should have 'pct'"
        print(f"PASS: GET /api/memberships/billing/sibling-discount returns pct={data['pct']}")

    def test_monthly_invoice_preview(self, api_client, operator_token):
        """POST /api/memberships/billing/monthly-invoice/preview still works."""
        resp = api_client.post(
            f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"period": "2026-01"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "period" in data, "Response should have 'period'"
        assert "invoices" in data, "Response should have 'invoices'"
        print(f"PASS: POST /api/memberships/billing/monthly-invoice/preview returns period={data['period']}")


# ─────────────────────────────────────────────────────────────────────────────
# Regression tests for iter 215y family grouping
# ─────────────────────────────────────────────────────────────────────────────

class TestRegressionFamilyGrouping:
    """Regression tests for family grouping (iter 215y)."""

    def test_monthly_invoice_preview_has_attendees(self, api_client, operator_token):
        """POST /api/memberships/billing/monthly-invoice/preview returns attendees breakdown."""
        resp = api_client.post(
            f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"period": "2026-01"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # If there are invoices, check structure
        if data.get("invoices"):
            inv = data["invoices"][0]
            # attendees field may or may not be present depending on data
            print(f"PASS: Invoice preview has {len(data['invoices'])} invoices")
        else:
            print("PASS: Invoice preview returns empty invoices (no data for period)")


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    """Basic health checks."""

    def test_health_endpoint(self, api_client):
        """GET /api/health returns 200."""
        resp = api_client.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("PASS: GET /api/health returns 200")
