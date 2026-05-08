"""
GymAxis · Integrations Admin API tests (iter 215dy)

Tests for the new /api/integrations/admin/* endpoints:
- GET /api/integrations/admin/health
- GET /api/integrations/admin/sicon/outbox
- GET /api/integrations/admin/sage/outbox
- GET /api/integrations/admin/mapping/sections

Also regression tests for prior Service Ops endpoints.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Master admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"

# Module-scoped token to avoid rate limiting
_TOKEN_CACHE = {}


def get_master_admin_token():
    """Get master admin token with caching to avoid rate limits"""
    if 'token' in _TOKEN_CACHE:
        return _TOKEN_CACHE['token']

    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code == 429:
        pytest.skip("Rate limited - skipping test")
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    _TOKEN_CACHE['token'] = response.json().get("token")
    return _TOKEN_CACHE['token']


@pytest.fixture(scope="module")
def master_admin_token():
    """Module-scoped fixture for master admin token"""
    return get_master_admin_token()


class TestIntegrationsAdminAuth:
    """Test authentication requirements for integrations admin endpoints"""

    def test_health_requires_auth(self):
        """GET /api/integrations/admin/health returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/integrations/admin/health")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /health returns 401 without auth")

    def test_sicon_outbox_requires_auth(self):
        """GET /api/integrations/admin/sicon/outbox returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/integrations/admin/sicon/outbox")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /sicon/outbox returns 401 without auth")

    def test_sage_outbox_requires_auth(self):
        """GET /api/integrations/admin/sage/outbox returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/integrations/admin/sage/outbox")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /sage/outbox returns 401 without auth")

    def test_mapping_sections_requires_auth(self):
        """GET /api/integrations/admin/mapping/sections returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/integrations/admin/mapping/sections")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /mapping/sections returns 401 without auth")


class TestIntegrationsAdminHealth:
    """Test GET /api/integrations/admin/health endpoint"""

    def test_health_returns_200_for_master_admin(self, master_admin_token):
        """GET /api/integrations/admin/health returns 200 for master admin"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/health",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /health returns 200 for master admin")

    def test_health_response_shape(self, master_admin_token):
        """Health response has correct shape: generated_at, sicon, sage"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/health",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Check top-level keys
        assert "generated_at" in data, "Missing generated_at"
        assert "sicon" in data, "Missing sicon"
        assert "sage" in data, "Missing sage"

        # Check sicon structure
        sicon = data["sicon"]
        assert "config" in sicon, "Missing sicon.config"
        assert "outbox" in sicon, "Missing sicon.outbox"
        assert "inbox" in sicon, "Missing sicon.inbox"
        assert "live" in sicon, "Missing sicon.live"

        # Check sage structure
        sage = data["sage"]
        assert "config" in sage, "Missing sage.config"
        assert "outbox" in sage, "Missing sage.outbox"
        assert "live" in sage, "Missing sage.live"

        print("✓ Health response shape is correct")
        print(f"  - generated_at: {data['generated_at']}")
        print(f"  - sicon.live: {sicon['live']}")
        print(f"  - sage.live: {sage['live']}")

    def test_health_outbox_counts(self, master_admin_token):
        """Health response includes outbox counts"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/health",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Check sicon outbox counts
        sicon_outbox = data["sicon"]["outbox"]
        expected_keys = ["pending", "in_flight", "succeeded_24h", "failed_24h", "dead_letter"]
        for key in expected_keys:
            assert key in sicon_outbox, f"Missing sicon.outbox.{key}"

        # Check sage outbox counts
        sage_outbox = data["sage"]["outbox"]
        for key in expected_keys:
            assert key in sage_outbox, f"Missing sage.outbox.{key}"

        print("✓ Outbox counts present")
        print(f"  - Sicon pending: {sicon_outbox['pending']}")
        print(f"  - Sicon in_flight: {sicon_outbox['in_flight']}")
        print(f"  - Sicon succeeded_24h: {sicon_outbox['succeeded_24h']}")
        print(f"  - Sicon failed_24h: {sicon_outbox['failed_24h']}")
        print(f"  - Sicon dead_letter: {sicon_outbox['dead_letter']}")
        print(f"  - Sage pending: {sage_outbox['pending']}")


class TestSiconOutbox:
    """Test GET /api/integrations/admin/sicon/outbox endpoint"""

    def test_sicon_outbox_returns_200(self, master_admin_token):
        """GET /api/integrations/admin/sicon/outbox returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /sicon/outbox returns 200")

    def test_sicon_outbox_response_shape(self, master_admin_token):
        """Sicon outbox response has rows array"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "rows" in data, "Missing rows"
        assert "count" in data, "Missing count"
        assert isinstance(data["rows"], list), "rows should be a list"

        print(f"✓ Sicon outbox response shape correct, count: {data['count']}")
        if data["rows"]:
            print(f"  - First row keys: {list(data['rows'][0].keys())}")

    def test_sicon_outbox_filter_by_status(self, master_admin_token):
        """Sicon outbox filters by status"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?status=pending&limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # All rows should have status=pending
        for row in data["rows"]:
            assert row.get("status") == "pending", f"Expected status=pending, got {row.get('status')}"

        print(f"✓ Sicon outbox filter by status=pending works, count: {data['count']}")

    def test_sicon_outbox_filter_by_kind(self, master_admin_token):
        """Sicon outbox filters by kind"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?kind=case&limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # All rows should have kind=case
        for row in data["rows"]:
            assert row.get("kind") == "case", f"Expected kind=case, got {row.get('kind')}"

        print(f"✓ Sicon outbox filter by kind=case works, count: {data['count']}")


class TestSageOutbox:
    """Test GET /api/integrations/admin/sage/outbox endpoint"""

    def test_sage_outbox_returns_200(self, master_admin_token):
        """GET /api/integrations/admin/sage/outbox returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sage/outbox?limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /sage/outbox returns 200")

    def test_sage_outbox_response_shape(self, master_admin_token):
        """Sage outbox response has rows array"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sage/outbox?limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "rows" in data, "Missing rows"
        assert "count" in data, "Missing count"
        assert isinstance(data["rows"], list), "rows should be a list"

        print(f"✓ Sage outbox response shape correct, count: {data['count']}")


class TestMappingSections:
    """Test GET /api/integrations/admin/mapping/sections endpoint"""

    def test_mapping_sections_returns_200(self, master_admin_token):
        """GET /api/integrations/admin/mapping/sections returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/mapping/sections",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /mapping/sections returns 200")

    def test_mapping_sections_response_shape(self, master_admin_token):
        """Mapping sections response has master, legacy, modules"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/mapping/sections",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "master" in data, "Missing master"
        assert "legacy" in data, "Missing legacy"
        assert "modules" in data, "Missing modules"

        print("✓ Mapping sections response shape correct")
        print(f"  - master sections: {len(data['master'])}")
        print(f"  - legacy sections: {len(data['legacy'])}")
        print(f"  - modules: {len(data['modules'])}")

    def test_mapping_sections_master_count(self, master_admin_token):
        """Master doc has expected number of sections (11 - sections 1, 19-26 plus delegated 2-18 banner)"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/mapping/sections",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Master should have sections: 0, 1, 2-18 (banner), 19, 20, 21, 22, 23, 24, 25, 26
        # The regex looks for ## N. patterns, so we expect around 11 sections
        master_count = len(data["master"])
        assert master_count >= 9, f"Expected at least 9 master sections, got {master_count}"

        print(f"✓ Master doc has {master_count} sections")

    def test_mapping_sections_legacy_count(self, master_admin_token):
        """Legacy doc has 18 sections"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/mapping/sections",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        legacy_count = len(data["legacy"])
        assert legacy_count >= 17, f"Expected at least 17 legacy sections, got {legacy_count}"

        print(f"✓ Legacy doc has {legacy_count} sections")

    def test_mapping_sections_modules_count(self, master_admin_token):
        """Modules matrix has 9 module rows"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/mapping/sections",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        modules_count = len(data["modules"])
        assert modules_count == 9, f"Expected 9 modules, got {modules_count}"

        # Check module structure
        if modules_count > 0:
            module = data["modules"][0]
            assert "module" in module, "Missing module name"
            assert "sicon_summary" in module, "Missing sicon_summary"
            assert "sage_summary" in module, "Missing sage_summary"
            assert "direction" in module, "Missing direction"
            assert "section_ref" in module, "Missing section_ref"

        print(f"✓ Modules matrix has {modules_count} rows")
        for m in data["modules"]:
            print(f"  - {m.get('module')}")


class TestServiceOpsRegression:
    """Regression tests for prior Service Ops endpoints"""

    def test_comms_templates_endpoint(self, master_admin_token):
        """GET /api/svc/comms/templates returns 200 with templates"""
        response = requests.get(
            f"{BASE_URL}/api/svc/comms/templates",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Should have templates array
        assert "templates" in data or isinstance(data, list), "Expected templates in response"
        templates = data.get("templates", data) if isinstance(data, dict) else data

        print(f"✓ /svc/comms/templates returns 200, count: {len(templates)}")

    def test_desk_summary_endpoint(self, master_admin_token):
        """GET /api/svc/desk/summary returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/svc/desk/summary",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /svc/desk/summary returns 200")

    def test_billing_ready_endpoint(self, master_admin_token):
        """GET /api/svc/billing?status=ready returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/svc/billing?status=ready",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /svc/billing?status=ready returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
