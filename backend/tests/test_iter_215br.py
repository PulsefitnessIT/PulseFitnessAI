"""
Iter 215br Backend Tests — Member full profile, CRM analytics enrichment, Site move.

Tests:
1. POST /api/memberships/members — full profile schema (14+ fields)
2. GET /api/memberships/members/{id} — verify all fields persist
3. GET /api/master-admin/crm-analytics — deals_at_risk, renewals_due, ai_usage, growth
4. POST /api/master-admin/organizations/{org_id}/sites/{site_id}/move — site relocation
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Authenticate as master admin."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD,
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_token():
    """Authenticate as operator (Pulse Pro site manager)."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD,
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


class TestMemberFullProfile:
    """Test POST /api/memberships/members with full 14+ field profile."""

    @pytest.fixture(autouse=True)
    def setup(self, operator_token):
        self.headers = {"Authorization": f"Bearer {operator_token}"}
        self.created_member_id = None

    def test_create_member_full_profile(self, operator_token):
        """POST /api/memberships/members with all profile fields."""
        unique_email = f"test.member.{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "first_name": "Test",
            "last_name": "Member215br",
            "email": unique_email,
            "phone": "+447700900123",
            "dob": "1990-05-15",
            "address_line1": "123 Test Street",
            "address_line2": "Flat 4B",
            "city": "London",
            "postcode": "SW1A 1AA",
            "country": "United Kingdom",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_phone": "+447700900456",
            "notes": "Test member created by iter 215br tests",
            "tags": ["test", "iter215br", "automated"],
        }

        resp = requests.post(
            f"{BASE_URL}/api/memberships/members",
            json=payload,
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert resp.status_code in [200, 201], f"Create failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "member" in data, "Response missing 'member' key"

        member = data["member"]
        self.created_member_id = member.get("id")

        # Verify all submitted fields are echoed back
        assert member.get("first_name") == "Test", "first_name mismatch"
        assert member.get("last_name") == "Member215br", "last_name mismatch"
        assert member.get("email") == unique_email, "email mismatch"
        assert member.get("phone") == "+447700900123", "phone mismatch"
        assert member.get("dob") == "1990-05-15", "dob mismatch"
        assert member.get("address_line1") == "123 Test Street", "address_line1 mismatch"
        assert member.get("address_line2") == "Flat 4B", "address_line2 mismatch"
        assert member.get("city") == "London", "city mismatch"
        assert member.get("postcode") == "SW1A 1AA", "postcode mismatch"
        assert member.get("country") == "United Kingdom", "country mismatch"
        assert member.get("emergency_contact_name") == "Jane Doe", "emergency_contact_name mismatch"
        assert member.get("emergency_contact_phone") == "+447700900456", "emergency_contact_phone mismatch"
        assert member.get("notes") == "Test member created by iter 215br tests", "notes mismatch"
        assert "test" in member.get("tags", []), "tags missing 'test'"
        assert "iter215br" in member.get("tags", []), "tags missing 'iter215br'"

        print(f"✓ Member created with ID: {self.created_member_id}")
        return self.created_member_id

    def test_get_member_full_profile_persistence(self, operator_token):
        """GET /api/memberships/members/{id} verifies all fields persisted."""
        # First create a member
        unique_email = f"test.persist.{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "first_name": "Persist",
            "last_name": "Test215br",
            "email": unique_email,
            "phone": "+447700900789",
            "dob": "1985-12-25",
            "address_line1": "456 Persist Lane",
            "address_line2": "Suite 10",
            "city": "Manchester",
            "postcode": "M1 1AA",
            "country": "UK",
            "emergency_contact_name": "John Smith",
            "emergency_contact_phone": "+447700900999",
            "notes": "Persistence test notes",
            "tags": ["persistence", "test"],
        }

        create_resp = requests.post(
            f"{BASE_URL}/api/memberships/members",
            json=payload,
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert create_resp.status_code in [200, 201], f"Create failed: {create_resp.text}"
        member_id = create_resp.json()["member"]["id"]

        # Now GET the member to verify persistence
        get_resp = requests.get(
            f"{BASE_URL}/api/memberships/members/{member_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert get_resp.status_code == 200, f"GET failed: {get_resp.status_code} - {get_resp.text}"
        data = get_resp.json()
        assert "member" in data, "Response missing 'member' key"

        member = data["member"]

        # Verify all fields persisted correctly
        assert member.get("first_name") == "Persist", "first_name not persisted"
        assert member.get("last_name") == "Test215br", "last_name not persisted"
        assert member.get("email") == unique_email, "email not persisted"
        assert member.get("phone") == "+447700900789", "phone not persisted"
        assert member.get("dob") == "1985-12-25", "dob not persisted"
        assert member.get("address_line1") == "456 Persist Lane", "address_line1 not persisted"
        assert member.get("address_line2") == "Suite 10", "address_line2 not persisted"
        assert member.get("city") == "Manchester", "city not persisted"
        assert member.get("postcode") == "M1 1AA", "postcode not persisted"
        assert member.get("country") == "UK", "country not persisted"
        assert member.get("emergency_contact_name") == "John Smith", "emergency_contact_name not persisted"
        assert member.get("emergency_contact_phone") == "+447700900999", "emergency_contact_phone not persisted"
        assert member.get("notes") == "Persistence test notes", "notes not persisted"
        assert "persistence" in member.get("tags", []), "tags not persisted"

        print(f"✓ All 14+ fields persisted correctly for member {member_id}")


class TestCRMAnalyticsEnrichment:
    """Test GET /api/master-admin/crm-analytics returns new enriched fields."""

    def test_crm_analytics_returns_deals_at_risk(self, master_admin_token):
        """Verify deals_at_risk is present in response."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/crm-analytics",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert resp.status_code == 200, f"CRM analytics failed: {resp.status_code} - {resp.text}"
        data = resp.json()

        # Verify deals_at_risk structure
        assert "deals_at_risk" in data, "Response missing 'deals_at_risk'"
        deals_at_risk = data["deals_at_risk"]
        assert isinstance(deals_at_risk, list), "deals_at_risk should be a list"

        # If there are deals at risk, verify structure
        if len(deals_at_risk) > 0:
            deal = deals_at_risk[0]
            assert "risk_reasons" in deal, "Deal missing 'risk_reasons'"
            assert isinstance(deal["risk_reasons"], list), "risk_reasons should be a list"
            print(f"✓ deals_at_risk has {len(deals_at_risk)} items with risk_reasons")
        else:
            print("✓ deals_at_risk is empty (no at-risk deals)")

    def test_crm_analytics_returns_renewals_due(self, master_admin_token):
        """Verify renewals_due structure with window_days, count, total_value, items."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/crm-analytics",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert resp.status_code == 200, f"CRM analytics failed: {resp.status_code} - {resp.text}"
        data = resp.json()

        # Verify renewals_due structure
        assert "renewals_due" in data, "Response missing 'renewals_due'"
        renewals = data["renewals_due"]
        assert isinstance(renewals, dict), "renewals_due should be an object"

        # Check required fields
        assert "window_days" in renewals, "renewals_due missing 'window_days'"
        assert "count" in renewals, "renewals_due missing 'count'"
        assert "total_value" in renewals, "renewals_due missing 'total_value'"
        assert "items" in renewals, "renewals_due missing 'items'"

        assert isinstance(renewals["window_days"], int), "window_days should be int"
        assert isinstance(renewals["count"], int), "count should be int"
        assert isinstance(renewals["items"], list), "items should be list"

        print(f"✓ renewals_due: window={renewals['window_days']}d, count={renewals['count']}, value={renewals['total_value']}")

    def test_crm_analytics_returns_ai_usage(self, master_admin_token):
        """Verify ai_usage structure with autopilot_drafts, win_intel_hits, copilot_sessions, total."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/crm-analytics",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert resp.status_code == 200, f"CRM analytics failed: {resp.status_code} - {resp.text}"
        data = resp.json()

        # Verify ai_usage structure
        assert "ai_usage" in data, "Response missing 'ai_usage'"
        ai = data["ai_usage"]
        assert isinstance(ai, dict), "ai_usage should be an object"

        # Check required fields
        assert "autopilot_drafts" in ai, "ai_usage missing 'autopilot_drafts'"
        assert "win_intel_hits" in ai, "ai_usage missing 'win_intel_hits'"
        assert "copilot_sessions" in ai, "ai_usage missing 'copilot_sessions'"
        assert "total" in ai, "ai_usage missing 'total'"

        # Verify total is sum of components
        expected_total = ai["autopilot_drafts"] + ai["win_intel_hits"] + ai["copilot_sessions"]
        assert ai["total"] == expected_total, f"total mismatch: {ai['total']} != {expected_total}"

        print(f"✓ ai_usage: autopilot={ai['autopilot_drafts']}, win_intel={ai['win_intel_hits']}, copilot={ai['copilot_sessions']}, total={ai['total']}")

    def test_crm_analytics_returns_v2_growth(self, master_admin_token):
        """Verify growth object has new_contacts_30d, new_deals_30d, recent_activities_30d."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/crm-analytics",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert resp.status_code == 200, f"CRM analytics failed: {resp.status_code} - {resp.text}"
        data = resp.json()

        # Verify growth structure
        assert "growth" in data, "Response missing 'growth'"
        growth = data["growth"]
        assert isinstance(growth, dict), "growth should be an object"

        # Check required fields
        assert "new_contacts_30d" in growth, "growth missing 'new_contacts_30d'"
        assert "new_deals_30d" in growth, "growth missing 'new_deals_30d'"
        assert "recent_activities_30d" in growth, "growth missing 'recent_activities_30d'"

        print(f"✓ growth: contacts_30d={growth['new_contacts_30d']}, deals_30d={growth['new_deals_30d']}, activities_30d={growth['recent_activities_30d']}")


class TestSiteMove:
    """Test POST /api/master-admin/organizations/{org_id}/sites/{site_id}/move."""

    def test_site_move_missing_target_org(self, master_admin_token):
        """Move without target_organization_id should return 400."""
        # First get an org with sites
        orgs_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert orgs_resp.status_code == 200, f"Get orgs failed: {orgs_resp.text}"
        orgs = orgs_resp.json().get("organizations", [])

        if len(orgs) < 1:
            pytest.skip("No organizations available for site move test")

        org_id = orgs[0]["id"]

        # Get sites for this org
        sites_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert sites_resp.status_code == 200, f"Get sites failed: {sites_resp.text}"
        sites = sites_resp.json().get("sites", [])

        if len(sites) < 1:
            pytest.skip("No sites available for move test")

        # Find a non-default site
        site = next((s for s in sites if not s.get("is_default")), None)
        if not site:
            pytest.skip("No non-default sites available for move test")

        # Try to move without target_organization_id
        move_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites/{site['id']}/move",
            json={},  # Missing target_organization_id
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert move_resp.status_code == 400, f"Expected 400, got {move_resp.status_code}"
        assert "target_organization_id" in move_resp.text.lower(), "Error should mention target_organization_id"
        print("✓ Move without target_organization_id returns 400")

    def test_site_move_same_org_error(self, master_admin_token):
        """Move to same org should return 400."""
        orgs_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert orgs_resp.status_code == 200
        orgs = orgs_resp.json().get("organizations", [])

        if len(orgs) < 1:
            pytest.skip("No organizations available")

        org_id = orgs[0]["id"]

        sites_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert sites_resp.status_code == 200
        sites = sites_resp.json().get("sites", [])

        site = next((s for s in sites if not s.get("is_default")), None)
        if not site:
            pytest.skip("No non-default sites available")

        # Try to move to same org
        move_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites/{site['id']}/move",
            json={"target_organization_id": org_id},  # Same org
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert move_resp.status_code == 400, f"Expected 400, got {move_resp.status_code}"
        assert "already" in move_resp.text.lower(), "Error should mention site is already on this org"
        print("✓ Move to same org returns 400")

    def test_site_move_nonexistent_site(self, master_admin_token):
        """Move nonexistent site should return 404."""
        orgs_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert orgs_resp.status_code == 200
        orgs = orgs_resp.json().get("organizations", [])

        if len(orgs) < 2:
            pytest.skip("Need at least 2 organizations for move test")

        org_id = orgs[0]["id"]
        target_org_id = orgs[1]["id"]
        fake_site_id = str(uuid.uuid4())

        move_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites/{fake_site_id}/move",
            json={"target_organization_id": target_org_id},
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert move_resp.status_code == 404, f"Expected 404, got {move_resp.status_code}"
        print("✓ Move nonexistent site returns 404")

    def test_site_move_success_and_back(self, master_admin_token):
        """Successfully move a site to another org and back."""
        orgs_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert orgs_resp.status_code == 200
        orgs = orgs_resp.json().get("organizations", [])

        if len(orgs) < 2:
            pytest.skip("Need at least 2 organizations for move test")

        # Find an org with non-default sites
        source_org = None
        site_to_move = None
        for org in orgs:
            sites_resp = requests.get(
                f"{BASE_URL}/api/master-admin/organizations/{org['id']}/sites",
                headers={"Authorization": f"Bearer {master_admin_token}"},
            )
            if sites_resp.status_code == 200:
                sites = sites_resp.json().get("sites", [])
                non_default = [s for s in sites if not s.get("is_default")]
                if non_default:
                    source_org = org
                    site_to_move = non_default[0]
                    break

        if not source_org or not site_to_move:
            pytest.skip("No non-default sites available for move test")

        # Find a different target org
        target_org = next((o for o in orgs if o["id"] != source_org["id"]), None)
        if not target_org:
            pytest.skip("No target org available")

        # Move site to target org
        move_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{source_org['id']}/sites/{site_to_move['id']}/move",
            json={"target_organization_id": target_org["id"]},
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert move_resp.status_code == 200, f"Move failed: {move_resp.status_code} - {move_resp.text}"
        move_data = move_resp.json()

        assert move_data.get("success") is True, "Move should return success=True"
        assert move_data.get("site_id") == site_to_move["id"], "site_id mismatch"
        assert move_data.get("moved_from") == source_org["id"], "moved_from mismatch"
        assert move_data.get("moved_to") == target_org["id"], "moved_to mismatch"

        print(f"✓ Site '{site_to_move['name']}' moved from {source_org['name']} to {target_org['name']}")
        print(f"  Equipment moved: {move_data.get('equipment_moved', 0)}, Issues moved: {move_data.get('issues_moved', 0)}")

        # Move it back
        move_back_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{target_org['id']}/sites/{site_to_move['id']}/move",
            json={"target_organization_id": source_org["id"]},
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )

        assert move_back_resp.status_code == 200, f"Move back failed: {move_back_resp.text}"
        print("✓ Site moved back to original org")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
