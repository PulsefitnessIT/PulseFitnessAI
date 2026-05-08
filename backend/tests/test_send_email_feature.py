"""
Test suite for POST /api/onboarding-packets/{id}/send-email feature
Tests the send-to-customer email functionality for onboarding packets
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
NON_ADMIN_EMAIL = os.environ.get("TEST_NON_ADMIN_EMAIL", "lee.somers@pulsefitness.com")
NON_ADMIN_PASSWORD = os.environ.get("TEST_NON_ADMIN_PASSWORD", "TempPass123!")


class TestSendEmailFeature:
    """Tests for POST /api/onboarding-packets/{id}/send-email endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def get_master_admin_token(self):
        """Get master admin auth token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Master admin login failed: {response.text}"
        return response.json().get("token")

    def get_non_admin_token(self):
        """Get non-admin auth token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": NON_ADMIN_EMAIL,
            "password": NON_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Non-admin login failed: {response.text}"
        return response.json().get("token")

    def create_test_packet(self, token, with_email=True):
        """Create a test packet for testing"""
        headers = {"Authorization": f"Bearer {token}"}
        response = self.session.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_SendEmail_{uuid.uuid4().hex[:8]}",
            "target_tier": "pro"
        }, headers=headers)
        assert response.status_code == 200, f"Create packet failed: {response.text}"
        packet = response.json()

        # If we need to set primary_contact_email, update the packet
        if with_email:
            update_response = self.session.put(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}",
                json={
                    "organisation": {
                        "legal_name": "Test Company",
                        "billing_postcode": "SW1A 1AA",
                        "primary_contact_email": "test@example.com",
                        "primary_contact_name": "Test Contact"
                    }
                },
                headers=headers
            )
            assert update_response.status_code == 200, f"Update packet failed: {update_response.text}"
            return update_response.json()

        return packet

    def delete_test_packet(self, token, packet_id):
        """Clean up test packet"""
        headers = {"Authorization": f"Bearer {token}"}
        self.session.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=headers)

    # ── Test 1: Send email with master admin token - success ──
    def test_send_email_success(self):
        """POST /send-email with master admin token sends invite and returns success"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        packet = self.create_test_packet(token, with_email=True)

        try:
            response = self.session.post(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}/send-email",
                json={},
                headers=headers
            )

            assert response.status_code == 200, f"Send email failed: {response.text}"
            data = response.json()

            # Verify response structure
            assert "success" in data, "Response missing 'success' field"
            assert data["success"] == True, "success should be True"
            assert "sent_to" in data, "Response missing 'sent_to' field"
            assert "send_count" in data, "Response missing 'send_count' field"
            assert data["sent_to"] == "test@example.com", f"Expected sent_to='test@example.com', got '{data['sent_to']}'"
            assert data["send_count"] >= 1, "send_count should be >= 1"

            # Verify packet was updated with last_sent_at and last_sent_to
            get_response = self.session.get(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}",
                headers=headers
            )
            assert get_response.status_code == 200
            updated_packet = get_response.json()
            assert "last_sent_at" in updated_packet, "Packet missing last_sent_at"
            assert "last_sent_to" in updated_packet, "Packet missing last_sent_to"
            assert updated_packet["last_sent_to"] == "test@example.com"
            assert "email_sends" in updated_packet, "Packet missing email_sends array"
            assert len(updated_packet["email_sends"]) >= 1, "email_sends should have at least 1 entry"

            print(f"✓ Send email success: sent to {data['sent_to']}, count={data['send_count']}")
        finally:
            self.delete_test_packet(token, packet['id'])

    # ── Test 2: Send email with override email ──
    def test_send_email_with_override(self):
        """POST /send-email with body.email override uses override address"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        packet = self.create_test_packet(token, with_email=True)

        try:
            override_email = "override@example.com"
            response = self.session.post(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}/send-email",
                json={"email": override_email},
                headers=headers
            )

            assert response.status_code == 200, f"Send email with override failed: {response.text}"
            data = response.json()

            assert data["success"] == True
            assert data["sent_to"] == override_email, f"Expected sent_to='{override_email}', got '{data['sent_to']}'"

            print(f"✓ Send email with override: sent to {data['sent_to']}")
        finally:
            self.delete_test_packet(token, packet['id'])

    # ── Test 3: Send email with no recipient - 400 ──
    def test_send_email_no_recipient(self):
        """POST /send-email when packet has no primary_contact_email AND no override returns 400"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        packet = self.create_test_packet(token, with_email=False)  # No email set

        try:
            response = self.session.post(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}/send-email",
                json={},
                headers=headers
            )

            assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
            data = response.json()
            assert "No recipient email" in data.get("detail", ""), f"Expected 'No recipient email' in detail, got: {data}"

            print("✓ Send email with no recipient returns 400")
        finally:
            self.delete_test_packet(token, packet['id'])

    # ── Test 4: Send email on provisioned packet - 400 ──
    def test_send_email_provisioned_packet(self):
        """POST /send-email on a provisioned packet returns 400"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}

        # Find an existing provisioned packet or skip
        response = self.session.get(
            f"{BASE_URL}/api/onboarding-packets?status=provisioned",
            headers=headers
        )
        assert response.status_code == 200
        packets = response.json().get("packets", [])

        if not packets:
            pytest.skip("No provisioned packets available for testing")

        provisioned_packet = packets[0]

        response = self.session.post(
            f"{BASE_URL}/api/onboarding-packets/{provisioned_packet['id']}/send-email",
            json={"email": "test@example.com"},
            headers=headers
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "already provisioned" in data.get("detail", "").lower(), f"Expected 'already provisioned' in detail, got: {data}"

        print("✓ Send email on provisioned packet returns 400")

    # ── Test 5: Send email on missing packet - 404 ──
    def test_send_email_missing_packet(self):
        """POST /send-email on a missing packet returns 404"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}

        fake_id = str(uuid.uuid4())
        response = self.session.post(
            f"{BASE_URL}/api/onboarding-packets/{fake_id}/send-email",
            json={"email": "test@example.com"},
            headers=headers
        )

        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"

        print("✓ Send email on missing packet returns 404")

    # ── Test 6: Send email as non-master-admin - 403 ──
    def test_send_email_non_admin(self):
        """POST /send-email as non-master-admin returns 403"""
        # First create a packet as admin
        admin_token = self.get_master_admin_token()
        packet = self.create_test_packet(admin_token, with_email=True)

        try:
            # Try to send email as non-admin
            non_admin_token = self.get_non_admin_token()
            headers = {"Authorization": f"Bearer {non_admin_token}"}

            response = self.session.post(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}/send-email",
                json={},
                headers=headers
            )

            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

            print("✓ Send email as non-admin returns 403")
        finally:
            self.delete_test_packet(admin_token, packet['id'])

    # ── Test 7: Multiple sends append to email_sends array ──
    def test_multiple_sends_append(self):
        """Multiple sends append to email_sends array; send_count reflects total"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        packet = self.create_test_packet(token, with_email=True)

        try:
            # First send
            response1 = self.session.post(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}/send-email",
                json={},
                headers=headers
            )
            assert response1.status_code == 200
            data1 = response1.json()
            assert data1["send_count"] == 1, f"First send should have count=1, got {data1['send_count']}"

            # Second send with different email
            response2 = self.session.post(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}/send-email",
                json={"email": "second@example.com"},
                headers=headers
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["send_count"] == 2, f"Second send should have count=2, got {data2['send_count']}"

            # Third send
            response3 = self.session.post(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}/send-email",
                json={"email": "third@example.com"},
                headers=headers
            )
            assert response3.status_code == 200
            data3 = response3.json()
            assert data3["send_count"] == 3, f"Third send should have count=3, got {data3['send_count']}"

            # Verify email_sends array has all entries
            get_response = self.session.get(
                f"{BASE_URL}/api/onboarding-packets/{packet['id']}",
                headers=headers
            )
            assert get_response.status_code == 200
            updated_packet = get_response.json()

            assert len(updated_packet["email_sends"]) == 3, f"Expected 3 email_sends, got {len(updated_packet['email_sends'])}"

            # Verify each send has required fields
            for send in updated_packet["email_sends"]:
                assert "sent_at" in send, "email_send missing sent_at"
                assert "sent_to" in send, "email_send missing sent_to"
                assert "sent_by" in send, "email_send missing sent_by"

            print(f"✓ Multiple sends: email_sends has {len(updated_packet['email_sends'])} entries")
        finally:
            self.delete_test_packet(token, packet['id'])


class TestRegressionOnboardingPackets:
    """Regression tests for existing onboarding packet endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def get_master_admin_token(self):
        """Get master admin auth token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Master admin login failed: {response.text}"
        return response.json().get("token")

    # ── Regression Test: POST /api/onboarding-packets still works ──
    def test_create_packet_regression(self):
        """POST /api/onboarding-packets still creates packets correctly"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = self.session.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_Regression_{uuid.uuid4().hex[:8]}",
            "target_tier": "starter"
        }, headers=headers)

        assert response.status_code == 200, f"Create packet failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "id" in data, "Response missing 'id'"
        assert "token" in data, "Response missing 'token'"
        assert "share_url" in data, "Response missing 'share_url'"
        assert "status" in data, "Response missing 'status'"
        assert data["status"] == "draft", f"Expected status='draft', got '{data['status']}'"

        # Clean up
        self.session.delete(f"{BASE_URL}/api/onboarding-packets/{data['id']}", headers=headers)

        print("✓ POST /api/onboarding-packets regression passed")

    # ── Regression Test: GET /api/onboarding-packets still returns packets ──
    def test_list_packets_regression(self):
        """GET /api/onboarding-packets still returns packets list"""
        token = self.get_master_admin_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = self.session.get(f"{BASE_URL}/api/onboarding-packets", headers=headers)

        assert response.status_code == 200, f"List packets failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "packets" in data, "Response missing 'packets'"
        assert "count" in data, "Response missing 'count'"
        assert isinstance(data["packets"], list), "packets should be a list"
        assert data["count"] == len(data["packets"]), "count should match packets length"

        # Verify each packet has required fields
        if data["packets"]:
            packet = data["packets"][0]
            assert "id" in packet, "Packet missing 'id'"
            assert "share_url" in packet, "Packet missing 'share_url'"
            assert "counts" in packet, "Packet missing 'counts'"

        print(f"✓ GET /api/onboarding-packets regression passed: {data['count']} packets")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
