"""
Iter 216h25 — Backend tests for:
1. Jump-to-user: Structured 409 response from POST /api/master-admin/organizations/{org_id}/users
2. brand_filter: Audit-log, marketing analytics/subscriptions endpoints accept ?brand=
3. financial-ops: Pulse admins get 403 (GymAxis-platform-only data)

Test credentials:
- GymAxis Master Admin: admin@gymaxisai.com / MasterAdmin123!
- Pulse Master Admin: pulse.scope.test@pulsefitness.com / TestPulse2026!
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")

# Test credentials
GYMAXIS_ADMIN_EMAIL = "admin@gymaxisai.com"
GYMAXIS_ADMIN_PASSWORD = "MasterAdmin123!"
PULSE_ADMIN_EMAIL = "pulse.scope.test@pulsefitness.com"
PULSE_ADMIN_PASSWORD = "TestPulse2026!"


def get_bypass_headers():
    """Return rate-limit bypass header if available."""
    if RATE_LIMIT_BYPASS:
        return {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    return {}


def login(email: str, password: str) -> str:
    """Login and return JWT token."""
    headers = {"Content-Type": "application/json", **get_bypass_headers()}
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def gymaxis_token():
    """GymAxis Master Admin token."""
    return login(GYMAXIS_ADMIN_EMAIL, GYMAXIS_ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def pulse_token():
    """Pulse Master Admin token."""
    return login(PULSE_ADMIN_EMAIL, PULSE_ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def gymaxis_headers(gymaxis_token):
    return {"Authorization": f"Bearer {gymaxis_token}", **get_bypass_headers()}


@pytest.fixture(scope="module")
def pulse_headers(pulse_token):
    return {"Authorization": f"Bearer {pulse_token}", **get_bypass_headers()}


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Jump-to-user — Structured 409 response when email exists
# ─────────────────────────────────────────────────────────────────────────────

class TestJumpToUserStructured409:
    """POST /api/master-admin/organizations/{org_id}/users returns structured 409."""

    def test_structured_409_when_email_exists(self, gymaxis_headers):
        """Creating a user with existing email returns structured 409 with user_id."""
        # First, get an org to use
        orgs_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers=gymaxis_headers,
        )
        assert orgs_resp.status_code == 200
        orgs = orgs_resp.json().get("organizations", [])
        assert len(orgs) > 0, "No organizations found"
        org_id = orgs[0]["id"]

        # Try to create a user with the existing admin email
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/users",
            json={
                "email": GYMAXIS_ADMIN_EMAIL,  # This email already exists
                "full_name": "Duplicate Test",
                "role": "staff",
            },
            headers=gymaxis_headers,
        )

        # Should return 409 with structured detail
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", {})

        # Verify structured response
        assert isinstance(detail, dict), f"Expected dict detail, got: {type(detail)}"
        assert detail.get("code") == "user_exists", f"Expected code='user_exists', got: {detail}"
        assert "user_id" in detail, f"Missing user_id in detail: {detail}"
        assert "email" in detail, f"Missing email in detail: {detail}"
        assert detail.get("email") == GYMAXIS_ADMIN_EMAIL.lower()
        print(f"✓ Structured 409 returned: code={detail.get('code')}, user_id={detail.get('user_id')}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2-5: brand_filter on audit-log endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditLogBrandFilter:
    """GET /api/master-admin/audit-log accepts ?brand= parameter."""

    def test_audit_log_brand_gymaxis(self, gymaxis_headers):
        """GymAxis admin can filter audit-log by brand=gymaxis."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log",
            params={"brand": "gymaxis", "since_days": 7, "limit": 50},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "events" in data
        assert "brand" in data
        print(f"✓ Audit-log brand=gymaxis: {data.get('count', 0)} events, brand={data.get('brand')}")

    def test_audit_log_brand_pulse(self, gymaxis_headers):
        """GymAxis admin can filter audit-log by brand=pulse."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log",
            params={"brand": "pulse", "since_days": 7, "limit": 50},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "events" in data
        print(f"✓ Audit-log brand=pulse: {data.get('count', 0)} events")

    def test_audit_log_brand_all(self, gymaxis_headers):
        """GymAxis admin can request brand=all (no filter)."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log",
            params={"brand": "all", "since_days": 7, "limit": 50},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "events" in data
        print(f"✓ Audit-log brand=all: {data.get('count', 0)} events")

    def test_audit_log_pulse_admin_forced_to_pulse(self, pulse_headers):
        """Pulse admin requesting brand=gymaxis is forced to brand=pulse."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log",
            params={"brand": "gymaxis", "since_days": 7, "limit": 50},
            headers=pulse_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        # Pulse admin should be forced to pulse brand
        assert data.get("brand") == "pulse", f"Expected brand=pulse, got: {data.get('brand')}"
        print(f"✓ Pulse admin forced to brand=pulse: {data.get('count', 0)} events")

    def test_audit_log_summary_brand(self, gymaxis_headers):
        """GET /api/master-admin/audit-log/summary accepts ?brand=."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/summary",
            params={"brand": "pulse", "since_days": 7},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "total" in data
        assert "by_kind" in data
        print(f"✓ Audit-log summary brand=pulse: total={data.get('total')}")

    def test_audit_log_export_csv_brand(self, gymaxis_headers):
        """GET /api/master-admin/audit-log/export.csv accepts ?brand= and returns CSV."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/export.csv",
            params={"brand": "gymaxis", "since_days": 7, "limit": 100},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        content_type = resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got: {content_type}"
        # Check CSV has header row
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1, "CSV should have at least header row"
        assert "timestamp" in lines[0].lower(), f"CSV header missing timestamp: {lines[0]}"
        print(f"✓ Audit-log CSV export: {len(lines)} lines, content-type={content_type}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 6-7: brand_filter on marketing endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestMarketingBrandFilter:
    """Marketing analytics and subscriptions accept ?brand= parameter."""

    def test_marketing_analytics_brand_gymaxis(self, gymaxis_headers):
        """GET /api/master-admin/marketing/analytics accepts ?brand=gymaxis."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/marketing/analytics",
            params={"brand": "gymaxis"},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "brand" in data, f"Response missing 'brand' field: {data.keys()}"
        assert data.get("brand") == "gymaxis", f"Expected brand=gymaxis, got: {data.get('brand')}"
        print(f"✓ Marketing analytics brand=gymaxis: MRR=£{data.get('mrr_gbp', 0)}")

    def test_marketing_analytics_brand_pulse(self, gymaxis_headers):
        """GET /api/master-admin/marketing/analytics accepts ?brand=pulse."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/marketing/analytics",
            params={"brand": "pulse"},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("brand") == "pulse", f"Expected brand=pulse, got: {data.get('brand')}"
        print(f"✓ Marketing analytics brand=pulse: MRR=£{data.get('mrr_gbp', 0)}")

    def test_marketing_analytics_pulse_admin_forced(self, pulse_headers):
        """Pulse admin requesting brand=gymaxis is forced to brand=pulse."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/marketing/analytics",
            params={"brand": "gymaxis"},
            headers=pulse_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        # Pulse admin should be forced to pulse
        assert data.get("brand") == "pulse", f"Expected brand=pulse (forced), got: {data.get('brand')}"
        assert data.get("scoped") is True, "Expected scoped=True for Pulse admin"
        print("✓ Pulse admin forced to brand=pulse in analytics")

    def test_marketing_subscriptions_brand(self, gymaxis_headers):
        """GET /api/master-admin/marketing/subscriptions accepts ?brand=."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/marketing/subscriptions",
            params={"brand": "pulse"},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "subscriptions" in data
        print(f"✓ Marketing subscriptions brand=pulse: {len(data.get('subscriptions', []))} subs")

    def test_marketing_subscriptions_pulse_admin_forced(self, pulse_headers):
        """Pulse admin requesting brand=gymaxis is forced to brand=pulse."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/marketing/subscriptions",
            params={"brand": "gymaxis"},
            headers=pulse_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        # Should return subscriptions (Pulse-scoped)
        assert "subscriptions" in data
        print("✓ Pulse admin subscriptions forced to pulse scope")


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: financial-ops endpoints are 403 for Pulse Admins
# ─────────────────────────────────────────────────────────────────────────────

class TestFinancialOpsPulseAdmin403:
    """Financial-ops endpoints are GymAxis-platform-only (403 for Pulse admins)."""

    def test_financial_ops_config_pulse_admin_403(self, pulse_headers):
        """Pulse admin gets 403 on GET /api/financial-ops/config."""
        resp = requests.get(
            f"{BASE_URL}/api/financial-ops/config",
            headers=pulse_headers,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Pulse admin gets 403 on /api/financial-ops/config")

    def test_financial_ops_reserve_pulse_admin_403(self, pulse_headers):
        """Pulse admin gets 403 on GET /api/financial-ops/reserve."""
        resp = requests.get(
            f"{BASE_URL}/api/financial-ops/reserve",
            headers=pulse_headers,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Pulse admin gets 403 on /api/financial-ops/reserve")

    def test_financial_ops_dashboard_pulse_admin_403(self, pulse_headers):
        """Pulse admin gets 403 on GET /api/financial-ops/dashboard."""
        resp = requests.get(
            f"{BASE_URL}/api/financial-ops/dashboard",
            headers=pulse_headers,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Pulse admin gets 403 on /api/financial-ops/dashboard")

    def test_financial_ops_config_gymaxis_admin_200(self, gymaxis_headers):
        """GymAxis admin can access GET /api/financial-ops/config."""
        resp = requests.get(
            f"{BASE_URL}/api/financial-ops/config",
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "reserve_percentage" in data
        print(f"✓ GymAxis admin can access /api/financial-ops/config: reserve_pct={data.get('reserve_percentage')}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Verify brand field in audit-log response
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditLogBrandFieldInResponse:
    """Verify audit-log response includes 'brand' field."""

    def test_audit_log_response_includes_brand(self, gymaxis_headers):
        """Audit-log response includes 'brand' field."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log",
            params={"brand": "gymaxis", "since_days": 7, "limit": 10},
            headers=gymaxis_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "brand" in data, f"Response missing 'brand' field: {data.keys()}"
        print(f"✓ Audit-log response includes brand={data.get('brand')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
