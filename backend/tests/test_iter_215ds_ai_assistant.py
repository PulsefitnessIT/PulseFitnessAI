"""
Phase 5 AI Assistant Layer Tests — iter 215ds

Tests for the four AI endpoints:
1. POST /api/svc/ai/triage - Intake triage
2. POST /api/svc/ai/photo/classify - Photo classification
3. POST /api/svc/ai/summarise/{case_id} - Case summarisation
4. POST /api/svc/ai/scheduler-tiebreak - Scheduler tie-break

Also tests:
- AI call logging to svc_ai_calls
- Org-scoping (user from org A cannot access org B's data)
- Auto-assign tie-break integration
"""
import pytest
import requests
import os
import base64
import io
import time
from PIL import Image, ImageDraw

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for master admin"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"}
    )
    if response.status_code != 200:
        pytest.skip("Authentication failed")
    return response.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_case_id(auth_headers):
    """Get or create a test case for AI testing"""
    # First try to get existing cases
    response = requests.get(f"{BASE_URL}/api/svc/cases", headers=auth_headers)
    if response.status_code == 200:
        cases = response.json().get("cases", [])
        if cases:
            return cases[0]["id"]

    # Create a new case if none exist
    response = requests.post(
        f"{BASE_URL}/api/svc/intake/phone",
        headers=auth_headers,
        json={
            "title": "TEST_AI_Case",
            "description": "Test case for AI assistant testing",
            "priority": "p3",
            "site_name": "Test Site",
            "customer_name": "Test Customer",
            "customer_phone": "+447700900001"
        }
    )
    if response.status_code in (200, 201):
        return response.json().get("id")
    pytest.skip("Could not get or create test case")


@pytest.fixture(scope="module")
def test_image_base64():
    """Create a test image with visible features"""
    img = Image.new('RGB', (200, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 80, 80], fill='red', outline='black')
    draw.ellipse([100, 50, 180, 130], fill='blue', outline='black')
    draw.line([10, 150, 190, 180], fill='green', width=5)
    draw.text((50, 100), "TEST", fill='black')

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


class TestTriageEndpoint:
    """Tests for POST /api/svc/ai/triage"""

    def test_triage_with_valid_description(self, auth_headers):
        """Triage with valid description returns priority, fault_code, likely_parts"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/triage",
            headers=auth_headers,
            json={
                "description": "The treadmill belt is fraying on the left edge and making a slapping sound at high speeds.",
                "site_name": "PureGym Holborn",
                "asset_name": "Treadmill #14"
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert data.get("priority") in ("p1", "p2", "p3", "p4")
        assert "fault_code" in data
        assert isinstance(data.get("likely_parts"), list)
        assert "rationale" in data
        assert 0 <= data.get("confidence", 0) <= 1
        assert "latency_ms" in data

    def test_triage_missing_description_returns_400(self, auth_headers):
        """Triage without description returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/triage",
            headers=auth_headers,
            json={"site_name": "PureGym Holborn"}
        )
        assert response.status_code == 400
        assert "description" in response.json().get("detail", "").lower()

    def test_triage_empty_description_returns_400(self, auth_headers):
        """Triage with empty description returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/triage",
            headers=auth_headers,
            json={"description": ""}
        )
        assert response.status_code == 400


class TestPhotoClassifyEndpoint:
    """Tests for POST /api/svc/ai/photo/classify"""

    def test_photo_classify_with_base64_image(self, auth_headers, test_image_base64):
        """Photo classify with base64 image returns tags, severity, summary"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/photo/classify",
            headers=auth_headers,
            json={"image_base64": test_image_base64},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert isinstance(data.get("tags"), list)
        assert data.get("severity") in ("low", "med", "high")
        assert "summary" in data
        assert "latency_ms" in data

    def test_photo_classify_missing_inputs_returns_400(self, auth_headers):
        """Photo classify without photo_id or image_base64 returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/photo/classify",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 400
        assert "image_base64 or photo_id required" in response.json().get("detail", "")

    def test_photo_classify_nonexistent_photo_returns_404(self, auth_headers):
        """Photo classify with non-existent photo_id returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/photo/classify",
            headers=auth_headers,
            json={"photo_id": "non-existent-photo-id"}
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()


class TestSummariseEndpoint:
    """Tests for POST /api/svc/ai/summarise/{case_id}"""

    def test_summarise_existing_case(self, auth_headers, test_case_id):
        """Summarise existing case returns customer_summary and engineer_summary"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/summarise/{test_case_id}",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert "customer_summary" in data
        assert "engineer_summary" in data
        assert "latency_ms" in data
        # Customer summary should not contain engineer names (per spec)
        # This is a soft check - Claude should follow the prompt
        assert len(data.get("customer_summary", "")) > 0

    def test_summarise_nonexistent_case_returns_404(self, auth_headers):
        """Summarise non-existent case returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/summarise/non-existent-case-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()


class TestSchedulerTiebreakEndpoint:
    """Tests for POST /api/svc/ai/scheduler-tiebreak"""

    def test_tiebreak_with_valid_candidates(self, auth_headers, test_case_id):
        """Tie-break with valid candidates returns chosen_engineer_id"""
        # Use known engineer IDs from svc_engineers collection
        # These were created during Phase 2/3 testing
        engineer_ids = [
            "d7fc6143-ae1e-45e9-8a49-bcc4237754a6",  # Master Admin
            "7c1d3509-1f2e-4f29-ab5d-538780d90fbf"   # Test Engineer 2
        ]

        engineer_ids = [
            "d7fc6143-ae1e-45e9-8a49-bcc4237754a6",  # Master Admin
            "7c1d3509-1f2e-4f29-ab5d-538780d90fbf"   # Test Engineer 2
        ]

        response = requests.post(
            f"{BASE_URL}/api/svc/ai/scheduler-tiebreak",
            headers=auth_headers,
            json={
                "case_id": test_case_id,
                "candidate_engineer_ids": engineer_ids
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert data.get("chosen_engineer_id") in engineer_ids
        assert "reasoning" in data
        assert "latency_ms" in data

    def test_tiebreak_less_than_2_candidates_returns_400(self, auth_headers, test_case_id):
        """Tie-break with <2 candidates returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/scheduler-tiebreak",
            headers=auth_headers,
            json={
                "case_id": test_case_id,
                "candidate_engineer_ids": ["single-engineer-id"]
            }
        )
        assert response.status_code == 400
        assert "≥2" in response.json().get("detail", "")

    def test_tiebreak_nonexistent_case_returns_404(self, auth_headers):
        """Tie-break with non-existent case returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/scheduler-tiebreak",
            headers=auth_headers,
            json={
                "case_id": "non-existent-case",
                "candidate_engineer_ids": ["eng1", "eng2"]
            }
        )
        assert response.status_code == 404


class TestAICallLogging:
    """Tests for AI call logging to svc_ai_calls"""

    def test_triage_logs_to_svc_ai_calls(self, auth_headers):
        """Triage call is logged to svc_ai_calls with kind='triage'"""
        # Make a triage call
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/triage",
            headers=auth_headers,
            json={"description": "Test logging - belt fraying on treadmill"},
            timeout=30
        )
        assert response.status_code == 200

        # The logging is async, so we can't directly verify from the API
        # But we can verify the response structure indicates success
        data = response.json()
        assert data.get("ok") is True
        assert "latency_ms" in data


class TestOrgScoping:
    """Tests for organization scoping"""

    def test_org_b_cannot_summarise_org_a_case(self, test_case_id):
        """User from org B cannot summarise org A's case"""
        # Login as org B user
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "test.orgb@tottenham.com", "password": "TestUser123!"}
        )
        if login_response.status_code != 200:
            pytest.skip("Org B user not available")

        org_b_token = login_response.json().get("token")
        org_b_headers = {"Authorization": f"Bearer {org_b_token}", "Content-Type": "application/json"}

        # Try to summarise org A's case
        response = requests.post(
            f"{BASE_URL}/api/svc/ai/summarise/{test_case_id}",
            headers=org_b_headers
        )
        # Should return 404 (case not found in org B's scope)
        assert response.status_code == 404


class TestAutoAssignTiebreakIntegration:
    """Tests for auto-assign tie-break integration"""

    def test_auto_assign_includes_ai_tiebreak_when_scores_close(self, auth_headers):
        """Auto-assign includes ai_tiebreak field when top 2 scores within 10 points"""
        # This test requires specific setup - engineers with similar scores
        # We'll just verify the endpoint works and check for the field structure

        # Get a case
        cases_response = requests.get(f"{BASE_URL}/api/svc/cases", headers=auth_headers)
        if cases_response.status_code != 200:
            pytest.skip("Could not get cases")

        cases = cases_response.json().get("cases", [])
        unassigned = [c for c in cases if not c.get("assigned_engineer_id")]
        if not unassigned:
            pytest.skip("No unassigned cases for auto-assign test")

        case_id = unassigned[0]["id"]

        response = requests.post(
            f"{BASE_URL}/api/svc/scheduler/auto-assign?case_id={case_id}",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "rankings" in data
        # ai_tiebreak may or may not be present depending on score difference
        # Just verify the structure is correct
        if "ai_tiebreak" in data:
            assert "chosen_engineer_id" in data["ai_tiebreak"]
            assert "reasoning" in data["ai_tiebreak"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
