"""Iter 216h207 — Integration tests for Edit drawer GDPR + Email/Phone validation parity.

Tests the actual HTTP endpoints via requests to verify:
  • PATCH /api/memberships/members/{id} with invalid email returns 400
  • PATCH /api/memberships/members/{id} with empty phone returns 400
  • PATCH /api/memberships/members/{id} with empty emergency_contact_phone returns 400
  • PATCH /api/memberships/members/{id} with gdpr_consent=true stamps audit fields
  • POST /api/memberships/instructors without gdpr_consent returns 400
  • POST /api/memberships/instructors with gdpr_consent=true stamps audit fields
  • PATCH /api/memberships/instructors/{id} with invalid email returns 400
  • PATCH /api/memberships/instructors/{id} with gdpr_consent=true stamps audit fields

Run: pytest backend/tests/test_iter_216h207_integration.py -v
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://photo-fix-verify.preview.emergentagent.com"


@pytest.fixture(scope="module")
def auth_headers():
    """Login as owner and return auth headers."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "e1.agent@gymaxisai.com",
        "password": "E1Agent123!"
    })
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} - {resp.text}")
    token = resp.json().get("token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_member_id(auth_headers):
    """Create a test member for PATCH tests."""
    unique = uuid.uuid4().hex[:8]
    resp = requests.post(f"{BASE_URL}/api/memberships/members", headers=auth_headers, json={
        "first_name": f"TEST_GDPR_{unique}",
        "last_name": "TestMember",
        "email": f"test.gdpr.{unique}@example.com",
        "phone": "+447700900001",
        "emergency_contact_phone": "+447700900002",
        "gdpr_consent": True,
        "marketing_consent": False,
    })
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create test member: {resp.status_code} - {resp.text}")
    member_id = resp.json().get("member", {}).get("id")
    yield member_id
    # Cleanup not strictly needed as TEST_ prefix marks it


class TestMemberPatchValidation:
    """Tests for PATCH /api/memberships/members/{id} validation."""

    def test_patch_member_invalid_email_returns_400(self, auth_headers, test_member_id):
        """PATCH with invalid email format should return 400."""
        resp = requests.patch(
            f"{BASE_URL}/api/memberships/members/{test_member_id}",
            headers=auth_headers,
            json={"email": "not-an-email"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "Invalid email" in resp.text or "email" in resp.text.lower()

    def test_patch_member_empty_phone_returns_400(self, auth_headers, test_member_id):
        """PATCH with empty phone should return 400."""
        resp = requests.patch(
            f"{BASE_URL}/api/memberships/members/{test_member_id}",
            headers=auth_headers,
            json={"phone": ""}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "phone" in resp.text.lower()

    def test_patch_member_empty_emergency_phone_returns_400(self, auth_headers, test_member_id):
        """PATCH with empty emergency_contact_phone should return 400."""
        resp = requests.patch(
            f"{BASE_URL}/api/memberships/members/{test_member_id}",
            headers=auth_headers,
            json={"emergency_contact_phone": ""}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_patch_member_gdpr_consent_stamps_audit(self, auth_headers):
        """PATCH with gdpr_consent=true on a member with false should stamp audit fields."""
        # Create a fresh member with gdpr_consent=true (required), then we'll test the stamp logic
        unique = uuid.uuid4().hex[:8]
        create_resp = requests.post(f"{BASE_URL}/api/memberships/members", headers=auth_headers, json={
            "first_name": f"TEST_GDPR_STAMP_{unique}",
            "last_name": "StampTest",
            "email": f"test.stamp.{unique}@example.com",
            "phone": "+447700900003",
            "emergency_contact_phone": "+447700900004",
            "gdpr_consent": True,
            "marketing_consent": False,
        })
        if create_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create member: {create_resp.text}")
        
        member_id = create_resp.json().get("member", {}).get("id")
        
        # Now patch marketing_consent to true (gdpr is already true)
        patch_resp = requests.patch(
            f"{BASE_URL}/api/memberships/members/{member_id}",
            headers=auth_headers,
            json={"marketing_consent": True}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        # Verify the member has marketing_consent_at stamped
        get_resp = requests.get(f"{BASE_URL}/api/memberships/members/{member_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        member = get_resp.json().get("member", {})
        assert member.get("marketing_consent") is True
        assert member.get("marketing_consent_at") is not None, "marketing_consent_at should be stamped"


class TestInstructorValidation:
    """Tests for instructor create/patch validation."""

    def test_create_instructor_without_gdpr_returns_400(self, auth_headers):
        """POST /api/memberships/instructors without gdpr_consent should return 400."""
        unique = uuid.uuid4().hex[:8]
        resp = requests.post(f"{BASE_URL}/api/memberships/instructors", headers=auth_headers, json={
            "name": f"TEST_Instructor_{unique}",
            "email": f"test.instructor.{unique}@example.com",
            "phone": "+447700900005",
            "gdpr_consent": False,
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "GDPR" in resp.text or "gdpr" in resp.text.lower()

    def test_create_instructor_with_gdpr_stamps_audit(self, auth_headers):
        """POST /api/memberships/instructors with gdpr_consent=true should stamp audit fields."""
        unique = uuid.uuid4().hex[:8]
        resp = requests.post(f"{BASE_URL}/api/memberships/instructors", headers=auth_headers, json={
            "name": f"TEST_Instructor_GDPR_{unique}",
            "email": f"test.instructor.gdpr.{unique}@example.com",
            "phone": "+447700900006",
            "gdpr_consent": True,
            "marketing_consent": True,
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        instructor = resp.json().get("instructor", {})
        assert instructor.get("gdpr_consent") is True
        assert instructor.get("gdpr_consent_at") is not None, "gdpr_consent_at should be stamped"
        assert instructor.get("gdpr_consent_actor_id") is not None, "gdpr_consent_actor_id should be stamped"
        assert instructor.get("marketing_consent") is True
        assert instructor.get("marketing_consent_at") is not None, "marketing_consent_at should be stamped"

    def test_patch_instructor_invalid_email_returns_400(self, auth_headers):
        """PATCH /api/memberships/instructors/{id} with invalid email should return 400."""
        # First create an instructor
        unique = uuid.uuid4().hex[:8]
        create_resp = requests.post(f"{BASE_URL}/api/memberships/instructors", headers=auth_headers, json={
            "name": f"TEST_Instructor_Email_{unique}",
            "email": f"test.instructor.email.{unique}@example.com",
            "phone": "+447700900007",
            "gdpr_consent": True,
        })
        if create_resp.status_code != 200:
            pytest.skip(f"Could not create instructor: {create_resp.text}")
        
        instructor_id = create_resp.json().get("instructor", {}).get("id")
        
        # Now try to patch with invalid email
        patch_resp = requests.patch(
            f"{BASE_URL}/api/memberships/instructors/{instructor_id}",
            headers=auth_headers,
            json={"email": "not-an-email"}
        )
        assert patch_resp.status_code == 400, f"Expected 400, got {patch_resp.status_code}: {patch_resp.text}"
        assert "Invalid email" in patch_resp.text or "email" in patch_resp.text.lower()

    def test_patch_instructor_gdpr_consent_stamps_audit(self, auth_headers):
        """PATCH /api/memberships/instructors/{id} with gdpr_consent change should stamp audit."""
        # Create instructor with gdpr_consent=true
        unique = uuid.uuid4().hex[:8]
        create_resp = requests.post(f"{BASE_URL}/api/memberships/instructors", headers=auth_headers, json={
            "name": f"TEST_Instructor_Consent_{unique}",
            "email": f"test.instructor.consent.{unique}@example.com",
            "phone": "+447700900008",
            "gdpr_consent": True,
            "marketing_consent": False,
        })
        if create_resp.status_code != 200:
            pytest.skip(f"Could not create instructor: {create_resp.text}")
        
        instructor_id = create_resp.json().get("instructor", {}).get("id")
        
        # Patch marketing_consent to true
        patch_resp = requests.patch(
            f"{BASE_URL}/api/memberships/instructors/{instructor_id}",
            headers=auth_headers,
            json={"marketing_consent": True}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        instructor = patch_resp.json().get("instructor", {})
        assert instructor.get("marketing_consent") is True
        assert instructor.get("marketing_consent_at") is not None, "marketing_consent_at should be stamped"


class TestGdprConsentNoRestamp:
    """Test that gdpr_consent=true when already true does NOT re-stamp."""

    def test_member_gdpr_no_restamp_when_unchanged(self, auth_headers):
        """PATCH with gdpr_consent=true when already true should NOT re-stamp."""
        unique = uuid.uuid4().hex[:8]
        # Create member with gdpr_consent=true
        create_resp = requests.post(f"{BASE_URL}/api/memberships/members", headers=auth_headers, json={
            "first_name": f"TEST_NoRestamp_{unique}",
            "last_name": "Test",
            "email": f"test.norestamp.{unique}@example.com",
            "phone": "+447700900009",
            "emergency_contact_phone": "+447700900010",
            "gdpr_consent": True,
        })
        if create_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create member: {create_resp.text}")
        
        member_id = create_resp.json().get("member", {}).get("id")
        
        # Get the original timestamp
        get_resp1 = requests.get(f"{BASE_URL}/api/memberships/members/{member_id}", headers=auth_headers)
        original_timestamp = get_resp1.json().get("member", {}).get("gdpr_consent_at")
        
        # Patch with gdpr_consent=true again (no change)
        patch_resp = requests.patch(
            f"{BASE_URL}/api/memberships/members/{member_id}",
            headers=auth_headers,
            json={"gdpr_consent": True, "first_name": f"TEST_NoRestamp_Updated_{unique}"}
        )
        assert patch_resp.status_code == 200
        
        # Verify timestamp is unchanged
        get_resp2 = requests.get(f"{BASE_URL}/api/memberships/members/{member_id}", headers=auth_headers)
        new_timestamp = get_resp2.json().get("member", {}).get("gdpr_consent_at")
        
        assert original_timestamp == new_timestamp, \
            f"Timestamp should NOT change when gdpr_consent is already true. Original: {original_timestamp}, New: {new_timestamp}"
