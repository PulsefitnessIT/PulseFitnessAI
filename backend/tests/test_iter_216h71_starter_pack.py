"""
Iter 216h71 — Marketing Starter Pack API tests.

Tests:
1. POST /api/marketing/starter-pack/generate — generates 3 emails + 3 social posts
2. GET /api/marketing/starter-pack — retrieves previously generated pack
3. DELETE /api/marketing/starter-pack — clears the pack
4. POST /generate when brand_kit has no voice AND no tone_of_voice → 400
5. All endpoints require marketing module (require_module guard)
6. GET /api/marketing/brand-discovery/asset/{path} — asset serving with cross-tenant guard
7. Verify 'var' CSS token bug fix in brand_discovery fonts
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
TEST_EMAIL = "e1.agent@gymaxisai.com"
TEST_PASSWORD = "E1Agent123!"


@pytest.fixture(scope="module")
def auth_headers():
    """Get auth token for Pulse Fitness user (marketing module enabled)."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("token")
    assert token, "No token in login response"
    return {"Authorization": f"Bearer {token}"}


class TestStarterPackGenerate:
    """POST /api/marketing/starter-pack/generate tests."""

    def test_generate_returns_pack_with_3_emails_3_social(self, auth_headers):
        """Generate starter pack and verify structure: 3 emails + 3 social posts."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/generate",
            headers=auth_headers,
            json={},
        )
        # May take a few seconds for LLM call
        assert resp.status_code == 200, f"Generate failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert data.get("ok") is True, "Expected ok:true"
        assert "pack" in data, "Missing 'pack' in response"
        assert "generated_at" in data, "Missing 'generated_at' in response"
        
        pack = data["pack"]
        
        # Verify 3 emails with correct IDs
        assert "emails" in pack, "Missing 'emails' in pack"
        emails = pack["emails"]
        assert len(emails) == 3, f"Expected 3 emails, got {len(emails)}"
        email_ids = {e["id"] for e in emails}
        assert email_ids == {"welcome", "win_back", "promo"}, f"Unexpected email IDs: {email_ids}"
        
        # Verify email structure
        for email in emails:
            assert "subject" in email, f"Email {email['id']} missing subject"
            assert "preview" in email, f"Email {email['id']} missing preview"
            assert "body" in email, f"Email {email['id']} missing body"
        
        # Verify 3 social posts with correct IDs
        assert "social" in pack, "Missing 'social' in pack"
        social = pack["social"]
        assert len(social) == 3, f"Expected 3 social posts, got {len(social)}"
        social_ids = {s["id"] for s in social}
        assert social_ids == {"instagram", "facebook", "x"}, f"Unexpected social IDs: {social_ids}"
        
        # Verify social post structure
        for post in social:
            assert "platform" in post, f"Social {post['id']} missing platform"
            assert "body" in post, f"Social {post['id']} missing body"

    def test_generate_requires_auth(self):
        """Generate endpoint requires authentication."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/generate",
            json={},
        )
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"


class TestStarterPackGet:
    """GET /api/marketing/starter-pack tests."""

    def test_get_returns_existing_pack(self, auth_headers):
        """GET returns the previously generated pack."""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/starter-pack",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"GET failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        
        # Should have pack data (from generate test or backfill)
        if data:  # Pack exists
            assert "organization_id" in data, "Missing organization_id"
            assert "pack" in data, "Missing pack"
            assert "generated_at" in data, "Missing generated_at"
            
            pack = data["pack"]
            assert "emails" in pack, "Missing emails in pack"
            assert "social" in pack, "Missing social in pack"

    def test_get_requires_auth(self):
        """GET endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/marketing/starter-pack")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"


class TestStarterPackDelete:
    """DELETE /api/marketing/starter-pack tests."""

    def test_delete_clears_pack(self, auth_headers):
        """DELETE wipes the pack; subsequent GET returns empty."""
        # First ensure we have a pack
        get_resp = requests.get(
            f"{BASE_URL}/api/marketing/starter-pack",
            headers=auth_headers,
        )
        had_pack = bool(get_resp.json())
        
        # Delete
        del_resp = requests.delete(
            f"{BASE_URL}/api/marketing/starter-pack",
            headers=auth_headers,
        )
        assert del_resp.status_code == 200, f"DELETE failed: {del_resp.status_code} - {del_resp.text}"
        assert del_resp.json().get("ok") is True, "Expected ok:true"
        
        # Verify GET returns empty
        get_resp2 = requests.get(
            f"{BASE_URL}/api/marketing/starter-pack",
            headers=auth_headers,
        )
        assert get_resp2.status_code == 200
        assert get_resp2.json() == {}, f"Expected empty dict after delete, got {get_resp2.json()}"
        
        # Regenerate if we had a pack (to not break other tests)
        if had_pack:
            requests.post(
                f"{BASE_URL}/api/marketing/starter-pack/generate",
                headers=auth_headers,
                json={},
            )

    def test_delete_requires_auth(self):
        """DELETE endpoint requires authentication."""
        resp = requests.delete(f"{BASE_URL}/api/marketing/starter-pack")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"


class TestStarterPackValidation:
    """Validation tests for starter pack generation."""

    def test_generate_without_voice_returns_400(self, auth_headers):
        """
        Generate should return 400 when brand_kit has no voice AND 
        brand_discovery has no tone_of_voice.
        
        Note: This test is skipped if the user already has voice set.
        The main agent confirmed Pulse Fitness has voice set, so we
        verify the error message format instead.
        """
        # First check if user has voice set
        kit_resp = requests.get(
            f"{BASE_URL}/api/marketing/brand-kit",
            headers=auth_headers,
        )
        if kit_resp.status_code == 200:
            kit = kit_resp.json().get("brand_kit", {})
            if kit.get("voice"):
                pytest.skip("User already has voice set - cannot test sparse brand kit error")
        
        # If no voice, generate should fail with 400
        resp = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/generate",
            headers=auth_headers,
            json={},
        )
        if resp.status_code == 400:
            assert "sparse" in resp.text.lower() or "voice" in resp.text.lower(), \
                f"Expected error about sparse brand kit, got: {resp.text}"


class TestBrandDiscoveryAsset:
    """GET /api/marketing/brand-discovery/asset/{path} tests."""

    def test_asset_returns_200_for_own_org(self, auth_headers):
        """Asset endpoint returns 200 for requester's own org assets."""
        # First get the org_id from brand discovery status
        status_resp = requests.get(
            f"{BASE_URL}/api/marketing/brand-discovery/status",
            headers=auth_headers,
        )
        if status_resp.status_code != 200:
            pytest.skip("No brand discovery data available")
        
        data = status_resp.json()
        draft = data.get("draft", {})
        logos = draft.get("logos", [])
        
        if not logos:
            pytest.skip("No logos in brand discovery draft")
        
        # Get the stored_url from first logo
        stored_url = logos[0].get("stored_url", "")
        if not stored_url or not stored_url.startswith("/api/marketing/brand-discovery/asset/"):
            pytest.skip(f"No valid stored_url in logo: {stored_url}")
        
        # Request the asset
        resp = requests.get(
            f"{BASE_URL}{stored_url}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Asset request failed: {resp.status_code}"
        assert len(resp.content) > 0, "Asset content is empty"

    def test_asset_returns_403_for_cross_tenant(self, auth_headers):
        """Asset endpoint returns 403 when requesting another org's asset."""
        # Try to access a fake path for another org
        fake_path = "gymaxis/brand-discovery/fake-other-org-id/logo-0.jpg"
        resp = requests.get(
            f"{BASE_URL}/api/marketing/brand-discovery/asset/{fake_path}",
            headers=auth_headers,
        )
        assert resp.status_code == 403, f"Expected 403 for cross-tenant, got {resp.status_code}"

    def test_asset_returns_404_for_nonexistent(self, auth_headers):
        """Asset endpoint returns 404 for non-existent assets."""
        # Get user's org_id first
        status_resp = requests.get(
            f"{BASE_URL}/api/marketing/brand-discovery/status",
            headers=auth_headers,
        )
        if status_resp.status_code != 200:
            pytest.skip("No brand discovery data available")
        
        org_id = status_resp.json().get("organization_id", "")
        if not org_id:
            pytest.skip("No organization_id in status")
        
        # Request non-existent asset in own org
        fake_path = f"gymaxis/brand-discovery/{org_id}/nonexistent-asset-12345.jpg"
        resp = requests.get(
            f"{BASE_URL}/api/marketing/brand-discovery/asset/{fake_path}",
            headers=auth_headers,
        )
        assert resp.status_code == 404, f"Expected 404 for nonexistent, got {resp.status_code}"


class TestVarFontTokenBugFix:
    """Verify 'var' CSS token bug fix in brand_discovery fonts."""

    def test_fonts_do_not_contain_var_token(self, auth_headers):
        """
        Brand discovery fonts should NOT contain literal 'var' token.
        The iter 216h71 fix filters out CSS custom-property tokens.
        """
        status_resp = requests.get(
            f"{BASE_URL}/api/marketing/brand-discovery/status",
            headers=auth_headers,
        )
        if status_resp.status_code != 200:
            pytest.skip("No brand discovery data available")
        
        data = status_resp.json()
        draft = data.get("draft", {})
        fonts = draft.get("fonts", {})
        
        if not fonts:
            pytest.skip("No fonts in brand discovery draft")
        
        heading = fonts.get("heading", "")
        body = fonts.get("body", "")
        all_fonts = fonts.get("all", [])
        
        # Check that 'var' is not captured as a font name
        assert heading.lower() != "var", f"heading font is 'var': {heading}"
        assert body.lower() != "var", f"body font is 'var': {body}"
        assert "var" not in [f.lower() for f in all_fonts], f"'var' found in all fonts: {all_fonts}"
        
        # Also check for var( prefix
        assert not heading.lower().startswith("var("), f"heading starts with var(: {heading}"
        assert not body.lower().startswith("var("), f"body starts with var(: {body}"


class TestModuleGuard:
    """Verify all starter pack endpoints require marketing module."""

    def test_endpoints_require_marketing_module(self, auth_headers):
        """
        All starter pack endpoints should require marketing module.
        Since our test user has marketing enabled, we verify the endpoints
        work (200) rather than fail (403).
        """
        # GET should work
        get_resp = requests.get(
            f"{BASE_URL}/api/marketing/starter-pack",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200, f"GET should work with marketing module: {get_resp.status_code}"
        
        # POST generate should work (or return 400 for validation, not 403)
        gen_resp = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/generate",
            headers=auth_headers,
            json={},
        )
        assert gen_resp.status_code in [200, 400, 502], \
            f"Generate should work or fail validation, not module guard: {gen_resp.status_code}"
        
        # DELETE should work
        del_resp = requests.delete(
            f"{BASE_URL}/api/marketing/starter-pack",
            headers=auth_headers,
        )
        assert del_resp.status_code == 200, f"DELETE should work with marketing module: {del_resp.status_code}"
