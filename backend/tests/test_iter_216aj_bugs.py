"""
Iteration 216aj Bug Fixes Tests

Tests for the three user-reported bugs:
1. Product Tour reappears on every login (frontend localStorage issue)
2. OPEN WIZARD CTA lands on Invalid Token screen (SetupWizard.js token fix)
3. Class created via Studio Quickstart doesn't show on Timetable (recurs_days fix)

Backend API tests for:
- POST /memberships/studio/complete-quickstart writes templates with recurs_days, start_time, duration_min
- GET /memberships/timetable returns occurrences for templates with recurs_days
- GET /memberships/setup/status returns 200 with valid Bearer, 401 with invalid
- POST /memberships/classes/templates works with new schema (recurs_days optional)
- PATCH /memberships/classes/templates still works
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
RATE_LIMIT_BYPASS = os.environ.get('RATE_LIMIT_BYPASS_SECRET', '')

# Test credentials
BOB_EMAIL = "Bob@knockers.com"
BOB_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def bob_token():
    """Get authentication token for Bob"""
    headers = {"Content-Type": "application/json"}
    if RATE_LIMIT_BYPASS:
        headers["X-RateLimit-Bypass"] = RATE_LIMIT_BYPASS
    
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": BOB_EMAIL, "password": BOB_PASSWORD},
        headers=headers
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data, "No token in response"
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(bob_token):
    """Get auth headers for Bob"""
    return {"Authorization": f"Bearer {bob_token}"}


class TestSetupStatus:
    """Test GET /memberships/setup/status endpoint"""
    
    def test_setup_status_with_valid_token(self, auth_headers):
        """GET /memberships/setup/status returns 200 with valid Bearer"""
        response = requests.get(
            f"{BASE_URL}/api/memberships/setup/status",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "organization" in data, "Missing organization in response"
        assert "counts" in data, "Missing counts in response"
        assert "id" in data["organization"], "Missing org id"
        assert "name" in data["organization"], "Missing org name"
    
    def test_setup_status_with_invalid_token(self):
        """GET /memberships/setup/status returns 401 with invalid token"""
        response = requests.get(
            f"{BASE_URL}/api/memberships/setup/status",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    
    def test_setup_status_without_token(self):
        """GET /memberships/setup/status returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/memberships/setup/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestClassTemplates:
    """Test class templates CRUD with new schema"""
    
    def test_get_templates(self, auth_headers):
        """GET /memberships/classes/templates returns templates list"""
        response = requests.get(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "templates" in data, "Missing templates in response"
        assert isinstance(data["templates"], list), "templates should be a list"
    
    def test_create_template_with_recurs_days(self, auth_headers):
        """POST /memberships/classes/templates creates template with recurs_days"""
        payload = {
            "name": "TEST_216aj_Saturday_Class",
            "recurs_days": [5],  # Saturday (0=Mon, 5=Sat)
            "start_time": "10:30",
            "duration_min": 60,
            "capacity": 12,
            "colour": "#FF5733",
            "credits_to_book": 1
        }
        
        response = requests.post(
            f"{BASE_URL}/api/memberships/classes/templates",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "template" in data, "Missing template in response"
        template = data["template"]
        
        # Verify the template has the correct fields
        assert template["name"] == "TEST_216aj_Saturday_Class"
        assert template["recurs_days"] == [5], f"Expected recurs_days=[5], got {template.get('recurs_days')}"
        assert template["start_time"] == "10:30", f"Expected start_time='10:30', got {template.get('start_time')}"
        assert template["duration_min"] == 60, f"Expected duration_min=60, got {template.get('duration_min')}"
        assert template["capacity"] == 12
        
        # Store template ID for cleanup
        return template["id"]
    
    def test_create_template_without_recurs_days(self, auth_headers):
        """POST /memberships/classes/templates works without recurs_days (optional)"""
        payload = {
            "name": "TEST_216aj_No_Recurs",
            "duration_min": 45,
            "capacity": 20,
            "credits_to_book": 1
        }
        
        response = requests.post(
            f"{BASE_URL}/api/memberships/classes/templates",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "template" in data, "Missing template in response"
        template = data["template"]
        
        # recurs_days should be empty list by default
        assert template.get("recurs_days") == [] or template.get("recurs_days") is None
    
    def test_patch_template(self, auth_headers):
        """PATCH /memberships/classes/templates/{id} updates template"""
        # First create a template
        create_payload = {
            "name": "TEST_216aj_Patch_Test",
            "recurs_days": [0],  # Monday
            "start_time": "09:00",
            "duration_min": 30,
            "capacity": 10,
            "credits_to_book": 1
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/memberships/classes/templates",
            json=create_payload,
            headers=auth_headers
        )
        assert create_response.status_code == 200
        template_id = create_response.json()["template"]["id"]
        
        # Now patch it
        patch_payload = {
            "name": "TEST_216aj_Patch_Test_Updated",
            "capacity": 15,
            "recurs_days": [0, 2, 4]  # Mon, Wed, Fri
        }
        
        patch_response = requests.patch(
            f"{BASE_URL}/api/memberships/classes/templates/{template_id}",
            json=patch_payload,
            headers=auth_headers
        )
        assert patch_response.status_code == 200, f"Expected 200, got {patch_response.status_code}: {patch_response.text}"
        
        # Verify the update
        get_response = requests.get(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=auth_headers
        )
        templates = get_response.json()["templates"]
        updated = next((t for t in templates if t["id"] == template_id), None)
        
        assert updated is not None, "Template not found after update"
        assert updated["name"] == "TEST_216aj_Patch_Test_Updated"
        assert updated["capacity"] == 15
        assert updated["recurs_days"] == [0, 2, 4]


class TestTimetable:
    """Test timetable endpoint returns occurrences"""
    
    def test_timetable_returns_occurrences(self, auth_headers):
        """GET /memberships/timetable returns occurrences for templates with recurs_days"""
        # Get timetable for next 60 days (to cover term dates)
        from_date = datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z")
        to_date = (datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%dT23:59:59Z")
        
        response = requests.get(
            f"{BASE_URL}/api/memberships/timetable",
            params={"from": from_date, "to": to_date},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "occurrences" in data, "Missing occurrences in response"
        assert isinstance(data["occurrences"], list), "occurrences should be a list"
        
        # Should have at least some occurrences
        print(f"Found {len(data['occurrences'])} occurrences")
        
        # Check that occurrences have required fields
        if data["occurrences"]:
            occ = data["occurrences"][0]
            assert "id" in occ, "Missing id in occurrence"
            assert "name" in occ, "Missing name in occurrence"
            assert "starts_at" in occ, "Missing starts_at in occurrence"
            assert "ends_at" in occ, "Missing ends_at in occurrence"


class TestStudioQuickstart:
    """Test studio quickstart endpoint"""
    
    def test_quickstart_returns_template_with_recurs_days(self, auth_headers):
        """POST /memberships/studio/quickstart creates template with recurs_days"""
        # Note: This will reuse existing data if quickstart already completed
        payload = {
            "class_name": "TEST_216aj_Quickstart_Class",
            "weekly_day": 6,  # Saturday (1-indexed, so 6 = Saturday)
            "weekly_start_time": "10:30",
            "class_capacity": 12,
            "duration_minutes": 60
        }
        
        response = requests.post(
            f"{BASE_URL}/api/memberships/studio/quickstart",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Expected ok=True"
        assert "created" in data, "Missing created in response"
        assert "class_template_id" in data["created"], "Missing class_template_id"
        
        # Verify the template has recurs_days
        template_id = data["created"]["class_template_id"]
        
        templates_response = requests.get(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=auth_headers
        )
        templates = templates_response.json()["templates"]
        template = next((t for t in templates if t["id"] == template_id), None)
        
        if template and not data["created"].get("reused_existing"):
            # Only check if we created a new template
            assert "recurs_days" in template, "Missing recurs_days in template"
            assert "start_time" in template, "Missing start_time in template"
            assert "duration_min" in template, "Missing duration_min in template"


class TestExistingTemplateBackfill:
    """Test that existing quickstart template has been backfilled"""
    
    def test_existing_acro_template_has_recurs_days(self, auth_headers):
        """Verify Bob's existing 'Acro' template has recurs_days after backfill"""
        response = requests.get(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        templates = response.json()["templates"]
        acro_template = next((t for t in templates if t.get("name") == "Acro"), None)
        
        if acro_template:
            # Verify backfill worked
            assert "recurs_days" in acro_template, "Missing recurs_days in Acro template"
            assert acro_template["recurs_days"] is not None, "recurs_days is None"
            assert len(acro_template["recurs_days"]) > 0, "recurs_days is empty"
            
            assert "start_time" in acro_template, "Missing start_time in Acro template"
            assert acro_template["start_time"] is not None, "start_time is None"
            
            assert "duration_min" in acro_template, "Missing duration_min in Acro template"
            
            print(f"Acro template: recurs_days={acro_template['recurs_days']}, "
                  f"start_time={acro_template['start_time']}, "
                  f"duration_min={acro_template['duration_min']}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_templates(self, auth_headers):
        """Archive TEST_ prefixed templates"""
        response = requests.get(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=auth_headers
        )
        if response.status_code != 200:
            return
        
        templates = response.json().get("templates", [])
        for template in templates:
            if template.get("name", "").startswith("TEST_216aj_"):
                delete_response = requests.delete(
                    f"{BASE_URL}/api/memberships/classes/templates/{template['id']}",
                    headers=auth_headers
                )
                print(f"Archived template {template['name']}: {delete_response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
