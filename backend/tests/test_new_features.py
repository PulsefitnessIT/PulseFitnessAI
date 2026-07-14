"""
GymFix AI Backend API Tests - New Features (Iteration 3)
Tests for: Risk Assessment, Check Sheets, Weekly Digest, Gym Layout, Email System
"""
import pytest
import requests
import os

from tests.conftest import REGULAR_USER_EMAIL, REGULAR_USER_PASSWORD
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://equipment-finance-1.preview.emergentagent.com')

# Test credentials sourced centrally from conftest (see _ensure_regular_test_user)
TEST_EMAIL = REGULAR_USER_EMAIL
TEST_PASSWORD = REGULAR_USER_PASSWORD


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for all tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed")


class TestRiskAssessment:
    """Risk Assessment API tests"""

    @pytest.mark.timeout(90)
    def test_ai_generate_hazards(self, auth_token):
        """Test POST /api/risk-assessments/ai-generate returns hazards array
        Note: This test may take 30-60 seconds due to AI generation
        """
        headers = {"Authorization": f"Bearer {auth_token}"}

        payload = {
            "site_name": "Test Gym Manchester",
            "equipment_types": ["Treadmills", "Exercise Bikes", "Strength Equipment"],
            "site_description": "Commercial gym with cardio and strength areas"
        }

        response = requests.post(
            f"{BASE_URL}/api/risk-assessments/ai-generate",
            json=payload,
            headers=headers,
            timeout=60  # AI generation can take 30-60 seconds
        )
        print(f"AI Generate response status: {response.status_code}")
        print(f"AI Generate response: {response.text[:1000]}")

        assert response.status_code == 200, f"AI generate failed: {response.text}"

        data = response.json()
        assert "hazards" in data, "Response missing 'hazards' field"
        assert isinstance(data["hazards"], list), "Hazards should be a list"
        assert len(data["hazards"]) > 0, "Should return at least one hazard"

        # Verify hazard structure
        hazard = data["hazards"][0]
        expected_fields = ["hazard", "harm", "who", "plr", "psr"]
        for field in expected_fields:
            assert field in hazard, f"Hazard missing field: {field}"

        print(f"Generated {len(data['hazards'])} hazards")
        print(f"First hazard: {hazard.get('hazard')}")

    def test_create_risk_assessment(self, auth_token):
        """Test POST /api/risk-assessments creates assessment with RRN calculation"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        payload = {
            "title": "TEST Risk Assessment - Service Area",
            "site_name": "Test Gym",
            "assessor": "Test User",
            "assessment_date": "2026-01-15",
            "validity_period": "12 months",
            "hazards": [
                {
                    "hazard": "Manual Handling",
                    "harm": "Back injuries from lifting equipment",
                    "who": "Staff, Engineers",
                    "recommended_controls": "Manual handling training",
                    "controls_in_place": "Training provided",
                    "plr": 3,
                    "psr": 4,
                    "further_controls": "Use mechanical aids",
                    "post_plr": 2,
                    "post_psr": 3
                },
                {
                    "hazard": "Electrical Hazards",
                    "harm": "Electric shock",
                    "who": "Engineers",
                    "recommended_controls": "PAT testing",
                    "controls_in_place": "Annual PAT testing",
                    "plr": 2,
                    "psr": 5,
                    "further_controls": "Lockout/tagout",
                    "post_plr": 1,
                    "post_psr": 5
                }
            ],
            "notes": "Test assessment for API testing"
        }

        response = requests.post(
            f"{BASE_URL}/api/risk-assessments",
            json=payload,
            headers=headers
        )
        print(f"Create RA response status: {response.status_code}")
        print(f"Create RA response: {response.text[:1000]}")

        assert response.status_code == 200, f"Create RA failed: {response.text}"

        data = response.json()
        assert "id" in data, "Response missing 'id'"
        assert data["title"] == payload["title"]
        assert data["site_name"] == payload["site_name"]
        assert len(data["hazards"]) == 2

        # Verify RRN calculation
        hazard1 = data["hazards"][0]
        assert hazard1["rrn"] == 12, f"RRN should be 3*4=12, got {hazard1.get('rrn')}"
        assert hazard1["post_rrn"] == 6, f"Post-RRN should be 2*3=6, got {hazard1.get('post_rrn')}"

        print(f"Created RA with ID: {data['id']}")
        return data["id"]

    def test_get_risk_assessments(self, auth_token):
        """Test GET /api/risk-assessments returns list"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/risk-assessments", headers=headers)
        print(f"Get RAs response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert "assessments" in data
        print(f"Found {len(data['assessments'])} risk assessments")


class TestCheckSheets:
    """Check Sheet API tests"""

    def test_get_templates(self, auth_token):
        """Test GET /api/check-sheets/templates returns 8 categories"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/check-sheets/templates", headers=headers)
        print(f"Templates response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert "templates" in data

        templates = data["templates"]
        expected_categories = [
            "Treadmills",
            "Upright & Recumbent Bikes",
            "Cross Trainers",
            "Rowers & Ski-Ergs",
            "Group Cycles",
            "Free Weights & Benches",
            "Strength/Selectorised",
            "StepMills & Steppers"
        ]

        assert len(templates) == 8, f"Expected 8 categories, got {len(templates)}"

        for cat in expected_categories:
            assert cat in templates, f"Missing category: {cat}"
            assert len(templates[cat]) > 0, f"Category {cat} has no check items"

        print(f"Categories: {list(templates.keys())}")
        print(f"Treadmills checks: {templates['Treadmills'][:3]}...")

    def test_complete_check_sheet(self, auth_token):
        """Test POST /api/check-sheets/complete saves completed sheet"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        payload = {
            "equipment_category": "Treadmills",
            "checks": {
                "All Areas Cleaned": True,
                "Hoover Underneath": True,
                "E-Stop Check": True,
                "Console + & - Keys Check": True,
                "Heart Rate Check": False,
                "Speed Test": True,
                "Incline Check": True,
                "Belt Aligned": True
            },
            "notes": "TEST - Heart rate sensor needs replacement on TM-003",
            "date": "2026-01-15"
        }

        response = requests.post(
            f"{BASE_URL}/api/check-sheets/complete",
            json=payload,
            headers=headers
        )
        print(f"Complete sheet response status: {response.status_code}")
        print(f"Complete sheet response: {response.text[:500]}")

        assert response.status_code == 200, f"Complete sheet failed: {response.text}"

        data = response.json()
        assert "id" in data
        assert data["equipment_category"] == "Treadmills"
        assert data["checks"]["All Areas Cleaned"] == True
        assert data["checks"]["Heart Rate Check"] == False

        print(f"Created check sheet with ID: {data['id']}")

    def test_get_check_sheet_history(self, auth_token):
        """Test GET /api/check-sheets/history returns completed sheets"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/check-sheets/history", headers=headers)
        print(f"History response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        # Endpoint was renamed from {sheets:[...]} to {completions:[...]} — accept either for backwards-compat.
        items_key = "completions" if "completions" in data else "sheets"
        assert items_key in data, f"Expected 'completions' or 'sheets' in response keys: {list(data.keys())}"
        print(f"Found {len(data[items_key])} completed check sheets")


class TestWeeklyDigest:
    """Weekly Digest API tests"""

    def test_preview_digest(self, auth_token):
        """Test GET /api/digest/preview returns digest data"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/digest/preview", headers=headers)
        print(f"Digest preview response status: {response.status_code}")
        print(f"Digest preview response: {response.text[:1000]}")

        assert response.status_code == 200, f"Digest preview failed: {response.text}"

        data = response.json()

        # Verify required fields
        assert "summary" in data, "Missing 'summary' field"
        assert "open_issues" in data, "Missing 'open_issues' field"
        assert "equipment_health" in data, "Missing 'equipment_health' field"
        assert "period" in data, "Missing 'period' field"

        # Verify summary structure
        summary = data["summary"]
        expected_summary_fields = [
            "open_issues",
            "in_progress_issues",
            "critical_issues",
            "check_sheets_completed",
            "avg_health_score"
        ]
        for field in expected_summary_fields:
            assert field in summary, f"Summary missing field: {field}"

        print(f"Digest period: {data['period']}")
        print(f"Summary: {summary}")

    def test_send_digest(self, auth_token):
        """Test POST /api/digest/send returns a digest (sent flag depends on Resend config)."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.post(f"{BASE_URL}/api/digest/send", json={}, headers=headers)
        print(f"Send digest response status: {response.status_code}")
        print(f"Send digest response: {response.text[:500]}")

        assert response.status_code == 200, f"Send digest failed: {response.text}"

        data = response.json()
        assert "sent" in data, "Missing 'sent' field"
        assert "digest" in data, "Missing 'digest' field"

        # `sent` is True when Resend is configured, False otherwise — both are valid.
        assert isinstance(data["sent"], bool), "Expected sent to be a bool"

        print(f"Sent: {data['sent']}, Message: {data.get('message', 'N/A')}")


class TestGymLayout:
    """Gym Layout API tests - verifying _id serialization fix"""

    def test_create_gym_layout(self, auth_token):
        """Test POST /api/gym-layouts creates layout without serialization error"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        payload = {
            "name": "TEST Layout - Main Floor",
            "gym_length": 20.0,
            "gym_width": 15.0,
            "equipment_positions": [
                {
                    "equipment_type": "treadmill",
                    "x": 2.0,
                    "y": 2.0,
                    "rotation": 0,
                    "width": 2.0,
                    "height": 1.5
                },
                {
                    "equipment_type": "bike",
                    "x": 5.0,
                    "y": 2.0,
                    "rotation": 0,
                    "width": 1.0,
                    "height": 1.5
                }
            ]
        }

        response = requests.post(
            f"{BASE_URL}/api/gym-layouts",
            json=payload,
            headers=headers
        )
        print(f"Create layout response status: {response.status_code}")
        print(f"Create layout response: {response.text[:500]}")

        assert response.status_code == 200, f"Create layout failed: {response.text}"

        data = response.json()
        assert "id" in data, "Response missing 'id'"
        assert "_id" not in data, "Response should not contain '_id' (MongoDB ObjectId)"
        assert data["name"] == payload["name"]
        assert data["gym_length"] == 20.0
        assert len(data["equipment_positions"]) == 2

        print(f"Created layout with ID: {data['id']}")
        return data["id"]

    def test_get_gym_layouts(self, auth_token):
        """Test GET /api/gym-layouts returns layouts without _id"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/gym-layouts", headers=headers)
        print(f"Get layouts response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert "layouts" in data

        # Verify no _id in any layout
        for layout in data["layouts"]:
            assert "_id" not in layout, f"Layout contains _id: {layout}"

        print(f"Found {len(data['layouts'])} gym layouts")


class TestEquipmentLibrary:
    """Equipment Library tests - verifying SVG icons are available"""

    def test_equipment_types_available(self, auth_token):
        """Verify equipment types are available for gym design"""
        # This is more of a frontend test, but we can verify the maintenance tasks
        # which use similar equipment categories

        response = requests.get(f"{BASE_URL}/api/maintenance/tasks")
        assert response.status_code == 200

        data = response.json()
        tasks = data["tasks"]

        # Verify equipment categories exist
        equipment_types = set(task["equipment"] for task in tasks)
        expected_types = ["Treadmills", "Exercise Bikes", "Cross Trainers", "Rowers", "Strength Equipment", "Free Weights"]

        for eq_type in expected_types:
            assert eq_type in equipment_types, f"Missing equipment type: {eq_type}"

        print(f"Equipment types in maintenance: {equipment_types}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
