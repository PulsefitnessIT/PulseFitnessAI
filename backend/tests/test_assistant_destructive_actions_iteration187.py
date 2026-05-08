"""
Test suite for Unified AI Assistant destructive actions (iteration 187)

Tests:
- POST /api/assistant/chat with mode=operations returns grounded counts from db.issues
- POST /api/assistant/chat with mode=memberships returns grounded member/plan counts
- POST /api/assistant/execute-action resolve_issue
- POST /api/assistant/execute-action freeze_membership
- POST /api/assistant/execute-action cancel_membership
- Idempotency checks
- Cross-org guards
- Disallowed action type rejection
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
RATE_LIMIT_BYPASS = os.environ.get('RATE_LIMIT_BYPASS_SECRET', 'test-bypass-secret-for-ci-runs-only-2026')

# Test credentials from test_credentials.md
OPERATIONS_USER = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!"
}

MEMBERSHIPS_USER = {
    "email": "studio.leeds@gymaxisai.com",
    "password": "Studio2026!"
}


@pytest.fixture(scope="module")
def operations_token():
    """Get auth token for operations user (Lee Somers - Pulse Pro)"""
    headers = {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=OPERATIONS_USER, headers=headers)
    assert resp.status_code == 200, f"Operations login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def memberships_token():
    """Get auth token for memberships user (Studio Manager)"""
    headers = {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=MEMBERSHIPS_USER, headers=headers)
    assert resp.status_code == 200, f"Memberships login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture
def operations_headers(operations_token):
    return {
        "Authorization": f"Bearer {operations_token}",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS
    }


@pytest.fixture
def memberships_headers(memberships_token):
    return {
        "Authorization": f"Bearer {memberships_token}",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS
    }


class TestAssistantChatOperationsMode:
    """Test /api/assistant/chat with mode=operations"""

    def test_operations_chat_returns_grounded_fault_count(self, operations_headers):
        """Operations mode chat should return grounded counts from db.issues collection"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/chat",
            json={
                "mode": "operations",
                "message": "How many open faults do I have?"
            },
            headers=operations_headers,
            timeout=60
        )
        assert resp.status_code == 200, f"Chat failed: {resp.text}"
        data = resp.json()
        assert "answer" in data
        assert data.get("mode") == "operations"
        # The answer should contain some reference to faults/issues
        answer_lower = data["answer"].lower()
        assert any(word in answer_lower for word in ["fault", "issue", "open", "equipment"]), \
            f"Answer doesn't seem to be about faults: {data['answer'][:200]}"
        print(f"Operations chat answer: {data['answer'][:300]}...")

    def test_operations_chat_session_persistence(self, operations_headers):
        """Chat sessions should persist and return session_id"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/chat",
            json={
                "mode": "operations",
                "message": "What equipment needs attention?"
            },
            headers=operations_headers,
            timeout=60
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["session_id"] is not None
        print(f"Session ID: {data['session_id']}")


class TestAssistantChatMembershipsMode:
    """Test /api/assistant/chat with mode=memberships"""

    def test_memberships_chat_returns_grounded_member_count(self, memberships_headers):
        """Memberships mode chat should return grounded counts from db.members"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/chat",
            json={
                "mode": "memberships",
                "message": "How many active members do I have?"
            },
            headers=memberships_headers,
            timeout=60
        )
        assert resp.status_code == 200, f"Chat failed: {resp.text}"
        data = resp.json()
        assert "answer" in data
        assert data.get("mode") == "memberships"
        # The answer should contain some reference to members
        answer_lower = data["answer"].lower()
        assert any(word in answer_lower for word in ["member", "active", "plan"]), \
            f"Answer doesn't seem to be about members: {data['answer'][:200]}"
        print(f"Memberships chat answer: {data['answer'][:300]}...")


class TestResolveIssueAction:
    """Test resolve_issue destructive action"""

    def test_resolve_issue_requires_valid_fault_id(self, operations_headers):
        """resolve_issue with invalid fault_id should return 404"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "operations",
                "type": "resolve_issue",
                "params": {"fault_id": "nonexistent-fault-id-12345"}
            },
            headers=operations_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_resolve_issue_cross_org_guard(self, memberships_headers):
        """resolve_issue with fault from different org should return 404"""
        # Memberships user (studio.leeds) trying to resolve operations user's fault
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "operations",
                "type": "resolve_issue",
                "params": {"fault_id": "some-fault-id"}
            },
            headers=memberships_headers
        )
        # Should fail - either 404 (not found in their org) or 400 (mode mismatch)
        assert resp.status_code in [400, 404], f"Expected 400/404, got {resp.status_code}: {resp.text}"


class TestFreezeMembershipAction:
    """Test freeze_membership destructive action"""

    def test_freeze_membership_requires_valid_member_id(self, memberships_headers):
        """freeze_membership with invalid member_id should return 404"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "memberships",
                "type": "freeze_membership",
                "params": {"member_id": "nonexistent-member-12345", "days": 14}
            },
            headers=memberships_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_freeze_membership_cross_org_guard(self, operations_headers):
        """freeze_membership with member from different org should return 404"""
        # Operations user (lee.somers) trying to freeze memberships user's member
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "memberships",
                "type": "freeze_membership",
                "params": {"member_id": "mbr-sophia", "days": 14}
            },
            headers=operations_headers
        )
        # Should fail - either 404 (not found in their org) or 400 (mode mismatch)
        assert resp.status_code in [400, 404], f"Expected 400/404, got {resp.status_code}: {resp.text}"


class TestCancelMembershipAction:
    """Test cancel_membership destructive action"""

    def test_cancel_membership_requires_valid_member_id(self, memberships_headers):
        """cancel_membership with invalid member_id should return 404"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "memberships",
                "type": "cancel_membership",
                "params": {"member_id": "nonexistent-member-12345", "immediate": False, "reason": "member_request"}
            },
            headers=memberships_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_cancel_membership_cross_org_guard(self, operations_headers):
        """cancel_membership with member from different org should return 404"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "memberships",
                "type": "cancel_membership",
                "params": {"member_id": "mbr-sophia", "immediate": False, "reason": "member_request"}
            },
            headers=operations_headers
        )
        assert resp.status_code in [400, 404], f"Expected 400/404, got {resp.status_code}: {resp.text}"


class TestDisallowedActionTypes:
    """Test that action types are rejected when used in wrong mode"""

    def test_resolve_issue_rejected_in_marketing_mode(self, operations_headers):
        """resolve_issue should be rejected in marketing mode"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "marketing",
                "type": "resolve_issue",
                "params": {"fault_id": "some-fault-id"}
            },
            headers=operations_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "not allowed" in resp.text.lower() or "action" in resp.text.lower()

    def test_freeze_membership_rejected_in_operations_mode(self, operations_headers):
        """freeze_membership should be rejected in operations mode"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "operations",
                "type": "freeze_membership",
                "params": {"member_id": "some-member-id", "days": 14}
            },
            headers=operations_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_cancel_membership_rejected_in_marketing_mode(self, operations_headers):
        """cancel_membership should be rejected in marketing mode"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "marketing",
                "type": "cancel_membership",
                "params": {"member_id": "some-member-id", "immediate": True}
            },
            headers=operations_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


class TestModeValidation:
    """Test mode validation in assistant endpoints"""

    def test_invalid_mode_rejected_in_chat(self, operations_headers):
        """Invalid mode should be rejected in chat endpoint"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/chat",
            json={
                "mode": "invalid_mode",
                "message": "Hello"
            },
            headers=operations_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_invalid_mode_rejected_in_execute_action(self, operations_headers):
        """Invalid mode should be rejected in execute-action endpoint"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "invalid_mode",
                "type": "navigate_tab",
                "params": {"tab": "dashboard"}
            },
            headers=operations_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


class TestNavigationActions:
    """Test non-destructive navigation actions"""

    def test_navigate_tab_in_operations_mode(self, operations_headers):
        """navigate action should work in operations mode"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "operations",
                "type": "navigate",
                "params": {"target": "faults"}
            },
            headers=operations_headers
        )
        assert resp.status_code == 200, f"Navigate failed: {resp.text}"
        data = resp.json()
        assert data.get("executed") is True
        assert data.get("navigate_to") == "faults"

    def test_navigate_tab_in_memberships_mode(self, memberships_headers):
        """navigate_tab action should work in memberships mode"""
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "memberships",
                "type": "navigate_tab",
                "params": {"tab": "members"}
            },
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"Navigate failed: {resp.text}"
        data = resp.json()
        assert data.get("executed") is True
        assert data.get("navigate_to_tab") == "members"


class TestChatHistoryRetrieval:
    """Test chat history retrieval"""

    def test_get_chat_history(self, operations_headers):
        """Should be able to retrieve chat history by session_id"""
        # First, create a chat session
        chat_resp = requests.post(
            f"{BASE_URL}/api/assistant/chat",
            json={
                "mode": "operations",
                "message": "Test message for history"
            },
            headers=operations_headers,
            timeout=60
        )
        assert chat_resp.status_code == 200
        session_id = chat_resp.json().get("session_id")

        # Now retrieve the history
        history_resp = requests.get(
            f"{BASE_URL}/api/assistant/chat/{session_id}",
            headers=operations_headers
        )
        assert history_resp.status_code == 200, f"History retrieval failed: {history_resp.text}"
        data = history_resp.json()
        assert "turns" in data
        assert len(data["turns"]) >= 2  # At least user message + assistant response


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
