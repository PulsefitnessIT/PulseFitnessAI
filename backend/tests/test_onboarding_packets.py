"""
Test suite for Customer Onboarding Packets feature
Tests Master Admin endpoints and Public (no-auth) endpoints
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
    """Get non-admin user auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": NON_ADMIN_EMAIL,
        "password": NON_ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Non-admin login failed: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(master_admin_token):
    """Headers with master admin auth"""
    return {"Authorization": f"Bearer {master_admin_token}"}


@pytest.fixture(scope="module")
def non_admin_headers(non_admin_token):
    """Headers with non-admin auth"""
    return {"Authorization": f"Bearer {non_admin_token}"}


# ═══════════════════════════════════════════════════════════════════
# MASTER ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

class TestMasterAdminCreatePacket:
    """POST /api/onboarding-packets — create packet"""

    def test_create_packet_success(self, admin_headers):
        """Create packet with valid data returns 200 with token and share_url"""
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Packet_Create",
            "target_tier": "pro"
        }, headers=admin_headers)

        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "id" in data, "Missing id in response"
        assert "token" in data, "Missing token in response"
        assert "share_url" in data, "Missing share_url in response"
        assert data["status"] == "draft", f"Expected status 'draft', got {data['status']}"
        assert data["target_tier"] == "pro", f"Expected tier 'pro', got {data['target_tier']}"
        assert data["customer_display_name"] == "TEST_Packet_Create"

        # Verify share_url contains token
        assert data["token"] in data["share_url"], "share_url should contain token"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{data['id']}", headers=admin_headers)
        print(f"✓ Create packet success - ID: {data['id'][:8]}...")

    def test_create_packet_invalid_tier(self, admin_headers):
        """Create packet with invalid tier returns 400"""
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Invalid_Tier",
            "target_tier": "invalid_tier"
        }, headers=admin_headers)

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "starter" in response.text.lower() or "pro" in response.text.lower() or "enterprise" in response.text.lower()
        print("✓ Invalid tier returns 400")

    def test_create_packet_all_tiers(self, admin_headers):
        """Create packet with each valid tier (starter, pro, enterprise)"""
        for tier in ["starter", "pro", "enterprise"]:
            response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
                "customer_display_name": f"TEST_Tier_{tier}",
                "target_tier": tier
            }, headers=admin_headers)

            assert response.status_code == 200, f"Create with tier '{tier}' failed: {response.text}"
            data = response.json()
            assert data["target_tier"] == tier

            # Cleanup
            requests.delete(f"{BASE_URL}/api/onboarding-packets/{data['id']}", headers=admin_headers)
        print("✓ All valid tiers (starter, pro, enterprise) work")


class TestMasterAdminListPackets:
    """GET /api/onboarding-packets — list packets"""

    def test_list_packets_success(self, admin_headers):
        """List packets returns {packets: [], count: N}"""
        response = requests.get(f"{BASE_URL}/api/onboarding-packets", headers=admin_headers)

        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()

        assert "packets" in data, "Missing 'packets' key"
        assert "count" in data, "Missing 'count' key"
        assert isinstance(data["packets"], list), "packets should be a list"
        assert data["count"] == len(data["packets"]), "count should match packets length"
        print(f"✓ List packets success - {data['count']} packets")

    def test_list_packets_with_status_filter(self, admin_headers):
        """List packets with ?status=draft filter"""
        # Create a draft packet first
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Filter_Draft",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]

        # Filter by draft status
        response = requests.get(f"{BASE_URL}/api/onboarding-packets?status=draft", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()

        # All returned packets should be draft
        for p in data["packets"]:
            assert p["status"] == "draft", f"Expected draft, got {p['status']}"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Status filter works")


class TestMasterAdminGetPacket:
    """GET /api/onboarding-packets/{id} — get single packet"""

    def test_get_packet_success(self, admin_headers):
        """Get packet by ID returns full packet data"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Get_Packet",
            "target_tier": "enterprise"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]

        # Get packet
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)

        assert response.status_code == 200, f"Get failed: {response.text}"
        data = response.json()

        assert data["id"] == packet_id
        assert data["customer_display_name"] == "TEST_Get_Packet"
        assert data["target_tier"] == "enterprise"
        assert "share_url" in data
        assert "organisation" in data
        assert "sites" in data
        assert "staff" in data
        assert "equipment" in data

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Get packet success")

    def test_get_packet_not_found(self, admin_headers):
        """Get non-existent packet returns 404"""
        fake_id = str(uuid.uuid4())
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/{fake_id}", headers=admin_headers)

        assert response.status_code == 404
        print("✓ Get non-existent packet returns 404")


class TestMasterAdminUpdatePacket:
    """PUT /api/onboarding-packets/{id} — update packet"""

    def test_update_packet_success(self, admin_headers):
        """Update packet fields"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Update_Original",
            "target_tier": "starter"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]

        # Update packet
        response = requests.put(f"{BASE_URL}/api/onboarding-packets/{packet_id}", json={
            "customer_display_name": "TEST_Update_Modified",
            "target_tier": "pro",
            "review_notes": "Updated by test"
        }, headers=admin_headers)

        assert response.status_code == 200, f"Update failed: {response.text}"
        data = response.json()

        assert data["customer_display_name"] == "TEST_Update_Modified"
        assert data["target_tier"] == "pro"
        assert data["review_notes"] == "Updated by test"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Update packet success")


class TestMasterAdminDeletePacket:
    """DELETE /api/onboarding-packets/{id} — delete packet"""

    def test_delete_packet_success(self, admin_headers):
        """Delete non-provisioned packet succeeds"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Delete_Me",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]

        # Delete packet
        response = requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)

        assert response.status_code == 200, f"Delete failed: {response.text}"
        assert response.json().get("success") == True

        # Verify deleted
        get_res = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        assert get_res.status_code == 404
        print("✓ Delete packet success")

    def test_delete_packet_not_found(self, admin_headers):
        """Delete non-existent packet returns 404"""
        fake_id = str(uuid.uuid4())
        response = requests.delete(f"{BASE_URL}/api/onboarding-packets/{fake_id}", headers=admin_headers)

        assert response.status_code == 404
        print("✓ Delete non-existent packet returns 404")


class TestMasterAdminRejectPacket:
    """POST /api/onboarding-packets/{id}/reject — reject packet"""

    def test_reject_packet_success(self, admin_headers):
        """Reject packet sets status=rejected and review_notes"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Reject_Me",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]

        # Reject packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets/{packet_id}/reject", json={
            "reason": "Missing required information"
        }, headers=admin_headers)

        assert response.status_code == 200, f"Reject failed: {response.text}"
        assert response.json().get("success") == True

        # Verify status changed
        get_res = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        data = get_res.json()
        assert data["status"] == "rejected"
        assert data["review_notes"] == "Missing required information"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Reject packet success")


class TestMasterAdminProvisionPacket:
    """POST /api/onboarding-packets/{id}/provision — provision packet"""

    def test_provision_without_required_fields_returns_400(self, admin_headers):
        """Provision packet without required fields returns 400 with errors"""
        # Create empty packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Provision_Empty",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]

        # Try to provision empty packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets/{packet_id}/provision",
                                 json={}, headers=admin_headers)

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()

        # Should have validation errors
        assert "detail" in data
        detail = data["detail"]
        if isinstance(detail, dict):
            assert "errors" in detail
            errors = detail["errors"]
            assert len(errors) > 0, "Should have validation errors"
            # Check for expected errors
            error_text = " ".join(errors).lower()
            assert "legal name" in error_text or "site" in error_text or "staff" in error_text or "owner" in error_text

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Provision without required fields returns 400 with errors")

    def test_provision_complete_packet_success(self, admin_headers):
        """Provision packet with all required fields succeeds"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Provision_Complete",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]
        token = create_res.json()["token"]

        # Fill in required data via public endpoint
        unique_suffix = str(uuid.uuid4())[:8]
        fill_data = {
            "organisation": {
                "legal_name": f"TEST Provision Org {unique_suffix}",
                "billing_postcode": "SW1A 1AA",
                "primary_contact_email": f"test.provision.{unique_suffix}@example.com"
            },
            "sites": [{
                "name": "Test Site 1",
                "postcode": "SW1A 1AA"
            }],
            "staff": [{
                "full_name": "Test Owner",
                "email": f"test.owner.{unique_suffix}@example.com",
                "role": "owner"
            }]
        }

        fill_res = requests.put(f"{BASE_URL}/api/onboarding/public/{token}", json=fill_data)
        assert fill_res.status_code == 200, f"Fill data failed: {fill_res.text}"

        # Provision packet
        response = requests.post(f"{BASE_URL}/api/onboarding-packets/{packet_id}/provision",
                                 json={}, headers=admin_headers)

        assert response.status_code == 200, f"Provision failed: {response.text}"
        data = response.json()

        assert data.get("success") == True
        assert "organization_id" in data
        assert "summary" in data

        # Verify packet status changed
        get_res = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        packet_data = get_res.json()
        assert packet_data["status"] == "provisioned"

        # Cannot delete provisioned packet
        del_res = requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        assert del_res.status_code == 400, "Should not be able to delete provisioned packet"

        print(f"✓ Provision complete packet success - Org ID: {data['organization_id'][:8]}...")


class TestMasterAdminCRMCompanies:
    """GET /api/onboarding-packets/crm/companies — CRM prefill dropdown"""

    def test_list_crm_companies(self, admin_headers):
        """List CRM companies for prefill dropdown"""
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/crm/companies", headers=admin_headers)

        assert response.status_code == 200, f"List CRM companies failed: {response.text}"
        data = response.json()

        assert "companies" in data
        assert isinstance(data["companies"], list)
        print(f"✓ List CRM companies success - {len(data['companies'])} companies")


class TestMasterAdminRBAC:
    """RBAC: All master admin endpoints return 403 for non-master-admin"""

    def test_create_packet_403_for_non_admin(self, non_admin_headers):
        """Create packet returns 403 for non-admin"""
        response = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_RBAC",
            "target_tier": "pro"
        }, headers=non_admin_headers)

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Create packet returns 403 for non-admin")

    def test_list_packets_403_for_non_admin(self, non_admin_headers):
        """List packets returns 403 for non-admin"""
        response = requests.get(f"{BASE_URL}/api/onboarding-packets", headers=non_admin_headers)

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ List packets returns 403 for non-admin")

    def test_crm_companies_403_for_non_admin(self, non_admin_headers):
        """CRM companies returns 403 for non-admin"""
        response = requests.get(f"{BASE_URL}/api/onboarding-packets/crm/companies", headers=non_admin_headers)

        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ CRM companies returns 403 for non-admin")


# ═══════════════════════════════════════════════════════════════════
# PUBLIC (NO-AUTH) ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

class TestPublicGetPacket:
    """GET /api/onboarding/public/{token} — public packet access"""

    def test_public_get_valid_token(self, admin_headers):
        """Get packet with valid token returns packet without internal fields"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Public_Get",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]
        token = create_res.json()["token"]

        # Public get (no auth)
        response = requests.get(f"{BASE_URL}/api/onboarding/public/{token}")

        assert response.status_code == 200, f"Public get failed: {response.text}"
        data = response.json()

        # Should have packet data
        assert "id" in data
        assert "organisation" in data
        assert "sites" in data
        assert "staff" in data

        # Should NOT have internal fields
        assert "created_by" not in data, "Should not expose created_by"
        assert "provisioned_organization_id" not in data, "Should not expose provisioned_organization_id"
        assert "_id" not in data, "Should not expose _id"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Public get with valid token works, internal fields hidden")

    def test_public_get_invalid_token(self):
        """Get packet with invalid token returns 404"""
        response = requests.get(f"{BASE_URL}/api/onboarding/public/invalid_token_12345")

        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Public get with invalid token returns 404")


class TestPublicSavePacket:
    """PUT /api/onboarding/public/{token} — save draft content"""

    def test_public_save_draft(self, admin_headers):
        """Save draft content via public endpoint"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Public_Save",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]
        token = create_res.json()["token"]

        # Save data (no auth)
        save_data = {
            "organisation": {
                "legal_name": "Test Legal Name",
                "billing_postcode": "SW1A 1AA",
                "primary_contact_email": "test@example.com"
            },
            "sites": [{"name": "Site 1", "postcode": "SW1A 1AA"}],
            "staff": [{"full_name": "John Doe", "email": "john@example.com", "role": "owner"}],
            "equipment": [{"name": "Treadmill", "brand": "Life Fitness"}],
            "suppliers": [{"name": "Supplier Co"}],
            "contracts": [{"contract_number": "C001", "provider": "Provider Inc"}]
        }

        response = requests.put(f"{BASE_URL}/api/onboarding/public/{token}", json=save_data)

        assert response.status_code == 200, f"Public save failed: {response.text}"
        data = response.json()

        # Verify data was saved
        assert data["organisation"]["legal_name"] == "Test Legal Name"
        assert len(data["sites"]) == 1
        assert len(data["staff"]) == 1
        assert len(data["equipment"]) == 1
        assert len(data["suppliers"]) == 1
        assert len(data["contracts"]) == 1

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Public save draft works")


class TestPublicSubmitPacket:
    """POST /api/onboarding/public/{token}/submit — submit packet"""

    def test_public_submit_missing_required_fields(self, admin_headers):
        """Submit packet with missing required fields returns 400"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Submit_Empty",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]
        token = create_res.json()["token"]

        # Try to submit empty packet
        response = requests.post(f"{BASE_URL}/api/onboarding/public/{token}/submit")

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()

        # Should have validation errors
        assert "detail" in data
        detail = data["detail"]
        if isinstance(detail, dict):
            assert "errors" in detail
            errors = detail["errors"]
            # Check for expected validation errors
            error_text = " ".join(errors).lower()
            assert "legal name" in error_text or "site" in error_text or "staff" in error_text or "owner" in error_text

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Submit with missing fields returns 400 with errors")

    def test_public_submit_complete_packet(self, admin_headers):
        """Submit packet with all required fields succeeds"""
        # Create packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Submit_Complete",
            "target_tier": "pro"
        }, headers=admin_headers)
        packet_id = create_res.json()["id"]
        token = create_res.json()["token"]

        # Fill in required data
        unique_suffix = str(uuid.uuid4())[:8]
        fill_data = {
            "organisation": {
                "legal_name": f"TEST Submit Org {unique_suffix}",
                "billing_postcode": "SW1A 1AA",
                "primary_contact_email": f"test.submit.{unique_suffix}@example.com"
            },
            "sites": [{
                "name": "Test Site",
                "postcode": "SW1A 1AA"
            }],
            "staff": [{
                "full_name": "Test Owner",
                "email": f"test.owner.submit.{unique_suffix}@example.com",
                "role": "owner"
            }]
        }

        fill_res = requests.put(f"{BASE_URL}/api/onboarding/public/{token}", json=fill_data)
        assert fill_res.status_code == 200

        # Submit packet
        response = requests.post(f"{BASE_URL}/api/onboarding/public/{token}/submit")

        assert response.status_code == 200, f"Submit failed: {response.text}"
        data = response.json()

        assert data.get("success") == True
        assert "message" in data

        # Verify status changed
        get_res = requests.get(f"{BASE_URL}/api/onboarding/public/{token}")
        packet_data = get_res.json()
        assert packet_data["status"] == "submitted"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        print("✓ Submit complete packet success")


# ═══════════════════════════════════════════════════════════════════
# CLEANUP TEST DATA
# ═══════════════════════════════════════════════════════════════════

class TestCleanup:
    """Cleanup any remaining test packets"""

    def test_cleanup_test_packets(self, admin_headers):
        """Delete all TEST_ prefixed packets"""
        response = requests.get(f"{BASE_URL}/api/onboarding-packets", headers=admin_headers)
        if response.status_code == 200:
            packets = response.json().get("packets", [])
            deleted = 0
            for p in packets:
                name = p.get("customer_display_name", "")
                if name.startswith("TEST_") and p.get("status") != "provisioned":
                    del_res = requests.delete(f"{BASE_URL}/api/onboarding-packets/{p['id']}", headers=admin_headers)
                    if del_res.status_code == 200:
                        deleted += 1
            print(f"✓ Cleanup: deleted {deleted} test packets")
        else:
            print("✓ Cleanup: no packets to clean")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
