"""
MOD Portal API Tests - Iteration 156
Tests for MOD Service Portal endpoints including:
- Site dashboard
- Staff CRUD
- Fault wizard submission
- AI triage preview
- Master Admin MOD console
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pulse-staging-10.preview.emergentagent.com').rstrip('/')
BYPASS_HEADERS = {
    'X-RateLimit-Bypass': '1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6',
    'X-Captcha-Token': 'bypass:1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6'
}


@pytest.fixture(scope="module")
def mod_user_token():
    """Get MOD site user token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "raf.brizenorton@mod.pulse.gym", "password": "BrizeNorton2026!"},
        headers=BYPASS_HEADERS
    )
    assert response.status_code == 200, f"MOD user login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    """Get Master Admin token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        headers=BYPASS_HEADERS
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]


class TestMODSiteDashboard:
    """MOD Site Dashboard endpoint tests"""

    def test_dashboard_returns_site_data(self, mod_user_token):
        """GET /api/mod/site/dashboard returns site stats and open faults"""
        response = requests.get(
            f"{BASE_URL}/api/mod/site/dashboard",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "site" in data
        assert "stats" in data
        assert "open_faults" in data

        # Verify site info
        assert data["site"]["name"] == "RAF Brize Norton Gym"
        assert data["site"]["id"] == "mod-site-raf.brizenorton"

        # Verify stats
        stats = data["stats"]
        assert "equipment_total" in stats
        assert "equipment_working" in stats
        assert "availability_pct" in stats
        assert "open_faults" in stats
        assert "overdue_checks" in stats
        assert stats["equipment_total"] == 12

    def test_dashboard_requires_auth(self):
        """GET /api/mod/site/dashboard requires authentication"""
        response = requests.get(f"{BASE_URL}/api/mod/site/dashboard")
        assert response.status_code == 401


class TestMODSiteEquipment:
    """MOD Site Equipment endpoint tests"""

    def test_equipment_list(self, mod_user_token):
        """GET /api/mod/site/equipment returns equipment list"""
        response = requests.get(
            f"{BASE_URL}/api/mod/site/equipment",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "equipment" in data
        assert len(data["equipment"]) == 12

        # Verify equipment structure
        eq = data["equipment"][0]
        assert "id" in eq
        assert "name" in eq
        assert "machine_type" in eq
        assert "serial_number" in eq


class TestMODStaffCRUD:
    """MOD Site Staff CRUD endpoint tests"""

    def test_staff_list(self, mod_user_token):
        """GET /api/mod/site/staff returns staff list"""
        response = requests.get(
            f"{BASE_URL}/api/mod/site/staff",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "staff" in data
        assert len(data["staff"]) >= 5  # 5 seeded staff

        # Verify staff structure
        staff = data["staff"][0]
        assert "id" in staff
        assert "name" in staff
        assert "email" in staff
        assert "phone" in staff

    def test_staff_create(self, mod_user_token):
        """POST /api/mod/site/staff creates new staff member"""
        unique_email = f"test.staff.{uuid.uuid4().hex[:8]}@mod.gov.uk"
        response = requests.post(
            f"{BASE_URL}/api/mod/site/staff",
            json={
                "name": "TEST Staff Member",
                "role": "Test Role",
                "email": unique_email,
                "phone": "+44 7700 900999"
            },
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "TEST Staff Member"
        assert data["email"] == unique_email
        assert data["is_active"] == True
        assert "id" in data

        # Cleanup - delete the test staff
        staff_id = data["id"]
        delete_response = requests.delete(
            f"{BASE_URL}/api/mod/site/staff/{staff_id}",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert delete_response.status_code == 200

    def test_staff_create_duplicate_email_rejected(self, mod_user_token):
        """POST /api/mod/site/staff rejects duplicate email"""
        # Try to create staff with existing email
        response = requests.post(
            f"{BASE_URL}/api/mod/site/staff",
            json={
                "name": "Duplicate Staff",
                "role": "Test",
                "email": "j.hughes@mod.gov.uk",  # Existing seeded staff
                "phone": "+44 7700 900999"
            },
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


class TestMODFaultWizard:
    """MOD Fault Wizard endpoint tests"""

    def test_triage_preview(self, mod_user_token):
        """POST /api/mod/site/faults/triage-preview returns AI triage"""
        # First get equipment ID
        eq_response = requests.get(
            f"{BASE_URL}/api/mod/site/equipment",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        equipment_id = eq_response.json()["equipment"][0]["id"]

        response = requests.post(
            f"{BASE_URL}/api/mod/site/faults/triage-preview",
            json={
                "equipment_id": equipment_id,
                "fault_type": "not_working",
                "description": "The treadmill belt is slipping when running at high speeds above 10 km/h.",
                "onset": "today",
                "usable": "limited",
                "safe_in_service": "yes"
            },
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "priority" in data
        assert "ai" in data
        assert data["priority"] in ["low", "medium", "high", "urgent"]

    def test_fault_submit(self, mod_user_token):
        """POST /api/mod/site/faults creates new fault ticket"""
        # Get equipment and staff IDs
        eq_response = requests.get(
            f"{BASE_URL}/api/mod/site/equipment",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        equipment_id = eq_response.json()["equipment"][0]["id"]

        staff_response = requests.get(
            f"{BASE_URL}/api/mod/site/staff",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        staff_id = staff_response.json()["staff"][0]["id"]

        response = requests.post(
            f"{BASE_URL}/api/mod/site/faults",
            json={
                "equipment_id": equipment_id,
                "fault_type": "not_working",
                "description": "TEST FAULT: The treadmill belt is slipping when running at high speeds above 10 km/h. Started yesterday.",
                "onset": "yesterday",
                "usable": "limited",
                "safe_in_service": "yes",
                "reporter_staff_id": staff_id,
                "attachment_urls": []
            },
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["ok"] == True
        assert "ticket_ref" in data
        assert data["ticket_ref"].startswith("MOD-")
        assert "priority" in data
        assert data["priority"] in ["low", "medium", "high", "urgent"]

    def test_fault_submit_urgent_when_unsafe(self, mod_user_token):
        """POST /api/mod/site/faults sets URGENT priority when safe_in_service=no"""
        eq_response = requests.get(
            f"{BASE_URL}/api/mod/site/equipment",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        equipment_id = eq_response.json()["equipment"][1]["id"]  # Use different equipment

        staff_response = requests.get(
            f"{BASE_URL}/api/mod/site/staff",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        staff_id = staff_response.json()["staff"][0]["id"]

        response = requests.post(
            f"{BASE_URL}/api/mod/site/faults",
            json={
                "equipment_id": equipment_id,
                "fault_type": "safety",
                "description": "TEST URGENT FAULT: Electrical sparking observed when machine is powered on. Immediate isolation required.",
                "onset": "today",
                "usable": "no",
                "safe_in_service": "no",
                "reporter_staff_id": staff_id,
                "attachment_urls": []
            },
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["priority"] == "urgent"


class TestMODProactiveNudges:
    """MOD Proactive Nudges endpoint tests"""

    def test_nudges_endpoint(self, mod_user_token):
        """GET /api/mod/site/proactive-nudges returns nudges"""
        response = requests.get(
            f"{BASE_URL}/api/mod/site/proactive-nudges",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "nudges" in data
        assert isinstance(data["nudges"], list)


class TestMasterAdminMODConsole:
    """Master Admin MOD Console endpoint tests"""

    def test_mod_sites_list(self, admin_token):
        """GET /api/master-admin/mod/sites returns all MOD sites"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/mod/sites",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "sites" in data
        assert len(data["sites"]) == 3  # 3 seeded MOD sites

        # Verify site structure
        site = data["sites"][0]
        assert "id" in site
        assert "name" in site
        assert "mod_branch" in site
        assert "equipment_count" in site
        assert "staff_count" in site
        assert "open_faults" in site

        # Verify branches
        branches = [s["mod_branch"] for s in data["sites"]]
        assert "RAF" in branches
        assert "Army" in branches
        assert "Navy" in branches

    def test_mod_sites_requires_master_admin(self, mod_user_token):
        """GET /api/master-admin/mod/sites requires master admin"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/mod/sites",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 403

    def test_audit_log(self, admin_token):
        """GET /api/master-admin/mod/audit-log/{site_id} returns audit entries"""
        # First get a site ID
        sites_response = requests.get(
            f"{BASE_URL}/api/master-admin/mod/sites",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        site_id = sites_response.json()["sites"][0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/master-admin/mod/audit-log/{site_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "log" in data
        assert isinstance(data["log"], list)


class TestMODWhoami:
    """MOD Whoami endpoint tests"""

    def test_whoami(self, mod_user_token):
        """GET /api/mod/me returns user and org context"""
        response = requests.get(
            f"{BASE_URL}/api/mod/me",
            headers={"Authorization": f"Bearer {mod_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "org" in data
        assert "user" in data
        assert data["org"]["account_type"] == "mod_site"
        assert data["org"]["mod_branch"] == "RAF"
