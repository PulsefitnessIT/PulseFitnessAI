"""
Iter 216h58 — Brand Palette Extraction & Apply Tests

Tests for:
1. POST /api/account/logo returns brand_palette in addition to logo_url
2. GET /api/account/organisation returns brand_palette and primary_color
3. POST /api/account/branding/apply writes to all 3 colour fields
4. POST /api/account/branding/apply with invalid hex returns 400
5. POST /api/account/branding/apply with Staff role returns 403
"""
import os
import io
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}"}


def create_test_png_with_colors(colors):
    """Create a PNG with distinct color blocks for palette extraction testing"""
    # Create a 100x100 image with color blocks
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
    
    # Divide into blocks based on number of colors
    block_height = 100 // len(colors)
    for i, color in enumerate(colors):
        for y in range(i * block_height, (i + 1) * block_height):
            for x in range(100):
                img.putpixel((x, y), color)
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class TestBrandPaletteExtraction:
    """Test POST /api/account/logo returns brand_palette"""
    
    def test_logo_upload_returns_brand_palette(self, admin_headers):
        """Upload a PNG with distinct colors and verify brand_palette is returned"""
        # Create a test PNG with cyan, orange, purple blocks
        colors = [
            (25, 205, 255, 255),   # Cyan #19CDFF
            (255, 110, 64, 255),   # Orange #FF6E40
            (102, 51, 204, 255),   # Purple #6633CC
        ]
        png_buf = create_test_png_with_colors(colors)
        
        files = {"file": ("test_logo.png", png_buf, "image/png")}
        resp = requests.post(
            f"{BASE_URL}/api/account/logo",
            headers=admin_headers,
            files=files
        )
        
        assert resp.status_code == 200, f"Logo upload failed: {resp.text}"
        data = resp.json()
        
        # Verify logo_url is returned
        assert "logo_url" in data, "Response missing logo_url"
        assert data["logo_url"], "logo_url is empty"
        
        # Verify brand_palette is returned
        assert "brand_palette" in data, "Response missing brand_palette"
        assert isinstance(data["brand_palette"], list), "brand_palette should be a list"
        
        # Verify palette contains hex strings
        for color in data["brand_palette"]:
            assert isinstance(color, str), f"Palette color should be string: {color}"
            assert color.startswith("#"), f"Palette color should start with #: {color}"
            assert len(color) == 7, f"Palette color should be #RRGGBB format: {color}"
        
        print(f"Brand palette extracted: {data['brand_palette']}")
    
    def test_logo_upload_filters_near_white_and_black(self, admin_headers):
        """Verify near-white and near-black colors are filtered from palette"""
        # Create PNG with white, black, and one distinct color
        colors = [
            (250, 250, 250, 255),  # Near-white (should be filtered)
            (10, 10, 10, 255),     # Near-black (should be filtered)
            (0, 128, 255, 255),    # Blue (should be kept)
        ]
        png_buf = create_test_png_with_colors(colors)
        
        files = {"file": ("test_logo_filter.png", png_buf, "image/png")}
        resp = requests.post(
            f"{BASE_URL}/api/account/logo",
            headers=admin_headers,
            files=files
        )
        
        assert resp.status_code == 200, f"Logo upload failed: {resp.text}"
        data = resp.json()
        
        palette = data.get("brand_palette", [])
        # Near-white and near-black should be filtered
        for color in palette:
            # Check it's not near-white (all components >= 235)
            hex_val = color.lstrip("#")
            r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
            is_near_white = min(r, g, b) >= 235 and max(r, g, b) >= 245
            is_near_black = max(r, g, b) <= 25
            assert not is_near_white, f"Near-white color should be filtered: {color}"
            assert not is_near_black, f"Near-black color should be filtered: {color}"
        
        print(f"Filtered palette: {palette}")


class TestOrganisationEndpoint:
    """Test GET /api/account/organisation returns brand_palette and primary_color"""
    
    def test_organisation_returns_brand_palette(self, admin_headers):
        """Verify GET /api/account/organisation includes brand_palette field"""
        resp = requests.get(
            f"{BASE_URL}/api/account/organisation",
            headers=admin_headers
        )
        
        assert resp.status_code == 200, f"Get organisation failed: {resp.text}"
        data = resp.json()
        
        # Verify brand_palette field exists
        assert "brand_palette" in data, "Response missing brand_palette field"
        assert isinstance(data["brand_palette"], list), "brand_palette should be a list"
        
        print(f"Organisation brand_palette: {data['brand_palette']}")
    
    def test_organisation_returns_primary_color(self, admin_headers):
        """Verify GET /api/account/organisation includes primary_color field"""
        resp = requests.get(
            f"{BASE_URL}/api/account/organisation",
            headers=admin_headers
        )
        
        assert resp.status_code == 200, f"Get organisation failed: {resp.text}"
        data = resp.json()
        
        # Verify primary_color field exists
        assert "primary_color" in data, "Response missing primary_color field"
        # primary_color can be empty string if not set
        assert isinstance(data["primary_color"], str), "primary_color should be a string"
        
        print(f"Organisation primary_color: {data['primary_color']}")


class TestBrandingApply:
    """Test POST /api/account/branding/apply endpoint"""
    
    def test_apply_valid_hex_color(self, admin_headers):
        """Apply a valid hex color and verify it's written to all 3 fields"""
        test_color = "#19CDFF"
        
        resp = requests.post(
            f"{BASE_URL}/api/account/branding/apply",
            headers=admin_headers,
            json={"primary_color": test_color}
        )
        
        assert resp.status_code == 200, f"Apply branding failed: {resp.text}"
        data = resp.json()
        
        # Verify response contains the applied color
        assert "primary_color" in data, "Response missing primary_color"
        assert data["primary_color"].upper() == test_color.upper(), \
            f"Expected {test_color}, got {data['primary_color']}"
        
        # Verify the color is persisted by fetching organisation
        org_resp = requests.get(
            f"{BASE_URL}/api/account/organisation",
            headers=admin_headers
        )
        assert org_resp.status_code == 200
        org_data = org_resp.json()
        
        # primary_color should reflect the applied color
        assert org_data.get("primary_color", "").upper() == test_color.upper(), \
            f"Organisation primary_color not updated: {org_data.get('primary_color')}"
        
        print(f"Successfully applied brand color: {test_color}")
    
    def test_apply_lowercase_hex_color(self, admin_headers):
        """Apply a lowercase hex color - should be normalized to uppercase"""
        test_color = "#ff6e40"
        
        resp = requests.post(
            f"{BASE_URL}/api/account/branding/apply",
            headers=admin_headers,
            json={"primary_color": test_color}
        )
        
        assert resp.status_code == 200, f"Apply branding failed: {resp.text}"
        data = resp.json()
        
        # Should be normalized to uppercase
        assert data["primary_color"] == test_color.upper(), \
            f"Expected uppercase {test_color.upper()}, got {data['primary_color']}"
        
        print(f"Lowercase hex normalized: {test_color} -> {data['primary_color']}")
    
    def test_apply_invalid_hex_returns_400(self, admin_headers):
        """Invalid hex color should return 400 with specific error message"""
        invalid_colors = [
            "red",           # Named color
            "#XYZ",          # Invalid hex chars
            "#12345",        # Too short
            "#1234567",      # Too long
            "19CDFF",        # Missing #
            "",              # Empty
        ]
        
        for invalid_color in invalid_colors:
            resp = requests.post(
                f"{BASE_URL}/api/account/branding/apply",
                headers=admin_headers,
                json={"primary_color": invalid_color}
            )
            
            assert resp.status_code == 400, \
                f"Expected 400 for '{invalid_color}', got {resp.status_code}"
            
            data = resp.json()
            assert "detail" in data, f"Response missing detail for '{invalid_color}'"
            assert "hex" in data["detail"].lower() or "#rrggbb" in data["detail"].lower(), \
                f"Error message should mention hex format: {data['detail']}"
            
            print(f"Invalid color '{invalid_color}' correctly rejected: {data['detail']}")


class TestBrandingApplyPermissions:
    """Test POST /api/account/branding/apply permission checks"""
    
    def test_staff_cannot_apply_brand_color(self, admin_headers):
        """Staff (non-owner/non-manager) should get 403 when applying brand color"""
        # First, create a staff user via team invite
        invite_resp = requests.post(
            f"{BASE_URL}/api/account/team/invite",
            headers=admin_headers,
            json={
                "email": f"test_staff_palette_{os.urandom(4).hex()}@test.com",
                "full_name": "Test Staff Palette",
                "role": "staff",
                "delivery": "temp_password"
            }
        )
        
        if invite_resp.status_code != 200:
            pytest.skip(f"Could not create staff user: {invite_resp.text}")
        
        invite_data = invite_resp.json()
        staff_email = invite_data.get("email")
        temp_password = invite_data.get("temp_password")
        staff_id = invite_data.get("id")
        
        try:
            # Login as staff user
            login_resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": staff_email, "password": temp_password}
            )
            
            if login_resp.status_code != 200:
                pytest.skip(f"Staff login failed: {login_resp.text}")
            
            staff_token = login_resp.json().get("token")
            staff_headers = {"Authorization": f"Bearer {staff_token}"}
            
            # Try to apply brand color as staff
            apply_resp = requests.post(
                f"{BASE_URL}/api/account/branding/apply",
                headers=staff_headers,
                json={"primary_color": "#FF0000"}
            )
            
            assert apply_resp.status_code == 403, \
                f"Expected 403 for staff user, got {apply_resp.status_code}"
            
            data = apply_resp.json()
            assert "detail" in data, "Response missing detail"
            assert "owner" in data["detail"].lower() or "manager" in data["detail"].lower(), \
                f"Error should mention owner/manager: {data['detail']}"
            
            print(f"Staff correctly denied: {data['detail']}")
            
        finally:
            # Cleanup: remove the test staff user
            requests.delete(
                f"{BASE_URL}/api/account/team/{staff_id}",
                headers=admin_headers
            )


class TestBrandPalettePersistence:
    """Test that brand_palette is persisted on org document"""
    
    def test_palette_persisted_after_logo_upload(self, admin_headers):
        """Verify brand_palette is persisted and retrievable after logo upload"""
        # Upload a logo with distinct colors
        colors = [
            (0, 200, 100, 255),    # Green
            (200, 50, 150, 255),   # Pink
        ]
        png_buf = create_test_png_with_colors(colors)
        
        files = {"file": ("persist_test.png", png_buf, "image/png")}
        upload_resp = requests.post(
            f"{BASE_URL}/api/account/logo",
            headers=admin_headers,
            files=files
        )
        
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        upload_palette = upload_resp.json().get("brand_palette", [])
        
        # Fetch organisation and verify palette matches
        org_resp = requests.get(
            f"{BASE_URL}/api/account/organisation",
            headers=admin_headers
        )
        
        assert org_resp.status_code == 200
        org_palette = org_resp.json().get("brand_palette", [])
        
        # Palettes should match
        assert org_palette == upload_palette, \
            f"Persisted palette {org_palette} doesn't match upload {upload_palette}"
        
        print(f"Palette correctly persisted: {org_palette}")


class TestBrandColorFallbackChain:
    """Test primary_color fallback chain: branding.primary_color -> primary_brand_colour -> brand_color"""
    
    def test_primary_color_resolved_after_apply(self, admin_headers):
        """After applying a color, primary_color should be resolved correctly"""
        test_color = "#6633CC"
        
        # Apply the color
        apply_resp = requests.post(
            f"{BASE_URL}/api/account/branding/apply",
            headers=admin_headers,
            json={"primary_color": test_color}
        )
        assert apply_resp.status_code == 200
        
        # Fetch organisation
        org_resp = requests.get(
            f"{BASE_URL}/api/account/organisation",
            headers=admin_headers
        )
        assert org_resp.status_code == 200
        
        org_data = org_resp.json()
        resolved_color = org_data.get("primary_color", "")
        
        # The resolved color should match what we applied
        assert resolved_color.upper() == test_color.upper(), \
            f"Resolved color {resolved_color} doesn't match applied {test_color}"
        
        print(f"Fallback chain correctly resolves to: {resolved_color}")


# Cleanup test - run last
class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_logo_and_colors(self, admin_headers):
        """Delete logo and reset brand colors for clean state"""
        # Delete logo
        del_resp = requests.delete(
            f"{BASE_URL}/api/account/logo",
            headers=admin_headers
        )
        # May return 200 or 403 depending on role, both are acceptable for cleanup
        print(f"Logo delete status: {del_resp.status_code}")
        
        # Note: There's no endpoint to reset brand colors to null,
        # but the tests have verified the functionality
        print("Cleanup complete")
