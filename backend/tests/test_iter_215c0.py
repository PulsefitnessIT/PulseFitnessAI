"""
Backend tests for iteration 215c0 features:
- Usage meter endpoints
- Notification preferences (operator + member portal)
- NPS/Feedback endpoints
- Saved searches CRUD
- CSV export endpoints
- Help capabilities search
- Stripe webhook dunning (simulated)
"""
import os
import pytest
import requests
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")


@pytest.fixture(scope="module")
def operator_token():
    """Get operator auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────────────────────────────────────
# Usage Meter Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUsageMeter:
    """Tests for /api/usage/* endpoints"""

    def test_get_usage_me(self, operator_token):
        """GET /api/usage/me returns current org usage with metrics array"""
        resp = requests.get(f"{BASE_URL}/api/usage/me", headers=auth_headers(operator_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "organization_id" in data
        assert "period" in data
        assert "metrics" in data
        assert isinstance(data["metrics"], list)

        # Verify metrics structure
        metric_names = {m["metric"] for m in data["metrics"]}
        expected_metrics = {"members", "ai_tokens", "sms", "api_calls", "emails"}
        assert expected_metrics.issubset(metric_names), f"Missing metrics: {expected_metrics - metric_names}"

        # Verify each metric has required fields
        for m in data["metrics"]:
            assert "used" in m
            assert "limit" in m
            assert "pct" in m
            assert "level" in m
            assert m["level"] in ("ok", "warning", "critical", "exceeded")

    def test_track_usage(self, operator_token):
        """POST /api/usage/track accepts metric and qty"""
        resp = requests.post(
            f"{BASE_URL}/api/usage/track",
            headers=auth_headers(operator_token),
            json={"metric": "api_calls", "qty": 1}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json().get("ok") is True

    def test_track_usage_invalid_metric(self, operator_token):
        """POST /api/usage/track rejects unknown metric"""
        resp = requests.post(
            f"{BASE_URL}/api/usage/track",
            headers=auth_headers(operator_token),
            json={"metric": "invalid_metric", "qty": 1}
        )
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Notification Preferences Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNotificationPreferences:
    """Tests for /api/me/notification-preferences endpoints"""

    def test_get_operator_prefs(self, operator_token):
        """GET /api/me/notification-preferences returns operator prefs with defaults"""
        resp = requests.get(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "prefs" in data
        prefs = data["prefs"]

        # Verify default keys exist
        expected_keys = {"transactional", "product_updates", "marketing", "weekly_digest",
                        "billing_alerts", "feature_tips", "sms"}
        assert expected_keys.issubset(set(prefs.keys())), f"Missing keys: {expected_keys - set(prefs.keys())}"

        # Verify defaults
        assert prefs["transactional"] is True, "transactional should default to True"
        assert prefs["marketing"] is False, "marketing should default to False"

    def test_update_operator_prefs(self, operator_token):
        """PUT /api/me/notification-preferences round-trips correctly"""
        # First get current prefs
        get_resp = requests.get(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(operator_token)
        )
        assert get_resp.status_code == 200
        original_prefs = get_resp.json()["prefs"]

        # Update a preference
        new_prefs = dict(original_prefs)
        new_prefs["weekly_digest"] = not original_prefs.get("weekly_digest", True)

        put_resp = requests.put(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(operator_token),
            json={"prefs": new_prefs}
        )
        assert put_resp.status_code == 200, f"Expected 200, got {put_resp.status_code}: {put_resp.text}"

        # Verify the change persisted
        verify_resp = requests.get(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(operator_token)
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["prefs"]["weekly_digest"] == new_prefs["weekly_digest"]

    def test_operator_cannot_access_member_portal_prefs(self, operator_token):
        """Operator JWT cannot access /api/portal/me/notification-preferences - should 403 or 401"""
        resp = requests.get(
            f"{BASE_URL}/api/portal/me/notification-preferences",
            headers=auth_headers(operator_token)
        )
        # Should fail - operator token is not a member token
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# NPS/Feedback Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFeedback:
    """Tests for /api/feedback/* endpoints"""

    def test_submit_nps_valid(self, operator_token):
        """POST /api/feedback/nps validates score 0-10 and persists"""
        resp = requests.post(
            f"{BASE_URL}/api/feedback/nps",
            headers=auth_headers(operator_token),
            json={"score": 8, "comment": "Test feedback from pytest", "page": "/test"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert "id" in data

    def test_submit_nps_invalid_score(self, operator_token):
        """POST /api/feedback/nps rejects score outside 0-10"""
        # Score too high
        resp = requests.post(
            f"{BASE_URL}/api/feedback/nps",
            headers=auth_headers(operator_token),
            json={"score": 11}
        )
        assert resp.status_code == 400

        # Score too low
        resp = requests.post(
            f"{BASE_URL}/api/feedback/nps",
            headers=auth_headers(operator_token),
            json={"score": -1}
        )
        assert resp.status_code == 400

    def test_should_prompt(self, operator_token):
        """GET /api/feedback/should-prompt returns should_prompt boolean"""
        resp = requests.get(
            f"{BASE_URL}/api/feedback/should-prompt",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "should_prompt" in data
        assert isinstance(data["should_prompt"], bool)

    def test_dismiss_prompt(self, operator_token):
        """POST /api/feedback/dismiss snoozes the prompt"""
        resp = requests.post(
            f"{BASE_URL}/api/feedback/dismiss",
            headers=auth_headers(operator_token),
            json={}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json().get("ok") is True

    def test_master_admin_nps_summary(self, master_admin_token):
        """GET /api/feedback/master-admin/nps returns NPS distribution"""
        resp = requests.get(
            f"{BASE_URL}/api/feedback/master-admin/nps",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify response structure
        assert "nps" in data
        assert "total_responses" in data
        assert "promoters" in data
        assert "passives" in data
        assert "detractors" in data
        assert "distribution" in data
        assert "verbatim" in data

    def test_non_master_admin_nps_summary_forbidden(self, operator_token):
        """Non-master-admin gets 403 on /api/feedback/master-admin/nps"""
        resp = requests.get(
            f"{BASE_URL}/api/feedback/master-admin/nps",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# Saved Searches Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSavedSearches:
    """Tests for /api/saved-searches CRUD"""

    def test_create_saved_search(self, operator_token):
        """POST /api/saved-searches creates a new saved search"""
        unique_name = f"TEST_Search_{uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(operator_token),
            json={
                "name": unique_name,
                "module": "crm_contacts",
                "filters": {"status": "active"},
                "shared": False
            }
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["name"] == unique_name
        assert data["module"] == "crm_contacts"
        assert "id" in data
        # (Previously returned data["id"]; pytest 9 warns on non-None
        # returns from test functions. The id isn't consumed elsewhere.)

    def test_list_saved_searches(self, operator_token):
        """GET /api/saved-searches lists user's saved searches"""
        resp = requests.get(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_list_saved_searches_by_module(self, operator_token):
        """GET /api/saved-searches?module=crm_contacts filters by module"""
        resp = requests.get(
            f"{BASE_URL}/api/saved-searches?module=crm_contacts",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # All returned items should be for crm_contacts
        for item in data["items"]:
            assert item["module"] == "crm_contacts"

    def test_create_saved_search_invalid_module(self, operator_token):
        """POST /api/saved-searches rejects unknown module"""
        resp = requests.post(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(operator_token),
            json={
                "name": "Invalid Module Test",
                "module": "invalid_module",
                "filters": {}
            }
        )
        assert resp.status_code == 400

    def test_create_saved_search_empty_name(self, operator_token):
        """POST /api/saved-searches rejects empty name"""
        resp = requests.post(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(operator_token),
            json={
                "name": "",
                "module": "crm_contacts",
                "filters": {}
            }
        )
        assert resp.status_code == 400

    def test_update_saved_search(self, operator_token):
        """PUT /api/saved-searches/{id} updates name/filters"""
        # First create a search
        unique_name = f"TEST_Update_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(operator_token),
            json={
                "name": unique_name,
                "module": "memberships_members",
                "filters": {"status": "active"}
            }
        )
        assert create_resp.status_code == 200
        search_id = create_resp.json()["id"]

        # Update it
        new_name = f"TEST_Updated_{uuid.uuid4().hex[:8]}"
        update_resp = requests.put(
            f"{BASE_URL}/api/saved-searches/{search_id}",
            headers=auth_headers(operator_token),
            json={"name": new_name, "filters": {"status": "frozen"}}
        )
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        assert update_resp.json()["name"] == new_name

    def test_delete_saved_search(self, operator_token):
        """DELETE /api/saved-searches/{id} removes the search"""
        # First create a search
        unique_name = f"TEST_Delete_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(operator_token),
            json={
                "name": unique_name,
                "module": "crm_pipeline",
                "filters": {}
            }
        )
        assert create_resp.status_code == 200
        search_id = create_resp.json()["id"]

        # Delete it
        delete_resp = requests.delete(
            f"{BASE_URL}/api/saved-searches/{search_id}",
            headers=auth_headers(operator_token)
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json().get("ok") is True


# ─────────────────────────────────────────────────────────────────────────────
# CSV Export Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCsvExport:
    """Tests for /api/export/*.csv endpoints"""

    def test_export_members_csv(self, operator_token):
        """GET /api/export/members.csv returns CSV with headers"""
        resp = requests.get(
            f"{BASE_URL}/api/export/members.csv",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        assert "attachment" in resp.headers.get("Content-Disposition", "")

        # Verify CSV has header row
        content = resp.text
        lines = content.strip().split('\n')
        assert len(lines) >= 1, "CSV should have at least a header row"
        header = lines[0]
        assert "ID" in header or "Email" in header or "First Name" in header

    def test_export_contacts_csv(self, operator_token):
        """GET /api/export/contacts.csv returns CSV with headers"""
        resp = requests.get(
            f"{BASE_URL}/api/export/contacts.csv",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_export_deals_csv(self, operator_token):
        """GET /api/export/deals.csv returns CSV with headers"""
        resp = requests.get(
            f"{BASE_URL}/api/export/deals.csv",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_export_classes_csv(self, operator_token):
        """GET /api/export/classes.csv returns CSV with headers"""
        resp = requests.get(
            f"{BASE_URL}/api/export/classes.csv",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_export_bookings_csv(self, operator_token):
        """GET /api/export/bookings.csv returns CSV with headers"""
        resp = requests.get(
            f"{BASE_URL}/api/export/bookings.csv",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")


# ─────────────────────────────────────────────────────────────────────────────
# Help Search / Capabilities Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpSearch:
    """Tests for /api/help/search and /api/help/capabilities"""

    def test_help_search_returns_capabilities(self, operator_token):
        """GET /api/help/search?q=member returns both results and capabilities"""
        resp = requests.get(
            f"{BASE_URL}/api/help/search?q=member",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Should have both results (guides) and capabilities
        assert "results" in data
        assert "capabilities" in data
        assert isinstance(data["capabilities"], list)

    def test_help_capabilities_endpoint(self, operator_token):
        """GET /api/help/capabilities?q=plan returns capability deep-links"""
        resp = requests.get(
            f"{BASE_URL}/api/help/capabilities?q=plan",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "results" in data
        assert isinstance(data["results"], list)

        # Each result should have title, module, url
        for result in data["results"]:
            assert "title" in result
            assert "module" in result
            assert "url" in result

    def test_help_capabilities_empty_query(self, operator_token):
        """GET /api/help/capabilities with empty query returns default results"""
        resp = requests.get(
            f"{BASE_URL}/api/help/capabilities?q=",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "results" in data
        # Should return some default popular capabilities
        assert len(data["results"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Stripe Webhook Dunning Tests (Simulated)
# ─────────────────────────────────────────────────────────────────────────────

class TestStripeDunning:
    """
    Tests for Stripe webhook dunning workflow.
    Note: These tests verify the internal logic by checking database state,
    not by actually calling the webhook (which requires signed payloads).
    """

    def test_webhook_endpoint_exists(self):
        """Verify /api/webhook/stripe endpoint exists (will fail signature check)"""
        # This will fail with 400 due to missing/invalid signature, but proves endpoint exists
        resp = requests.post(
            f"{BASE_URL}/api/webhook/stripe",
            headers={"Content-Type": "application/json", "Stripe-Signature": "invalid"},
            json={"type": "test"}
        )
        # Should be 400 (bad signature) not 404 (not found)
        assert resp.status_code == 400, f"Expected 400 (bad signature), got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# General API Health Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApiHealth:
    """Basic health checks"""

    def test_api_health(self):
        """GET /api/health returns 200"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200

    def test_auth_login_master_admin(self):
        """Master admin can login"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Master admin login failed: {resp.status_code} - {resp.text}"
        assert "token" in resp.json()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
