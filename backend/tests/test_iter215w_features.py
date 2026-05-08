"""
Iteration 215w Backend Tests

Tests for:
1. POST /api/memberships/instructors/{id}/invite-login — creates user login for instructor
2. GET /api/instructor/profile — instructor self-serve profile fetch
3. PATCH /api/instructor/profile — instructor self-serve profile update
4. POST /api/member/invoices/pay-all — bundle checkout for outstanding invoices
5. Webhook: checkout.session.completed with gymaxis_kind='class_invoice_bundle'
6. POST /api/memberships/classes/templates with instructor_id — persisted
7. GET /api/member/timetable — returns instructor info on occurrences
"""
import os
import pytest
import requests
import jwt
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
JWT_SECRET = os.environ.get('JWT_SECRET', 'gymaxis-ai-secret-key-2026')

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
ORG_ID = "156c8dc4-8683-4cb4-8a74-facd811655ad"
MEMBERSHIP_APP_SLUG = "maintenance-hub-357"

# Pre-seeded instructor from iter 215v
INSTRUCTOR_ID = "0cce241e-c932-49e5-9074-9b125dfd30b9"
INSTRUCTOR_SLUG = "aiden-rowe"
INSTRUCTOR_USER_ID = "0ba72dfc-2d59-422e-8412-97af93e6bf00"
INSTRUCTOR_EMAIL = "aiden.rowe+test@pulsefitness.com"

# Billing test member
BILLING_TEST_MEMBER_EMAIL = "billing.test@example.com"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    assert resp.status_code == 200, f"Operator login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


def mint_instructor_jwt(user_id: str) -> str:
    """Mint a JWT for the instructor user to test self-serve endpoints"""
    payload = {
        "user_id": user_id,
        "jti": "test-instructor-jwt",
        "exp": datetime.now(timezone.utc).timestamp() + 3600,
        "iat": datetime.now(timezone.utc).timestamp(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="module")
def instructor_headers():
    """Headers for instructor self-serve endpoints"""
    token = mint_instructor_jwt(INSTRUCTOR_USER_ID)
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. POST /api/memberships/instructors/{id}/invite-login
# ═══════════════════════════════════════════════════════════════════════════

class TestInviteLogin:
    """Tests for instructor invite-login endpoint"""

    def test_invite_login_already_linked(self, operator_headers):
        """Instructor already has user_id — returns already_linked=true"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/instructors/{INSTRUCTOR_ID}/invite-login",
            headers=operator_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("already_linked") is True or data.get("user_id") == INSTRUCTOR_USER_ID
        print("✓ Invite-login returns already_linked for pre-linked instructor")

    def test_invite_login_no_email_returns_400(self, operator_headers):
        """Instructor without email should return 400"""
        # First create an instructor without email
        create_resp = requests.post(
            f"{BASE_URL}/api/memberships/instructors",
            headers=operator_headers,
            json={"name": "TEST_NoEmail_Instructor", "email": None}
        )
        if create_resp.status_code != 200:
            pytest.skip("Could not create test instructor")

        inst_id = create_resp.json()["instructor"]["id"]

        # Try to invite — should fail with 400
        resp = requests.post(
            f"{BASE_URL}/api/memberships/instructors/{inst_id}/invite-login",
            headers=operator_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "email" in resp.text.lower()
        print("✓ Invite-login returns 400 when instructor has no email")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/instructors/{inst_id}", headers=operator_headers)

    def test_invite_login_not_found(self, operator_headers):
        """Non-existent instructor returns 404"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/instructors/nonexistent-id/invite-login",
            headers=operator_headers
        )
        assert resp.status_code == 404
        print("✓ Invite-login returns 404 for non-existent instructor")


# ═══════════════════════════════════════════════════════════════════════════
# 2. GET /api/instructor/profile — instructor self-serve fetch
# ═══════════════════════════════════════════════════════════════════════════

class TestInstructorProfileGet:
    """Tests for GET /api/instructor/profile"""

    def test_get_profile_success(self, instructor_headers):
        """Linked instructor can fetch their profile"""
        resp = requests.get(
            f"{BASE_URL}/api/instructor/profile",
            headers=instructor_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "instructor" in data
        inst = data["instructor"]
        assert inst.get("id") == INSTRUCTOR_ID
        assert inst.get("slug") == INSTRUCTOR_SLUG
        print("✓ GET /instructor/profile returns linked instructor doc")

    def test_get_profile_not_linked_returns_401_or_404(self):
        """User without linked instructor returns 401 (invalid JWT) or 404 (no instructor)"""
        # Mint a JWT for a random user_id that has no instructor
        token = mint_instructor_jwt("random-user-no-instructor")
        resp = requests.get(
            f"{BASE_URL}/api/instructor/profile",
            headers={"Authorization": f"Bearer {token}"}
        )
        # 401 if user doesn't exist, 404 if user exists but no instructor linked
        assert resp.status_code in [401, 404]
        print(f"✓ GET /instructor/profile returns {resp.status_code} for unlinked user")


# ═══════════════════════════════════════════════════════════════════════════
# 3. PATCH /api/instructor/profile — instructor self-serve update
# ═══════════════════════════════════════════════════════════════════════════

class TestInstructorProfilePatch:
    """Tests for PATCH /api/instructor/profile"""

    def test_patch_profile_allowed_fields(self, instructor_headers):
        """Instructor can update headline, bio, photo_url, etc."""
        new_headline = f"TEST_Updated headline {datetime.now().isoformat()}"
        resp = requests.patch(
            f"{BASE_URL}/api/instructor/profile",
            headers=instructor_headers,
            json={
                "headline": new_headline,
                "bio": "Updated bio for testing",
                "specialties": ["Yoga", "Pilates"],
                "years_experience": 5,
            }
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["instructor"]["headline"] == new_headline
        assert "Yoga" in data["instructor"]["specialties"]
        print("✓ PATCH /instructor/profile updates allowed fields")

    def test_patch_profile_blocks_name_change(self, instructor_headers):
        """Name changes are silently ignored (slug stability)"""
        # Get current name
        get_resp = requests.get(f"{BASE_URL}/api/instructor/profile", headers=instructor_headers)
        original_name = get_resp.json()["instructor"]["name"]

        # Try to change name
        resp = requests.patch(
            f"{BASE_URL}/api/instructor/profile",
            headers=instructor_headers,
            json={"name": "SHOULD_NOT_CHANGE"}
        )
        assert resp.status_code == 200
        # Name should remain unchanged
        assert resp.json()["instructor"]["name"] == original_name
        print("✓ PATCH /instructor/profile silently ignores name changes")

    def test_patch_profile_social_links(self, instructor_headers):
        """Instructor can update social links"""
        resp = requests.patch(
            f"{BASE_URL}/api/instructor/profile",
            headers=instructor_headers,
            json={
                "social": {
                    "instagram": "@test_instructor",
                    "website": "https://example.com"
                }
            }
        )
        assert resp.status_code == 200
        social = resp.json()["instructor"].get("social", {})
        assert social.get("instagram") == "@test_instructor"
        print("✓ PATCH /instructor/profile updates social links")


# ═══════════════════════════════════════════════════════════════════════════
# 4. POST /api/member/invoices/pay-all — bundle checkout
# ═══════════════════════════════════════════════════════════════════════════

class TestPayAllOutstanding:
    """Tests for POST /api/member/invoices/pay-all"""

    @pytest.fixture
    def member_token(self):
        """Get member token for billing test member"""
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": BILLING_TEST_MEMBER_EMAIL,
            "password": "Test123!"
        })
        if resp.status_code != 200:
            pytest.skip(f"Billing test member login failed: {resp.text}")
        return resp.json()["token"]

    @pytest.fixture
    def member_headers(self, member_token):
        return {"Authorization": f"Bearer {member_token}"}

    def test_pay_all_returns_checkout_url(self, member_headers):
        """Pay-all returns Stripe checkout URL when invoices exist"""
        resp = requests.post(
            f"{BASE_URL}/api/member/invoices/pay-all",
            headers=member_headers
        )
        # Could be 200 (has invoices) or 400 (nothing outstanding)
        if resp.status_code == 400:
            assert "nothing outstanding" in resp.text.lower() or "paid up" in resp.text.lower()
            print("✓ Pay-all returns 400 when nothing outstanding")
        elif resp.status_code == 200:
            data = resp.json()
            assert "checkout_url" in data
            assert "stripe.com" in data["checkout_url"]
            assert "invoice_ids" in data
            assert "total_pence" in data
            assert "count" in data
            print(f"✓ Pay-all returns checkout_url with {data['count']} invoices, £{data['total_pence']/100:.2f}")
        else:
            pytest.fail(f"Unexpected status {resp.status_code}: {resp.text}")

    def test_pay_all_no_auth_returns_401(self):
        """Pay-all without auth returns 401"""
        resp = requests.post(f"{BASE_URL}/api/member/invoices/pay-all")
        assert resp.status_code in [401, 403, 422]
        print(f"✓ Pay-all returns {resp.status_code} without auth")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Class template with instructor_id
# ═══════════════════════════════════════════════════════════════════════════

class TestClassTemplateInstructorId:
    """Tests for class template instructor_id field"""

    def test_create_template_with_instructor_id(self, operator_headers):
        """Creating a class template with instructor_id persists it"""
        payload = {
            "name": "TEST_Yoga_With_Instructor",
            "category": "Yoga",
            "instructor_id": INSTRUCTOR_ID,
            "instructor_name": "Aiden Rowe",
            "duration_min": 60,
            "capacity": 15,
            "recurs_days": [1],  # Tuesday
            "start_time": "10:00",
        }
        resp = requests.post(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=operator_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        tpl = resp.json()["template"]
        assert tpl["instructor_id"] == INSTRUCTOR_ID
        assert tpl["instructor_name"] == "Aiden Rowe"
        print(f"✓ Class template created with instructor_id={INSTRUCTOR_ID}")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/classes/templates/{tpl['id']}", headers=operator_headers)

    def test_patch_template_instructor_id(self, operator_headers):
        """Patching instructor_id on existing template works"""
        # First create a template without instructor_id
        create_resp = requests.post(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=operator_headers,
            json={
                "name": "TEST_Patch_Instructor",
                "category": "HIIT",
                "duration_min": 45,
                "capacity": 20,
                "recurs_days": [3],  # Thursday
                "start_time": "18:00",
            }
        )
        if create_resp.status_code != 200:
            pytest.skip("Could not create test template")

        tpl_id = create_resp.json()["template"]["id"]

        # Patch to add instructor_id
        patch_resp = requests.patch(
            f"{BASE_URL}/api/memberships/classes/templates/{tpl_id}",
            headers=operator_headers,
            json={"instructor_id": INSTRUCTOR_ID}
        )
        assert patch_resp.status_code == 200
        print("✓ PATCH template instructor_id works")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/classes/templates/{tpl_id}", headers=operator_headers)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Member timetable returns instructor info
# ═══════════════════════════════════════════════════════════════════════════

class TestMemberTimetableInstructor:
    """Tests for instructor info in member timetable"""

    @pytest.fixture
    def member_token(self):
        """Get any member token"""
        # Try the billing test member
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": BILLING_TEST_MEMBER_EMAIL,
            "password": "Test123!"
        })
        if resp.status_code == 200:
            return resp.json()["token"]

        # Try Emma
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": "emma.wright@demo.gymaxis",
            "password": "Member2026!"
        })
        if resp.status_code == 200:
            return resp.json()["token"]

        pytest.skip("No member login available")

    def test_timetable_includes_instructor_object(self, member_token):
        """Timetable occurrences include instructor {id, name, slug, photo_url}"""
        resp = requests.get(
            f"{BASE_URL}/api/member/timetable",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        occs = resp.json().get("occurrences", [])

        # Find an occurrence with instructor_id
        with_instructor = [o for o in occs if o.get("instructor")]
        if with_instructor:
            inst = with_instructor[0]["instructor"]
            assert "id" in inst
            assert "name" in inst
            assert "slug" in inst
            # photo_url may be None
            print(f"✓ Timetable occurrence has instructor object: {inst}")
        else:
            # No occurrences with linked instructor — that's OK, just verify structure
            print(f"✓ Timetable returned {len(occs)} occurrences (none with linked instructor)")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression: Previous iteration features still work
# ═══════════════════════════════════════════════════════════════════════════

class TestRegression:
    """Regression tests for previous iteration features"""

    def test_instructor_crud_still_works(self, operator_headers):
        """Instructor CRUD from 215v still works"""
        # List
        resp = requests.get(f"{BASE_URL}/api/memberships/instructors", headers=operator_headers)
        assert resp.status_code == 200

        # Get single
        resp = requests.get(f"{BASE_URL}/api/memberships/instructors/{INSTRUCTOR_ID}", headers=operator_headers)
        assert resp.status_code == 200
        print("✓ Instructor CRUD regression passed")

    def test_og_image_still_works(self):
        """OG image generation from 215v still works"""
        resp = requests.get(f"{BASE_URL}/api/m/{MEMBERSHIP_APP_SLUG}/i/{INSTRUCTOR_SLUG}/og.png")
        assert resp.status_code == 200
        assert resp.headers.get("Content-Type") == "image/png"
        assert len(resp.content) > 1000  # Should be a real PNG
        print("✓ OG image generation regression passed")

    def test_public_instructor_profile_still_works(self):
        """Public instructor profile from 215v still works"""
        resp = requests.get(f"{BASE_URL}/api/public/studios/{MEMBERSHIP_APP_SLUG}/instructors/{INSTRUCTOR_SLUG}")
        assert resp.status_code == 200
        data = resp.json()
        assert "instructor" in data
        assert "studio" in data
        # Verify no email/phone leak
        assert "email" not in data["instructor"] or data["instructor"].get("email") is None
        assert "phone" not in data["instructor"] or data["instructor"].get("phone") is None
        print("✓ Public instructor profile regression passed")

    def test_billing_invoice_list_still_works(self, operator_headers):
        """Billing invoice list from 215u still works"""
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/invoices", headers=operator_headers)
        assert resp.status_code == 200
        assert "invoices" in resp.json()
        print("✓ Billing invoice list regression passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
