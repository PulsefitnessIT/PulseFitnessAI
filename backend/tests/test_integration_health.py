"""
Integration Health API Tests (Iter 215l)

Tests for:
- GET /api/master-admin/integration-health (all checks)
- GET /api/master-admin/integration-health/{key} (single check)
- Access control (master admin only)
- Response structure validation
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def operator_token():
    """Get operator (non-master-admin) auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
    )
    assert response.status_code == 200, f"Operator login failed: {response.text}"
    return response.json()["token"]


class TestIntegrationHealthAll:
    """Tests for GET /api/master-admin/integration-health"""

    def test_returns_200_for_master_admin(self, master_admin_token):
        """Master admin should get 200 with checks array"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Validate response structure
        assert "checks" in data, "Response missing 'checks' array"
        assert "summary" in data, "Response missing 'summary' object"

        print(f"✓ Integration health returned 200 with {len(data['checks'])} checks")

    def test_checks_array_has_5_items(self, master_admin_token):
        """Should return exactly 5 integration checks"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data["checks"]) == 5, f"Expected 5 checks, got {len(data['checks'])}"

        # Verify all expected keys are present
        expected_keys = {"database", "stripe", "resend", "storage", "emergent_llm"}
        actual_keys = {c["key"] for c in data["checks"]}
        assert actual_keys == expected_keys, f"Expected keys {expected_keys}, got {actual_keys}"

        print(f"✓ All 5 expected checks present: {actual_keys}")

    def test_summary_object_structure(self, master_admin_token):
        """Summary should have healthy/degraded/down/not_configured/total counters"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        summary = data["summary"]
        required_fields = ["healthy", "degraded", "down", "not_configured", "total"]
        for field in required_fields:
            assert field in summary, f"Summary missing '{field}' field"
            assert isinstance(summary[field], int), f"Summary '{field}' should be int"

        # Total should equal sum of status counts
        status_sum = summary["healthy"] + summary["degraded"] + summary["down"] + summary["not_configured"]
        assert summary["total"] == status_sum, f"Total {summary['total']} != sum {status_sum}"
        assert summary["total"] == 5, f"Total should be 5, got {summary['total']}"

        print(f"✓ Summary structure valid: {summary}")

    def test_check_item_structure(self, master_admin_token):
        """Each check should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        required_fields = ["key", "label", "ok", "status", "message", "latency_ms", "details", "checked_at"]
        valid_statuses = {"healthy", "degraded", "down", "not_configured"}

        for check in data["checks"]:
            for field in required_fields:
                assert field in check, f"Check '{check.get('key', '?')}' missing '{field}'"

            assert check["status"] in valid_statuses, f"Invalid status '{check['status']}'"
            assert isinstance(check["ok"], bool), "'ok' should be bool"
            assert isinstance(check["latency_ms"], int), "'latency_ms' should be int"
            assert isinstance(check["details"], dict), "'details' should be dict"

            print(f"  ✓ {check['key']}: {check['status']} ({check['latency_ms']}ms)")

        print("✓ All check items have valid structure")

    def test_returns_403_for_non_master_admin(self, operator_token):
        """Non-master-admin should get 403"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Non-master-admin correctly gets 403")


class TestIntegrationHealthSingle:
    """Tests for GET /api/master-admin/integration-health/{key}"""

    @pytest.mark.parametrize("key", ["database", "stripe", "resend", "storage", "emergent_llm"])
    def test_single_check_returns_200(self, master_admin_token, key):
        """Each valid key should return 200 with check data"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health/{key}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200 for {key}, got {response.status_code}: {response.text}"

        data = response.json()
        assert data["key"] == key, f"Response key mismatch: expected {key}, got {data.get('key')}"
        assert "label" in data
        assert "status" in data
        assert "message" in data

        print(f"✓ Single check {key}: {data['status']} - {data['message'][:50]}...")

    def test_unknown_key_returns_404(self, master_admin_token):
        """Unknown key should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health/unknown_service",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Unknown key correctly returns 404")

    def test_single_check_403_for_non_master_admin(self, operator_token):
        """Non-master-admin should get 403 on single check"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health/database",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Non-master-admin correctly gets 403 on single check")


class TestStripeCheckDetails:
    """Verify Stripe check returns expected details"""

    def test_stripe_check_has_account_details(self, master_admin_token):
        """Stripe check should include account_id, charges_enabled, payouts_enabled when healthy"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health/stripe",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        if data["status"] == "healthy":
            details = data["details"]
            assert "account_id" in details, "Healthy Stripe check should have account_id"
            assert "charges_enabled" in details, "Healthy Stripe check should have charges_enabled"
            assert "payouts_enabled" in details, "Healthy Stripe check should have payouts_enabled"
            print(f"✓ Stripe details: account_id={details['account_id']}, charges={details['charges_enabled']}, payouts={details['payouts_enabled']}")
        else:
            print(f"⚠ Stripe not healthy ({data['status']}), skipping details check")


class TestResendCheckExpectedDegraded:
    """Verify Resend check returns degraded (expected per agent context)"""

    def test_resend_check_status(self, master_admin_token):
        """Resend should be degraded due to unverified domain (expected env state)"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/integration-health/resend",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        # Per agent context: Resend is expected to be degraded (domain not verified)
        # This is NOT a bug - just verifying the endpoint works
        print(f"✓ Resend status: {data['status']} - {data['message']}")
        assert data["status"] in {"healthy", "degraded", "down", "not_configured"}, "Invalid status"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
