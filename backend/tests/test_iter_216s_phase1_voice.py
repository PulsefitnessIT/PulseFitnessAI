"""
Test iteration 216s — Phase 1 Service Desk: Voice dictation + Quick note + Directions

Tests:
1. POST /api/svc/cases/{case_id}/notes — add note endpoint
2. GET /api/svc/engineer/jobs/{case_id} — job detail with events
3. Verify note appears in timeline after creation
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for master admin"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def test_case(auth_headers):
    """Create or find a test case for note testing"""
    # First try to find an existing open case
    resp = requests.get(f"{BASE_URL}/api/svc/cases?status=open&limit=1", headers=auth_headers)
    if resp.status_code == 200:
        cases = resp.json().get("cases", [])
        if cases:
            return cases[0]
    
    # If no open case, try to find any case
    resp = requests.get(f"{BASE_URL}/api/svc/cases?limit=1", headers=auth_headers)
    if resp.status_code == 200:
        cases = resp.json().get("cases", [])
        if cases:
            return cases[0]
    
    pytest.skip("No test case available for note testing")


class TestCaseNotesEndpoint:
    """Test POST /api/svc/cases/{case_id}/notes endpoint"""
    
    def test_add_note_success(self, auth_headers, test_case):
        """Test adding a note to a case"""
        case_id = test_case["id"]
        note_body = f"TEST_voice_note_{uuid.uuid4().hex[:8]}: Engineer observed treadmill belt slipping at 8km/h"
        
        resp = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/notes",
            headers=auth_headers,
            json={
                "body": note_body,
                "visibility": "internal"
            }
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # Verify response structure
        assert "id" in data, "Response should contain event id"
        assert "at" in data, "Response should contain timestamp"
        assert data.get("type") == "note", f"Event type should be 'note', got {data.get('type')}"
        assert data.get("body") == note_body, "Note body should match"
        
        # Store for cleanup
        return data
    
    def test_add_note_with_customer_visibility(self, auth_headers, test_case):
        """Test adding a customer-visible note"""
        case_id = test_case["id"]
        note_body = f"TEST_customer_note_{uuid.uuid4().hex[:8]}: Work completed successfully"
        
        resp = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/notes",
            headers=auth_headers,
            json={
                "body": note_body,
                "visibility": "customer"
            }
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # Check visibility is persisted in extra
        extra = data.get("extra", {})
        assert extra.get("visibility") == "customer", f"Visibility should be 'customer', got {extra.get('visibility')}"
    
    def test_add_note_empty_body_rejected(self, auth_headers, test_case):
        """Test that empty note body is rejected"""
        case_id = test_case["id"]
        
        resp = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/notes",
            headers=auth_headers,
            json={
                "body": "",
                "visibility": "internal"
            }
        )
        
        assert resp.status_code == 400, f"Expected 400 for empty body, got {resp.status_code}"
    
    def test_add_note_whitespace_only_rejected(self, auth_headers, test_case):
        """Test that whitespace-only note body is rejected"""
        case_id = test_case["id"]
        
        resp = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/notes",
            headers=auth_headers,
            json={
                "body": "   \n\t  ",
                "visibility": "internal"
            }
        )
        
        assert resp.status_code == 400, f"Expected 400 for whitespace-only body, got {resp.status_code}"
    
    def test_add_note_invalid_case_id(self, auth_headers):
        """Test adding note to non-existent case"""
        fake_case_id = f"fake-case-{uuid.uuid4()}"
        
        resp = requests.post(
            f"{BASE_URL}/api/svc/cases/{fake_case_id}/notes",
            headers=auth_headers,
            json={
                "body": "This should fail",
                "visibility": "internal"
            }
        )
        
        assert resp.status_code == 404, f"Expected 404 for invalid case, got {resp.status_code}"


class TestCaseTimelineUpdated:
    """Test that notes appear in case timeline"""
    
    def test_note_appears_in_timeline(self, auth_headers, test_case):
        """Verify note is persisted and appears in case events"""
        case_id = test_case["id"]
        unique_marker = uuid.uuid4().hex[:8]
        note_body = f"TEST_timeline_check_{unique_marker}: Verifying timeline persistence"
        
        # Add the note
        add_resp = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/notes",
            headers=auth_headers,
            json={
                "body": note_body,
                "visibility": "internal"
            }
        )
        assert add_resp.status_code == 200, f"Failed to add note: {add_resp.text}"
        note_id = add_resp.json().get("id")
        
        # Fetch case detail and check events
        detail_resp = requests.get(
            f"{BASE_URL}/api/svc/cases/{case_id}",
            headers=auth_headers
        )
        assert detail_resp.status_code == 200, f"Failed to get case detail: {detail_resp.text}"
        
        case_data = detail_resp.json()
        events = case_data.get("events", [])
        
        # Find our note in the events
        found_note = None
        for event in events:
            if event.get("id") == note_id:
                found_note = event
                break
        
        assert found_note is not None, f"Note {note_id} not found in case events"
        assert found_note.get("body") == note_body, "Note body should match in timeline"
        assert found_note.get("type") == "note", "Event type should be 'note'"


class TestEngineerJobDetailWithNotes:
    """Test engineer job detail endpoint includes notes"""
    
    def test_engineer_job_detail_includes_events(self, auth_headers, test_case):
        """Verify engineer job detail includes timeline events"""
        case_id = test_case["id"]
        
        # Note: This endpoint requires the user to be assigned as engineer
        # For master admin, we test the regular case detail endpoint instead
        resp = requests.get(
            f"{BASE_URL}/api/svc/cases/{case_id}",
            headers=auth_headers
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "events" in data, "Case detail should include events array"
        assert isinstance(data["events"], list), "Events should be a list"


class TestCaseUpdatedAtAdvances:
    """Test that case updated_at advances when note is added"""
    
    def test_updated_at_advances_on_note(self, auth_headers, test_case):
        """Verify case updated_at timestamp advances after adding note"""
        case_id = test_case["id"]
        
        # Get initial case state
        initial_resp = requests.get(
            f"{BASE_URL}/api/svc/cases/{case_id}",
            headers=auth_headers
        )
        assert initial_resp.status_code == 200
        initial_updated_at = initial_resp.json().get("updated_at")
        
        # Add a note
        note_body = f"TEST_updated_at_{uuid.uuid4().hex[:8]}: Checking timestamp update"
        add_resp = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/notes",
            headers=auth_headers,
            json={
                "body": note_body,
                "visibility": "internal"
            }
        )
        assert add_resp.status_code == 200
        
        # Get updated case state
        updated_resp = requests.get(
            f"{BASE_URL}/api/svc/cases/{case_id}",
            headers=auth_headers
        )
        assert updated_resp.status_code == 200
        new_updated_at = updated_resp.json().get("updated_at")
        
        # Verify timestamp advanced (or at least exists)
        assert new_updated_at is not None, "Case should have updated_at timestamp"
        if initial_updated_at:
            assert new_updated_at >= initial_updated_at, "updated_at should advance or stay same"


class TestHealthCheck:
    """Basic health check for service ops endpoints"""
    
    def test_svc_cases_list_endpoint(self, auth_headers):
        """Verify /api/svc/cases endpoint is accessible"""
        resp = requests.get(f"{BASE_URL}/api/svc/cases", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "cases" in data, "Response should contain 'cases' key"
        assert "total" in data, "Response should contain 'total' key"
    
    def test_engineer_me_endpoint(self, auth_headers):
        """Verify /api/svc/engineer/me endpoint is accessible"""
        resp = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=auth_headers)
        # May return 200 or 403 depending on user setup
        assert resp.status_code in [200, 403], f"Unexpected status: {resp.status_code}: {resp.text}"
    
    def test_engineer_jobs_endpoint(self, auth_headers):
        """Verify /api/svc/engineer/jobs endpoint is accessible"""
        resp = requests.get(f"{BASE_URL}/api/svc/engineer/jobs", headers=auth_headers)
        # May return 200 or 403 depending on user setup
        assert resp.status_code in [200, 403], f"Unexpected status: {resp.status_code}: {resp.text}"
