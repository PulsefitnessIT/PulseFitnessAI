"""
P1-D Human-escalation pipeline & Analytics tests for Ask GymAxis / Pulse Fitness AI support orb.

Tests:
- POST /api/support/escalate (needs existing session_id from POST /api/support/session)
- POST /api/support/feedback (rating 'up'|'down' + optional comment)
- GET /api/master-admin/support/cases (master admin only)
- GET /api/master-admin/support/cases/{case_id}
- PATCH /api/master-admin/support/cases/{case_id}
- GET /api/master-admin/support/analytics?days=30
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials sourced from the central conftest (env-var overridable).
# No secret values live in this file.
from tests.conftest import (
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
    PULSE_PRO_EMAIL,
    PULSE_PRO_PASSWORD,
)


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def master_admin_token(api_client):
    """Get master admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Master admin authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def pulse_pro_token(api_client):
    """Get Pulse Pro user authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Pulse Pro user authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def master_admin_client(api_client, master_admin_token):
    """Session with master admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {master_admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def pulse_pro_client(api_client, pulse_pro_token):
    """Session with Pulse Pro user auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {pulse_pro_token}"
    })
    return session


class TestSupportSession:
    """Test support session creation"""

    def test_create_support_session(self, pulse_pro_client):
        """POST /api/support/session - creates a new support session"""
        response = pulse_pro_client.post(f"{BASE_URL}/api/support/session", json={
            "page": "/pulse",
            "entity_id": None,
            "entity_type": None
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "session_id" in data, "Response should contain session_id"
        assert "assistant_name" in data, "Response should contain assistant_name"
        print(f"✓ Support session created: {data.get('session_id')[:8]}...")


class TestSupportEscalate:
    """Test human escalation endpoint"""

    @pytest.fixture
    def session_id(self, pulse_pro_client):
        """Create a support session for escalation tests"""
        response = pulse_pro_client.post(f"{BASE_URL}/api/support/session", json={
            "page": "/pulse",
            "entity_id": None,
            "entity_type": None
        })
        if response.status_code == 200:
            return response.json().get("session_id")
        pytest.skip("Could not create support session")

    def test_escalate_to_human_pulse_pro(self, pulse_pro_client, session_id):
        """POST /api/support/escalate - Pulse Pro user escalation"""
        response = pulse_pro_client.post(f"{BASE_URL}/api/support/escalate", json={
            "session_id": session_id,
            "reason": "Test escalation from Pulse Pro user",
            "last_message": "I need help with my equipment"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify response structure
        assert data.get("success") is True, "Response should have success: true"
        assert "case_id" in data, "Response should contain case_id"
        assert "case_ref" in data, "Response should contain case_ref"
        assert data["case_ref"].startswith("ASK-"), f"Case ref should start with ASK-, got {data['case_ref']}"
        assert "email_sent" in data, "Response should contain email_sent"
        assert "recipient" in data, "Response should contain recipient"
        assert "platform_name" in data, "Response should contain platform_name"

        # Verify Pulse Pro user gets routed to Pulse Fitness support
        assert data["recipient"] == "service.dept@pulsefitness.com", \
            f"Pulse Pro user should route to service.dept@pulsefitness.com, got {data['recipient']}"
        assert data["platform_name"] == "Pulse Fitness", \
            f"Platform name should be 'Pulse Fitness', got {data['platform_name']}"

        print(f"✓ Escalation created: {data['case_ref']}, recipient: {data['recipient']}, platform: {data['platform_name']}")
        return data["case_id"]


class TestSupportFeedback:
    """Test CSAT feedback endpoint"""

    @pytest.fixture
    def session_id(self, pulse_pro_client):
        """Create a support session for feedback tests"""
        response = pulse_pro_client.post(f"{BASE_URL}/api/support/session", json={
            "page": "/pulse",
            "entity_id": None,
            "entity_type": None
        })
        if response.status_code == 200:
            return response.json().get("session_id")
        pytest.skip("Could not create support session")

    def test_submit_feedback_thumbs_up(self, pulse_pro_client, session_id):
        """POST /api/support/feedback - thumbs up rating"""
        response = pulse_pro_client.post(f"{BASE_URL}/api/support/feedback", json={
            "session_id": session_id,
            "turn_id": "turn-1",
            "rating": "up",
            "comment": None
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") is True, "Response should have success: true"
        assert "id" in data, "Response should contain feedback id"
        print(f"✓ Thumbs up feedback submitted: {data['id'][:8]}...")

    def test_submit_feedback_thumbs_down_with_comment(self, pulse_pro_client, session_id):
        """POST /api/support/feedback - thumbs down with comment"""
        response = pulse_pro_client.post(f"{BASE_URL}/api/support/feedback", json={
            "session_id": session_id,
            "turn_id": "turn-2",
            "rating": "down",
            "comment": "The answer was not helpful"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") is True, "Response should have success: true"
        assert "id" in data, "Response should contain feedback id"
        print(f"✓ Thumbs down feedback with comment submitted: {data['id'][:8]}...")

    def test_multiple_feedback_per_session(self, pulse_pro_client, session_id):
        """Multiple feedback rows can be written per session"""
        feedback_ids = []
        for i in range(3):
            response = pulse_pro_client.post(f"{BASE_URL}/api/support/feedback", json={
                "session_id": session_id,
                "turn_id": f"turn-{i+10}",
                "rating": "up" if i % 2 == 0 else "down",
                "comment": f"Feedback {i+1}"
            })
            assert response.status_code == 200, f"Feedback {i+1} failed: {response.status_code}"
            feedback_ids.append(response.json().get("id"))

        # Verify all feedback IDs are unique
        assert len(set(feedback_ids)) == 3, "All feedback IDs should be unique"
        print(f"✓ Multiple feedback rows created: {len(feedback_ids)} entries")


class TestMasterAdminSupportCases:
    """Test master admin support case endpoints"""

    @pytest.fixture
    def test_case_id(self, pulse_pro_client, master_admin_client):
        """Create a test case for admin tests"""
        # Create session
        session_res = pulse_pro_client.post(f"{BASE_URL}/api/support/session", json={
            "page": "/pulse", "entity_id": None, "entity_type": None
        })
        if session_res.status_code != 200:
            pytest.skip("Could not create support session")
        session_id = session_res.json().get("session_id")

        # Escalate to create a case
        escalate_res = pulse_pro_client.post(f"{BASE_URL}/api/support/escalate", json={
            "session_id": session_id,
            "reason": "Test case for admin tests",
            "last_message": "Admin test message"
        })
        if escalate_res.status_code != 200:
            pytest.skip("Could not create escalation case")
        return escalate_res.json().get("case_id")

    def test_list_cases_master_admin(self, master_admin_client):
        """GET /api/master-admin/support/cases - master admin can list cases"""
        response = master_admin_client.get(f"{BASE_URL}/api/master-admin/support/cases?limit=50")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "cases" in data, "Response should contain cases array"
        assert "total" in data, "Response should contain total count"
        assert isinstance(data["cases"], list), "cases should be a list"
        print(f"✓ Listed {data['total']} support cases")

    def test_list_cases_with_status_filter(self, master_admin_client):
        """GET /api/master-admin/support/cases?status=open - filter by status"""
        response = master_admin_client.get(f"{BASE_URL}/api/master-admin/support/cases?status=open")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "cases" in data, "Response should contain cases array"
        # Verify all returned cases have status=open
        for case in data["cases"]:
            assert case.get("status") == "open", f"Expected status=open, got {case.get('status')}"
        print(f"✓ Filtered cases by status=open: {len(data['cases'])} cases")

    def test_list_cases_non_admin_forbidden(self, pulse_pro_client):
        """GET /api/master-admin/support/cases - non-admin should get 403"""
        response = pulse_pro_client.get(f"{BASE_URL}/api/master-admin/support/cases")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly denied access to support cases")

    def test_get_case_detail(self, master_admin_client, test_case_id):
        """GET /api/master-admin/support/cases/{case_id} - get case with transcript"""
        response = master_admin_client.get(f"{BASE_URL}/api/master-admin/support/cases/{test_case_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify case structure
        assert "id" in data, "Case should have id"
        assert "ref" in data, "Case should have ref"
        assert "transcript" in data, "Case should have transcript array"
        assert isinstance(data["transcript"], list), "transcript should be a list"
        assert "status" in data, "Case should have status"
        assert "user_email" in data, "Case should have user_email"
        print(f"✓ Retrieved case detail: {data['ref']} with {len(data['transcript'])} transcript entries")

    def test_patch_case_status_resolved(self, master_admin_client, test_case_id):
        """PATCH /api/master-admin/support/cases/{case_id} - update status to resolved"""
        response = master_admin_client.patch(
            f"{BASE_URL}/api/master-admin/support/cases/{test_case_id}",
            json={
                "status": "resolved",
                "resolution": "handled via phone"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify updates applied
        assert data.get("status") == "resolved", f"Expected status=resolved, got {data.get('status')}"
        assert data.get("resolution") == "handled via phone", "Resolution should be set"
        assert "closed_at" in data and data["closed_at"] is not None, "closed_at should be set for resolved status"
        print(f"✓ Case {data['ref']} updated to resolved with closed_at set")


class TestMasterAdminSupportAnalytics:
    """Test master admin support analytics endpoint"""

    def test_analytics_summary(self, master_admin_client):
        """GET /api/master-admin/support/analytics?days=30 - get analytics summary"""
        response = master_admin_client.get(f"{BASE_URL}/api/master-admin/support/analytics?days=30")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify all required fields
        required_fields = [
            "window_days", "since", "until", "volume", "deflection_pct",
            "avg_latency_ms", "csat", "classifier_breakdown", "cases_by_status"
        ]
        for field in required_fields:
            assert field in data, f"Analytics should contain {field}"

        # Verify volume structure
        volume = data.get("volume", {})
        assert "asks" in volume, "volume should contain asks"
        assert "blocked" in volume, "volume should contain blocked"
        assert "escalated" in volume, "volume should contain escalated"

        # Verify csat structure
        csat = data.get("csat", {})
        assert "thumbs_up" in csat, "csat should contain thumbs_up"
        assert "thumbs_down" in csat, "csat should contain thumbs_down"
        assert "score_pct" in csat, "csat should contain score_pct"

        # Verify cases_by_status structure
        cases_by_status = data.get("cases_by_status", {})
        for status in ["open", "in_progress", "resolved", "closed"]:
            assert status in cases_by_status, f"cases_by_status should contain {status}"

        print(f"✓ Analytics summary: {data['window_days']} days, {volume.get('asks', 0)} asks, "
              f"{data['deflection_pct']}% deflection, CSAT: {csat.get('score_pct', 'N/A')}%")

    def test_analytics_non_admin_forbidden(self, pulse_pro_client):
        """GET /api/master-admin/support/analytics - non-admin should get 403"""
        response = pulse_pro_client.get(f"{BASE_URL}/api/master-admin/support/analytics?days=30")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly denied access to analytics")


class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_cases(self, master_admin_client):
        """Clean up test cases created during testing"""
        # List all cases
        response = master_admin_client.get(f"{BASE_URL}/api/master-admin/support/cases?limit=100")
        if response.status_code == 200:
            cases = response.json().get("cases", [])
            test_cases = [c for c in cases if "Test" in (c.get("reason") or "")]
            print(f"✓ Found {len(test_cases)} test cases (cleanup skipped - cases preserved for analytics)")
        else:
            print("✓ Cleanup check completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
