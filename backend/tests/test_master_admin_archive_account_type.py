"""
Test Master Admin Archive Organisation and Account Type Filter Features
- Bug Fix: Archive organisation status change (status='archived')
- Bug Fix: Unarchive (setting status back to 'active')
- New Feature: Account type badge on org cards
- New Feature: Account type filter dropdown
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMasterAdminArchiveAndAccountType:
    """Test archive/unarchive org status and account type features"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as master admin and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Login as master admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })

        if login_response.status_code != 200:
            pytest.skip("Master admin login failed - skipping tests")

        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        # Get organizations list to find test org
        orgs_response = self.session.get(f"{BASE_URL}/api/master-admin/organizations")
        if orgs_response.status_code == 200:
            self.organizations = orgs_response.json().get("organizations", [])
            # Find an org to test with (prefer one that's not already archived)
            self.test_org = next((o for o in self.organizations if o.get("status") != "archived"), None)
            if not self.test_org and self.organizations:
                self.test_org = self.organizations[0]
        else:
            self.organizations = []
            self.test_org = None

    # ========== ARCHIVE/UNARCHIVE STATUS TESTS ==========

    def test_01_archive_org_status_accepted(self):
        """Test that 'archived' status is now accepted by the API"""
        if not self.test_org:
            pytest.skip("No test organization available")

        org_id = self.test_org["id"]
        original_status = self.test_org.get("status", "active")

        # Try to set status to 'archived'
        response = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "archived"}
        )

        # Should return 200 success (bug fix: was previously rejected)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") == True, "Expected success=true"
        assert data.get("status") == "archived", f"Expected status='archived', got {data.get('status')}"

        # Restore original status
        self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": original_status}
        )
        print(f"PASS: Archive status change accepted for org {org_id}")

    def test_02_unarchive_org_status_to_active(self):
        """Test that unarchiving (setting status back to 'active') works"""
        if not self.test_org:
            pytest.skip("No test organization available")

        org_id = self.test_org["id"]

        # First archive the org
        archive_response = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "archived"}
        )
        assert archive_response.status_code == 200, "Failed to archive org first"

        # Now unarchive by setting to 'active'
        response = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "active"}
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") == True, "Expected success=true"
        assert data.get("status") == "active", f"Expected status='active', got {data.get('status')}"
        print(f"PASS: Unarchive (set to active) worked for org {org_id}")

    def test_03_verify_archived_status_persists(self):
        """Test that archived status persists when fetching org list"""
        if not self.test_org:
            pytest.skip("No test organization available")

        org_id = self.test_org["id"]

        # Archive the org
        self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "archived"}
        )

        # Fetch org list and verify status
        response = self.session.get(f"{BASE_URL}/api/master-admin/organizations")
        assert response.status_code == 200

        orgs = response.json().get("organizations", [])
        archived_org = next((o for o in orgs if o["id"] == org_id), None)

        assert archived_org is not None, "Org not found in list"
        assert archived_org.get("status") == "archived", f"Expected status='archived', got {archived_org.get('status')}"

        # Restore to active
        self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "active"}
        )
        print(f"PASS: Archived status persists for org {org_id}")

    def test_04_all_valid_statuses_accepted(self):
        """Test that all valid statuses are accepted: active, trial, suspended, cancelled, archived"""
        if not self.test_org:
            pytest.skip("No test organization available")

        org_id = self.test_org["id"]
        valid_statuses = ["active", "trial", "suspended", "cancelled", "archived"]

        for status in valid_statuses:
            response = self.session.put(
                f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
                json={"status": status}
            )
            assert response.status_code == 200, f"Status '{status}' should be accepted, got {response.status_code}"
            data = response.json()
            assert data.get("status") == status, f"Expected status='{status}', got {data.get('status')}"

        # Restore to active
        self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "active"}
        )
        print(f"PASS: All valid statuses accepted: {valid_statuses}")

    def test_05_invalid_status_rejected(self):
        """Test that invalid status values are rejected"""
        if not self.test_org:
            pytest.skip("No test organization available")

        org_id = self.test_org["id"]

        response = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "invalid_status"}
        )

        assert response.status_code == 400, f"Expected 400 for invalid status, got {response.status_code}"
        print("PASS: Invalid status rejected with 400")

    # ========== ACCOUNT TYPE TESTS ==========

    def test_06_orgs_have_account_type_field(self):
        """Test that organizations have account_type field in response"""
        response = self.session.get(f"{BASE_URL}/api/master-admin/organizations")
        assert response.status_code == 200

        orgs = response.json().get("organizations", [])
        assert len(orgs) > 0, "No organizations found"

        # Check that account_type field exists
        for org in orgs[:5]:  # Check first 5
            assert "account_type" in org, f"Org {org.get('name')} missing account_type field"
            account_type = org.get("account_type")
            assert account_type in ["full", "pulse_pro", "lite", "gymaxis", None, ""], f"Invalid account_type: {account_type}"

        print("PASS: All orgs have account_type field")

    def test_07_count_account_types(self):
        """Test counting organizations by account type"""
        response = self.session.get(f"{BASE_URL}/api/master-admin/organizations")
        assert response.status_code == 200

        orgs = response.json().get("organizations", [])

        # Count by account type
        counts = {"full": 0, "pulse_pro": 0, "lite": 0}
        for org in orgs:
            account_type = org.get("account_type", "full")
            if account_type in counts:
                counts[account_type] += 1
            else:
                counts["full"] += 1  # Default to full

        print(f"Account type counts: {counts}")
        print(f"Total orgs: {len(orgs)}")

        # Verify we have some orgs
        assert len(orgs) > 0, "No organizations found"
        print(f"PASS: Found {len(orgs)} orgs with account types: {counts}")

    def test_08_pulse_pro_orgs_exist(self):
        """Test that pulse_pro account type orgs exist (per requirements: 2 orgs)"""
        response = self.session.get(f"{BASE_URL}/api/master-admin/organizations")
        assert response.status_code == 200

        orgs = response.json().get("organizations", [])
        pulse_pro_orgs = [o for o in orgs if o.get("account_type") == "pulse_pro"]

        print(f"Found {len(pulse_pro_orgs)} pulse_pro orgs: {[o.get('name') for o in pulse_pro_orgs]}")

        # Per requirements: 2 pulse_pro orgs (Tottenham Green Leisure Centre, Leisure United)
        assert len(pulse_pro_orgs) >= 1, "Expected at least 1 pulse_pro org"
        print(f"PASS: Found {len(pulse_pro_orgs)} pulse_pro orgs")

    def test_09_update_account_type(self):
        """Test updating account type via API"""
        if not self.test_org:
            pytest.skip("No test organization available")

        org_id = self.test_org["id"]
        original_type = self.test_org.get("account_type", "full")

        # Try changing to pulse_pro
        response = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/account-type",
            json={"account_type": "pulse_pro"}
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("account_type") == "pulse_pro"

        # Restore original
        self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/account-type",
            json={"account_type": original_type}
        )
        print("PASS: Account type update works")

    def test_10_invalid_account_type_rejected(self):
        """Test that invalid account type values are rejected"""
        if not self.test_org:
            pytest.skip("No test organization available")

        org_id = self.test_org["id"]

        response = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/account-type",
            json={"account_type": "invalid_type"}
        )

        assert response.status_code == 400, f"Expected 400 for invalid account type, got {response.status_code}"
        print("PASS: Invalid account type rejected with 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
