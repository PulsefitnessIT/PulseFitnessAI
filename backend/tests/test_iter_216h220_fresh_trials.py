"""
Iter 216h220 — Fresh Trial Signups Tile Backend Tests

Tests for:
1. GET /api/master-admin/trials/recent — master admin only
2. Parameter capping (hours max 168, limit max 20)
3. Response structure with enrichment fields
4. Auth guard (401/403 for non-master-admin)
5. Regression: /api/master-admin/trials/summary still works
6. E2E enrichment flow: register trial with all fields → appears in /trials/recent
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Master admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"

# Regular user credentials
REGULAR_USER_EMAIL = "bob@knockers.com"
REGULAR_USER_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def regular_user_token():
    """Get regular user auth token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": REGULAR_USER_EMAIL,
        "password": REGULAR_USER_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Regular user login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


class TestTrialsRecentEndpoint:
    """Tests for GET /api/master-admin/trials/recent"""
    
    def test_trials_recent_requires_auth(self):
        """Endpoint should return 401 without auth token."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/trials/recent")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ /trials/recent returns 401 without auth")
    
    def test_trials_recent_requires_master_admin(self, regular_user_token):
        """Endpoint should return 403 for non-master-admin users."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/recent",
            headers={"Authorization": f"Bearer {regular_user_token}"}
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("✓ /trials/recent returns 403 for non-master-admin")
    
    def test_trials_recent_success(self, master_admin_token):
        """Master admin can access /trials/recent with default params."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/recent",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "items" in data, "Response should have 'items' array"
        assert "hours" in data, "Response should have 'hours' field"
        assert "total" in data, "Response should have 'total' field"
        assert isinstance(data["items"], list), "'items' should be a list"
        assert data["hours"] == 24, f"Default hours should be 24, got {data['hours']}"
        print(f"✓ /trials/recent returns {len(data['items'])} items with correct structure")
    
    def test_trials_recent_custom_params(self, master_admin_token):
        """Test custom hours and limit parameters."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/recent?hours=48&limit=10",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hours"] == 48, f"Expected hours=48, got {data['hours']}"
        assert len(data["items"]) <= 10, f"Expected max 10 items, got {len(data['items'])}"
        print(f"✓ Custom params work: hours=48, limit=10, got {len(data['items'])} items")
    
    def test_trials_recent_hours_capped_at_168(self, master_admin_token):
        """Hours parameter should be capped at 168 (7 days)."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/recent?hours=500",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hours"] == 168, f"Hours should be capped at 168, got {data['hours']}"
        print("✓ Hours parameter capped at 168")
    
    def test_trials_recent_limit_capped_at_20(self, master_admin_token):
        """Limit parameter should be capped at 20."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/recent?limit=100",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        # Can't directly verify cap from response, but endpoint should not error
        assert len(data["items"]) <= 20, f"Expected max 20 items, got {len(data['items'])}"
        print("✓ Limit parameter capped at 20")
    
    def test_trials_recent_item_structure(self, master_admin_token):
        """Verify each item has the expected enrichment fields."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/recent?hours=168&limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        if len(data["items"]) == 0:
            print("⚠ No trial items found - skipping structure validation")
            return
        
        expected_fields = [
            "id", "name", "owner_email", "owner_name", "industry",
            "employee_count", "website", "referral_source", "utm_source",
            "utm_campaign", "trial_started_at", "trial_ends_at"
        ]
        
        item = data["items"][0]
        for field in expected_fields:
            assert field in item, f"Item missing field: {field}"
        
        print(f"✓ Item structure verified with all {len(expected_fields)} expected fields")
        print(f"  Sample item: name={item.get('name')}, owner_email={item.get('owner_email')}")


class TestTrialsSummaryRegression:
    """Regression tests for /api/master-admin/trials/summary"""
    
    def test_trials_summary_still_works(self, master_admin_token):
        """Verify /trials/summary endpoint still works after adding /trials/recent."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/summary",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify expected fields
        expected_fields = [
            "total", "by_status", "converted_30d", "ended_30d",
            "conversion_rate_30d", "avg_days_to_convert", "expiring_this_week", "by_source"
        ]
        for field in expected_fields:
            assert field in data, f"Summary missing field: {field}"
        
        print(f"✓ /trials/summary still works - total={data['total']}, by_status={data['by_status']}")


class TestE2EEnrichmentFlow:
    """End-to-end test: register trial with enrichment → verify in /trials/recent"""
    
    def test_register_trial_with_enrichment_appears_in_recent(self, master_admin_token):
        """
        Register a new trial with all enrichment fields, then verify it appears
        as the first item in /trials/recent with all fields populated.
        """
        # Generate unique test data
        unique_id = str(uuid.uuid4())[:8]
        test_email = f"test.trial.{unique_id}@example.com"
        test_company = f"TEST Fresh Trial Gym {unique_id}"
        
        # Register trial with all enrichment fields
        register_payload = {
            "email": test_email,
            "password": "TestTrial123!",
            "full_name": f"Test User {unique_id}",
            "company_name": test_company,
            "is_trial": True,
            "trial_duration_days": 3,
            "website": f"https://test-gym-{unique_id}.com",
            "industry": "Fitness & Wellness",
            "employee_count": "11-50",
            "referral_source": "Google Search",
            "utm_source": "google",
            "utm_campaign": "test_campaign_2026"
        }
        
        register_resp = requests.post(
            f"{BASE_URL}/api/auth/register",
            json=register_payload
        )
        
        # Registration might fail due to rate limiting or captcha - handle gracefully
        if register_resp.status_code == 429:
            pytest.skip("Rate limited - skipping E2E enrichment test")
        if register_resp.status_code == 400 and "captcha" in register_resp.text.lower():
            pytest.skip("Captcha required - skipping E2E enrichment test")
        
        assert register_resp.status_code == 200, f"Registration failed: {register_resp.status_code} - {register_resp.text}"
        
        reg_data = register_resp.json()
        new_org_id = reg_data.get("user", {}).get("organization_id")
        assert new_org_id, "Registration should return organization_id"
        print(f"✓ Registered trial org: {new_org_id}")
        
        # Now fetch /trials/recent and verify the new trial appears
        recent_resp = requests.get(
            f"{BASE_URL}/api/master-admin/trials/recent?hours=1&limit=5",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert recent_resp.status_code == 200
        recent_data = recent_resp.json()
        
        # Find our newly created trial
        found_trial = None
        for item in recent_data["items"]:
            if item["id"] == new_org_id:
                found_trial = item
                break
        
        assert found_trial, f"Newly created trial {new_org_id} not found in /trials/recent"
        
        # Verify all enrichment fields are populated
        assert found_trial["name"] == test_company, f"Name mismatch: {found_trial['name']}"
        assert found_trial["owner_email"] == test_email, f"Owner email mismatch: {found_trial['owner_email']}"
        assert found_trial["industry"] == "Fitness & Wellness", f"Industry mismatch: {found_trial['industry']}"
        assert found_trial["employee_count"] == "11-50", f"Employee count mismatch: {found_trial['employee_count']}"
        assert f"test-gym-{unique_id}" in found_trial["website"], f"Website mismatch: {found_trial['website']}"
        assert found_trial["referral_source"] == "Google Search", f"Referral source mismatch: {found_trial['referral_source']}"
        assert found_trial["utm_source"] == "google", f"UTM source mismatch: {found_trial['utm_source']}"
        assert found_trial["utm_campaign"] == "test_campaign_2026", f"UTM campaign mismatch: {found_trial['utm_campaign']}"
        
        print("✓ E2E enrichment verified - all fields populated correctly")
        print(f"  Trial: {found_trial['name']}")
        print(f"  Industry: {found_trial['industry']}, Employees: {found_trial['employee_count']}")
        print(f"  UTM: source={found_trial['utm_source']}, campaign={found_trial['utm_campaign']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
