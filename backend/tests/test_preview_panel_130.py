"""
Test Suite for Onboarding Packet Preview Panel - Iteration 130
Tests the new GET /api/onboarding-packets/{id}/preview endpoint
and related validation logic.
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials (loaded from env with local-dev fallbacks)
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
NON_ADMIN_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
NON_ADMIN_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def non_admin_token():
    """Get non-admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": NON_ADMIN_EMAIL,
        "password": NON_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Non-admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    """Headers with master admin auth"""
    return {"Authorization": f"Bearer {master_admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def non_admin_headers(non_admin_token):
    """Headers with non-admin auth"""
    return {"Authorization": f"Bearer {non_admin_token}", "Content-Type": "application/json"}


class TestPreviewEndpointEmptyPacket:
    """Test preview endpoint with empty packet - should return errors"""

    @pytest.fixture(autouse=True)
    def setup_empty_packet(self, master_admin_headers):
        """Create an empty packet for testing"""
        # Create empty packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_EMPTY_PREVIEW_{uuid.uuid4().hex[:8]}",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 14
        }, headers=master_admin_headers)
        assert response.status_code == 200, f"Failed to create packet: {response.text}"
        self.packet = response.json()
        self.packet_id = self.packet["id"]
        yield
        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{self.packet_id}", headers=master_admin_headers)

    def test_empty_packet_preview_returns_not_ready(self, master_admin_headers):
        """Empty packet should return ready=false with 6 errors"""
        response = requests.get(
            f"{BASE_URL}/api/onboarding-packets/{self.packet_id}/preview",
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Preview failed: {response.text}"
        data = response.json()

        # Verify ready=false
        assert data["ready"] == False, "Empty packet should not be ready"
        assert data["already_provisioned"] == False

        # Verify errors array has expected items
        errors = data["errors"]
        assert len(errors) >= 6, f"Expected at least 6 errors, got {len(errors)}: {errors}"

        # Check for specific required errors
        error_text = " ".join(errors).lower()
        assert "legal name" in error_text, "Should require legal name"
        assert "postcode" in error_text, "Should require postcode"
        assert "primary contact email" in error_text, "Should require primary contact email"
        assert "site" in error_text, "Should require at least 1 site"
        assert "staff" in error_text, "Should require at least 1 staff"
        assert "owner" in error_text, "Should require owner role"

        # Verify plan object has zero counts
        plan = data["plan"]
        assert plan["counts"]["sites"] == 0
        assert plan["counts"]["staff"] == 0
        assert plan["counts"]["equipment"] == 0
        assert plan["counts"]["suppliers"] == 0
        assert plan["counts"]["contracts"] == 0

        print(f"PASS: Empty packet preview returns {len(errors)} errors, ready=false")


class TestPreviewEndpointFullyPopulatedPacket:
    """Test preview endpoint with fully populated valid packet"""

    @pytest.fixture(autouse=True)
    def setup_full_packet(self, master_admin_headers):
        """Create a fully populated packet for testing"""
        unique_id = uuid.uuid4().hex[:8]

        # Create packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_FULL_PREVIEW_{unique_id}",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 14
        }, headers=master_admin_headers)
        assert response.status_code == 200
        self.packet = response.json()
        self.packet_id = self.packet["id"]

        # Populate with valid data
        update_data = {
            "organisation": {
                "legal_name": f"Test Legal Name {unique_id}",
                "trading_name": f"Test Trading Name {unique_id}",
                "vat_number": "GB123456789",
                "company_number": "12345678",
                "billing_address_line1": "123 Test Street",
                "billing_city": "London",
                "billing_postcode": "SW1A 1AA",
                "billing_country": "United Kingdom",
                "primary_contact_name": "John Doe",
                "primary_contact_email": f"test_{unique_id}@example.com",
                "primary_contact_phone": "+44 20 1234 5678"
            },
            "sites": [
                {
                    "name": "Main Site",
                    "address_line1": "456 Site Road",
                    "city": "Manchester",
                    "postcode": "M1 1AA",
                    "on_site_contact_name": "Jane Smith",
                    "on_site_contact_phone": "+44 161 123 4567"
                }
            ],
            "staff": [
                {
                    "full_name": "Owner User",
                    "email": f"owner_{unique_id}@example.com",
                    "phone": "+44 7700 900000",
                    "role": "owner",
                    "default_site_index": 0
                },
                {
                    "full_name": "Manager User",
                    "email": f"manager_{unique_id}@example.com",
                    "phone": "+44 7700 900001",
                    "role": "manager",
                    "default_site_index": 0
                }
            ],
            "equipment": [
                {
                    "name": "Treadmill 1",
                    "equipment_type": "Cardio",
                    "brand": "Life Fitness",
                    "model": "T5",
                    "serial_number": "LF-T5-001",
                    "site_index": 0
                }
            ],
            "suppliers": [
                {
                    "name": "Equipment Supplier Ltd",
                    "contact_email": "supplier@example.com",
                    "phone": "+44 20 9876 5432"
                }
            ]
        }

        response = requests.put(
            f"{BASE_URL}/api/onboarding-packets/{self.packet_id}",
            json=update_data,
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Failed to update packet: {response.text}"

        yield
        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{self.packet_id}", headers=master_admin_headers)

    def test_full_packet_preview_returns_ready(self, master_admin_headers):
        """Fully populated packet should return ready=true"""
        response = requests.get(
            f"{BASE_URL}/api/onboarding-packets/{self.packet_id}/preview",
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Preview failed: {response.text}"
        data = response.json()

        # Verify ready=true
        assert data["ready"] == True, f"Full packet should be ready, errors: {data.get('errors')}"
        assert data["already_provisioned"] == False
        assert len(data["errors"]) == 0, f"Should have no errors: {data['errors']}"

        # Verify warnings array is populated (advisory notes)
        warnings = data["warnings"]
        assert isinstance(warnings, list), "Warnings should be a list"
        # Warnings are advisory, so we just check they exist
        print(f"PASS: Full packet has {len(warnings)} advisory warnings")

        # Verify plan counts are correct
        plan = data["plan"]
        assert plan["counts"]["sites"] == 1
        assert plan["counts"]["staff"] == 2
        assert plan["counts"]["equipment"] == 1
        assert plan["counts"]["suppliers"] == 1

        # Verify will_send_magic_links_to contains staff emails
        magic_links = plan.get("will_send_magic_links_to", [])
        assert len(magic_links) == 2, f"Should have 2 magic link emails, got {len(magic_links)}"

        # Verify role breakdown
        role_breakdown = plan.get("role_breakdown", {})
        assert role_breakdown.get("owner") == 1, "Should have 1 owner"
        assert role_breakdown.get("manager") == 1, "Should have 1 manager"

        print(f"PASS: Full packet preview ready=true, counts correct, {len(magic_links)} magic links")


class TestPreviewEndpointProvisionedPacket:
    """Test preview endpoint with already provisioned packet"""

    def test_provisioned_packet_returns_already_provisioned(self, master_admin_headers):
        """Provisioned packet should return ready=false, already_provisioned=true"""
        unique_id = uuid.uuid4().hex[:8]

        # Create and populate a packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_PROVISION_PREVIEW_{unique_id}",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 14
        }, headers=master_admin_headers)
        assert response.status_code == 200
        packet_id = response.json()["id"]

        # Populate with valid data
        update_data = {
            "organisation": {
                "legal_name": f"Provision Test {unique_id}",
                "billing_postcode": "SW1A 1AA",
                "primary_contact_email": f"provision_{unique_id}@example.com"
            },
            "sites": [{"name": "Test Site", "postcode": "M1 1AA"}],
            "staff": [{"full_name": "Test Owner", "email": f"owner_prov_{unique_id}@example.com", "role": "owner"}]
        }
        requests.put(f"{BASE_URL}/api/onboarding-packets/{packet_id}", json=update_data, headers=master_admin_headers)

        # Provision the packet
        prov_response = requests.post(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/provision",
            json={},
            headers=master_admin_headers
        )
        assert prov_response.status_code == 200, f"Provision failed: {prov_response.text}"
        org_id = prov_response.json().get("organization_id")

        # Now test preview
        preview_response = requests.get(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/preview",
            headers=master_admin_headers
        )
        assert preview_response.status_code == 200
        data = preview_response.json()

        assert data["ready"] == False, "Provisioned packet should not be ready"
        assert data["already_provisioned"] == True, "Should indicate already provisioned"

        print("PASS: Provisioned packet returns ready=false, already_provisioned=true")

        # Cleanup - delete org and related data
        if org_id:
            requests.delete(f"{BASE_URL}/api/organizations/{org_id}", headers=master_admin_headers)


class TestPreviewEndpointAccessControl:
    """Test access control for preview endpoint"""

    @pytest.fixture(autouse=True)
    def setup_packet(self, master_admin_headers):
        """Create a packet for access control testing"""
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_ACCESS_{uuid.uuid4().hex[:8]}",
            "target_tier": "pro"
        }, headers=master_admin_headers)
        assert response.status_code == 200
        self.packet_id = response.json()["id"]
        yield
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{self.packet_id}", headers=master_admin_headers)

    def test_non_existent_packet_returns_404(self, master_admin_headers):
        """Non-existent packet should return 404"""
        fake_id = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/onboarding-packets/{fake_id}/preview",
            headers=master_admin_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Non-existent packet returns 404")

    def test_non_admin_returns_403(self, non_admin_headers):
        """Non-master-admin should get 403"""
        response = requests.get(
            f"{BASE_URL}/api/onboarding-packets/{self.packet_id}/preview",
            headers=non_admin_headers
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: Non-admin returns 403")


class TestPreviewEndpointEmailCollision:
    """Test preview endpoint with email collision detection"""

    def test_email_collision_populates_conflicts(self, master_admin_headers):
        """Staff email already in db.users should populate conflicts array"""
        unique_id = uuid.uuid4().hex[:8]

        # Create packet with staff email that already exists (master admin email)
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_COLLISION_{unique_id}",
            "target_tier": "pro"
        }, headers=master_admin_headers)
        assert response.status_code == 200
        packet_id = response.json()["id"]

        # Update with existing user email
        update_data = {
            "organisation": {
                "legal_name": f"Collision Test {unique_id}",
                "billing_postcode": "SW1A 1AA",
                "primary_contact_email": f"collision_{unique_id}@example.com"
            },
            "sites": [{"name": "Test Site", "postcode": "M1 1AA"}],
            "staff": [
                {"full_name": "Existing User", "email": MASTER_ADMIN_EMAIL, "role": "owner"},
                {"full_name": "New User", "email": f"new_{unique_id}@example.com", "role": "manager"}
            ]
        }
        requests.put(f"{BASE_URL}/api/onboarding-packets/{packet_id}", json=update_data, headers=master_admin_headers)

        # Get preview
        preview_response = requests.get(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/preview",
            headers=master_admin_headers
        )
        assert preview_response.status_code == 200
        data = preview_response.json()

        # Check conflicts array
        conflicts = data.get("conflicts", [])
        assert len(conflicts) >= 1, f"Should have at least 1 conflict, got {conflicts}"
        assert MASTER_ADMIN_EMAIL in conflicts, f"Should contain {MASTER_ADMIN_EMAIL}"

        # Check warning about collisions
        warnings = data.get("warnings", [])
        warning_messages = [w.get("message", "") for w in warnings]
        collision_warning = any("already exist" in msg.lower() for msg in warning_messages)
        assert collision_warning, f"Should have collision warning in: {warning_messages}"

        print(f"PASS: Email collision detected, conflicts={conflicts}")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=master_admin_headers)


class TestRegressionExistingFlows:
    """Regression tests for existing provision/reject/delete flows"""

    def test_provision_flow_still_works(self, master_admin_headers):
        """Existing provision flow should still work"""
        unique_id = uuid.uuid4().hex[:8]

        # Create and populate packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_REGRESSION_PROV_{unique_id}",
            "target_tier": "pro",
            "is_trial": True
        }, headers=master_admin_headers)
        assert response.status_code == 200
        packet_id = response.json()["id"]

        # Populate
        update_data = {
            "organisation": {
                "legal_name": f"Regression Provision {unique_id}",
                "billing_postcode": "SW1A 1AA",
                "primary_contact_email": f"regprov_{unique_id}@example.com"
            },
            "sites": [{"name": "Regression Site", "postcode": "M1 1AA"}],
            "staff": [{"full_name": "Regression Owner", "email": f"regowner_{unique_id}@example.com", "role": "owner"}]
        }
        requests.put(f"{BASE_URL}/api/onboarding-packets/{packet_id}", json=update_data, headers=master_admin_headers)

        # Provision
        prov_response = requests.post(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/provision",
            json={},
            headers=master_admin_headers
        )
        assert prov_response.status_code == 200, f"Provision failed: {prov_response.text}"
        assert prov_response.json().get("success") == True
        org_id = prov_response.json().get("organization_id")
        assert org_id is not None

        print(f"PASS: Provision flow works, org_id={org_id[:8]}...")

        # Cleanup
        if org_id:
            requests.delete(f"{BASE_URL}/api/organizations/{org_id}", headers=master_admin_headers)

    def test_reject_flow_still_works(self, master_admin_headers):
        """Existing reject flow should still work"""
        unique_id = uuid.uuid4().hex[:8]

        # Create packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_REGRESSION_REJ_{unique_id}",
            "target_tier": "pro"
        }, headers=master_admin_headers)
        assert response.status_code == 200
        packet_id = response.json()["id"]

        # Reject
        reject_response = requests.post(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/reject",
            json={"reason": "Test rejection"},
            headers=master_admin_headers
        )
        assert reject_response.status_code == 200
        assert reject_response.json().get("success") == True

        # Verify status
        get_response = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=master_admin_headers)
        assert get_response.json().get("status") == "rejected"

        print("PASS: Reject flow works")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=master_admin_headers)

    def test_delete_flow_still_works(self, master_admin_headers):
        """Existing delete flow should still work"""
        unique_id = uuid.uuid4().hex[:8]

        # Create packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_REGRESSION_DEL_{unique_id}",
            "target_tier": "pro"
        }, headers=master_admin_headers)
        assert response.status_code == 200
        packet_id = response.json()["id"]

        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}",
            headers=master_admin_headers
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("success") == True

        # Verify deleted
        get_response = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=master_admin_headers)
        assert get_response.status_code == 404

        print("PASS: Delete flow works")

    def test_send_email_flow_still_works(self, master_admin_headers):
        """Existing send email flow should still work"""
        unique_id = uuid.uuid4().hex[:8]

        # Create packet with email
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_REGRESSION_EMAIL_{unique_id}",
            "target_tier": "pro"
        }, headers=master_admin_headers)
        assert response.status_code == 200
        packet_id = response.json()["id"]

        # Update with primary contact email
        update_data = {
            "organisation": {
                "primary_contact_email": f"regemail_{unique_id}@example.com"
            }
        }
        requests.put(f"{BASE_URL}/api/onboarding-packets/{packet_id}", json=update_data, headers=master_admin_headers)

        # Send email
        email_response = requests.post(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/send-email",
            json={"email": f"regemail_{unique_id}@example.com"},
            headers=master_admin_headers
        )
        # Email may fail in test env but endpoint should work
        assert email_response.status_code in [200, 502], f"Unexpected status: {email_response.status_code}"

        print(f"PASS: Send email endpoint works (status={email_response.status_code})")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=master_admin_headers)


class TestOnboardingFunnelAnalytics:
    """Test onboarding funnel analytics endpoint (regression)"""

    def test_analytics_summary_endpoint(self, master_admin_headers):
        """Onboarding funnel analytics should still work"""
        response = requests.get(
            f"{BASE_URL}/api/onboarding-packets/analytics/summary",
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Analytics failed: {response.text}"
        data = response.json()

        # Verify expected fields
        assert "total" in data
        assert "by_status" in data
        assert "draft" in data
        assert "submitted" in data
        assert "provisioned" in data

        print(f"PASS: Analytics summary works, total={data['total']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
