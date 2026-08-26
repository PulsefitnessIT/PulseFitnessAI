"""Iter 220ci — Engineer Equipment Tab · API integration tests.

Tests the actual HTTP endpoints via requests against the live backend.
Covers:
  - GET /api/svc/engineer/equipment/picklists (auth required, returns canonical lists)
  - GET /api/svc/engineer/equipment (auth required, list with filters)
  - POST /api/svc/engineer/equipment (auth required, strict validation)
  - 401 without auth on all endpoints
  - 422 on missing mandatory fields
  - 422 on off-picklist values
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = 'https://photo-fix-verify.preview.emergentagent.com'


class TestEngineerEquipmentAPI:
    """API integration tests for Engineer Equipment Tab (iter 220ci)."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for master admin."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        if resp.status_code != 200:
            pytest.skip(f"Login failed: {resp.status_code} - {resp.text}")
        return resp.json().get("token")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Auth headers for authenticated requests."""
        return {"Authorization": f"Bearer {auth_token}"}

    # ── 1. Auth required tests ──────────────────────────────────────

    def test_picklists_401_without_auth(self):
        """GET /api/svc/engineer/equipment/picklists returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/svc/engineer/equipment/picklists")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_list_401_without_auth(self):
        """GET /api/svc/engineer/equipment returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/svc/engineer/equipment")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_create_401_without_auth(self):
        """POST /api/svc/engineer/equipment returns 401 without auth."""
        resp = requests.post(f"{BASE_URL}/api/svc/engineer/equipment", json={
            "name": "Test",
            "equipment_type": "Treadmill",
            "manufacturer": "Test",
            "model": "Test",
            "location": "Cardio Zone"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    # ── 2. Picklists endpoint ───────────────────────────────────────

    def test_picklists_returns_200_with_auth(self, auth_headers):
        """GET /api/svc/engineer/equipment/picklists returns 200 with canonical lists."""
        resp = requests.get(
            f"{BASE_URL}/api/svc/engineer/equipment/picklists",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "equipment_type_options" in data, "Missing equipment_type_options"
        assert "location_options" in data, "Missing location_options"
        assert "status_options" in data, "Missing status_options"
        assert "sites" in data, "Missing sites"
        
        # Verify canonical values
        assert "Treadmill" in data["equipment_type_options"]
        assert "Exercise Bike" in data["equipment_type_options"]
        assert "Cardio Zone" in data["location_options"]
        assert "Strength Zone" in data["location_options"]
        assert "in_service" in data["status_options"]
        assert "out_of_service" in data["status_options"]
        
        # Sites should be a list
        assert isinstance(data["sites"], list)
        print(f"✓ Picklists returned {len(data['equipment_type_options'])} types, "
              f"{len(data['location_options'])} locations, {len(data['sites'])} sites")

    # ── 3. List endpoint ────────────────────────────────────────────

    def test_list_returns_200_with_auth(self, auth_headers):
        """GET /api/svc/engineer/equipment returns 200 with equipment list."""
        resp = requests.get(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "equipment" in data, "Missing equipment key"
        assert "count" in data, "Missing count key"
        assert isinstance(data["equipment"], list)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["equipment"])
        print(f"✓ List returned {data['count']} equipment items")

    def test_list_with_q_filter(self, auth_headers):
        """GET /api/svc/engineer/equipment?q=test filters by search term."""
        resp = requests.get(
            f"{BASE_URL}/api/svc/engineer/equipment?q=nonexistent_xyz_123",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        # Should return empty or filtered results
        assert "equipment" in data
        assert "count" in data
        print(f"✓ Search filter returned {data['count']} results")

    # ── 4. Create endpoint - validation ─────────────────────────────

    def test_create_422_missing_name(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 when name is missing."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "equipment_type": "Treadmill",
                "manufacturer": "Life Fitness",
                "model": "Integrity DX",
                "location": "Cardio Zone"
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Missing name correctly rejected with 422")

    def test_create_422_missing_equipment_type(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 when equipment_type is missing."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": "Test Treadmill",
                "manufacturer": "Life Fitness",
                "model": "Integrity DX",
                "location": "Cardio Zone"
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Missing equipment_type correctly rejected with 422")

    def test_create_422_missing_manufacturer(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 when manufacturer is missing."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": "Test Treadmill",
                "equipment_type": "Treadmill",
                "model": "Integrity DX",
                "location": "Cardio Zone"
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Missing manufacturer correctly rejected with 422")

    def test_create_422_missing_model(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 when model is missing."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": "Test Treadmill",
                "equipment_type": "Treadmill",
                "manufacturer": "Life Fitness",
                "location": "Cardio Zone"
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Missing model correctly rejected with 422")

    def test_create_422_missing_location(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 when location is missing."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": "Test Treadmill",
                "equipment_type": "Treadmill",
                "manufacturer": "Life Fitness",
                "model": "Integrity DX"
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Missing location correctly rejected with 422")

    def test_create_422_off_picklist_equipment_type(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 for off-picklist equipment_type."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": "Test Machine",
                "equipment_type": "Tradmill",  # Typo - not in picklist
                "manufacturer": "Life Fitness",
                "model": "Test Model",
                "location": "Cardio Zone"
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Off-picklist equipment_type 'Tradmill' correctly rejected with 422")

    def test_create_422_off_picklist_location(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 for off-picklist location."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": "Test Machine",
                "equipment_type": "Treadmill",
                "manufacturer": "Life Fitness",
                "model": "Test Model",
                "location": "Random Zone XYZ"  # Not in picklist
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Off-picklist location 'Random Zone XYZ' correctly rejected with 422")

    def test_create_422_off_picklist_status(self, auth_headers):
        """POST /api/svc/engineer/equipment returns 422 for off-picklist status."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": "Test Machine",
                "equipment_type": "Treadmill",
                "manufacturer": "Life Fitness",
                "model": "Test Model",
                "location": "Cardio Zone",
                "status": "broken"  # Not in picklist
            }
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Off-picklist status 'broken' correctly rejected with 422")

    # ── 5. Create endpoint - success case ───────────────────────────

    def test_create_success_with_valid_payload(self, auth_headers):
        """POST /api/svc/engineer/equipment creates equipment with valid payload."""
        unique_name = f"TEST_Treadmill_{uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment",
            headers=auth_headers,
            json={
                "name": unique_name,
                "equipment_type": "Treadmill",
                "manufacturer": "Life Fitness",
                "model": "Integrity DX",
                "location": "Cardio Zone",
                "serial_number": f"TEST-SN-{uuid.uuid4().hex[:6]}",
                "status": "in_service",
                "notes": "Created by iter 220ci test"
            }
        )
        # May return 200 or 400 depending on site_id requirements
        if resp.status_code == 400:
            # Multi-site org requires site_id
            detail = resp.json().get("detail", "")
            if "site_id" in detail.lower() or "multiple sites" in detail.lower():
                print(f"✓ Create correctly requires site_id for multi-site org: {detail}")
                return
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "id" in data, "Missing id in response"
        assert data["name"] == unique_name
        assert data["equipment_type"] == "Treadmill"
        assert data["manufacturer"] == "Life Fitness"
        assert data["model"] == "Integrity DX"
        assert data["location"] == "Cardio Zone"
        assert data["created_via"] == "engineer_app"
        assert "attached_to_case" in data
        
        print(f"✓ Equipment created successfully: {data['id']}")
        
        # Verify it appears in the list
        list_resp = requests.get(
            f"{BASE_URL}/api/svc/engineer/equipment?q={unique_name}",
            headers=auth_headers
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        found = any(e["id"] == data["id"] for e in list_data["equipment"])
        assert found, f"Created equipment {data['id']} not found in list"
        print("✓ Created equipment verified in list")

    def test_create_with_unknown_case_id(self, auth_headers):
        """POST /api/svc/engineer/equipment?case_id=unknown persists equipment but skips case attach."""
        unique_name = f"TEST_Bike_{uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{BASE_URL}/api/svc/engineer/equipment?case_id=nonexistent-case-xyz",
            headers=auth_headers,
            json={
                "name": unique_name,
                "equipment_type": "Exercise Bike",
                "manufacturer": "Concept 2",
                "model": "BikeErg",
                "location": "Cardio Zone"
            }
        )
        # May return 200 or 400 depending on site_id requirements
        if resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if "site_id" in detail.lower() or "multiple sites" in detail.lower():
                print("✓ Create correctly requires site_id for multi-site org")
                return
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Equipment should be created but not attached to case
        assert "id" in data
        assert data["attached_to_case"] is False
        assert data.get("case_skip_reason") == "case_not_found"
        print("✓ Equipment created with case_skip_reason='case_not_found'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
