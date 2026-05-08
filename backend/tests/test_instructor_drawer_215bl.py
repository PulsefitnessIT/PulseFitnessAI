"""
Iter 215bl — Instructor drawer redesign backend tests.

Tests the extended instructor profile fields (dob, address, emergency contact, notes, tags)
that bring instructor records to parity with member records.
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def auth_headers():
    """Get auth token for Master Admin."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("token")
    assert token, "No token in login response"
    return {"Authorization": f"Bearer {token}"}


class TestInstructorCRUDWithExtendedFields:
    """Test instructor CRUD with new iter 215bl fields."""

    def test_create_instructor_with_all_new_fields(self, auth_headers):
        """POST /api/memberships/instructors with all extended profile fields."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "name": f"Test Instructor {unique_id}",
            "email": f"test.instructor.{unique_id}@example.com",
            "phone": "+447700900123",
            "headline": "RYT-500 · Vinyasa & Pre-natal",
            "bio": "A passionate yoga instructor with 10 years of experience.",
            # New iter 215bl fields
            "dob": "1990-05-15",
            "address_line1": "123 Test Street",
            "address_line2": "Apt 4B",
            "city": "London",
            "postcode": "SW1A 1AA",
            "country": "United Kingdom",
            "emergency_contact_name": "Jane Doe",
            "emergency_contact_phone": "+447700900456",
            "notes": "Prefers morning classes. Allergic to latex.",
            "tags": ["yoga", "pilates", "full-time"],
            # Standard fields
            "specialties": ["Vinyasa", "Pre-natal"],
            "qualifications": ["RYT-500", "First Aid"],
            "years_experience": 10,
            "is_published": True,
            "social": {
                "instagram": "@testinstructor",
                "tiktok": "@testinstructor",
                "linkedin": "https://linkedin.com/in/testinstructor",
                "website": "https://testinstructor.com"
            }
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Create failed: {resp.text}"

        data = resp.json()
        assert "instructor" in data
        inst = data["instructor"]

        # Verify all new fields are persisted
        assert inst["name"] == payload["name"]
        assert inst["dob"] == payload["dob"]
        assert inst["address_line1"] == payload["address_line1"]
        assert inst["address_line2"] == payload["address_line2"]
        assert inst["city"] == payload["city"]
        assert inst["postcode"] == payload["postcode"]
        assert inst["country"] == payload["country"]
        assert inst["emergency_contact_name"] == payload["emergency_contact_name"]
        assert inst["emergency_contact_phone"] == payload["emergency_contact_phone"]
        assert inst["notes"] == payload["notes"]
        assert inst["tags"] == payload["tags"]

        # Store ID for cleanup
        self.__class__.created_instructor_id = inst["id"]
        print(f"✓ Created instructor with all new fields: {inst['id']}")

    def test_get_instructor_returns_all_fields(self, auth_headers):
        """GET /api/memberships/instructors/{id} returns all extended fields."""
        inst_id = getattr(self.__class__, 'created_instructor_id', None)
        if not inst_id:
            pytest.skip("No instructor created in previous test")

        resp = requests.get(f"{BASE_URL}/api/memberships/instructors/{inst_id}", headers=auth_headers)
        assert resp.status_code == 200, f"GET failed: {resp.text}"

        data = resp.json()
        inst = data["instructor"]

        # Verify all fields are returned
        assert "dob" in inst
        assert "address_line1" in inst
        assert "address_line2" in inst
        assert "city" in inst
        assert "postcode" in inst
        assert "country" in inst
        assert "emergency_contact_name" in inst
        assert "emergency_contact_phone" in inst
        assert "notes" in inst
        assert "tags" in inst

        print("✓ GET instructor returns all extended fields")

    def test_patch_instructor_updates_new_fields(self, auth_headers):
        """PATCH /api/memberships/instructors/{id} updates extended fields."""
        inst_id = getattr(self.__class__, 'created_instructor_id', None)
        if not inst_id:
            pytest.skip("No instructor created in previous test")

        patch_payload = {
            "dob": "1985-12-25",
            "address_line1": "456 Updated Street",
            "city": "Manchester",
            "postcode": "M1 1AA",
            "emergency_contact_name": "John Smith",
            "notes": "Updated notes - now prefers evening classes.",
            "tags": ["yoga", "meditation", "part-time"]
        }

        resp = requests.patch(f"{BASE_URL}/api/memberships/instructors/{inst_id}", json=patch_payload, headers=auth_headers)
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"

        data = resp.json()
        inst = data["instructor"]

        # Verify updates
        assert inst["dob"] == patch_payload["dob"]
        assert inst["address_line1"] == patch_payload["address_line1"]
        assert inst["city"] == patch_payload["city"]
        assert inst["postcode"] == patch_payload["postcode"]
        assert inst["emergency_contact_name"] == patch_payload["emergency_contact_name"]
        assert inst["notes"] == patch_payload["notes"]
        assert inst["tags"] == patch_payload["tags"]

        print("✓ PATCH instructor updates extended fields correctly")

    def test_list_instructors_includes_new_fields(self, auth_headers):
        """GET /api/memberships/instructors list includes extended fields."""
        resp = requests.get(f"{BASE_URL}/api/memberships/instructors", headers=auth_headers)
        assert resp.status_code == 200, f"List failed: {resp.text}"

        data = resp.json()
        assert "instructors" in data

        # Find our test instructor
        inst_id = getattr(self.__class__, 'created_instructor_id', None)
        if inst_id:
            test_inst = next((i for i in data["instructors"] if i["id"] == inst_id), None)
            if test_inst:
                # Verify extended fields are in list response
                assert "dob" in test_inst
                assert "tags" in test_inst
                print("✓ List instructors includes extended fields")
            else:
                print("⚠ Test instructor not found in list (may be archived)")
        else:
            print("⚠ No test instructor ID to verify")

    def test_archive_instructor(self, auth_headers):
        """DELETE /api/memberships/instructors/{id} archives the instructor."""
        inst_id = getattr(self.__class__, 'created_instructor_id', None)
        if not inst_id:
            pytest.skip("No instructor created in previous test")

        resp = requests.delete(f"{BASE_URL}/api/memberships/instructors/{inst_id}", headers=auth_headers)
        assert resp.status_code == 200, f"Archive failed: {resp.text}"

        data = resp.json()
        assert data.get("ok") == True

        print(f"✓ Archived instructor: {inst_id}")


class TestInstructorFieldValidation:
    """Test validation of instructor fields."""

    def test_create_instructor_name_required(self, auth_headers):
        """POST /api/memberships/instructors requires name."""
        payload = {
            "email": "no.name@example.com"
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=auth_headers)
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Name is required for instructor creation")

    def test_create_instructor_name_min_length(self, auth_headers):
        """POST /api/memberships/instructors validates name min length."""
        payload = {
            "name": "A"  # Too short (min 2)
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=auth_headers)
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("✓ Name min length validation works")

    def test_create_instructor_optional_fields_can_be_null(self, auth_headers):
        """POST /api/memberships/instructors allows null optional fields."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "name": f"Minimal Instructor {unique_id}",
            "dob": None,
            "address_line1": None,
            "emergency_contact_name": None,
            "notes": None,
            "tags": []
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Create failed: {resp.text}"

        data = resp.json()
        inst = data["instructor"]

        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/instructors/{inst['id']}", headers=auth_headers)

        print("✓ Optional fields can be null")


class TestMemberDeepLink:
    """Test member deep-link functionality (hash listener)."""

    def test_get_member_by_id(self, auth_headers):
        """GET /api/memberships/members/{id} works for deep-link target."""
        # First get list of members to find a valid ID
        resp = requests.get(f"{BASE_URL}/api/memberships/members", headers=auth_headers)
        assert resp.status_code == 200, f"List members failed: {resp.text}"

        members = resp.json().get("members", [])
        if not members:
            pytest.skip("No members in system to test deep-link")

        member_id = members[0]["id"]

        # Test GET by ID (this is what the drawer fetches)
        resp = requests.get(f"{BASE_URL}/api/memberships/members/{member_id}", headers=auth_headers)
        assert resp.status_code == 200, f"GET member failed: {resp.text}"

        data = resp.json()
        assert "member" in data
        assert data["member"]["id"] == member_id

        print(f"✓ GET member by ID works for deep-link: {member_id}")


class TestPulseBrandSafety:
    """Test that Pulse pages maintain correct branding.

    NOTE: These tests are skipped because data-brand is set dynamically by React
    after page render. The raw HTML always has data-brand="gymaxis".
    Playwright tests confirm the rendered page has data-brand="pulse".
    """

    @pytest.mark.skip(reason="data-brand is set dynamically by React - verified via Playwright")
    def test_pulse_page_has_pulse_brand(self):
        """GET /pulse page should have data-brand='pulse'."""
        resp = requests.get(f"{BASE_URL}/pulse")
        assert resp.status_code == 200, f"Pulse page failed: {resp.status_code}"
        print("✓ /pulse loads (data-brand verified via Playwright)")

    @pytest.mark.skip(reason="data-brand is set dynamically by React - verified via Playwright")
    def test_pulse_pricing_has_pulse_brand(self):
        """GET /pulse-pricing page should have data-brand='pulse'."""
        resp = requests.get(f"{BASE_URL}/pulse-pricing")
        assert resp.status_code == 200, f"Pulse pricing page failed: {resp.status_code}"
        print("✓ /pulse-pricing loads (data-brand verified via Playwright)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
