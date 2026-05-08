"""
Iteration 215 — Equipment Photo Upload & QR Code Bug Fixes Testing

Tests for P0 bugs:
- BUG 6: Equipment photo upload returns absolute HTTPS photo_url
- BUG 7: QR code scan URL is absolute, public equipment endpoint returns absolute photo_url
- CRM compile verification (duplicate-email detection)
"""

import pytest
import requests
import os
import io
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "test-bypass-secret-for-ci-runs-only-2026")

# Test credentials
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
CRM_MANAGER_EMAIL = "craig.henshall@pulsefitness.com"
CRM_MANAGER_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def operator_token():
    """Get auth token for operator user"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
        headers={"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def crm_token():
    """Get auth token for CRM manager"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CRM_MANAGER_EMAIL, "password": CRM_MANAGER_PASSWORD},
        headers={"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    )
    assert resp.status_code == 200, f"CRM login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def equipment_with_photo(operator_token):
    """Get or create equipment with a photo for testing"""
    headers = {"Authorization": f"Bearer {operator_token}"}

    # Get existing equipment
    resp = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
    assert resp.status_code == 200
    equipment_list = resp.json().get("equipment", [])

    # Find equipment with photo_url
    for eq in equipment_list:
        if eq.get("photo_url"):
            return eq

    # If no equipment with photo, create one and upload photo
    if equipment_list:
        eq = equipment_list[0]
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Upload photo
        files = {"file": ("test.png", img_bytes, "image/png")}
        resp = requests.post(
            f"{BASE_URL}/api/equipment/{eq['id']}/photo",
            headers=headers,
            files=files
        )
        if resp.status_code == 200:
            # Refresh equipment data
            resp = requests.get(f"{BASE_URL}/api/equipment/{eq['id']}", headers=headers)
            return resp.json()

    pytest.skip("No equipment available for testing")


class TestBug6PhotoUpload:
    """BUG 6 — Equipment photo upload returns absolute HTTPS photo_url"""

    def test_photo_url_is_absolute_https(self, equipment_with_photo):
        """Verify photo_url starts with HTTPS base URL"""
        photo_url = equipment_with_photo.get("photo_url")
        assert photo_url is not None, "Equipment should have photo_url"
        assert photo_url.startswith("https://"), f"photo_url should be absolute HTTPS, got: {photo_url}"
        assert BASE_URL.replace("https://", "") in photo_url, "photo_url should contain base URL"
        assert "/api/public/equipment/" in photo_url, "photo_url should use public endpoint"

    def test_photo_url_is_fetchable_without_auth(self, equipment_with_photo):
        """Verify photo_url can be fetched without authentication"""
        photo_url = equipment_with_photo.get("photo_url")
        assert photo_url is not None

        # Fetch without auth
        resp = requests.get(photo_url)
        assert resp.status_code == 200, f"Photo should be fetchable without auth, got {resp.status_code}"

    def test_photo_returns_image_content_type(self, equipment_with_photo):
        """Verify photo endpoint returns image/* content-type"""
        photo_url = equipment_with_photo.get("photo_url")
        assert photo_url is not None

        resp = requests.get(photo_url)
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert content_type.startswith("image/"), f"Expected image/* content-type, got: {content_type}"

    def test_upload_photo_returns_absolute_url(self, operator_token):
        """Verify POST /api/equipment/{id}/photo returns absolute photo_url"""
        headers = {"Authorization": f"Bearer {operator_token}"}

        # Get equipment
        resp = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
        assert resp.status_code == 200
        equipment_list = resp.json().get("equipment", [])
        if not equipment_list:
            pytest.skip("No equipment available")

        eq_id = equipment_list[0]["id"]

        # Create test image
        img = Image.new('RGB', (50, 50), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Upload photo
        files = {"file": ("test_upload.png", img_bytes, "image/png")}
        resp = requests.post(
            f"{BASE_URL}/api/equipment/{eq_id}/photo",
            headers=headers,
            files=files
        )
        assert resp.status_code == 200, f"Photo upload failed: {resp.text}"

        data = resp.json()
        photo_url = data.get("photo_url")
        assert photo_url is not None, "Response should contain photo_url"
        assert photo_url.startswith("https://"), f"Returned photo_url should be absolute HTTPS: {photo_url}"


class TestBug7QRCodeAndPublicEndpoints:
    """BUG 7 — QR code scan URL and public equipment endpoint fixes"""

    def test_qr_label_returns_absolute_scan_url(self, operator_token, equipment_with_photo):
        """Verify GET /api/equipment/{id}/qr-label returns absolute scan_url"""
        headers = {"Authorization": f"Bearer {operator_token}"}
        eq_id = equipment_with_photo["id"]

        resp = requests.get(f"{BASE_URL}/api/equipment/{eq_id}/qr-label", headers=headers)
        assert resp.status_code == 200, f"QR label endpoint failed: {resp.text}"

        data = resp.json()
        scan_url = data.get("scan_url")
        assert scan_url is not None, "Response should contain scan_url"
        assert scan_url.startswith("https://"), f"scan_url should be absolute HTTPS: {scan_url}"
        assert "/scan/" in scan_url, "scan_url should contain /scan/ path"
        assert eq_id in scan_url, "scan_url should contain equipment ID"

    def test_qr_code_returns_png(self, operator_token, equipment_with_photo):
        """Verify GET /api/equipment/{id}/qr-code returns PNG image"""
        headers = {"Authorization": f"Bearer {operator_token}"}
        eq_id = equipment_with_photo["id"]

        resp = requests.get(f"{BASE_URL}/api/equipment/{eq_id}/qr-code", headers=headers)
        assert resp.status_code == 200, f"QR code endpoint failed: {resp.text}"

        content_type = resp.headers.get("content-type", "")
        assert "image/png" in content_type, f"Expected image/png, got: {content_type}"

        # Verify it's a valid PNG (starts with PNG signature)
        assert resp.content[:8] == b'\x89PNG\r\n\x1a\n', "Response should be valid PNG"

    def test_public_equipment_returns_absolute_photo_url(self, equipment_with_photo):
        """Verify GET /api/public/equipment/{id} returns absolute photo_url"""
        eq_id = equipment_with_photo["id"]

        # No auth required for public endpoint
        resp = requests.get(f"{BASE_URL}/api/public/equipment/{eq_id}")
        assert resp.status_code == 200, f"Public equipment endpoint failed: {resp.text}"

        data = resp.json()
        photo_url = data.get("photo_url")
        if photo_url:  # Only check if photo exists
            assert photo_url.startswith("https://"), f"photo_url should be absolute HTTPS: {photo_url}"
            assert "/api/public/equipment/" in photo_url, "photo_url should use public endpoint"

    def test_public_photo_endpoint_serves_image(self, equipment_with_photo):
        """Verify GET /api/public/equipment/{id}/photo serves image without auth"""
        eq_id = equipment_with_photo["id"]

        resp = requests.get(f"{BASE_URL}/api/public/equipment/{eq_id}/photo")
        assert resp.status_code == 200, f"Public photo endpoint failed: {resp.status_code}"

        content_type = resp.headers.get("content-type", "")
        assert content_type.startswith("image/"), f"Expected image/* content-type, got: {content_type}"


class TestCRMCompileVerification:
    """CRM compile verification — ContactsList and duplicate-email detection

    Note: CRM uses a separate auth system (/crm/auth/login).
    The compile verification is done via Playwright frontend tests.
    These API tests verify the CRM cross-login endpoint works.
    """

    def test_crm_cross_login_endpoint_exists(self, operator_token):
        """Verify CRM cross-login endpoint is accessible"""
        headers = {"Authorization": f"Bearer {operator_token}"}

        # Cross-login should work for users with CRM access
        resp = requests.post(f"{BASE_URL}/api/crm/auth/cross-login", headers=headers)
        # Either 200 (success) or 403 (no CRM access) - both indicate endpoint works
        assert resp.status_code in [200, 403], f"CRM cross-login endpoint failed: {resp.text}"

    def test_crm_plans_endpoint(self):
        """Verify CRM plans endpoint is accessible (public)"""
        resp = requests.get(f"{BASE_URL}/api/crm/auth/plans")
        assert resp.status_code == 200, f"CRM plans endpoint failed: {resp.text}"

        data = resp.json()
        assert "plans" in data, "Response should contain plans"


class TestGalleryPhotoUpload:
    """BUG 6 (gallery) — POST /api/equipment/{id}/photos returns absolute URL"""

    def test_gallery_photo_upload_returns_absolute_url(self, operator_token):
        """Verify gallery photo upload returns absolute URL"""
        headers = {"Authorization": f"Bearer {operator_token}"}

        # Get equipment
        resp = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
        assert resp.status_code == 200
        equipment_list = resp.json().get("equipment", [])
        if not equipment_list:
            pytest.skip("No equipment available")

        eq_id = equipment_list[0]["id"]

        # Create test image
        img = Image.new('RGB', (50, 50), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Upload gallery photo
        files = {"file": ("gallery_test.png", img_bytes, "image/png")}
        resp = requests.post(
            f"{BASE_URL}/api/equipment/{eq_id}/photos",
            headers=headers,
            files=files
        )

        # Gallery upload requires manager/owner role
        if resp.status_code == 403:
            pytest.skip("User doesn't have permission for gallery upload")

        assert resp.status_code == 200, f"Gallery photo upload failed: {resp.text}"

        data = resp.json()
        photo = data.get("photo", {})
        url = photo.get("url")
        assert url is not None, "Response should contain photo.url"
        assert url.startswith("https://"), f"Gallery photo URL should be absolute HTTPS: {url}"


class TestBackwardCompatibility:
    """BACKWARD COMPAT — legacy equipment records with storage key photo_url"""

    def test_public_photo_endpoint_handles_legacy_records(self, operator_token):
        """Verify public photo endpoint can serve photos from legacy records"""
        headers = {"Authorization": f"Bearer {operator_token}"}

        # Get equipment list
        resp = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
        assert resp.status_code == 200
        equipment_list = resp.json().get("equipment", [])

        # Test each equipment's public photo endpoint
        for eq in equipment_list:
            if eq.get("photo_url") or eq.get("photo_path"):
                eq_id = eq["id"]
                resp = requests.get(f"{BASE_URL}/api/public/equipment/{eq_id}/photo")
                # Should return 200 with image or 404 if no photo
                assert resp.status_code in [200, 404], f"Unexpected status for {eq_id}: {resp.status_code}"
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    assert content_type.startswith("image/"), f"Expected image content-type for {eq_id}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
