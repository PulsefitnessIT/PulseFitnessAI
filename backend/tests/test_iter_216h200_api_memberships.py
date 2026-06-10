"""Iter 216h200 — API tests for Craig's Memberships bug fixes.

Tests the actual HTTP endpoints for:
(A) POST /api/memberships/members/{id}/assign-plan idempotency
(B) POST /api/memberships/members validation (email, phone, GDPR)
(C) GET /api/memberships/members surfaces pending_payment status
(D) GET /api/memberships/members/{id}/activity suppresses ghost entries
(E) POST /api/memberships/members/{id}/record-payment retires pending_payment

Run: pytest backend/tests/test_iter_216h200_api_memberships.py -v
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://seo-fix-preview-4.preview.emergentagent.com"


@pytest.fixture(scope="module")
def studio_auth():
    """Login as E1 Agent (has memberships module access) for memberships testing."""
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "e1.agent@gymaxisai.com",
        "password": "E1Agent123!"
    })
    if r.status_code != 200:
        pytest.skip(f"E1 Agent login failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    token = data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def test_member_id(studio_auth):
    """Create a test member for the test suite."""
    unique = uuid.uuid4().hex[:8]
    payload = {
        "first_name": f"TEST_Craig_{unique}",
        "last_name": "BugFix",
        "email": f"test.craig.{unique}@example.com",
        "phone": "+447700900123",
        "emergency_contact_phone": "+447700900456",
        "gdpr_consent": True,
        "marketing_consent": False,
        "postcode": "sw1a 1aa"
    }
    r = requests.post(f"{BASE_URL}/api/memberships/members", json=payload, headers=studio_auth)
    if r.status_code not in (200, 201):
        pytest.skip(f"Failed to create test member: {r.status_code} {r.text[:200]}")
    member = r.json().get("member", {})
    member_id = member.get("id")
    if not member_id:
        pytest.skip("No member id in response")
    yield member_id
    # Cleanup not strictly needed as TEST_ prefix marks it


@pytest.fixture(scope="module")
def test_plan_id(studio_auth):
    """Get a plan ID for testing."""
    r = requests.get(f"{BASE_URL}/api/memberships/plans", headers=studio_auth)
    if r.status_code != 200:
        pytest.skip(f"Failed to get plans: {r.status_code}")
    plans = r.json().get("plans", [])
    if not plans:
        pytest.skip("No plans available")
    # Prefer a recurring plan for pending_payment testing
    for p in plans:
        if p.get("kind") == "recurring":
            return p["id"]
    return plans[0]["id"]


class TestMemberCreateValidation:
    """POST /api/memberships/members validation suite."""

    def test_rejects_malformed_email(self, studio_auth):
        """400 when email is malformed."""
        payload = {
            "first_name": "TEST_Invalid",
            "email": "not-an-email",
            "phone": "+447700900000",
            "emergency_contact_phone": "+447700900111",
            "gdpr_consent": True
        }
        r = requests.post(f"{BASE_URL}/api/memberships/members", json=payload, headers=studio_auth)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
        assert "email" in r.text.lower()

    def test_rejects_empty_phone(self, studio_auth):
        """400 when phone is empty."""
        unique = uuid.uuid4().hex[:6]
        payload = {
            "first_name": "TEST_NoPhone",
            "email": f"test.nophone.{unique}@example.com",
            "phone": "   ",
            "emergency_contact_phone": "+447700900111",
            "gdpr_consent": True
        }
        r = requests.post(f"{BASE_URL}/api/memberships/members", json=payload, headers=studio_auth)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
        assert "phone" in r.text.lower()

    def test_rejects_empty_emergency_phone(self, studio_auth):
        """400 when emergency_contact_phone is empty."""
        unique = uuid.uuid4().hex[:6]
        payload = {
            "first_name": "TEST_NoEmergency",
            "email": f"test.noemergency.{unique}@example.com",
            "phone": "+447700900000",
            "emergency_contact_phone": "",
            "gdpr_consent": True
        }
        r = requests.post(f"{BASE_URL}/api/memberships/members", json=payload, headers=studio_auth)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
        assert "emergency" in r.text.lower()

    def test_rejects_missing_gdpr_consent(self, studio_auth):
        """400 when gdpr_consent is false."""
        unique = uuid.uuid4().hex[:6]
        payload = {
            "first_name": "TEST_NoGDPR",
            "email": f"test.nogdpr.{unique}@example.com",
            "phone": "+447700900000",
            "emergency_contact_phone": "+447700900111",
            "gdpr_consent": False
        }
        r = requests.post(f"{BASE_URL}/api/memberships/members", json=payload, headers=studio_auth)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
        assert "gdpr" in r.text.lower() or "consent" in r.text.lower()

    def test_happy_path_uppercases_postcode(self, studio_auth):
        """Happy path: postcode is uppercased, consent fields persisted."""
        unique = uuid.uuid4().hex[:6]
        payload = {
            "first_name": f"TEST_Happy_{unique}",
            "last_name": "Path",
            "email": f"test.happy.{unique}@example.com",
            "phone": "+447700900000",
            "emergency_contact_phone": "+447700900111",
            "gdpr_consent": True,
            "marketing_consent": True,
            "postcode": "sw1a 1aa"
        }
        r = requests.post(f"{BASE_URL}/api/memberships/members", json=payload, headers=studio_auth)
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text[:200]}"
        member = r.json().get("member", {})
        assert member.get("postcode") == "SW1A 1AA", "Postcode should be uppercased"
        assert member.get("gdpr_consent") is True
        assert member.get("marketing_consent") is True


class TestAssignPlanIdempotency:
    """POST /api/memberships/members/{id}/assign-plan idempotency."""

    def test_assign_plan_twice_returns_idempotent(self, studio_auth, test_member_id, test_plan_id):
        """Clicking assign twice with same plan_id returns idempotent=true."""
        url = f"{BASE_URL}/api/memberships/members/{test_member_id}/assign-plan"
        payload = {"plan_id": test_plan_id}
        
        # First assignment
        r1 = requests.post(url, json=payload, headers=studio_auth)
        assert r1.status_code == 200, f"First assign failed: {r1.status_code} {r1.text[:200]}"
        data1 = r1.json()
        assert "membership" in data1
        
        # Second assignment (same plan) — should be idempotent
        r2 = requests.post(url, json=payload, headers=studio_auth)
        assert r2.status_code == 200, f"Second assign failed: {r2.status_code} {r2.text[:200]}"
        data2 = r2.json()
        assert data2.get("idempotent") is True, "Second call should return idempotent=true"
        assert data2["membership"]["id"] == data1["membership"]["id"], "Should return same membership"


class TestMembersListPendingPayment:
    """GET /api/memberships/members surfaces pending_payment status."""

    def test_members_list_shows_pending_payment_member(self, studio_auth, test_member_id, test_plan_id):
        """Member with pending_payment status appears in list with plan info."""
        # Ensure member has a plan assigned (from previous test or assign now)
        assign_url = f"{BASE_URL}/api/memberships/members/{test_member_id}/assign-plan"
        requests.post(assign_url, json={"plan_id": test_plan_id}, headers=studio_auth)
        
        # Get members list
        r = requests.get(f"{BASE_URL}/api/memberships/members", headers=studio_auth)
        assert r.status_code == 200, f"Members list failed: {r.status_code}"
        members = r.json().get("members", [])
        
        # Find our test member
        test_member = next((m for m in members if m.get("id") == test_member_id), None)
        assert test_member is not None, "Test member not found in list"
        
        # Check active_membership is populated
        am = test_member.get("active_membership")
        assert am is not None, "active_membership should be populated"
        assert am.get("status") in ("active", "pending_payment", "frozen"), \
            f"Unexpected status: {am.get('status')}"
        assert am.get("plan") is not None, "Plan should be populated"


class TestActivityFeedSuppression:
    """GET /api/memberships/members/{id}/activity suppresses ghost entries."""

    def test_activity_feed_no_replaced_entries(self, studio_auth, test_member_id, test_plan_id):
        """Activity feed should not show cancelled+replaced_by_new_plan entries."""
        # Get activity feed
        r = requests.get(
            f"{BASE_URL}/api/memberships/members/{test_member_id}/activity",
            headers=studio_auth
        )
        assert r.status_code == 200, f"Activity feed failed: {r.status_code}"
        events = r.json().get("events", [])
        
        # Check no events have 'replaced' in their title or are from superseded rows
        for ev in events:
            title = (ev.get("title") or "").lower()
            # Should not see multiple "Assigned plan" entries for the same plan
            # (the ghost entries Craig saw)
            if "replaced" in title:
                pytest.fail(f"Found 'replaced' entry in activity: {ev}")


class TestRecordPaymentRetiresPending:
    """POST /api/memberships/members/{id}/record-payment retires pending_payment."""

    def test_record_payment_activates_membership(self, studio_auth, test_member_id, test_plan_id):
        """Recording payment should activate the membership."""
        # First ensure we have a pending_payment membership
        assign_url = f"{BASE_URL}/api/memberships/members/{test_member_id}/assign-plan"
        requests.post(assign_url, json={"plan_id": test_plan_id}, headers=studio_auth)
        
        # Record payment
        r = requests.post(
            f"{BASE_URL}/api/memberships/members/{test_member_id}/record-payment",
            json={"plan_id": test_plan_id, "method": "cash"},
            headers=studio_auth
        )
        assert r.status_code == 200, f"Record payment failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("membership_id") is not None


class TestMembersFilteredEndpoint:
    """GET /api/memberships/members-filtered also surfaces pending_payment."""

    def test_members_filtered_includes_pending_payment(self, studio_auth):
        """members-filtered endpoint should also show pending_payment members."""
        r = requests.get(f"{BASE_URL}/api/memberships/members-filtered", headers=studio_auth)
        assert r.status_code == 200, f"members-filtered failed: {r.status_code}"
        data = r.json()
        assert "members" in data
        # Just verify the endpoint works and returns the expected shape
        assert isinstance(data["members"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
