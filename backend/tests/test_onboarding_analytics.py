"""
Test Onboarding Analytics Summary Endpoint
Tests for GET /api/onboarding-packets/analytics/summary
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
NON_ADMIN_EMAIL = os.environ.get("TEST_NON_ADMIN_EMAIL", "lee.somers@pulsefitness.com")
NON_ADMIN_PASSWORD = os.environ.get("TEST_NON_ADMIN_PASSWORD", "TempPass123!")


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Master admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def non_admin_token():
    """Get non-admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": NON_ADMIN_EMAIL,
        "password": NON_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Non-admin login failed: {response.status_code} - {response.text}")


class TestOnboardingAnalyticsSummary:
    """Tests for GET /api/onboarding-packets/analytics/summary"""

    def test_analytics_summary_returns_expected_keys(self, master_admin_token):
        """Analytics summary should return all expected keys"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/analytics/summary", headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Verify all required keys are present
        required_keys = [
            "total", "by_status", "draft", "submitted", "provisioned", "rejected",
            "avg_provision_hours", "avg_review_hours", "created_7d", "created_30d",
            "provisioned_7d", "oldest_unprovisioned"
        ]

        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

        # Verify data types
        assert isinstance(data["total"], int), "total should be int"
        assert isinstance(data["by_status"], dict), "by_status should be dict"
        assert isinstance(data["draft"], int), "draft should be int"
        assert isinstance(data["submitted"], int), "submitted should be int"
        assert isinstance(data["provisioned"], int), "provisioned should be int"
        assert isinstance(data["rejected"], int), "rejected should be int"
        assert isinstance(data["avg_provision_hours"], (int, float)), "avg_provision_hours should be numeric"
        assert isinstance(data["avg_review_hours"], (int, float)), "avg_review_hours should be numeric"
        assert isinstance(data["created_7d"], int), "created_7d should be int"
        assert isinstance(data["created_30d"], int), "created_30d should be int"
        assert isinstance(data["provisioned_7d"], int), "provisioned_7d should be int"

        print(f"Analytics summary: total={data['total']}, draft={data['draft']}, submitted={data['submitted']}, provisioned={data['provisioned']}")

    def test_analytics_summary_403_for_non_admin(self, non_admin_token):
        """Non-admin users should get 403 Forbidden"""
        headers = {"Authorization": f"Bearer {non_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/analytics/summary", headers=headers)

        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}: {response.text}"
        print("Non-admin correctly received 403 Forbidden")

    def test_analytics_summary_401_or_403_without_auth(self):
        """Request without auth should get 401 or 403"""
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/analytics/summary")

        assert response.status_code in [401, 403], f"Expected 401 or 403 without auth, got {response.status_code}"
        print(f"Unauthenticated request correctly received {response.status_code}")


class TestOnboardingPacketsListRegression:
    """Regression tests for GET /api/onboarding-packets (list)"""

    def test_list_packets_returns_expected_structure(self, master_admin_token):
        """List packets should return {packets, count} with share_url and counts"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/onboarding-packets", headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Verify structure
        assert "packets" in data, "Response should have 'packets' key"
        assert "count" in data, "Response should have 'count' key"
        assert isinstance(data["packets"], list), "packets should be a list"
        assert isinstance(data["count"], int), "count should be int"
        assert data["count"] == len(data["packets"]), "count should match packets length"

        # If there are packets, verify each has share_url and counts
        if data["packets"]:
            packet = data["packets"][0]
            assert "share_url" in packet, "Each packet should have share_url"
            assert "counts" in packet, "Each packet should have counts"
            assert isinstance(packet["counts"], dict), "counts should be a dict"

            # Verify counts structure
            expected_count_keys = ["sites", "staff", "equipment", "suppliers", "contracts"]
            for key in expected_count_keys:
                assert key in packet["counts"], f"counts should have '{key}'"

            print(f"List packets: {data['count']} packets found, first packet has share_url and counts")
        else:
            print("List packets: 0 packets found (empty list)")


class TestOnboardingPacketsCreateRegression:
    """Regression tests for POST /api/onboarding-packets"""

    def test_create_packet_works(self, master_admin_token):
        """Create packet should work and return expected structure"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        # Create a test packet
        create_payload = {
            "customer_display_name": "TEST_Analytics_Test_Gym",
            "target_tier": "pro"
        }

        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json=create_payload, headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Verify structure
        assert "id" in data, "Response should have 'id'"
        assert "token" in data, "Response should have 'token'"
        assert "share_url" in data, "Response should have 'share_url'"
        assert "status" in data, "Response should have 'status'"
        assert data["status"] == "draft", "New packet should be in draft status"
        assert data["customer_display_name"] == "TEST_Analytics_Test_Gym"

        print(f"Created test packet: id={data['id']}, status={data['status']}")

        # Cleanup - delete the test packet
        packet_id = data["id"]
        delete_response = requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=headers)
        assert delete_response.status_code == 200, f"Cleanup failed: {delete_response.status_code}"
        print(f"Cleaned up test packet: {packet_id}")


class TestAnalyticsByStatusConsistency:
    """Verify analytics by_status matches individual counts"""

    def test_by_status_matches_individual_counts(self, master_admin_token):
        """by_status dict values should match individual draft/submitted/provisioned/rejected counts"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/analytics/summary", headers=headers)

        assert response.status_code == 200
        data = response.json()

        # Verify consistency
        by_status = data["by_status"]

        assert data["draft"] == by_status.get("draft", 0), "draft count mismatch"
        assert data["submitted"] == by_status.get("submitted", 0), "submitted count mismatch"
        assert data["provisioned"] == by_status.get("provisioned", 0), "provisioned count mismatch"
        assert data["rejected"] == by_status.get("rejected", 0), "rejected count mismatch"

        # Total should be sum of all statuses
        total_from_status = sum(by_status.values())
        assert data["total"] == total_from_status, f"total ({data['total']}) should equal sum of by_status ({total_from_status})"

        print(f"Analytics consistency verified: total={data['total']}, by_status={by_status}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
