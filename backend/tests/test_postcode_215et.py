"""
Iter 215et — Postcode API Tests

Tests for the PUBLIC postcode lookup and autocomplete endpoints.
These endpoints are now unauthenticated (postcodes.io is open public ONS data).
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestPostcodeEndpointsPublic:
    """Test that postcode endpoints are PUBLIC (no auth required)"""

    def test_postcode_lookup_valid_no_auth(self):
        """GET /api/integrations/postcode/lookup?postcode=BR8+7RE — PUBLIC, returns full data"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/postcode/lookup",
            params={"postcode": "BR8 7RE"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("found") is True
        assert data.get("postcode") == "BR8 7RE"
        assert data.get("city") == "Sevenoaks"
        assert data.get("county") == "Kent"
        assert data.get("country") == "England"
        assert data.get("region") == "South East"
        assert "latitude" in data
        assert "longitude" in data
        assert "parliamentary_constituency" in data
        assert "ccg" in data
        assert "nhs_region" in data

    def test_postcode_lookup_invalid_no_auth(self):
        """GET /api/integrations/postcode/lookup?postcode=ZZ99+ZZZ — PUBLIC, returns found=false"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/postcode/lookup",
            params={"postcode": "ZZ99 ZZZ"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("found") is False
        assert data.get("postcode") == "ZZ99 ZZZ"

    def test_postcode_autocomplete_no_auth(self):
        """GET /api/integrations/postcode/autocomplete?q=N15&limit=5 — PUBLIC, returns suggestions"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/postcode/autocomplete",
            params={"q": "N15", "limit": 5}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) <= 5
        assert data.get("query") == "N15"
        # All suggestions should start with N15
        for suggestion in data["suggestions"]:
            assert suggestion.startswith("N15"), f"Suggestion {suggestion} doesn't start with N15"

    def test_postcode_lookup_another_valid(self):
        """Test another valid postcode to ensure consistency"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/postcode/lookup",
            params={"postcode": "SW1A 1AA"}  # Buckingham Palace
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("found") is True
        assert "city" in data
        assert "country" in data

    def test_postcode_lookup_with_lowercase(self):
        """Test that lowercase postcodes work"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/postcode/lookup",
            params={"postcode": "br8 7re"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("found") is True

    def test_postcode_autocomplete_limit(self):
        """Test autocomplete respects limit parameter"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/postcode/autocomplete",
            params={"q": "SW1", "limit": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) <= 3


class TestCRMCrossLogin:
    """Test CRM cross-login for authenticated CRM tests"""

    @pytest.fixture
    def master_admin_token(self):
        """Get master admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"}
        )
        if response.status_code != 200:
            pytest.skip("Master admin login failed")
        return response.json().get("token")

    @pytest.fixture
    def crm_token(self, master_admin_token):
        """Get CRM token via cross-login"""
        response = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        if response.status_code != 200:
            pytest.skip("CRM cross-login failed")
        return response.json().get("token")

    def test_crm_cross_login_works(self, master_admin_token):
        """Verify CRM cross-login endpoint works"""
        response = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data


class TestCompaniesHouseStatus:
    """Test Companies House integration status"""

    @pytest.fixture
    def master_admin_token(self):
        """Get master admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"}
        )
        if response.status_code != 200:
            pytest.skip("Master admin login failed")
        return response.json().get("token")

    def test_companies_house_status(self, master_admin_token):
        """Check Companies House integration is enabled"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/companies-house/status",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("enabled") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
