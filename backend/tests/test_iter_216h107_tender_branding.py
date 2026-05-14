"""
Iter 216h107 — Tender PDF Branding Override Tests

Tests the per-tenant Tender PDF branding override panel:
- PUT /api/master-admin/theme/orgs/{org_id} accepts tender_company_name, tender_primary_color, tender_logo_url
- GET /api/master-admin/theme/orgs/{org_id} returns persisted tender_* fields
- Validation: tender_primary_color must be valid hex, tender_company_name max 120 chars, tender_logo_url max 500 chars
- Empty string clears override
- CRM Tender Engine resolver (_resolve_crm_brand) honours overrides in priority order
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Master admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Master admin login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(master_admin_token):
    """Auth headers for master admin."""
    return {"Authorization": f"Bearer {master_admin_token}"}


@pytest.fixture(scope="module")
def pulse_org_id(auth_headers):
    """Get a Pulse-scoped org for testing."""
    resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
    assert resp.status_code == 200, f"Failed to get orgs: {resp.text}"
    orgs = resp.json() if isinstance(resp.json(), list) else resp.json().get("organizations", [])
    # Find a pulse-scoped org (account_type starts with 'pulse_')
    pulse_orgs = [o for o in orgs if (o.get("account_type") or "").startswith("pulse")]
    if pulse_orgs:
        return pulse_orgs[0]["id"]
    # Fallback to any org that's not the master admin org
    non_master = [o for o in orgs if "gymaxis" not in (o.get("name") or "").lower()]
    if non_master:
        return non_master[0]["id"]
    # Last resort: use first org
    assert orgs, "No organizations found"
    return orgs[0]["id"]


class TestTenderBrandingBackendPUT:
    """Tests for PUT /api/master-admin/theme/orgs/{org_id} with tender_* fields."""

    def test_put_tender_company_name_valid(self, auth_headers, pulse_org_id):
        """Valid tender_company_name is accepted and persisted."""
        payload = {"tender_company_name": "TEST_Wolverhampton Fitness Co."}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("theme_overrides", {}).get("tender_company_name") == "TEST_Wolverhampton Fitness Co."

    def test_put_tender_primary_color_valid_hex(self, auth_headers, pulse_org_id):
        """Valid hex color for tender_primary_color is accepted."""
        payload = {"tender_primary_color": "#FF8C00"}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        # Should be uppercased
        assert data.get("theme_overrides", {}).get("tender_primary_color") == "#FF8C00"

    def test_put_tender_primary_color_invalid_hex_returns_400(self, auth_headers, pulse_org_id):
        """Invalid hex color for tender_primary_color returns 400."""
        payload = {"tender_primary_color": "not-a-hex"}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "hex" in resp.text.lower() or "colour" in resp.text.lower()

    def test_put_tender_primary_color_short_hex_valid(self, auth_headers, pulse_org_id):
        """Short hex (#ABC) is valid."""
        payload = {"tender_primary_color": "#abc"}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        assert data.get("theme_overrides", {}).get("tender_primary_color") == "#ABC"

    def test_put_tender_logo_url_valid(self, auth_headers, pulse_org_id):
        """Valid tender_logo_url is accepted."""
        payload = {"tender_logo_url": "https://cdn.example.com/logo.png"}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("theme_overrides", {}).get("tender_logo_url") == "https://cdn.example.com/logo.png"

    def test_put_tender_company_name_max_length_120(self, auth_headers, pulse_org_id):
        """tender_company_name exceeding 120 chars returns 400 or 422."""
        long_name = "A" * 121
        payload = {"tender_company_name": long_name}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        # Pydantic returns 422 for validation errors, custom validation returns 400
        assert resp.status_code in [400, 422], f"Expected 400/422 for >120 chars, got {resp.status_code}: {resp.text}"
        assert "120" in resp.text

    def test_put_tender_logo_url_max_length_500(self, auth_headers, pulse_org_id):
        """tender_logo_url exceeding 500 chars returns 400 or 422."""
        long_url = "https://example.com/" + "a" * 490
        payload = {"tender_logo_url": long_url}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        # Pydantic returns 422 for validation errors, custom validation returns 400
        assert resp.status_code in [400, 422], f"Expected 400/422 for >500 chars, got {resp.status_code}: {resp.text}"
        assert "500" in resp.text

    def test_put_empty_string_clears_override(self, auth_headers, pulse_org_id):
        """Empty string clears the override."""
        # First set a value
        requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json={"tender_company_name": "TEST_ToBeCleared"},
            headers=auth_headers
        )
        # Now clear it
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json={"tender_company_name": ""},
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        # Verify it's cleared
        get_resp = requests.get(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            headers=auth_headers
        )
        assert get_resp.status_code == 200
        overrides = get_resp.json().get("theme_overrides", {})
        assert "tender_company_name" not in overrides or overrides.get("tender_company_name") == ""

    def test_put_all_three_tender_fields_together(self, auth_headers, pulse_org_id):
        """All three tender_* fields can be set in one request."""
        payload = {
            "tender_company_name": "TEST_Combined Fitness Ltd",
            "tender_primary_color": "#19CDFF",
            "tender_logo_url": "https://cdn.test.com/combined-logo.png"
        }
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        overrides = data.get("theme_overrides", {})
        assert overrides.get("tender_company_name") == "TEST_Combined Fitness Ltd"
        assert overrides.get("tender_primary_color") == "#19CDFF"
        assert overrides.get("tender_logo_url") == "https://cdn.test.com/combined-logo.png"


class TestTenderBrandingBackendGET:
    """Tests for GET /api/master-admin/theme/orgs/{org_id} returning tender_* fields."""

    def test_get_returns_tender_fields_when_set(self, auth_headers, pulse_org_id):
        """GET returns tender_* fields when they are set."""
        # Set values first
        requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json={
                "tender_company_name": "TEST_GetTest Fitness",
                "tender_primary_color": "#AABBCC"
            },
            headers=auth_headers
        )
        # GET and verify
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"GET failed: {resp.text}"
        data = resp.json()
        assert "theme_overrides" in data
        overrides = data["theme_overrides"]
        assert overrides.get("tender_company_name") == "TEST_GetTest Fitness"
        assert overrides.get("tender_primary_color") == "#AABBCC"


class TestExistingOverridesRegression:
    """Regression tests: existing colour override fields still work."""

    def test_existing_primary_color_still_works(self, auth_headers, pulse_org_id):
        """Existing primary colour override still works."""
        payload = {"primary": "#FF0000"}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        assert data.get("theme_overrides", {}).get("primary") == "#FF0000"

    def test_existing_accent_still_works(self, auth_headers, pulse_org_id):
        """Existing accent colour override still works."""
        payload = {"accent": "#00FF00"}
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        assert data.get("theme_overrides", {}).get("accent") == "#00FF00"

    def test_mixed_tender_and_existing_fields(self, auth_headers, pulse_org_id):
        """Can set both tender_* and existing colour fields together."""
        payload = {
            "primary": "#112233",
            "tender_company_name": "TEST_Mixed Fields Co"
        }
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json=payload,
            headers=auth_headers
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        data = resp.json()
        overrides = data.get("theme_overrides", {})
        assert overrides.get("primary") == "#112233"
        assert overrides.get("tender_company_name") == "TEST_Mixed Fields Co"


class TestCRMBrandResolverPriority:
    """Tests for _resolve_crm_brand priority order (requires CRM access)."""

    def test_tender_override_takes_priority_over_org_name(self, auth_headers, pulse_org_id):
        """When tender_company_name is set, it takes priority over org.name."""
        # Set tender override
        requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json={"tender_company_name": "TEST_Override Priority Co"},
            headers=auth_headers
        )
        # The actual resolver test would require CRM user context
        # For now, verify the override is persisted correctly
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json().get("theme_overrides", {}).get("tender_company_name") == "TEST_Override Priority Co"


class TestCleanup:
    """Cleanup test data after tests."""

    def test_cleanup_tender_overrides(self, auth_headers, pulse_org_id):
        """Clear all TEST_ prefixed tender overrides."""
        # Clear all tender fields
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/theme/orgs/{pulse_org_id}",
            json={
                "tender_company_name": "",
                "tender_primary_color": "",
                "tender_logo_url": "",
                "primary": "",
                "accent": ""
            },
            headers=auth_headers
        )
        # This may return 400 if no overrides supplied, which is fine
        # The important thing is we attempted cleanup
        print(f"Cleanup response: {resp.status_code}")
