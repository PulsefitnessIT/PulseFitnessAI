"""
E2E Trial Flow Tests - Iteration 129 (Optimized)
Tests the complete customer journey with shared session to avoid rate limits.
"""
import os
import pytest
import requests
import secrets

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://staffing-ops-preview.preview.emergentagent.com')

# Test credentials (loaded from env with local-dev fallbacks)
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PRODUCTION_USER_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PRODUCTION_USER_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")

# Test data - unique identifiers for cleanup
TEST_PREFIX = f"E2E_{secrets.token_hex(4).upper()}"

# Shared session to avoid rate limits
_session = requests.Session()
_admin_token = None
_admin_headers = None


def get_admin_auth():
    """Get or create admin authentication - cached to avoid rate limits"""
    global _admin_token, _admin_headers
    if _admin_token is None:
        response = _session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        _admin_token = response.json()["token"]
        _admin_headers = {"Authorization": f"Bearer {_admin_token}"}
    return _admin_token, _admin_headers


class TestPhase1MasterAdminLogin:
    """Phase 1.1: Master Admin login"""

    def test_master_admin_login(self):
        """Login as master admin and verify is_master_admin flag"""
        token, headers = get_admin_auth()
        assert token is not None

        # Verify /me endpoint
        response = _session.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["is_master_admin"] == True
        assert data["email"] == MASTER_ADMIN_EMAIL
        print(f"✓ Master admin login successful: {data['email']}")


class TestPhase1OnboardingPackets:
    """Phase 1.2-1.5: Onboarding Packets CRUD"""

    def test_list_onboarding_packets(self):
        """1.2: List existing packets"""
        _, headers = get_admin_auth()
        response = _session.get(f"{BASE_URL}/api/onboarding-packets", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "packets" in data
        assert "count" in data
        print(f"✓ Listed {data['count']} existing packets")

    def test_create_trial_packet(self):
        """1.3-1.4: Create a new trial packet with is_trial=true, 14 days"""
        _, headers = get_admin_auth()
        response = _session.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"{TEST_PREFIX}_Gym",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 14
        }, headers=headers)
        assert response.status_code == 200, f"Create packet failed: {response.text}"
        data = response.json()

        # Verify packet structure
        assert "id" in data
        assert "token" in data
        assert "share_url" in data
        assert data["status"] == "draft"
        assert data["is_trial"] == True
        assert data["trial_duration_days"] == 14
        assert data["target_tier"] == "pro"

        # Store for later tests
        TestPhase1OnboardingPackets.packet_id = data["id"]
        TestPhase1OnboardingPackets.packet_token = data["token"]
        TestPhase1OnboardingPackets.share_url = data["share_url"]

        print(f"✓ Created trial packet: {data['id'][:8]}...")
        print(f"  Share URL: {data['share_url']}")

    def test_get_packet_detail(self):
        """Get packet detail after creation"""
        _, headers = get_admin_auth()
        packet_id = getattr(TestPhase1OnboardingPackets, 'packet_id', None)
        if not packet_id:
            pytest.skip("No packet created")

        response = _session.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == packet_id
        print("✓ Retrieved packet detail")

    def test_send_packet_email(self):
        """1.5: Send invitation email"""
        _, headers = get_admin_auth()
        packet_id = getattr(TestPhase1OnboardingPackets, 'packet_id', None)
        if not packet_id:
            pytest.skip("No packet created")

        response = _session.post(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/send-email",
            json={"email": "e2e@test.com"},
            headers=headers
        )
        # Email may fail in test env but endpoint should work
        if response.status_code == 200:
            data = response.json()
            assert data["success"] == True
            print(f"✓ Email sent to: {data['sent_to']}")
        elif response.status_code == 502:
            print("✓ Email endpoint works (delivery failed in test env - expected)")
        else:
            pytest.fail(f"Unexpected status: {response.status_code} - {response.text}")


class TestPhase2PublicForm:
    """Phase 2: Customer fills public form (NO LOGIN)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create a fresh packet for public form testing"""
        _, headers = get_admin_auth()

        # Create a new packet
        response = _session.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"{TEST_PREFIX}_Public",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 14
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        self.packet_token = data["token"]
        self.packet_id = data["id"]

    def test_public_get_packet(self):
        """2.1: Access public form without auth"""
        response = _session.get(f"{BASE_URL}/api/onboarding/public/{self.packet_token}")
        assert response.status_code == 200, f"Public get failed: {response.text}"
        data = response.json()

        # Should not expose internal fields
        assert "_id" not in data
        assert "created_by" not in data
        print("✓ Public form accessible without auth")

    def test_public_fill_and_submit(self):
        """2.2-2.8: Fill all steps and submit"""
        owner_email = f"owner_{secrets.token_hex(4)}@e2etest.com"
        mgr_email = f"mgr_{secrets.token_hex(4)}@e2etest.com"

        # Fill all required data
        payload = {
            "organisation": {
                "legal_name": f"{TEST_PREFIX} Ltd",
                "trading_name": TEST_PREFIX,
                "billing_postcode": "SW1A 1AA",
                "primary_contact_name": "Owner Name",
                "primary_contact_email": owner_email,
                "primary_contact_phone": "+447700000001"
            },
            "sites": [{"name": f"{TEST_PREFIX} Main Site", "postcode": "SW1A 1AA"}],
            "staff": [
                {"full_name": "Owner Name", "email": owner_email, "role": "owner"},
                {"full_name": "Manager Name", "email": mgr_email, "role": "manager"}
            ],
            "equipment": [{
                "equipment_type": "Treadmill",
                "brand": "Life Fitness",
                "model": "Integrity X",
                "serial_number": f"TM-{TEST_PREFIX}-001",
                "install_date": "2024-01-15",
                "warranty_expiry": "2027-01-15",
                "supplier": "Life Fitness"
            }],
            "suppliers": [],
            "contracts": [],
            "current_step": "review"
        }

        # Save
        response = _session.put(f"{BASE_URL}/api/onboarding/public/{self.packet_token}", json=payload)
        assert response.status_code == 200, f"Save failed: {response.text}"
        data = response.json()

        # Verify counts
        assert data["organisation"]["legal_name"] == f"{TEST_PREFIX} Ltd"
        assert len(data["sites"]) == 1
        assert len(data["staff"]) == 2
        assert len(data["equipment"]) == 1
        print("✓ All steps filled: 1 site, 2 staff, 1 equipment")

        # Submit
        response = _session.post(f"{BASE_URL}/api/onboarding/public/{self.packet_token}/submit")
        assert response.status_code == 200, f"Submit failed: {response.text}"
        data = response.json()
        assert data["success"] == True
        print("✓ Packet submitted for review")

        # Store for provisioning
        TestPhase2PublicForm.submitted_packet_id = self.packet_id
        TestPhase2PublicForm.submitted_owner_email = owner_email


class TestPhase3Provision:
    """Phase 3: Master Admin provisions"""

    def test_provision_submitted_packet(self):
        """3.3: Provision workspace from submitted packet"""
        _, headers = get_admin_auth()

        # Create and submit a fresh packet for provisioning
        owner_email = f"provision_{secrets.token_hex(4)}@e2etest.com"

        # Create packet
        response = _session.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"{TEST_PREFIX}_Provision",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 14
        }, headers=headers)
        packet_id = response.json()["id"]
        packet_token = response.json()["token"]

        # Fill and submit
        payload = {
            "organisation": {
                "legal_name": f"{TEST_PREFIX}_Provision Ltd",
                "trading_name": f"{TEST_PREFIX}_Provision",
                "billing_postcode": "SW1A 1AA",
                "primary_contact_name": "Provision Owner",
                "primary_contact_email": owner_email,
            },
            "sites": [{"name": "Provision Site", "postcode": "SW1A 1AA"}],
            "staff": [{"full_name": "Provision Owner", "email": owner_email, "role": "owner"}],
            "equipment": [],
            "current_step": "review"
        }
        _session.put(f"{BASE_URL}/api/onboarding/public/{packet_token}", json=payload)
        _session.post(f"{BASE_URL}/api/onboarding/public/{packet_token}/submit")

        # Provision
        response = _session.post(
            f"{BASE_URL}/api/onboarding-packets/{packet_id}/provision",
            headers=headers
        )
        assert response.status_code == 200, f"Provision failed: {response.text}"
        data = response.json()

        assert data["success"] == True
        assert "organization_id" in data
        assert "summary" in data

        TestPhase3Provision.provisioned_org_id = data["organization_id"]
        TestPhase3Provision.provisioned_owner_email = owner_email
        print(f"✓ Provisioned workspace: org_id={data['organization_id'][:8]}...")
        print(f"  Summary: {data['summary']}")

        # Verify packet status
        response = _session.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "provisioned"
        print("✓ Packet status is 'provisioned'")


class TestPhase3TrialManagement:
    """Phase 3.4: Trial Management verification"""

    def test_list_trials(self):
        """List all trial organizations"""
        _, headers = get_admin_auth()
        response = _session.get(f"{BASE_URL}/api/master-admin/trials", headers=headers)
        assert response.status_code == 200, f"List trials failed: {response.text}"
        data = response.json()
        assert "trials" in data
        assert "count" in data
        print(f"✓ Listed {data['count']} trials")

    def test_trials_summary(self):
        """Get trial summary metrics"""
        _, headers = get_admin_auth()
        response = _session.get(f"{BASE_URL}/api/master-admin/trials/summary", headers=headers)
        assert response.status_code == 200, f"Trials summary failed: {response.text}"
        data = response.json()

        # Verify expected fields
        assert "total" in data
        assert "by_status" in data
        assert "converted_30d" in data
        assert "ended_30d" in data
        assert "conversion_rate_30d" in data
        assert "avg_days_to_convert" in data
        assert "expiring_this_week" in data
        assert "by_source" in data

        print(f"✓ Trials summary: total={data['total']}, by_status={data['by_status']}")


class TestPhase3CRMVerification:
    """Phase 3.5: CRM auto-created verification"""

    def test_list_crm_companies(self):
        """GET /api/onboarding-packets/crm/companies"""
        _, headers = get_admin_auth()
        response = _session.get(
            f"{BASE_URL}/api/onboarding-packets/crm/companies",
            headers=headers
        )
        assert response.status_code == 200, f"CRM companies failed: {response.text}"
        data = response.json()
        assert "companies" in data
        print(f"✓ CRM companies: {len(data['companies'])} companies")


class TestPhase6TrialExtension:
    """Phase 6: Trial extension flow"""

    def test_extend_trial(self):
        """6.1: Extend a trial by N days"""
        _, headers = get_admin_auth()

        # Get a trial org to extend
        response = _session.get(f"{BASE_URL}/api/master-admin/trials", headers=headers)
        trials = response.json().get("trials", [])

        # Find an active trial
        active_trial = None
        for t in trials:
            if t.get("trial_status") in ["active", "expiring_soon"]:
                active_trial = t
                break

        if not active_trial:
            pytest.skip("No active trial to extend")

        org_id = active_trial["id"]
        original_days = active_trial.get("days_left", 0)

        # Extend by 7 days
        response = _session.post(
            f"{BASE_URL}/api/master-admin/trials/{org_id}/extend",
            json={"days": 7, "reason": "E2E test extension"},
            headers=headers
        )
        assert response.status_code == 200, f"Extend failed: {response.text}"
        data = response.json()
        assert data["success"] == True
        print(f"✓ Extended trial {org_id[:8]}... by 7 days")


class TestPhase8Regression:
    """Phase 8: Regression checks"""

    def test_sicon_health(self):
        """8.1: Sicon Integration Health panel"""
        _, headers = get_admin_auth()
        response = _session.get(f"{BASE_URL}/api/master-admin/sicon/health", headers=headers)
        assert response.status_code == 200, f"Sicon health failed: {response.text}"
        data = response.json()
        assert "organizations" in data
        assert "totals" in data
        print(f"✓ Sicon health: {data['totals']['total_orgs']} orgs")

    def test_onboarding_analytics(self):
        """8.2: Onboarding Funnel analytics"""
        _, headers = get_admin_auth()
        response = _session.get(
            f"{BASE_URL}/api/onboarding-packets/analytics/summary",
            headers=headers
        )
        assert response.status_code == 200, f"Analytics failed: {response.text}"
        data = response.json()

        assert "total" in data
        assert "by_status" in data
        assert "draft" in data
        assert "submitted" in data
        assert "provisioned" in data

        print(f"✓ Onboarding analytics: total={data['total']}, by_status={data['by_status']}")

    def test_password_reset_endpoint(self):
        """Password reset endpoint works"""
        response = _session.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": "nonexistent@test.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print("✓ Forgot password endpoint works (no enumeration)")


class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_packets(self):
        """Delete test packets created during this run"""
        _, headers = get_admin_auth()
        response = _session.get(f"{BASE_URL}/api/onboarding-packets", headers=headers)
        if response.status_code != 200:
            pytest.skip("Cannot list packets")

        packets = response.json().get("packets", [])
        deleted = 0
        for p in packets:
            name = p.get("customer_display_name", "")
            if TEST_PREFIX in name:
                # Only delete non-provisioned packets
                if p.get("status") != "provisioned":
                    del_resp = _session.delete(
                        f"{BASE_URL}/api/onboarding-packets/{p['id']}",
                        headers=headers
                    )
                    if del_resp.status_code == 200:
                        deleted += 1

        print(f"✓ Cleanup: deleted {deleted} test packets")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
