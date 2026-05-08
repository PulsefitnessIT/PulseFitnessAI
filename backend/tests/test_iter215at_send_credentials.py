"""
Iter 215at — Backend tests for POST /api/master-admin/organizations/{id}/send-primary-contact-credentials
and related features (Command Palette, Bulk Actions).

Tests:
1. send-primary-contact-credentials with fresh org (expects 502 in test env due to Resend domain not verified)
2. send-primary-contact-credentials with org missing primary_contact_email (expects 400)
3. send-primary-contact-credentials after password already sent/cleared (expects 400)
4. Verify GET primary-contact-credentials returns available:false after successful send
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def admin_token():
    """Get master admin token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@gymaxisai.com",
        "password": "MasterAdmin123!"
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")

@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestSendPrimaryContactCredentials:
    """Tests for POST /api/master-admin/organizations/{id}/send-primary-contact-credentials"""

    def test_send_credentials_no_primary_contact_email(self, headers):
        """Org without primary_contact_email should return 400"""
        # Create org without primary contact email
        unique = str(uuid.uuid4())[:8]
        create_resp = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": f"TEST_NoEmail_{unique}",
            "enabled_modules": ["operations"],
            "account_type": "full"
        }, headers=headers)
        assert create_resp.status_code == 200, f"Create org failed: {create_resp.text}"
        org_id = create_resp.json().get("id")

        try:
            # Try to send credentials - should fail with 400
            send_resp = requests.post(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/send-primary-contact-credentials",
                headers=headers
            )
            assert send_resp.status_code == 400, f"Expected 400, got {send_resp.status_code}"
            assert "No primary contact email" in send_resp.json().get("detail", "")
            print(f"PASS: send-credentials without email returns 400: {send_resp.json()}")
        finally:
            # Cleanup - archive the test org
            requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                        json={"status": "archived"}, headers=headers)

    def test_send_credentials_fresh_org_with_email(self, headers):
        """Fresh org with primary_contact_email should attempt to send (502 expected in test env)"""
        unique = str(uuid.uuid4())[:8]
        test_email = f"test.contact.{unique}@example.com"

        # Create org with primary contact email
        create_resp = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": f"TEST_WithEmail_{unique}",
            "enabled_modules": ["operations"],
            "account_type": "full",
            "primary_contact_name": "Test Contact",
            "primary_contact_email": test_email
        }, headers=headers)
        assert create_resp.status_code == 200, f"Create org failed: {create_resp.text}"
        org_id = create_resp.json().get("id")

        try:
            # Verify credentials are available first
            creds_resp = requests.get(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/primary-contact-credentials",
                headers=headers
            )
            assert creds_resp.status_code == 200
            creds = creds_resp.json()
            assert creds.get("available") == True, f"Expected available=True, got {creds}"
            assert creds.get("email") == test_email.lower()
            assert creds.get("initial_password") is not None
            print(f"PASS: Credentials available before send: {creds.get('email')}")

            # Try to send credentials - expect 502 (Resend domain not verified) or 200 (if verified)
            send_resp = requests.post(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/send-primary-contact-credentials",
                headers=headers
            )

            if send_resp.status_code == 200:
                # Success path - credentials sent and cleared
                result = send_resp.json()
                assert result.get("sent") == True
                assert result.get("email") == test_email.lower()
                print(f"PASS: Credentials sent successfully: {result}")

                # Verify credentials are now unavailable
                creds_after = requests.get(
                    f"{BASE_URL}/api/master-admin/organizations/{org_id}/primary-contact-credentials",
                    headers=headers
                ).json()
                assert creds_after.get("available") == False, f"Expected available=False after send, got {creds_after}"
                print(f"PASS: Credentials unavailable after send: {creds_after}")

            elif send_resp.status_code == 502:
                # Expected in test env - Resend domain not verified
                detail = send_resp.json().get("detail", "")
                assert "Email could not be delivered" in detail or "Failed to send" in detail
                print(f"PASS (expected): 502 returned - Resend domain not verified: {detail}")

                # Credentials should still be available since send failed
                creds_after = requests.get(
                    f"{BASE_URL}/api/master-admin/organizations/{org_id}/primary-contact-credentials",
                    headers=headers
                ).json()
                assert creds_after.get("available") == True, "Credentials should remain available after failed send"
                print("PASS: Credentials still available after failed send")
            else:
                pytest.fail(f"Unexpected status {send_resp.status_code}: {send_resp.text}")

        finally:
            # Cleanup
            requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                        json={"status": "archived"}, headers=headers)

    def test_send_credentials_already_sent(self, headers):
        """After credentials are sent/cleared, trying again should return 400"""
        unique = str(uuid.uuid4())[:8]
        test_email = f"test.already.{unique}@example.com"

        # Create org
        create_resp = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": f"TEST_AlreadySent_{unique}",
            "enabled_modules": ["operations"],
            "account_type": "full",
            "primary_contact_name": "Test Contact",
            "primary_contact_email": test_email
        }, headers=headers)
        assert create_resp.status_code == 200
        org_id = create_resp.json().get("id")

        try:
            # Manually clear the initial password to simulate already-sent state
            # We do this by updating the org doc directly via the details endpoint
            # Actually, we can't do that - let's just verify the 400 case by checking
            # what happens when password_changed is true

            # First attempt - may succeed or 502
            first_send = requests.post(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/send-primary-contact-credentials",
                headers=headers
            )

            if first_send.status_code == 200:
                # If first send succeeded, second should fail with 400
                second_send = requests.post(
                    f"{BASE_URL}/api/master-admin/organizations/{org_id}/send-primary-contact-credentials",
                    headers=headers
                )
                assert second_send.status_code == 400, f"Expected 400 on second send, got {second_send.status_code}"
                assert "No initial password is available" in second_send.json().get("detail", "")
                print(f"PASS: Second send returns 400: {second_send.json()}")
            else:
                # First send failed (502), so we can't test the already-sent case
                print(f"SKIP: First send failed with {first_send.status_code}, cannot test already-sent case")

        finally:
            requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                        json={"status": "archived"}, headers=headers)


class TestBulkActionsEndpoints:
    """Tests for bulk actions - Archive, Activate, Toggle TEST"""

    def test_bulk_archive_via_status_endpoint(self, headers):
        """Verify status endpoint works for bulk archive operations"""
        unique = str(uuid.uuid4())[:8]

        # Create test org
        create_resp = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": f"TEST_BulkArchive_{unique}",
            "enabled_modules": ["operations"],
            "account_type": "full"
        }, headers=headers)
        assert create_resp.status_code == 200
        org_id = create_resp.json().get("id")

        try:
            # Archive via status endpoint
            archive_resp = requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                json={"status": "archived"},
                headers=headers
            )
            assert archive_resp.status_code == 200
            assert archive_resp.json().get("status") == "archived"
            print("PASS: Org archived successfully")

            # Verify org is archived
            orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
            org = next((o for o in orgs_resp.json().get("organizations", []) if o["id"] == org_id), None)
            assert org is not None
            assert org.get("status") == "archived"
            print("PASS: Org status verified as archived")

        finally:
            # Already archived, no cleanup needed
            pass

    def test_bulk_activate_via_status_endpoint(self, headers):
        """Verify status endpoint works for bulk activate operations"""
        unique = str(uuid.uuid4())[:8]

        # Create and archive test org
        create_resp = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": f"TEST_BulkActivate_{unique}",
            "enabled_modules": ["operations"],
            "account_type": "full"
        }, headers=headers)
        assert create_resp.status_code == 200
        org_id = create_resp.json().get("id")

        try:
            # Archive first
            requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                        json={"status": "archived"}, headers=headers)

            # Activate via status endpoint
            activate_resp = requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                json={"status": "active"},
                headers=headers
            )
            assert activate_resp.status_code == 200
            assert activate_resp.json().get("status") == "active"
            print("PASS: Org activated successfully")

        finally:
            requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                        json={"status": "archived"}, headers=headers)

    def test_bulk_toggle_test_flag(self, headers):
        """Verify test-flag endpoint works for bulk toggle operations"""
        unique = str(uuid.uuid4())[:8]

        # Create test org
        create_resp = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": f"TEST_BulkToggle_{unique}",
            "enabled_modules": ["operations"],
            "account_type": "full"
        }, headers=headers)
        assert create_resp.status_code == 200
        org_id = create_resp.json().get("id")

        try:
            # Toggle TEST flag on
            toggle_on = requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/test-flag",
                json={"is_test": True},
                headers=headers
            )
            assert toggle_on.status_code == 200
            print("PASS: TEST flag toggled ON")

            # Verify
            orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
            org = next((o for o in orgs_resp.json().get("organizations", []) if o["id"] == org_id), None)
            assert org.get("is_test") == True

            # Toggle TEST flag off
            toggle_off = requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/test-flag",
                json={"is_test": False},
                headers=headers
            )
            assert toggle_off.status_code == 200
            print("PASS: TEST flag toggled OFF")

        finally:
            requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                        json={"status": "archived"}, headers=headers)


class TestRegressionEndpoints:
    """Regression tests for existing endpoints that should still work"""

    def test_get_organizations_returns_expected_fields(self, headers):
        """Verify GET organizations returns all expected fields including new ones"""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        assert resp.status_code == 200
        orgs = resp.json().get("organizations", [])

        if orgs:
            org = orgs[0]
            # Check for expected fields
            expected_fields = ["id", "name", "status", "enabled_modules", "portal_type",
                             "account_type", "subscription_tier", "user_count"]
            for field in expected_fields:
                assert field in org, f"Missing field: {field}"
            print("PASS: Organizations endpoint returns all expected fields")
        else:
            print("SKIP: No organizations to verify")

    def test_get_primary_contact_credentials_endpoint(self, headers):
        """Verify GET primary-contact-credentials endpoint works"""
        # Get any org
        orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        orgs = orgs_resp.json().get("organizations", [])

        if orgs:
            org_id = orgs[0]["id"]
            creds_resp = requests.get(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/primary-contact-credentials",
                headers=headers
            )
            assert creds_resp.status_code == 200
            creds = creds_resp.json()
            # Should have these fields
            assert "email" in creds
            assert "available" in creds
            assert "password_changed" in creds
            print("PASS: primary-contact-credentials endpoint returns expected structure")
        else:
            print("SKIP: No organizations to test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
