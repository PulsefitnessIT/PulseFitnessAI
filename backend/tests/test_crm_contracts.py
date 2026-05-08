"""
CRM Contracts Management System - Backend API Tests
Tests for: Contract CRUD, Sites, Assets, SLA, Approvals, Signing, Sync (Sicon/Sage)
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials — loaded from environment
CRM_EMAIL = os.environ.get('CRM_TEST_EMAIL', 'craig.henshall@pulsefitness.com')
CRM_PASSWORD = os.environ.get('CRM_TEST_PASSWORD', 'Test123!')


class TestContractsAPI:
    """CRM Contracts Management API Tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Login to CRM
        login_res = self.session.post(f"{BASE_URL}/api/crm/auth/login", json={
            "email": CRM_EMAIL,
            "password": CRM_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json().get("token")
        assert token, "No token returned"
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.token = token
        yield
        # Cleanup handled in individual tests

    # ── LOOKUP ENDPOINTS ──────────────────────────────────────────────

    def test_01_get_contract_tiers(self):
        """GET /api/crm/v2/contracts/tiers returns tier list"""
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/tiers")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "tiers" in data, "Response should have 'tiers' key"
        assert len(data["tiers"]) >= 5, "Should have at least 5 tiers"
        tier_ids = [t["id"] for t in data["tiers"]]
        assert "bronze" in tier_ids, "Should have bronze tier"
        assert "gold" in tier_ids, "Should have gold tier"
        print(f"PASS: GET /api/crm/v2/contracts/tiers - {len(data['tiers'])} tiers returned")

    def test_02_get_contract_statuses(self):
        """GET /api/crm/v2/contracts/statuses returns status list"""
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/statuses")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "statuses" in data, "Response should have 'statuses' key"
        status_ids = [s["id"] for s in data["statuses"]]
        assert "draft" in status_ids, "Should have draft status"
        assert "active" in status_ids, "Should have active status"
        assert "pending_approval" in status_ids, "Should have pending_approval status"
        print(f"PASS: GET /api/crm/v2/contracts/statuses - {len(data['statuses'])} statuses returned")

    def test_03_get_contract_stats(self):
        """GET /api/crm/v2/contracts/stats returns stats object"""
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/stats")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "total" in data, "Stats should have 'total'"
        assert "active" in data, "Stats should have 'active'"
        assert "draft" in data, "Stats should have 'draft'"
        assert "pending_approval" in data, "Stats should have 'pending_approval'"
        assert "expiring_soon" in data, "Stats should have 'expiring_soon'"
        assert "active_annual_value" in data, "Stats should have 'active_annual_value'"
        print(f"PASS: GET /api/crm/v2/contracts/stats - total={data['total']}, active={data['active']}")

    def test_04_check_coverage_endpoint(self):
        """GET /api/crm/v2/contracts/check-coverage returns valid response"""
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/check-coverage")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "has_coverage" in data, "Response should have 'has_coverage'"
        assert "contracts" in data, "Response should have 'contracts'"
        print(f"PASS: GET /api/crm/v2/contracts/check-coverage - has_coverage={data['has_coverage']}")

    # ── CONTRACT CRUD ─────────────────────────────────────────────────

    def test_05_list_contracts(self):
        """GET /api/crm/v2/contracts returns contract list"""
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "contracts" in data, "Response should have 'contracts'"
        assert "total" in data, "Response should have 'total'"
        print(f"PASS: GET /api/crm/v2/contracts - {data['total']} contracts")

    def test_06_create_contract(self):
        """POST /api/crm/v2/contracts creates a new contract"""
        payload = {
            "title": f"TEST_Contract_{uuid.uuid4().hex[:6]}",
            "type": "service",
            "tier": "gold",
            "company_name": "Test Company Ltd",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "annual_value": 12000,
            "billing_frequency": "monthly"
        }
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json=payload)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "id" in data, "Response should have 'id'"
        assert "contract_number" in data, "Response should have 'contract_number'"
        assert data["title"] == payload["title"], "Title should match"
        assert data["tier"] == "gold", "Tier should be gold"
        assert data["status"] == "draft", "New contract should be draft"
        self.created_contract_id = data["id"]
        print(f"PASS: POST /api/crm/v2/contracts - created {data['contract_number']}")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{data['id']}")

    def test_07_get_contract_detail(self):
        """GET /api/crm/v2/contracts/{id} returns full contract detail"""
        # First create a contract
        payload = {"title": f"TEST_Detail_{uuid.uuid4().hex[:6]}", "tier": "silver"}
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json=payload)
        assert create_res.status_code == 200
        contract_id = create_res.json()["id"]

        # Get detail
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["id"] == contract_id, "ID should match"
        assert "sites" in data, "Detail should include sites"
        assert "covered_assets" in data, "Detail should include covered_assets"
        assert "activities" in data, "Detail should include activities"
        print(f"PASS: GET /api/crm/v2/contracts/{contract_id} - detail retrieved")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_08_update_contract(self):
        """PUT /api/crm/v2/contracts/{id} updates contract fields"""
        # Create
        payload = {"title": f"TEST_Update_{uuid.uuid4().hex[:6]}", "tier": "bronze", "annual_value": 5000}
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json=payload)
        contract_id = create_res.json()["id"]

        # Update
        update_payload = {"title": "Updated Title", "tier": "platinum", "annual_value": 25000}
        res = self.session.put(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}", json=update_payload)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify
        get_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        data = get_res.json()
        assert data["title"] == "Updated Title", "Title should be updated"
        assert data["tier"] == "platinum", "Tier should be updated"
        assert data["annual_value"] == 25000, "Annual value should be updated"
        print(f"PASS: PUT /api/crm/v2/contracts/{contract_id} - updated successfully")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_09_delete_draft_contract(self):
        """DELETE /api/crm/v2/contracts/{id} deletes draft contract"""
        # Create
        payload = {"title": f"TEST_Delete_{uuid.uuid4().hex[:6]}"}
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json=payload)
        contract_id = create_res.json()["id"]

        # Delete
        res = self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify deleted
        get_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assert get_res.status_code == 404, "Deleted contract should return 404"
        print(f"PASS: DELETE /api/crm/v2/contracts/{contract_id} - deleted successfully")

    # ── SITES ─────────────────────────────────────────────────────────

    def test_10_add_site_to_contract(self):
        """POST /api/crm/v2/contracts/{id}/sites adds a site"""
        # Create contract
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Sites_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]

        # Add site
        site_payload = {
            "site_name": "Main Gym Floor",
            "address": "123 Fitness Street",
            "city": "Manchester",
            "postcode": "M1 1AA"
        }
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sites", json=site_payload)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "id" in data, "Site should have id"
        assert data["site_name"] == "Main Gym Floor", "Site name should match"
        site_id = data["id"]
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/sites - site added")

        # Verify in contract detail
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        sites = detail_res.json().get("sites", [])
        assert len(sites) == 1, "Contract should have 1 site"

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sites/{site_id}")
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_11_remove_site_from_contract(self):
        """DELETE /api/crm/v2/contracts/{id}/sites/{site_id} removes site"""
        # Create contract and site
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_RemoveSite_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]
        site_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sites", json={"site_name": "To Remove"})
        site_id = site_res.json()["id"]

        # Remove site
        res = self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sites/{site_id}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify removed
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        sites = detail_res.json().get("sites", [])
        assert len(sites) == 0, "Contract should have 0 sites after removal"
        print(f"PASS: DELETE /api/crm/v2/contracts/{contract_id}/sites/{site_id} - site removed")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    # ── ASSETS ────────────────────────────────────────────────────────

    def test_12_add_asset_to_contract(self):
        """POST /api/crm/v2/contracts/{id}/assets adds an asset"""
        # Create contract
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Assets_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]

        # Add asset
        asset_payload = {
            "asset_name": "Treadmill X500",
            "model_code": "TX500",
            "serial_number": "SN123456",
            "coverage_type": "full"
        }
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/assets", json=asset_payload)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "id" in data, "Asset should have id"
        assert data["asset_name"] == "Treadmill X500", "Asset name should match"
        asset_id = data["id"]
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/assets - asset added")

        # Verify in contract detail
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assets = detail_res.json().get("covered_assets", [])
        assert len(assets) == 1, "Contract should have 1 asset"

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/assets/{asset_id}")
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_13_remove_asset_from_contract(self):
        """DELETE /api/crm/v2/contracts/{id}/assets/{asset_id} removes asset"""
        # Create contract and asset
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_RemoveAsset_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]
        asset_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/assets", json={"asset_name": "To Remove"})
        asset_id = asset_res.json()["id"]

        # Remove asset
        res = self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/assets/{asset_id}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify removed
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assets = detail_res.json().get("covered_assets", [])
        assert len(assets) == 0, "Contract should have 0 assets after removal"
        print(f"PASS: DELETE /api/crm/v2/contracts/{contract_id}/assets/{asset_id} - asset removed")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    # ── SLA ────────────────────────────────────────────────────────────

    def test_14_update_contract_sla(self):
        """PUT /api/crm/v2/contracts/{id}/sla updates SLA fields"""
        # Create contract
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_SLA_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]

        # Update SLA
        sla_payload = {
            "response_hours": 4,
            "resolution_hours": 24,
            "parts_included": True,
            "labour_included": True,
            "visits_per_year": 12,
            "preventive_maintenance": True
        }
        res = self.session.put(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sla", json=sla_payload)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["success"], "Should return success"
        assert data["sla"]["response_hours"] == 4, "Response hours should be 4"
        assert data["sla"]["parts_included"], "Parts should be included"
        print(f"PASS: PUT /api/crm/v2/contracts/{contract_id}/sla - SLA updated")

        # Verify in contract detail
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        sla = detail_res.json().get("sla", {})
        assert sla.get("response_hours") == 4, "SLA response_hours should persist"

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    # ── APPROVAL WORKFLOW ─────────────────────────────────────────────

    def test_15_submit_for_approval(self):
        """POST /api/crm/v2/contracts/{id}/submit-approval submits draft for approval"""
        # Create contract
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Approval_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]

        # Submit for approval
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/submit-approval", json={
            "approver_name": "Manager",
            "notes": "Please review"
        })
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "id" in data, "Approval should have id"
        assert data["status"] == "pending", "Approval status should be pending"
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/submit-approval - submitted")

        # Verify contract status changed
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assert detail_res.json()["status"] == "pending_approval", "Contract status should be pending_approval"

        # Cleanup - need to approve/reject first to delete
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/approve", json={"decision": "rejected"})
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_16_approve_contract(self):
        """POST /api/crm/v2/contracts/{id}/approve approves pending contract"""
        # Create and submit
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Approve_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/submit-approval", json={"approver_name": "Test"})

        # Approve
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/approve", json={
            "decision": "approved",
            "notes": "Looks good"
        })
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify status
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assert detail_res.json()["status"] == "approved", "Contract status should be approved"
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/approve - approved")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_17_reject_contract(self):
        """POST /api/crm/v2/contracts/{id}/approve with rejected decision"""
        # Create and submit
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Reject_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/submit-approval", json={"approver_name": "Test"})

        # Reject
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/approve", json={
            "decision": "rejected",
            "notes": "Needs changes"
        })
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify status back to draft
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        assert detail_res.json()["status"] == "draft", "Rejected contract should return to draft"
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/approve (rejected) - back to draft")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_18_get_approval_history(self):
        """GET /api/crm/v2/contracts/{id}/approvals returns approval history"""
        # Create and submit
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_ApprovalHistory_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/submit-approval", json={"approver_name": "Test"})

        # Get approvals
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/approvals")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "approvals" in data, "Response should have 'approvals'"
        assert len(data["approvals"]) >= 1, "Should have at least 1 approval record"
        print(f"PASS: GET /api/crm/v2/contracts/{contract_id}/approvals - {len(data['approvals'])} records")

        # Cleanup
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/approve", json={"decision": "rejected"})
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    # ── SIGNING ───────────────────────────────────────────────────────

    def test_19_sign_approved_contract(self):
        """POST /api/crm/v2/contracts/{id}/sign signs and activates contract"""
        # Create, submit, approve
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Sign_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/submit-approval", json={"approver_name": "Test"})
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/approve", json={"decision": "approved"})

        # Sign
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sign", json={
            "signature": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "signer_name": "John Doe",
            "activate": True
        })
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["success"], "Should return success"
        assert data["status"] == "active", "Contract should be active after signing"
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/sign - signed and activated")

        # Verify
        detail_res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")
        detail = detail_res.json()
        assert detail["status"] == "active", "Contract status should be active"
        assert detail["signed_by"] == "John Doe", "Signed by should be set"
        assert detail["signature"] is not None, "Signature should be set"

        # Note: Cannot delete active contract - leave for manual cleanup
        print(f"  Note: Active contract {contract_id} left for manual cleanup")

    # ── SERVICE INTEGRATION (MOCKED) ──────────────────────────────────

    def test_20_sync_to_sicon(self):
        """POST /api/crm/v2/contracts/{id}/sync-sicon syncs to Sicon (MOCKED)"""
        # Create contract
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Sicon_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]

        # Sync to Sicon
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sync-sicon")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["success"], "Should return success"
        assert "sicon_contract_id" in data, "Should return sicon_contract_id"
        assert data["sicon_contract_id"].startswith("SICON-"), "Sicon ID should start with SICON-"
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/sync-sicon - MOCKED sync returned {data['sicon_contract_id']}")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    def test_21_sync_to_sage(self):
        """POST /api/crm/v2/contracts/{id}/sync-sage syncs to Sage 200 (MOCKED)"""
        # Create contract
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={"title": f"TEST_Sage_{uuid.uuid4().hex[:6]}"})
        contract_id = create_res.json()["id"]

        # Sync to Sage
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sync-sage")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["success"], "Should return success"
        assert "sage_reference" in data, "Should return sage_reference"
        assert data["sage_reference"].startswith("SAGE-"), "Sage ref should start with SAGE-"
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/sync-sage - MOCKED sync returned {data['sage_reference']}")

        # Cleanup
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}")

    # ── RENEWAL ───────────────────────────────────────────────────────

    def test_22_renew_contract(self):
        """POST /api/crm/v2/contracts/{id}/renew creates renewal contract"""
        # Create and activate a contract
        create_res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts", json={
            "title": f"TEST_Renew_{uuid.uuid4().hex[:6]}",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "annual_value": 10000
        })
        contract_id = create_res.json()["id"]

        # Submit, approve, sign to make active
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/submit-approval", json={"approver_name": "Test"})
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/approve", json={"decision": "approved"})
        self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/sign", json={"signer_name": "Test", "activate": True})

        # Renew
        res = self.session.post(f"{BASE_URL}/api/crm/v2/contracts/{contract_id}/renew", json={
            "proposed_value": 12000,
            "start_date": "2026-01-01",
            "end_date": "2026-12-31"
        })
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "contract" in data, "Should return new contract"
        assert "opportunity" in data, "Should return renewal opportunity"
        assert data["contract"]["status"] == "draft", "Renewal should be draft"
        assert data["contract"]["annual_value"] == 12000, "Renewal value should be 12000"
        print(f"PASS: POST /api/crm/v2/contracts/{contract_id}/renew - created renewal {data['contract']['id']}")

        # Cleanup renewal (draft can be deleted)
        self.session.delete(f"{BASE_URL}/api/crm/v2/contracts/{data['contract']['id']}")
        # Original active contract cannot be deleted

    # ── FILTER TESTS ──────────────────────────────────────────────────

    def test_23_filter_by_status(self):
        """GET /api/crm/v2/contracts?status=draft filters by status"""
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts?status=draft")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        for c in data["contracts"]:
            assert c["status"] == "draft", f"All contracts should be draft, got {c['status']}"
        print(f"PASS: GET /api/crm/v2/contracts?status=draft - {len(data['contracts'])} draft contracts")

    def test_24_expiring_contracts(self):
        """GET /api/crm/v2/contracts/expiring returns expiring contracts"""
        res = self.session.get(f"{BASE_URL}/api/crm/v2/contracts/expiring?days=90")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "contracts" in data, "Response should have 'contracts'"
        assert "days_threshold" in data, "Response should have 'days_threshold'"
        assert data["days_threshold"] == 90, "Days threshold should be 90"
        print(f"PASS: GET /api/crm/v2/contracts/expiring - {len(data['contracts'])} expiring in 90 days")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
