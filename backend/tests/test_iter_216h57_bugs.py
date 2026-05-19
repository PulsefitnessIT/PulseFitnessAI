"""
Iter 216h57 — Bug fix verification tests

BUG 4b: POST /api/account/logo with PNG → 200 with logo_url
        GET /api/account/logo/{org_id} → 200 image/png
        DELETE /api/account/logo → 200 with logo_url=null

BUG 5b: /api/auth/me includes avatar_url and phone fields
        POST /api/account/avatar → 200 with avatar_url
        GET /api/account/avatar/{user_id} → 200 image/jpeg
"""
import os
import io
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_session():
    """Login as master admin and return session with auth headers."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data.get("token")
    assert token, "No token in login response"
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session, data.get("user", {})


def create_test_png(width=100, height=100):
    """Create a valid PNG image in memory."""
    img = Image.new('RGB', (width, height), color='blue')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def create_test_jpeg(width=100, height=100):
    """Create a valid JPEG image in memory."""
    img = Image.new('RGB', (width, height), color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf


class TestBug5b_AuthMeFields:
    """BUG 5b: /api/auth/me must include avatar_url and phone fields."""
    
    def test_auth_me_includes_avatar_url_field(self, admin_session):
        """Verify /api/auth/me response includes avatar_url field."""
        session, _ = admin_session
        resp = session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"GET /auth/me failed: {resp.text}"
        data = resp.json()
        # avatar_url should be present (can be null)
        assert "avatar_url" in data, f"avatar_url field missing from /auth/me response. Keys: {list(data.keys())}"
        print(f"✓ /auth/me includes avatar_url: {data.get('avatar_url')}")
    
    def test_auth_me_includes_phone_field(self, admin_session):
        """Verify /api/auth/me response includes phone field."""
        session, _ = admin_session
        resp = session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"GET /auth/me failed: {resp.text}"
        data = resp.json()
        # phone should be present (can be null)
        assert "phone" in data, f"phone field missing from /auth/me response. Keys: {list(data.keys())}"
        print(f"✓ /auth/me includes phone: {data.get('phone')}")


class TestBug5b_AvatarUpload:
    """BUG 5b: Avatar upload and proxy endpoint tests."""
    
    def test_avatar_upload_returns_avatar_url(self, admin_session):
        """POST /api/account/avatar with JPEG returns avatar_url."""
        session, user = admin_session
        
        # Create a test JPEG
        img_buf = create_test_jpeg(100, 100)
        
        # Remove Content-Type header for multipart
        headers = dict(session.headers)
        headers.pop("Content-Type", None)
        
        files = {"file": ("test_avatar.jpg", img_buf, "image/jpeg")}
        resp = requests.post(
            f"{BASE_URL}/api/account/avatar",
            headers=headers,
            files=files
        )
        
        assert resp.status_code == 200, f"Avatar upload failed: {resp.text}"
        data = resp.json()
        assert "avatar_url" in data, f"avatar_url missing from response: {data}"
        avatar_url = data["avatar_url"]
        assert avatar_url, "avatar_url is empty"
        # Should be the proxy URL format
        assert "/api/account/avatar/" in avatar_url, f"avatar_url should be proxy URL, got: {avatar_url}"
        print(f"✓ Avatar upload returned avatar_url: {avatar_url}")
        return avatar_url
    
    def test_avatar_proxy_returns_image(self, admin_session):
        """GET /api/account/avatar/{user_id} returns image/jpeg."""
        session, user = admin_session
        user_id = user.get("id")
        assert user_id, "No user_id in session"
        
        # First upload an avatar
        img_buf = create_test_jpeg(100, 100)
        headers = dict(session.headers)
        headers.pop("Content-Type", None)
        files = {"file": ("test_avatar.jpg", img_buf, "image/jpeg")}
        upload_resp = requests.post(
            f"{BASE_URL}/api/account/avatar",
            headers=headers,
            files=files
        )
        assert upload_resp.status_code == 200, f"Avatar upload failed: {upload_resp.text}"
        
        # Now GET the avatar via proxy (public endpoint, no auth needed)
        resp = requests.get(f"{BASE_URL}/api/account/avatar/{user_id}")
        assert resp.status_code == 200, f"Avatar proxy GET failed: {resp.status_code} {resp.text}"
        content_type = resp.headers.get("Content-Type", "")
        assert "image" in content_type, f"Expected image content-type, got: {content_type}"
        assert len(resp.content) > 0, "Avatar response is empty"
        print(f"✓ Avatar proxy returned image ({len(resp.content)} bytes, {content_type})")
    
    def test_auth_me_reflects_uploaded_avatar(self, admin_session):
        """After avatar upload, /auth/me returns the new avatar_url."""
        session, user = admin_session
        user_id = user.get("id")
        
        # Upload avatar
        img_buf = create_test_jpeg(100, 100)
        headers = dict(session.headers)
        headers.pop("Content-Type", None)
        files = {"file": ("test_avatar.jpg", img_buf, "image/jpeg")}
        upload_resp = requests.post(
            f"{BASE_URL}/api/account/avatar",
            headers=headers,
            files=files
        )
        assert upload_resp.status_code == 200
        uploaded_url = upload_resp.json().get("avatar_url")
        
        # Check /auth/me
        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        
        # avatar_url should match the proxy URL pattern
        assert me_data.get("avatar_url"), "avatar_url is null after upload"
        assert f"/api/account/avatar/{user_id}" in me_data.get("avatar_url", ""), \
            f"avatar_url should contain proxy path, got: {me_data.get('avatar_url')}"
        print(f"✓ /auth/me reflects uploaded avatar: {me_data.get('avatar_url')}")


class TestBug4b_LogoUpload:
    """BUG 4b: Organisation logo upload and proxy endpoint tests."""
    
    def test_logo_upload_returns_logo_url(self, admin_session):
        """POST /api/account/logo with PNG returns logo_url."""
        session, user = admin_session
        
        # Create a test PNG
        img_buf = create_test_png(200, 200)
        
        # Remove Content-Type header for multipart
        headers = dict(session.headers)
        headers.pop("Content-Type", None)
        
        files = {"file": ("test_logo.png", img_buf, "image/png")}
        resp = requests.post(
            f"{BASE_URL}/api/account/logo",
            headers=headers,
            files=files
        )
        
        assert resp.status_code == 200, f"Logo upload failed: {resp.text}"
        data = resp.json()
        assert "logo_url" in data, f"logo_url missing from response: {data}"
        logo_url = data["logo_url"]
        assert logo_url, "logo_url is empty"
        # Should be the proxy URL format
        assert "/api/account/logo/" in logo_url, f"logo_url should be proxy URL, got: {logo_url}"
        print(f"✓ Logo upload returned logo_url: {logo_url}")
        return logo_url
    
    def test_logo_proxy_returns_image(self, admin_session):
        """GET /api/account/logo/{org_id} returns image/png."""
        session, user = admin_session
        org_id = user.get("organization_id")
        assert org_id, "No organization_id in session"
        
        # First upload a logo
        img_buf = create_test_png(200, 200)
        headers = dict(session.headers)
        headers.pop("Content-Type", None)
        files = {"file": ("test_logo.png", img_buf, "image/png")}
        upload_resp = requests.post(
            f"{BASE_URL}/api/account/logo",
            headers=headers,
            files=files
        )
        assert upload_resp.status_code == 200, f"Logo upload failed: {upload_resp.text}"
        
        # Now GET the logo via proxy (public endpoint, no auth needed)
        resp = requests.get(f"{BASE_URL}/api/account/logo/{org_id}")
        assert resp.status_code == 200, f"Logo proxy GET failed: {resp.status_code} {resp.text}"
        content_type = resp.headers.get("Content-Type", "")
        assert "image" in content_type, f"Expected image content-type, got: {content_type}"
        assert len(resp.content) > 0, "Logo response is empty"
        print(f"✓ Logo proxy returned image ({len(resp.content)} bytes, {content_type})")
    
    def test_logo_delete_returns_null(self, admin_session):
        """DELETE /api/account/logo returns logo_url=null."""
        session, _ = admin_session
        
        # First upload a logo
        img_buf = create_test_png(200, 200)
        headers = dict(session.headers)
        headers.pop("Content-Type", None)
        files = {"file": ("test_logo.png", img_buf, "image/png")}
        upload_resp = requests.post(
            f"{BASE_URL}/api/account/logo",
            headers=headers,
            files=files
        )
        assert upload_resp.status_code == 200
        
        # Now delete
        del_resp = session.delete(f"{BASE_URL}/api/account/logo")
        assert del_resp.status_code == 200, f"Logo delete failed: {del_resp.text}"
        data = del_resp.json()
        assert "logo_url" in data, f"logo_url missing from delete response: {data}"
        assert data["logo_url"] is None, f"logo_url should be null after delete, got: {data['logo_url']}"
        print("✓ Logo delete returned logo_url=null")


class TestBug4b_OnboardingSteps:
    """BUG 4b: Onboarding step upload_logo uses cta_section='organisation'."""
    
    def test_onboarding_upload_logo_step_has_cta_section(self, admin_session):
        """GET /api/account/onboarding returns upload_logo step with cta_section='organisation'."""
        session, _ = admin_session
        
        resp = session.get(f"{BASE_URL}/api/account/onboarding")
        assert resp.status_code == 200, f"GET /account/onboarding failed: {resp.text}"
        data = resp.json()
        
        steps = data.get("steps", [])
        upload_logo_step = next((s for s in steps if s.get("id") == "upload_logo"), None)
        assert upload_logo_step, f"upload_logo step not found in onboarding steps: {[s.get('id') for s in steps]}"
        
        # Should have cta_section='organisation' instead of cta_route
        cta_section = upload_logo_step.get("cta_section")
        cta_route = upload_logo_step.get("cta_route")
        
        assert cta_section == "organisation", \
            f"upload_logo step should have cta_section='organisation', got cta_section={cta_section}, cta_route={cta_route}"
        print("✓ upload_logo step has cta_section='organisation'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
