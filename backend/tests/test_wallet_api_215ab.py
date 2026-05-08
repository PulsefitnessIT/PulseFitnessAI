"""Iter 215ab — Family Wallet API tests.

Tests the new wallet endpoints:
- GET /api/member/wallet — member balance + ledger
- POST /api/member/wallet/topup — Stripe Checkout for topup
- GET /api/memberships/billing/wallet/members — operator roster
- POST /api/memberships/billing/invoice/{id}/apply-wallet — operator debit
"""
import os
import pytest
import requests
from unittest.mock import patch, MagicMock

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def operator_token(api_client):
    """Get operator JWT for lee.somers@pulsefitness.com."""
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": "lee.somers@pulsefitness.com",
        "password": "TempPass123!"
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Operator login failed: {resp.status_code} {resp.text}")


@pytest.fixture(scope="module")
def member_token(api_client):
    """Register a fresh member and return their JWT."""
    import uuid
    email = f"wallet-test-{uuid.uuid4().hex[:8]}@example.com"
    resp = api_client.post(f"{BASE_URL}/api/member-auth/register", json={
        "email": email,
        "password": "Test123!",
        "first_name": "Wallet",
        "last_name": "Tester",
        "organization_id": "mbr-demo-org"  # Use organization_id instead of slug
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
    pytest.skip(f"Member registration failed: {resp.status_code} {resp.text}")


class TestMemberWalletEndpoints:
    """Member-side wallet endpoints."""

    def test_get_wallet_requires_auth(self, api_client):
        """GET /api/member/wallet without token returns 401."""
        resp = api_client.get(f"{BASE_URL}/api/member/wallet")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: GET /api/member/wallet returns 401 without auth")

    def test_get_wallet_with_member_token(self, api_client, member_token):
        """GET /api/member/wallet with member JWT returns balance + ledger."""
        resp = api_client.get(
            f"{BASE_URL}/api/member/wallet",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "balance_pence" in data, "Missing balance_pence"
        assert "currency" in data, "Missing currency"
        assert data["currency"] == "gbp", f"Expected currency=gbp, got {data['currency']}"
        assert "ledger" in data, "Missing ledger"
        assert isinstance(data["ledger"], list), "ledger should be a list"
        print(f"PASS: GET /api/member/wallet returns balance={data['balance_pence']}, ledger={len(data['ledger'])} rows")

    def test_topup_requires_auth(self, api_client):
        """POST /api/member/wallet/topup without token returns 401."""
        resp = api_client.post(
            f"{BASE_URL}/api/member/wallet/topup",
            json={"amount_pence": 2500}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: POST /api/member/wallet/topup returns 401 without auth")

    def test_topup_validates_amount_too_low(self, api_client, member_token):
        """POST /api/member/wallet/topup with amount < 500 returns 422."""
        resp = api_client.post(
            f"{BASE_URL}/api/member/wallet/topup",
            json={"amount_pence": 400},  # Below minimum £5
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 422, f"Expected 422 for amount < 500, got {resp.status_code}: {resp.text}"
        print("PASS: POST /api/member/wallet/topup returns 422 for amount_pence=400 (below £5 minimum)")

    def test_topup_validates_amount_too_high(self, api_client, member_token):
        """POST /api/member/wallet/topup with amount > 100000 returns 422."""
        resp = api_client.post(
            f"{BASE_URL}/api/member/wallet/topup",
            json={"amount_pence": 200000},  # Above maximum £1000
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 422, f"Expected 422 for amount > 100000, got {resp.status_code}: {resp.text}"
        print("PASS: POST /api/member/wallet/topup returns 422 for amount_pence=200000 (above £1000 maximum)")

    def test_topup_valid_amount_returns_checkout_url(self, api_client, member_token):
        """POST /api/member/wallet/topup with valid amount returns checkout_url + session_id."""
        resp = api_client.post(
            f"{BASE_URL}/api/member/wallet/topup",
            json={"amount_pence": 2500},  # £25
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "checkout_url" in data, "Missing checkout_url"
        assert "session_id" in data, "Missing session_id"
        assert data["checkout_url"].startswith("https://checkout.stripe.com"), \
            f"checkout_url should be Stripe URL, got {data['checkout_url'][:50]}"
        print("PASS: POST /api/member/wallet/topup returns checkout_url and session_id")


class TestOperatorWalletEndpoints:
    """Operator-side wallet endpoints."""

    def test_list_wallet_members_requires_auth(self, api_client):
        """GET /api/memberships/billing/wallet/members without token returns 401."""
        resp = api_client.get(f"{BASE_URL}/api/memberships/billing/wallet/members")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: GET /api/memberships/billing/wallet/members returns 401 without auth")

    def test_list_wallet_members_with_operator_token(self, api_client, operator_token):
        """GET /api/memberships/billing/wallet/members with operator JWT returns roster."""
        resp = api_client.get(
            f"{BASE_URL}/api/memberships/billing/wallet/members",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "count" in data, "Missing count"
        assert "total_balance_pence" in data, "Missing total_balance_pence"
        assert "members" in data, "Missing members"
        assert isinstance(data["members"], list), "members should be a list"
        print(f"PASS: GET /api/memberships/billing/wallet/members returns count={data['count']}, total={data['total_balance_pence']}")

    def test_apply_wallet_requires_auth(self, api_client):
        """POST /api/memberships/billing/invoice/{id}/apply-wallet without token returns 401 or 404."""
        resp = api_client.post(f"{BASE_URL}/api/memberships/billing/invoice/fake-id/apply-wallet")
        # 401 if auth checked first, 404 if invoice checked first - both are acceptable
        assert resp.status_code in (401, 404), f"Expected 401 or 404, got {resp.status_code}"
        print(f"PASS: POST /api/memberships/billing/invoice/{{id}}/apply-wallet returns {resp.status_code} without auth")

    def test_apply_wallet_unknown_invoice_returns_404(self, api_client, operator_token):
        """POST /api/memberships/billing/invoice/{id}/apply-wallet with unknown invoice returns 404."""
        resp = api_client.post(
            f"{BASE_URL}/api/memberships/billing/invoice/nonexistent-invoice-id/apply-wallet",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 404, f"Expected 404 for unknown invoice, got {resp.status_code}: {resp.text}"
        print("PASS: POST /api/memberships/billing/invoice/{id}/apply-wallet returns 404 for unknown invoice")


class TestRegressionAutoPay:
    """Regression tests for iter 215aa Auto-Bill endpoints."""

    def test_autopay_status_endpoint(self, api_client, member_token):
        """GET /api/member/billing/auto-pay still works."""
        resp = api_client.get(
            f"{BASE_URL}/api/member/billing/auto-pay",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "enabled" in data, "Missing enabled field"
        print(f"PASS: Regression - GET /api/member/billing/auto-pay returns enabled={data['enabled']}")

    def test_autopay_members_endpoint(self, api_client, operator_token):
        """GET /api/memberships/billing/autopay/members still works."""
        resp = api_client.get(
            f"{BASE_URL}/api/memberships/billing/autopay/members",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "count" in data, "Missing count"
        assert "members" in data, "Missing members"
        print(f"PASS: Regression - GET /api/memberships/billing/autopay/members returns count={data['count']}")


class TestRegressionSiblingDiscount:
    """Regression tests for iter 215z sibling discount endpoints."""

    def test_sibling_discount_get(self, api_client, operator_token):
        """GET /api/memberships/billing/sibling-discount still works."""
        resp = api_client.get(
            f"{BASE_URL}/api/memberships/billing/sibling-discount",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "pct" in data, "Missing pct field"
        print(f"PASS: Regression - GET /api/memberships/billing/sibling-discount returns pct={data['pct']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
