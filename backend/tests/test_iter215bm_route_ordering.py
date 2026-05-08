"""
Iter 215bm — Route ordering fix verification tests.

Tests that:
1. GET /api/memberships/instructors/performance?days=30 returns 200 (was 404 before fix)
2. GET /api/memberships/instructors/performance?days=7 returns 200 (different window)
3. GET /api/memberships/instructors/{actual_id} still works (regression check)
4. Instructor CRUD (POST/PATCH/DELETE) still works
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API = f"{BASE_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def auth_headers():
    """Get auth token for Master Admin."""
    resp = requests.post(f"{API}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("token")
    assert token, "No token in login response"
    return {"Authorization": f"Bearer {token}"}


class TestRouteOrderingFix:
    """Test that the route ordering fix works correctly."""

    def test_performance_endpoint_30_days(self, auth_headers):
        """GET /api/memberships/instructors/performance?days=30 returns 200 with correct structure.

        This was returning 404 'Instructor not found' before the fix because
        /memberships/instructors/{instructor_id} was registered before /memberships/instructors/performance.
        """
        resp = requests.get(f"{API}/memberships/instructors/performance?days=30", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        # Verify response structure
        assert "rows" in data, "Missing 'rows' in response"
        assert "count" in data, "Missing 'count' in response"
        assert "window_days" in data, "Missing 'window_days' in response"
        assert "since" in data, "Missing 'since' in response"

        assert data["window_days"] == 30, f"Expected window_days=30, got {data['window_days']}"
        assert isinstance(data["rows"], list), "rows should be a list"
        assert isinstance(data["count"], int), "count should be an int"

        print("✓ GET /api/memberships/instructors/performance?days=30 returns 200")
        print(f"  - rows: {data['count']}, window_days: {data['window_days']}, since: {data['since'][:10]}")

    def test_performance_endpoint_7_days(self, auth_headers):
        """GET /api/memberships/instructors/performance?days=7 returns 200 with correct window."""
        resp = requests.get(f"{API}/memberships/instructors/performance?days=7", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "rows" in data
        assert "window_days" in data
        assert data["window_days"] == 7, f"Expected window_days=7, got {data['window_days']}"

        print("✓ GET /api/memberships/instructors/performance?days=7 returns 200")

    def test_instructor_by_id_still_works(self, auth_headers):
        """GET /api/memberships/instructors/{id} still works after route reordering.

        Regression check to ensure the path-param route wasn't broken by the fix.
        """
        # First create an instructor to get a valid ID
        unique_id = str(uuid.uuid4())[:8]
        create_resp = requests.post(f"{API}/memberships/instructors", json={
            "name": f"Route Test Instructor {unique_id}",
            "email": f"route.test.{unique_id}@example.com"
        }, headers=auth_headers)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"

        instructor_id = create_resp.json()["instructor"]["id"]

        # Now test GET by ID
        resp = requests.get(f"{API}/memberships/instructors/{instructor_id}", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "instructor" in data
        assert data["instructor"]["id"] == instructor_id

        # Cleanup
        requests.delete(f"{API}/memberships/instructors/{instructor_id}", headers=auth_headers)

        print(f"✓ GET /api/memberships/instructors/{{id}} still works: {instructor_id}")

    def test_instructor_crud_regression(self, auth_headers):
        """POST/PATCH/DELETE /api/memberships/instructors still work after route reordering."""
        unique_id = str(uuid.uuid4())[:8]

        # POST - Create
        create_resp = requests.post(f"{API}/memberships/instructors", json={
            "name": f"CRUD Test Instructor {unique_id}",
            "email": f"crud.test.{unique_id}@example.com",
            "headline": "Test headline"
        }, headers=auth_headers)
        assert create_resp.status_code == 200, f"POST failed: {create_resp.text}"
        instructor_id = create_resp.json()["instructor"]["id"]
        print("✓ POST /api/memberships/instructors works")

        # PATCH - Update
        patch_resp = requests.patch(f"{API}/memberships/instructors/{instructor_id}", json={
            "headline": "Updated headline"
        }, headers=auth_headers)
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        assert patch_resp.json()["instructor"]["headline"] == "Updated headline"
        print("✓ PATCH /api/memberships/instructors/{id} works")

        # DELETE - Archive
        delete_resp = requests.delete(f"{API}/memberships/instructors/{instructor_id}", headers=auth_headers)
        assert delete_resp.status_code == 200, f"DELETE failed: {delete_resp.text}"
        assert delete_resp.json().get("ok") == True
        print("✓ DELETE /api/memberships/instructors/{id} works")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
