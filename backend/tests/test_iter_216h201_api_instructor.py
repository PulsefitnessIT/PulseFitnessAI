"""Iter 216h201 — API tests for instructor email+phone validation.

Tests the live backend endpoint POST /api/memberships/instructors.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_headers():
    """Login as E1 test agent and return auth headers."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "e1.agent@gymaxisai.com",
        "password": "E1Agent123!"
    })
    if resp.status_code != 200:
        pytest.skip(f"Login failed: {resp.status_code} - {resp.text}")
    token = resp.json().get("token")
    return {"Authorization": f"Bearer {token}"}


class TestInstructorValidation:
    """POST /api/memberships/instructors validation tests."""

    def test_rejects_missing_email(self, auth_headers):
        """Missing email → 400 'email required'."""
        resp = requests.post(f"{BASE_URL}/api/memberships/instructors", 
            headers=auth_headers,
            json={"name": "Test Instructor", "phone": "07700900000"})
        assert resp.status_code == 400
        assert "email" in resp.text.lower()

    def test_rejects_invalid_email_format(self, auth_headers):
        """Invalid email format → 400 'Invalid email format'."""
        resp = requests.post(f"{BASE_URL}/api/memberships/instructors",
            headers=auth_headers,
            json={"name": "Test Instructor", "email": "not-an-email", "phone": "07700900000"})
        assert resp.status_code == 400
        assert "email" in resp.text.lower()

    def test_rejects_missing_phone(self, auth_headers):
        """Missing phone → 400 'phone required'."""
        resp = requests.post(f"{BASE_URL}/api/memberships/instructors",
            headers=auth_headers,
            json={"name": "Test Instructor", "email": "test@example.com"})
        assert resp.status_code == 400
        assert "phone" in resp.text.lower()

    def test_rejects_whitespace_phone(self, auth_headers):
        """Whitespace-only phone → 400 'phone required'."""
        resp = requests.post(f"{BASE_URL}/api/memberships/instructors",
            headers=auth_headers,
            json={"name": "Test Instructor", "email": "test@example.com", "phone": "   "})
        assert resp.status_code == 400
        assert "phone" in resp.text.lower()

    def test_happy_path_creates_instructor(self, auth_headers):
        """Valid email + phone → 200 with instructor.id."""
        import uuid
        unique_email = f"test.instructor.{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(f"{BASE_URL}/api/memberships/instructors",
            headers=auth_headers,
            json={
                "name": "TEST_Happy Path Instructor",
                "email": unique_email,
                "phone": "07700900123"
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "instructor" in data
        assert "id" in data["instructor"]
        assert data["instructor"]["email"] == unique_email
        assert data["instructor"]["phone"] == "07700900123"
        
        # Cleanup - archive the test instructor
        inst_id = data["instructor"]["id"]
        requests.delete(f"{BASE_URL}/api/memberships/instructors/{inst_id}", headers=auth_headers)
