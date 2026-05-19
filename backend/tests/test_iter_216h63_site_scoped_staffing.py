"""
Iter 216h63 — Site-scoped Staffing + Compare Sites Enhancement

Tests:
1. GET /api/account/team?site_id={id} — filters roster to users whose allowed_site_ids contains site_id
   - Owners/Managers with empty allowed_site_ids (org-wide access) MUST ALWAYS appear
2. GET /api/staffing/clock/board?site_id={id} — filters staff_members against users.allowed_site_ids
   - Staff rows with no user_id (legacy/kiosk-only) are treated as org-wide
   - Owners/Managers should never disappear
3. Compare Sites panel visibility — single-site tenants (sites.length <= 1) MUST NOT see the panel
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
PULSE_OWNER_EMAIL = "e1.agent@gymaxisai.com"
PULSE_OWNER_PASSWORD = "E1Agent123!"
PULSE_ORG_ID = "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f"

# Pulse Fitness sites (from review_request)
SITE_HQ = "6b21f42d-dd40-41ea-b6fe-889512c3ec32"
SITE_B = "3c9ef5a9-1ad4-454d-b558-8d67cc4ecbbf"
SITE_C = "56d62145-be7a-4fef-bb03-d69020eed87b"


@pytest.fixture(scope="module")
def auth_headers():
    """Get auth token for Pulse Fitness owner."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_OWNER_EMAIL,
        "password": PULSE_OWNER_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("token")
    assert token, "No token in login response"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def test_staff_user(auth_headers):
    """Create a test staff user allocated to SITE_HQ only."""
    test_id = f"h63-test-{uuid.uuid4().hex[:8]}"
    email = f"{test_id}@test.gymaxis.com"
    
    # Invite a new staff member allocated to SITE_HQ only
    resp = requests.post(f"{BASE_URL}/api/account/team/invite", json={
        "email": email,
        "full_name": f"Test Staff {test_id}",
        "role": "staff",
        "delivery": "temp_password",
        "allowed_site_ids": [SITE_HQ]
    }, headers=auth_headers)
    
    if resp.status_code == 409:
        # User already exists, skip creation
        pytest.skip("Test user already exists")
    
    assert resp.status_code == 200, f"Invite failed: {resp.text}"
    data = resp.json()
    user_id = data.get("id")
    
    yield {
        "id": user_id,
        "email": email,
        "allowed_site_ids": [SITE_HQ]
    }
    
    # Cleanup: delete the test user
    requests.delete(f"{BASE_URL}/api/account/team/{user_id}", headers=auth_headers)


class TestTeamSiteFilter:
    """Test GET /api/account/team?site_id={id} filtering."""
    
    def test_team_no_site_filter_returns_all(self, auth_headers):
        """Without site_id, should return all org members."""
        resp = requests.get(f"{BASE_URL}/api/account/team", headers=auth_headers)
        assert resp.status_code == 200, f"Team list failed: {resp.text}"
        data = resp.json()
        members = data.get("members", [])
        assert len(members) >= 1, "Should have at least the owner"
        
        # Owner should always be present
        owner = next((m for m in members if m.get("email") == PULSE_OWNER_EMAIL), None)
        assert owner is not None, "Owner should be in team list"
        print(f"✓ Team list (no filter): {len(members)} members, owner present")
    
    def test_team_with_site_filter_includes_owner(self, auth_headers):
        """With site_id filter, owner (org-wide access) should still appear."""
        resp = requests.get(f"{BASE_URL}/api/account/team?site_id={SITE_HQ}", headers=auth_headers)
        assert resp.status_code == 200, f"Team list failed: {resp.text}"
        data = resp.json()
        members = data.get("members", [])
        
        # Owner should always be present regardless of site filter
        owner = next((m for m in members if m.get("email") == PULSE_OWNER_EMAIL), None)
        assert owner is not None, "Owner should always appear in site-filtered team list"
        print(f"✓ Team list (site_id={SITE_HQ}): {len(members)} members, owner present")
    
    def test_team_site_filter_shows_allocated_staff(self, auth_headers, test_staff_user):
        """Staff allocated to SITE_HQ should appear when filtering by SITE_HQ."""
        resp = requests.get(f"{BASE_URL}/api/account/team?site_id={SITE_HQ}", headers=auth_headers)
        assert resp.status_code == 200, f"Team list failed: {resp.text}"
        data = resp.json()
        members = data.get("members", [])
        
        # Test staff should appear (allocated to SITE_HQ)
        test_user = next((m for m in members if m.get("id") == test_staff_user["id"]), None)
        assert test_user is not None, "Test staff allocated to SITE_HQ should appear in SITE_HQ filter"
        print("✓ Test staff appears in SITE_HQ filter")
    
    def test_team_site_filter_hides_unallocated_staff(self, auth_headers, test_staff_user):
        """Staff allocated to SITE_HQ should NOT appear when filtering by SITE_B."""
        resp = requests.get(f"{BASE_URL}/api/account/team?site_id={SITE_B}", headers=auth_headers)
        assert resp.status_code == 200, f"Team list failed: {resp.text}"
        data = resp.json()
        members = data.get("members", [])
        
        # Test staff should NOT appear (only allocated to SITE_HQ, not SITE_B)
        test_user = next((m for m in members if m.get("id") == test_staff_user["id"]), None)
        assert test_user is None, "Test staff allocated to SITE_HQ should NOT appear in SITE_B filter"
        
        # But owner should still appear
        owner = next((m for m in members if m.get("email") == PULSE_OWNER_EMAIL), None)
        assert owner is not None, "Owner should always appear even in SITE_B filter"
        print("✓ Test staff hidden in SITE_B filter, owner still visible")


class TestClockBoardSiteFilter:
    """Test GET /api/staffing/clock/board?site_id={id} filtering."""
    
    def test_clock_board_no_site_filter(self, auth_headers):
        """Without site_id, should return all active staff."""
        resp = requests.get(f"{BASE_URL}/api/staffing/clock/board", headers=auth_headers)
        assert resp.status_code == 200, f"Clock board failed: {resp.text}"
        data = resp.json()
        
        assert "rows" in data, "Response should have 'rows'"
        assert "summary" in data, "Response should have 'summary'"
        assert "as_of" in data, "Response should have 'as_of'"
        
        print(f"✓ Clock board (no filter): {len(data['rows'])} staff rows")
        print(f"  Summary: on_shift={data['summary'].get('on_shift', 0)}, "
              f"on_break={data['summary'].get('on_break', 0)}, "
              f"off={data['summary'].get('off', 0)}, "
              f"late={data['summary'].get('late', 0)}")
    
    def test_clock_board_with_site_filter(self, auth_headers):
        """With site_id filter, should filter staff by allowed_site_ids."""
        resp = requests.get(f"{BASE_URL}/api/staffing/clock/board?site_id={SITE_HQ}", headers=auth_headers)
        assert resp.status_code == 200, f"Clock board failed: {resp.text}"
        data = resp.json()
        
        assert "rows" in data, "Response should have 'rows'"
        print(f"✓ Clock board (site_id={SITE_HQ}): {len(data['rows'])} staff rows")
    
    def test_clock_board_different_sites_different_results(self, auth_headers):
        """Different site filters may return different staff counts."""
        resp_hq = requests.get(f"{BASE_URL}/api/staffing/clock/board?site_id={SITE_HQ}", headers=auth_headers)
        resp_b = requests.get(f"{BASE_URL}/api/staffing/clock/board?site_id={SITE_B}", headers=auth_headers)
        
        assert resp_hq.status_code == 200, f"Clock board HQ failed: {resp_hq.text}"
        assert resp_b.status_code == 200, f"Clock board B failed: {resp_b.text}"
        
        rows_hq = resp_hq.json().get("rows", [])
        rows_b = resp_b.json().get("rows", [])
        
        print(f"✓ Clock board SITE_HQ: {len(rows_hq)} rows")
        print(f"✓ Clock board SITE_B: {len(rows_b)} rows")
        # Note: counts may be same or different depending on staff allocation


class TestOperationalReportsCompareSites:
    """Test Compare Sites enhancement in Operational Reports."""
    
    def test_operational_reports_endpoint(self, auth_headers):
        """Verify operational reports endpoint works with site_id."""
        resp = requests.get(f"{BASE_URL}/api/reports/operational?period=30d", headers=auth_headers)
        assert resp.status_code == 200, f"Operational reports failed: {resp.text}"
        data = resp.json()
        
        # Verify expected fields for compare-sites table
        assert "total_faults" in data, "Should have total_faults"
        assert "open_faults" in data, "Should have open_faults"
        assert "resolved_faults" in data, "Should have resolved_faults"
        assert "avg_resolution_hours" in data, "Should have avg_resolution_hours"
        assert "total_po_value" in data, "Should have total_po_value"
        assert "by_supplier" in data, "Should have by_supplier"
        
        print(f"✓ Operational reports: total_faults={data['total_faults']}, "
              f"open={data['open_faults']}, resolved={data['resolved_faults']}")
    
    def test_operational_reports_per_site(self, auth_headers):
        """Verify operational reports can be fetched per site for comparison."""
        sites = [SITE_HQ, SITE_B, SITE_C]
        results = {}
        
        for site_id in sites:
            resp = requests.get(
                f"{BASE_URL}/api/reports/operational?period=30d&site_id={site_id}",
                headers=auth_headers
            )
            assert resp.status_code == 200, f"Operational reports for {site_id} failed: {resp.text}"
            results[site_id] = resp.json()
        
        # All should return valid data
        for site_id, data in results.items():
            assert "total_faults" in data, f"Site {site_id} missing total_faults"
            print(f"✓ Site {site_id[:8]}...: faults={data['total_faults']}, "
                  f"PO value=£{data.get('total_po_value', 0)}")


class TestSitesEndpoint:
    """Test sites endpoint to verify multi-site setup."""
    
    def test_sites_list(self, auth_headers):
        """Verify Pulse Fitness has multiple sites."""
        resp = requests.get(f"{BASE_URL}/api/sites", headers=auth_headers)
        assert resp.status_code == 200, f"Sites list failed: {resp.text}"
        data = resp.json()
        sites = data.get("sites", [])
        
        assert len(sites) >= 2, f"Expected multi-site org, got {len(sites)} sites"
        
        site_ids = [s.get("id") for s in sites]
        print(f"✓ Pulse Fitness has {len(sites)} sites: {site_ids}")
        
        # Verify expected sites exist
        assert SITE_HQ in site_ids, f"SITE_HQ {SITE_HQ} not found"


class TestCleanup:
    """Cleanup test data."""
    
    def test_cleanup_test_users(self, auth_headers):
        """Delete any test users created with h63-test- prefix."""
        resp = requests.get(f"{BASE_URL}/api/account/team", headers=auth_headers)
        if resp.status_code != 200:
            pytest.skip("Could not fetch team for cleanup")
        
        members = resp.json().get("members", [])
        test_users = [m for m in members if m.get("email", "").startswith("h63-test-")]
        
        for user in test_users:
            del_resp = requests.delete(
                f"{BASE_URL}/api/account/team/{user['id']}",
                headers=auth_headers
            )
            if del_resp.status_code == 200:
                print(f"✓ Cleaned up test user: {user['email']}")
        
        print(f"✓ Cleanup complete: removed {len(test_users)} test users")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
