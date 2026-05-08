"""
Backend tests for Iteration 215q — Studio Polish features:
- Walk-in check-in (POST /api/memberships/checkin/walk-in)
- Book again / Rebook (POST /api/member/bookings/rebook)
- Broadcast to class (POST /api/memberships/classes/{occ}/broadcast)
- Assistant admin/crm modes (POST /api/assistant/chat)
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
REBOOK_MEMBER_EMAIL = "rebook-1777578936@example.com"
REBOOK_MEMBER_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    return {"Authorization": f"Bearer {master_admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def rebook_member_token():
    """Get member JWT token for rebook testing"""
    resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
        "email": REBOOK_MEMBER_EMAIL,
        "password": REBOOK_MEMBER_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Rebook member login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def rebook_member_headers(rebook_member_token):
    return {"Authorization": f"Bearer {rebook_member_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_occurrence_id(operator_headers):
    """Get a valid occurrence ID for testing"""
    # Get today's classes
    resp = requests.get(f"{BASE_URL}/api/memberships/checkin/today?days=7", headers=operator_headers)
    if resp.status_code != 200:
        pytest.skip(f"Failed to get classes: {resp.status_code}")
    classes = resp.json().get("classes", [])
    if not classes:
        pytest.skip("No classes available for testing")
    return classes[0]["id"]


# ═══════════════════════ Walk-in Check-in Tests ═══════════════════════

class TestWalkInCheckin:
    """Tests for POST /api/memberships/checkin/walk-in"""

    def test_walkin_creates_new_member(self, operator_headers, test_occurrence_id):
        """Walk-in with new email creates a new member and booking"""
        unique_email = f"TEST_walkin_{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(f"{BASE_URL}/api/memberships/checkin/walk-in",
            headers=operator_headers,
            json={
                "name": "Test Walk-in User",
                "email": unique_email,
                "phone": "+447700900999",
                "occurrence_id": test_occurrence_id
            })

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("created_member") is True, "Should create new member"
        assert "member_id" in data
        assert "booking_id" in data
        print(f"✓ Walk-in created new member: {data['member_id']}")

    def test_walkin_reuses_existing_member(self, operator_headers, test_occurrence_id):
        """Walk-in with existing email reuses the member"""
        unique_email = f"TEST_walkin_reuse_{uuid.uuid4().hex[:8]}@example.com"

        # First walk-in creates the member
        resp1 = requests.post(f"{BASE_URL}/api/memberships/checkin/walk-in",
            headers=operator_headers,
            json={
                "name": "Reuse Test User",
                "email": unique_email,
                "occurrence_id": test_occurrence_id
            })
        assert resp1.status_code == 200
        first_member_id = resp1.json().get("member_id")

        # Get another occurrence for second walk-in (can't book same class twice)
        resp_classes = requests.get(f"{BASE_URL}/api/memberships/checkin/today?days=7", headers=operator_headers)
        classes = resp_classes.json().get("classes", [])
        other_occ_id = None
        for c in classes:
            if c["id"] != test_occurrence_id:
                other_occ_id = c["id"]
                break

        if not other_occ_id:
            pytest.skip("Need at least 2 classes to test member reuse")

        # Second walk-in should reuse the member
        resp2 = requests.post(f"{BASE_URL}/api/memberships/checkin/walk-in",
            headers=operator_headers,
            json={
                "name": "Reuse Test User",
                "email": unique_email,
                "occurrence_id": other_occ_id
            })
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("ok") is True
        assert data2.get("created_member") is False, "Should reuse existing member"
        assert data2.get("member_id") == first_member_id
        print(f"✓ Walk-in reused existing member: {first_member_id}")

    def test_walkin_unknown_occurrence_returns_404(self, operator_headers):
        """Walk-in with unknown occurrence_id returns 404"""
        resp = requests.post(f"{BASE_URL}/api/memberships/checkin/walk-in",
            headers=operator_headers,
            json={
                "name": "Test User",
                "occurrence_id": "nonexistent-occurrence-id-12345"
            })

        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        assert "not found" in resp.text.lower() or "Class not found" in resp.text
        print("✓ Walk-in with unknown occurrence returns 404")

    def test_walkin_requires_name(self, operator_headers, test_occurrence_id):
        """Walk-in without name should fail validation"""
        resp = requests.post(f"{BASE_URL}/api/memberships/checkin/walk-in",
            headers=operator_headers,
            json={
                "email": "test@example.com",
                "occurrence_id": test_occurrence_id
            })

        assert resp.status_code == 422, f"Expected 422 validation error, got {resp.status_code}"
        print("✓ Walk-in requires name field")


# ═══════════════════════ Rebook Tests ═══════════════════════

class TestRebook:
    """Tests for POST /api/member/bookings/rebook"""

    def test_rebook_with_prior_booking(self, rebook_member_headers):
        """Rebook finds next occurrence of same class template"""
        resp = requests.post(f"{BASE_URL}/api/member/bookings/rebook",
            headers=rebook_member_headers,
            json={})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert "booking_id" in data or data.get("already_booked") is True
        assert "occurrence_id" in data
        print(f"✓ Rebook successful: already_booked={data.get('already_booked')}, starts_at={data.get('starts_at')}")

    def test_rebook_duplicate_returns_already_booked(self, rebook_member_headers):
        """Rebook same occurrence twice returns already_booked:true"""
        # First rebook
        resp1 = requests.post(f"{BASE_URL}/api/member/bookings/rebook",
            headers=rebook_member_headers,
            json={})
        assert resp1.status_code == 200

        # Second rebook should return already_booked
        resp2 = requests.post(f"{BASE_URL}/api/member/bookings/rebook",
            headers=rebook_member_headers,
            json={})

        assert resp2.status_code == 200
        data = resp2.json()
        assert data.get("ok") is True
        assert data.get("already_booked") is True, "Second rebook should return already_booked:true"
        print("✓ Duplicate rebook returns already_booked:true")

    def test_rebook_no_prior_booking_returns_404(self, operator_headers):
        """Rebook with no prior booking returns 404"""
        # Create a fresh member with no bookings
        unique_email = f"TEST_norebook_{uuid.uuid4().hex[:8]}@example.com"

        # Register new member
        reg_resp = requests.post(f"{BASE_URL}/api/member-auth/register", json={
            "email": unique_email,
            "password": "Test123!",
            "first_name": "No",
            "last_name": "Booking",
            "organization_id": "mbr-demo-org"
        })

        if reg_resp.status_code != 200:
            pytest.skip(f"Could not register test member: {reg_resp.status_code}")

        new_token = reg_resp.json().get("token")
        new_headers = {"Authorization": f"Bearer {new_token}", "Content-Type": "application/json"}

        # Try to rebook with no prior booking
        resp = requests.post(f"{BASE_URL}/api/member/bookings/rebook",
            headers=new_headers,
            json={})

        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        assert "No previous class" in resp.text or "no previous" in resp.text.lower()
        print("✓ Rebook with no prior booking returns 404")


# ═══════════════════════ Broadcast Tests ═══════════════════════

class TestBroadcast:
    """Tests for POST /api/memberships/classes/{occ}/broadcast"""

    def test_broadcast_returns_delivery_counts(self, operator_headers, test_occurrence_id):
        """Broadcast returns ok:true with delivery counts"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/classes/{test_occurrence_id}/broadcast",
            headers=operator_headers,
            json={
                "message": "Test broadcast message from automated testing",
                "subject": "Test Subject"
            })

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert "recipient_count" in data
        assert "delivered" in data
        assert "skipped_no_email" in data
        assert "failed" in data
        print(f"✓ Broadcast: recipients={data['recipient_count']}, delivered={data['delivered']}, skipped={data['skipped_no_email']}, failed={data['failed']}")

    def test_broadcast_unknown_occurrence_returns_404(self, operator_headers):
        """Broadcast to unknown occurrence returns 404"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/classes/nonexistent-occ-id/broadcast",
            headers=operator_headers,
            json={
                "message": "Test message"
            })

        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ Broadcast to unknown occurrence returns 404")

    def test_broadcast_requires_message(self, operator_headers, test_occurrence_id):
        """Broadcast without message should fail validation"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/classes/{test_occurrence_id}/broadcast",
            headers=operator_headers,
            json={
                "subject": "Subject only"
            })

        assert resp.status_code == 422, f"Expected 422 validation error, got {resp.status_code}"
        print("✓ Broadcast requires message field")


# ═══════════════════════ Assistant Admin/CRM Mode Tests ═══════════════════════

class TestAssistantModes:
    """Tests for POST /api/assistant/chat with admin and crm modes"""

    def test_assistant_admin_mode(self, master_admin_headers):
        """Assistant chat with mode='admin' returns grounded answer"""
        resp = requests.post(f"{BASE_URL}/api/assistant/chat",
            headers=master_admin_headers,
            json={
                "mode": "admin",
                "message": "What integrations are available?",
                "session_id": f"test-admin-{uuid.uuid4().hex[:8]}"
            },
            timeout=60)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "answer" in data
        assert data.get("mode") == "admin"
        assert len(data.get("answer", "")) > 10, "Answer should be substantive"
        print(f"✓ Admin mode chat: {data['answer'][:100]}...")

    def test_assistant_crm_mode(self, master_admin_headers):
        """Assistant chat with mode='crm' returns grounded answer"""
        resp = requests.post(f"{BASE_URL}/api/assistant/chat",
            headers=master_admin_headers,
            json={
                "mode": "crm",
                "message": "How do I customize pipeline stages?",
                "session_id": f"test-crm-{uuid.uuid4().hex[:8]}"
            },
            timeout=60)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "answer" in data
        assert data.get("mode") == "crm"
        assert len(data.get("answer", "")) > 10, "Answer should be substantive"
        print(f"✓ CRM mode chat: {data['answer'][:100]}...")

    def test_assistant_operations_mode_regression(self, operator_headers):
        """Regression: operations mode still works"""
        resp = requests.post(f"{BASE_URL}/api/assistant/chat",
            headers=operator_headers,
            json={
                "mode": "operations",
                "message": "What faults are open?",
                "session_id": f"test-ops-{uuid.uuid4().hex[:8]}"
            },
            timeout=60)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("mode") == "operations"
        print(f"✓ Operations mode regression: {data['answer'][:80]}...")

    def test_assistant_marketing_mode_regression(self, operator_headers):
        """Regression: marketing mode still works"""
        resp = requests.post(f"{BASE_URL}/api/assistant/chat",
            headers=operator_headers,
            json={
                "mode": "marketing",
                "message": "How are my campaigns performing?",
                "session_id": f"test-mkt-{uuid.uuid4().hex[:8]}"
            },
            timeout=60)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("mode") == "marketing"
        print(f"✓ Marketing mode regression: {data['answer'][:80]}...")

    def test_assistant_memberships_mode_regression(self, operator_headers):
        """Regression: memberships mode still works"""
        resp = requests.post(f"{BASE_URL}/api/assistant/chat",
            headers=operator_headers,
            json={
                "mode": "memberships",
                "message": "How many active members do I have?",
                "session_id": f"test-mbr-{uuid.uuid4().hex[:8]}"
            },
            timeout=60)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("mode") == "memberships"
        print(f"✓ Memberships mode regression: {data['answer'][:80]}...")

    def test_assistant_invalid_mode_returns_400(self, operator_headers):
        """Assistant chat with invalid mode returns 400"""
        resp = requests.post(f"{BASE_URL}/api/assistant/chat",
            headers=operator_headers,
            json={
                "mode": "invalid_mode",
                "message": "Test message"
            })

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✓ Invalid mode returns 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
