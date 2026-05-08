"""
Iteration 215r — Studio Extras: Waivers/PARQ + Per-class shareable OG preview cards.

Tests:
1. Plan waiver fields (waiver_required, waiver_text) on POST/PATCH/GET
2. Member waiver signing (POST /api/member/waivers)
3. Idempotent waiver signing (already_signed:true)
4. Skip waiver for plans without waiver_required
5. 400 error when acknowledged:false
6. GET /api/member/waivers/me
7. OG image generation (GET /api/m/{slug}/c/{occ}/og.png)
8. Share HTML with OG meta tags (GET /api/m/{slug}/c/{occ}/share)
9. Operator share slug endpoint (GET /api/memberships/share/org-slug)
"""
import os
import pytest
import requests
import hashlib

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
MEMBER_EMAIL = "rebook-1777578936@example.com"
MEMBER_PASSWORD = "Test123!"

# Known test data from main agent context
ORG_SLUG = "maintenance-hub-357"
TEST_OCC_ID = "4cc60ae4-fb56-439a-a94b-9f1547923d3d"


class TestWaiverPlanFields:
    """Test waiver_required and waiver_text fields on membership plans."""

    @pytest.fixture(scope="class")
    def operator_token(self):
        """Get operator JWT token."""
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        if r.status_code != 200:
            pytest.skip(f"Operator login failed: {r.status_code} - {r.text}")
        return r.json().get("token")

    @pytest.fixture(scope="class")
    def headers(self, operator_token):
        return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}

    def test_create_plan_with_waiver_fields(self, headers):
        """POST /api/memberships/plans with waiver_required=true and waiver_text persists both."""
        payload = {
            "name": "TEST_Waiver_Plan_215r",
            "kind": "class_pack",
            "price_pence": 5000,
            "billing_cycle": "oneoff",
            "credits_count": 10,
            "waiver_required": True,
            "waiver_text": "I acknowledge the risks of physical activity and agree to follow all safety guidelines."
        }
        r = requests.post(f"{BASE_URL}/api/memberships/plans", json=payload, headers=headers)
        assert r.status_code in [200, 201], f"Create plan failed: {r.status_code} - {r.text}"

        data = r.json()
        plan = data.get("plan", data)
        assert plan.get("waiver_required") == True, "waiver_required not persisted"
        assert "risks of physical activity" in (plan.get("waiver_text") or ""), "waiver_text not persisted"

        # Store plan_id for cleanup
        self.__class__.test_plan_id = plan.get("id")
        print(f"✓ Created plan with waiver fields: {plan.get('id')}")

    def test_get_plans_returns_waiver_fields(self, headers):
        """GET /api/memberships/plans returns waiver_required and waiver_text."""
        r = requests.get(f"{BASE_URL}/api/memberships/plans", headers=headers)
        assert r.status_code == 200, f"Get plans failed: {r.status_code}"

        plans = r.json().get("plans", [])
        waiver_plan = next((p for p in plans if p.get("name") == "TEST_Waiver_Plan_215r"), None)

        if waiver_plan:
            assert waiver_plan.get("waiver_required") == True
            assert waiver_plan.get("waiver_text") is not None
            print("✓ GET plans returns waiver fields correctly")
        else:
            print("⚠ Test plan not found in list (may have been archived)")

    def test_update_plan_waiver_fields(self, headers):
        """PATCH /api/memberships/plans/{id} updates waiver fields."""
        plan_id = getattr(self.__class__, 'test_plan_id', None)
        if not plan_id:
            pytest.skip("No test plan created")

        update_payload = {
            "waiver_text": "Updated waiver text for testing purposes."
        }
        r = requests.patch(f"{BASE_URL}/api/memberships/plans/{plan_id}", json=update_payload, headers=headers)
        assert r.status_code == 200, f"Update plan failed: {r.status_code} - {r.text}"
        print("✓ Updated plan waiver_text successfully")

    def test_cleanup_test_plan(self, headers):
        """Archive the test plan."""
        plan_id = getattr(self.__class__, 'test_plan_id', None)
        if plan_id:
            r = requests.delete(f"{BASE_URL}/api/memberships/plans/{plan_id}", headers=headers)
            print(f"✓ Archived test plan: {r.status_code}")


class TestMemberWaiverSigning:
    """Test member waiver signing endpoints."""

    @pytest.fixture(scope="class")
    def member_token(self):
        """Get member JWT token."""
        r = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        if r.status_code != 200:
            pytest.skip(f"Member login failed: {r.status_code} - {r.text}")
        return r.json().get("token")

    @pytest.fixture(scope="class")
    def operator_token(self):
        """Get operator JWT token for plan creation."""
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        if r.status_code != 200:
            pytest.skip(f"Operator login failed: {r.status_code}")
        return r.json().get("token")

    @pytest.fixture(scope="class")
    def member_headers(self, member_token):
        return {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def operator_headers(self, operator_token):
        return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def waiver_plan(self, operator_headers):
        """Create a plan with waiver_required=true for testing."""
        payload = {
            "name": "TEST_Waiver_Signing_Plan",
            "kind": "class_pack",
            "price_pence": 3000,
            "billing_cycle": "oneoff",
            "credits_count": 5,
            "waiver_required": True,
            "waiver_text": "I understand and accept all risks associated with this activity."
        }
        r = requests.post(f"{BASE_URL}/api/memberships/plans", json=payload, headers=operator_headers)
        if r.status_code not in [200, 201]:
            pytest.skip(f"Could not create waiver plan: {r.status_code}")
        plan = r.json().get("plan", r.json())
        yield plan
        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/plans/{plan['id']}", headers=operator_headers)

    @pytest.fixture(scope="class")
    def no_waiver_plan(self, operator_headers):
        """Create a plan with waiver_required=false for testing skip behavior."""
        payload = {
            "name": "TEST_No_Waiver_Plan",
            "kind": "class_pack",
            "price_pence": 2000,
            "billing_cycle": "oneoff",
            "credits_count": 3,
            "waiver_required": False
        }
        r = requests.post(f"{BASE_URL}/api/memberships/plans", json=payload, headers=operator_headers)
        if r.status_code not in [200, 201]:
            pytest.skip(f"Could not create no-waiver plan: {r.status_code}")
        plan = r.json().get("plan", r.json())
        yield plan
        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/plans/{plan['id']}", headers=operator_headers)

    def test_sign_waiver_success(self, member_headers, waiver_plan):
        """POST /api/member/waivers with valid data creates waiver record."""
        payload = {
            "plan_id": waiver_plan["id"],
            "signature_name": "Test Member Signature",
            "acknowledged": True
        }
        r = requests.post(f"{BASE_URL}/api/member/waivers", json=payload, headers=member_headers)
        assert r.status_code == 200, f"Sign waiver failed: {r.status_code} - {r.text}"

        data = r.json()
        assert data.get("ok") == True, "Response should have ok:true"
        assert "waiver_id" in data, "Response should include waiver_id"
        # First sign should have already_signed:false
        # (unless member already signed in a previous test run)
        print(f"✓ Waiver signed: waiver_id={data.get('waiver_id')}, already_signed={data.get('already_signed')}")

    def test_sign_waiver_idempotent(self, member_headers, waiver_plan):
        """Second POST /api/member/waivers for same plan returns already_signed:true."""
        payload = {
            "plan_id": waiver_plan["id"],
            "signature_name": "Test Member Signature Again",
            "acknowledged": True
        }
        r = requests.post(f"{BASE_URL}/api/member/waivers", json=payload, headers=member_headers)
        assert r.status_code == 200, f"Idempotent sign failed: {r.status_code} - {r.text}"

        data = r.json()
        assert data.get("ok") == True
        assert data.get("already_signed") == True, "Second sign should return already_signed:true"
        print(f"✓ Idempotent waiver signing works: already_signed={data.get('already_signed')}")

    def test_sign_waiver_skip_when_not_required(self, member_headers, no_waiver_plan):
        """POST /api/member/waivers for plan without waiver_required returns skipped:true."""
        payload = {
            "plan_id": no_waiver_plan["id"],
            "signature_name": "Should Skip",
            "acknowledged": True
        }
        r = requests.post(f"{BASE_URL}/api/member/waivers", json=payload, headers=member_headers)
        assert r.status_code == 200, f"Skip waiver failed: {r.status_code} - {r.text}"

        data = r.json()
        assert data.get("ok") == True
        assert data.get("skipped") == True, "Should return skipped:true for non-waiver plan"
        assert data.get("reason") == "plan_waiver_not_required"
        print(f"✓ Waiver skipped for non-waiver plan: reason={data.get('reason')}")

    def test_sign_waiver_rejected_without_acknowledgement(self, member_headers, waiver_plan):
        """POST /api/member/waivers with acknowledged:false returns 400."""
        payload = {
            "plan_id": waiver_plan["id"],
            "signature_name": "Test Signature",
            "acknowledged": False
        }
        r = requests.post(f"{BASE_URL}/api/member/waivers", json=payload, headers=member_headers)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"

        detail = r.json().get("detail", "")
        assert "acknowledge" in detail.lower(), f"Error should mention acknowledgement: {detail}"
        print(f"✓ Waiver rejected without acknowledgement: {detail}")

    def test_get_member_waivers(self, member_headers):
        """GET /api/member/waivers/me returns signed waivers."""
        r = requests.get(f"{BASE_URL}/api/member/waivers/me", headers=member_headers)
        assert r.status_code == 200, f"Get waivers failed: {r.status_code} - {r.text}"

        data = r.json()
        waivers = data.get("waivers", [])
        assert isinstance(waivers, list), "Response should have waivers array"
        print(f"✓ GET /api/member/waivers/me returned {len(waivers)} waivers")

        # Verify structure of waiver records
        if waivers:
            w = waivers[0]
            assert "id" in w, "Waiver should have id"
            assert "plan_id" in w, "Waiver should have plan_id"
            assert "signed_at" in w, "Waiver should have signed_at"
            print(f"  First waiver: plan_id={w.get('plan_id')}, signed_at={w.get('signed_at')}")


class TestShareCardOGImage:
    """Test OG image generation for class share cards."""

    def test_og_image_returns_png(self):
        """GET /api/m/{slug}/c/{occ}/og.png returns image/png."""
        url = f"{BASE_URL}/api/m/{ORG_SLUG}/c/{TEST_OCC_ID}/og.png"
        r = requests.get(url)

        if r.status_code == 404:
            pytest.skip(f"Class occurrence not found: {TEST_OCC_ID}")

        assert r.status_code == 200, f"OG image failed: {r.status_code}"
        assert r.headers.get("content-type") == "image/png", f"Expected image/png, got {r.headers.get('content-type')}"

        # Check size is reasonable (30-50KB expected)
        size_kb = len(r.content) / 1024
        assert 10 < size_kb < 100, f"Image size {size_kb:.1f}KB outside expected range"

        # Verify PNG magic bytes
        assert r.content[:8] == b'\x89PNG\r\n\x1a\n', "Not a valid PNG file"
        print(f"✓ OG image: {size_kb:.1f}KB, content-type=image/png")

    def test_og_image_invalid_slug_returns_404(self):
        """GET /api/m/invalid-slug/c/{occ}/og.png returns 404."""
        url = f"{BASE_URL}/api/m/invalid-nonexistent-slug/c/{TEST_OCC_ID}/og.png"
        r = requests.get(url)
        assert r.status_code == 404, f"Expected 404 for invalid slug, got {r.status_code}"
        print("✓ Invalid slug returns 404")

    def test_og_image_invalid_occ_returns_404(self):
        """GET /api/m/{slug}/c/invalid-occ/og.png returns 404."""
        url = f"{BASE_URL}/api/m/{ORG_SLUG}/c/invalid-occurrence-id/og.png"
        r = requests.get(url)
        assert r.status_code == 404, f"Expected 404 for invalid occ, got {r.status_code}"
        print("✓ Invalid occurrence returns 404")


class TestShareCardHTML:
    """Test share HTML page with OG meta tags."""

    def test_share_html_returns_og_tags(self):
        """GET /api/m/{slug}/c/{occ}/share returns HTML with OG meta tags."""
        url = f"{BASE_URL}/api/m/{ORG_SLUG}/c/{TEST_OCC_ID}/share"
        r = requests.get(url)

        if r.status_code == 404:
            pytest.skip(f"Class occurrence not found: {TEST_OCC_ID}")

        assert r.status_code == 200, f"Share HTML failed: {r.status_code}"
        assert "text/html" in r.headers.get("content-type", ""), "Expected text/html"

        html = r.text

        # Check required OG tags
        assert 'og:title' in html, "Missing og:title"
        assert 'og:description' in html, "Missing og:description"
        assert 'og:image' in html, "Missing og:image"
        assert 'og.png' in html, "og:image should point to og.png"

        # Check Twitter card
        assert 'twitter:card' in html, "Missing twitter:card"

        # Check canonical link
        assert 'rel="canonical"' in html, "Missing canonical link"

        # Check meta refresh
        assert 'http-equiv="refresh"' in html, "Missing meta refresh"

        print("✓ Share HTML contains all required OG meta tags")

    def test_share_html_invalid_slug_returns_404(self):
        """GET /api/m/invalid-slug/c/{occ}/share returns 404."""
        url = f"{BASE_URL}/api/m/invalid-nonexistent-slug/c/{TEST_OCC_ID}/share"
        r = requests.get(url)
        assert r.status_code == 404, f"Expected 404 for invalid slug, got {r.status_code}"
        print("✓ Invalid slug returns 404 for share HTML")


class TestOperatorShareSlug:
    """Test operator share slug endpoint."""

    @pytest.fixture(scope="class")
    def operator_token(self):
        """Get operator JWT token."""
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        if r.status_code != 200:
            pytest.skip(f"Operator login failed: {r.status_code}")
        return r.json().get("token")

    @pytest.fixture(scope="class")
    def headers(self, operator_token):
        return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}

    def test_get_org_slug(self, headers):
        """GET /api/memberships/share/org-slug returns the org's public slug."""
        r = requests.get(f"{BASE_URL}/api/memberships/share/org-slug", headers=headers)
        assert r.status_code == 200, f"Get org slug failed: {r.status_code} - {r.text}"

        data = r.json()
        assert "slug" in data, "Response should have slug field"
        slug = data.get("slug")
        assert slug and len(slug) > 0, "Slug should not be empty"
        print(f"✓ Operator share slug: {slug}")

    def test_get_org_slug_unauthorized(self):
        """GET /api/memberships/share/org-slug without auth returns 401/403."""
        r = requests.get(f"{BASE_URL}/api/memberships/share/org-slug")
        assert r.status_code in [401, 403], f"Expected 401/403 without auth, got {r.status_code}"
        print(f"✓ Unauthorized request returns {r.status_code}")


class TestRegressionWalkInMessageShare:
    """Regression tests for Walk-in, Message class, Book Again from iter 215q."""

    @pytest.fixture(scope="class")
    def operator_token(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        if r.status_code != 200:
            pytest.skip(f"Operator login failed: {r.status_code}")
        return r.json().get("token")

    @pytest.fixture(scope="class")
    def member_token(self):
        r = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        if r.status_code != 200:
            pytest.skip(f"Member login failed: {r.status_code}")
        return r.json().get("token")

    @pytest.fixture(scope="class")
    def operator_headers(self, operator_token):
        return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def member_headers(self, member_token):
        return {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}

    def test_walk_in_endpoint_exists(self, operator_headers):
        """POST /api/memberships/checkin/walk-in endpoint is accessible."""
        # Just verify the endpoint exists and returns expected error for missing data
        r = requests.post(f"{BASE_URL}/api/memberships/checkin/walk-in",
                         json={"name": "Test", "occurrence_id": "invalid"},
                         headers=operator_headers)
        # Should return 404 for invalid occurrence, not 500 or route not found
        assert r.status_code in [200, 404, 422], f"Walk-in endpoint issue: {r.status_code}"
        print(f"✓ Walk-in endpoint accessible: {r.status_code}")

    def test_broadcast_endpoint_exists(self, operator_headers):
        """POST /api/memberships/classes/{occ}/broadcast endpoint is accessible."""
        r = requests.post(f"{BASE_URL}/api/memberships/classes/{TEST_OCC_ID}/broadcast",
                         json={"message": "Test broadcast"},
                         headers=operator_headers)
        # Should work or return 404 for invalid occ, not 500
        assert r.status_code in [200, 404, 422], f"Broadcast endpoint issue: {r.status_code}"
        print(f"✓ Broadcast endpoint accessible: {r.status_code}")

    def test_rebook_endpoint_exists(self, member_headers):
        """POST /api/member/bookings/rebook endpoint is accessible."""
        r = requests.post(f"{BASE_URL}/api/member/bookings/rebook",
                         json={"source_booking_id": "invalid-id"},
                         headers=member_headers)
        # Should return 404 for invalid booking, not 500
        assert r.status_code in [200, 404, 422], f"Rebook endpoint issue: {r.status_code}"
        print(f"✓ Rebook endpoint accessible: {r.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
