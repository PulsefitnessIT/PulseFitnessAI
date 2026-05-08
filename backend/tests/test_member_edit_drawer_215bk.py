"""
Iter 215bk — Member Edit Drawer Backend Tests

Tests for the new member edit drawer endpoints:
- PATCH /api/memberships/members/{member_id} — profile updates
- GET /api/memberships/members/{member_id}/payments — payments + invoices
- GET /api/memberships/members/{member_id}/children — linked children
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Master Admin credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin JWT token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def headers(admin_token):
    """Auth headers"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_member(headers):
    """Create a test member for the drawer tests"""
    import uuid
    unique_email = f"test-drawer-{uuid.uuid4().hex[:8]}@example.com"
    resp = requests.post(f"{BASE_URL}/api/memberships/members", json={
        "email": unique_email,
        "first_name": "DrawerTest",
        "last_name": "Member",
        "phone": "+447700900999"
    }, headers=headers)
    if resp.status_code not in (200, 201):
        pytest.skip(f"Failed to create test member: {resp.status_code} - {resp.text}")
    member = resp.json().get("member", {})
    yield member
    # Cleanup not strictly needed as test data is ephemeral


class TestMemberPatchEndpoint:
    """Tests for PATCH /api/memberships/members/{member_id}"""

    def test_patch_basic_profile_fields(self, headers, test_member):
        """Test updating basic profile fields (first_name, last_name, phone)"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "first_name": "UpdatedFirst",
            "last_name": "UpdatedLast",
            "phone": "+447700900888"
        }, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "member" in data
        assert data["member"]["first_name"] == "UpdatedFirst"
        assert data["member"]["last_name"] == "UpdatedLast"
        assert data["member"]["phone"] == "+447700900888"

    def test_patch_address_fields(self, headers, test_member):
        """Test updating address fields"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "address_line1": "123 Test Street",
            "address_line2": "Flat 4B",
            "city": "London",
            "postcode": "SW1A 1AA",
            "country": "UK"
        }, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["member"]["address_line1"] == "123 Test Street"
        assert data["member"]["city"] == "London"
        assert data["member"]["postcode"] == "SW1A 1AA"

    def test_patch_dob_field(self, headers, test_member):
        """Test updating date of birth"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "dob": "2010-05-15"  # Minor (under 18)
        }, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["member"]["dob"] == "2010-05-15"

    def test_patch_emergency_contact(self, headers, test_member):
        """Test updating emergency contact fields"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_phone": "+447700900777"
        }, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["member"]["emergency_contact_name"] == "Jane Doe"
        assert data["member"]["emergency_contact_phone"] == "+447700900777"

    def test_patch_notes_and_tags(self, headers, test_member):
        """Test updating notes and tags"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "notes": "VIP member, prefers morning classes",
            "tags": ["vip", "morning", "corporate"]
        }, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["member"]["notes"] == "VIP member, prefers morning classes"
        assert "vip" in data["member"]["tags"]
        assert "corporate" in data["member"]["tags"]

    def test_patch_email_conflict_returns_409(self, headers):
        """Test that updating email to an existing member's email returns 409"""
        import uuid

        # Create first member
        email1 = f"test-conflict1-{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(f"{BASE_URL}/api/memberships/members", json={
            "email": email1,
            "first_name": "Conflict1",
            "last_name": "Test"
        }, headers=headers)
        assert resp.status_code in (200, 201), f"Failed to create member1: {resp.text}"

        # Create second member
        email2 = f"test-conflict2-{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(f"{BASE_URL}/api/memberships/members", json={
            "email": email2,
            "first_name": "Conflict2",
            "last_name": "Test"
        }, headers=headers)
        assert resp.status_code in (200, 201), f"Failed to create member2: {resp.text}"
        member2_id = resp.json().get("member", {}).get("id")

        # Try to change member2's email to member1's email
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member2_id}", json={
            "email": email1
        }, headers=headers)

        # Should return 409 Conflict
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"

    def test_patch_self_parent_returns_400(self, headers, test_member):
        """Test that setting parent_member_id to self returns 400"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "parent_member_id": member_id
        }, headers=headers)

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_patch_nonexistent_parent_returns_404(self, headers, test_member):
        """Test that setting parent_member_id to non-existent member returns 404"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "parent_member_id": "nonexistent-member-id-12345"
        }, headers=headers)

        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_patch_clear_parent_member_id(self, headers, test_member):
        """Test clearing parent_member_id with null"""
        member_id = test_member["id"]
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{member_id}", json={
            "parent_member_id": None
        }, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["member"].get("parent_member_id") is None


class TestMemberPaymentsEndpoint:
    """Tests for GET /api/memberships/members/{member_id}/payments"""

    def test_get_payments_returns_200(self, headers, test_member):
        """Test that payments endpoint returns 200 with correct structure"""
        member_id = test_member["id"]
        resp = requests.get(f"{BASE_URL}/api/memberships/members/{member_id}/payments", headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify response structure
        assert "payments" in data
        assert "invoices" in data
        assert "totals" in data
        assert "paid_pence" in data["totals"]
        assert "outstanding_pence" in data["totals"]

        # Verify types
        assert isinstance(data["payments"], list)
        assert isinstance(data["invoices"], list)
        assert isinstance(data["totals"]["paid_pence"], int)
        assert isinstance(data["totals"]["outstanding_pence"], int)

    def test_get_payments_nonexistent_member_returns_404(self, headers):
        """Test that payments endpoint returns 404 for non-existent member"""
        resp = requests.get(f"{BASE_URL}/api/memberships/members/nonexistent-id-12345/payments", headers=headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


class TestMemberChildrenEndpoint:
    """Tests for GET /api/memberships/members/{member_id}/children"""

    def test_get_children_returns_200(self, headers, test_member):
        """Test that children endpoint returns 200 with correct structure"""
        member_id = test_member["id"]
        resp = requests.get(f"{BASE_URL}/api/memberships/members/{member_id}/children", headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify response structure
        assert "children" in data
        assert isinstance(data["children"], list)

    def test_get_children_nonexistent_member_returns_404(self, headers):
        """Test that children endpoint returns 404 for non-existent member"""
        resp = requests.get(f"{BASE_URL}/api/memberships/members/nonexistent-id-12345/children", headers=headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


class TestParentChildLinking:
    """Tests for parent-child member linking via PATCH"""

    def test_link_parent_and_verify_children(self, headers):
        """Test linking a parent member and verifying via children endpoint"""
        import uuid

        # Create parent member
        parent_email = f"test-parent-{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(f"{BASE_URL}/api/memberships/members", json={
            "email": parent_email,
            "first_name": "ParentTest",
            "last_name": "Member"
        }, headers=headers)
        assert resp.status_code in (200, 201), f"Failed to create parent: {resp.text}"
        parent = resp.json().get("member", {})
        parent_id = parent["id"]

        # Create child member
        child_email = f"test-child-{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(f"{BASE_URL}/api/memberships/members", json={
            "email": child_email,
            "first_name": "ChildTest",
            "last_name": "Member",
            "dob": "2015-03-20"  # Minor
        }, headers=headers)
        assert resp.status_code in (200, 201), f"Failed to create child: {resp.text}"
        child = resp.json().get("member", {})
        child_id = child["id"]

        # Link child to parent
        resp = requests.patch(f"{BASE_URL}/api/memberships/members/{child_id}", json={
            "parent_member_id": parent_id
        }, headers=headers)
        assert resp.status_code == 200, f"Failed to link parent: {resp.text}"
        assert resp.json()["member"]["parent_member_id"] == parent_id

        # Verify parent's children endpoint shows the child
        resp = requests.get(f"{BASE_URL}/api/memberships/members/{parent_id}/children", headers=headers)
        assert resp.status_code == 200
        children = resp.json().get("children", [])
        child_ids = [c["id"] for c in children]
        assert child_id in child_ids, f"Child {child_id} not found in parent's children list"


class TestMemberGetEndpoint:
    """Tests for GET /api/memberships/members/{member_id}"""

    def test_get_member_returns_full_data(self, headers, test_member):
        """Test that GET member returns full member data with memberships and bookings"""
        member_id = test_member["id"]
        resp = requests.get(f"{BASE_URL}/api/memberships/members/{member_id}", headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify response structure
        assert "member" in data
        assert "memberships" in data
        assert "recent_bookings" in data

        # Verify member fields
        member = data["member"]
        assert "id" in member
        assert "email" in member
        assert "first_name" in member
        assert "last_name" in member


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
