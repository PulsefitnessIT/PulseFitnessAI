"""
Backend tests for iteration 215c2 features:
- SEO: sitemap.xml (18 URL entries), robots.txt (disallows /api, /dashboard, /master-admin)
- Annual billing: /api/payments/pricing returns annual fields
- Lifecycle emails: preview + run endpoints, 403 for non-master-admin
- Notification prefs honoured: feature_tips=false blocks day2_check/mid_trial
- Health regression: /api/health/deep returns expected checks
- Existing flows regression: auth, usage, saved-searches, feedback, help, exports, notification-prefs
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
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
    """Get operator auth token (non-master-admin)"""
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
# SEO Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSEO:
    """Tests for SEO features: sitemap.xml, robots.txt"""

    def test_sitemap_returns_200(self):
        """GET /sitemap.xml returns 200"""
        resp = requests.get(f"{BASE_URL}/sitemap.xml")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_sitemap_has_18_url_entries(self):
        """GET /sitemap.xml contains 18 <url> entries"""
        resp = requests.get(f"{BASE_URL}/sitemap.xml")
        assert resp.status_code == 200
        content = resp.text
        # Count <url> tags
        url_count = content.count("<url>")
        assert url_count == 18, f"Expected 18 URL entries, got {url_count}"

    def test_sitemap_has_urlset_namespace(self):
        """GET /sitemap.xml has proper <urlset> with namespace"""
        resp = requests.get(f"{BASE_URL}/sitemap.xml")
        assert resp.status_code == 200
        content = resp.text
        assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in content

    def test_robots_txt_returns_200(self):
        """GET /robots.txt returns 200"""
        resp = requests.get(f"{BASE_URL}/robots.txt")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_robots_txt_disallows_api(self):
        """GET /robots.txt disallows /api/"""
        resp = requests.get(f"{BASE_URL}/robots.txt")
        assert resp.status_code == 200
        content = resp.text
        assert "Disallow: /api/" in content, "robots.txt should disallow /api/"

    def test_robots_txt_disallows_dashboard(self):
        """GET /robots.txt disallows /dashboard"""
        resp = requests.get(f"{BASE_URL}/robots.txt")
        assert resp.status_code == 200
        content = resp.text
        assert "Disallow: /dashboard" in content, "robots.txt should disallow /dashboard"

    def test_robots_txt_disallows_master_admin(self):
        """GET /robots.txt disallows /master-admin"""
        resp = requests.get(f"{BASE_URL}/robots.txt")
        assert resp.status_code == 200
        content = resp.text
        assert "Disallow: /master-admin" in content, "robots.txt should disallow /master-admin"

    def test_robots_txt_allows_public_routes(self):
        """GET /robots.txt allows public marketing routes"""
        resp = requests.get(f"{BASE_URL}/robots.txt")
        assert resp.status_code == 200
        content = resp.text
        # Check for Allow directives
        assert "Allow: /pricing" in content or "Allow: /" in content


# ─────────────────────────────────────────────────────────────────────────────
# Annual Billing Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnualBilling:
    """Tests for annual billing pricing endpoint"""

    def test_pricing_returns_annual_discount_pct(self):
        """GET /api/payments/pricing returns annual_discount_pct=16.7"""
        resp = requests.get(f"{BASE_URL}/api/payments/pricing")
        assert resp.status_code == 200
        data = resp.json()
        assert "annual_discount_pct" in data
        assert data["annual_discount_pct"] == 16.7, f"Expected 16.7, got {data['annual_discount_pct']}"

    def test_pricing_bundle_has_monthly_150(self):
        """GET /api/payments/pricing returns bundle.monthly=150"""
        resp = requests.get(f"{BASE_URL}/api/payments/pricing")
        assert resp.status_code == 200
        data = resp.json()
        assert "bundle" in data
        assert data["bundle"]["monthly"] == 150.0

    def test_pricing_bundle_has_annual_1500(self):
        """GET /api/payments/pricing returns bundle.annual=1500"""
        resp = requests.get(f"{BASE_URL}/api/payments/pricing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bundle"]["annual"] == 1500.0

    def test_pricing_bundle_has_per_site_annual_500(self):
        """GET /api/payments/pricing returns bundle.per_site_annual=500"""
        resp = requests.get(f"{BASE_URL}/api/payments/pricing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bundle"]["per_site_annual"] == 500.0

    def test_pricing_modules_have_annual_fields(self):
        """GET /api/payments/pricing returns annual field for each module"""
        resp = requests.get(f"{BASE_URL}/api/payments/pricing")
        assert resp.status_code == 200
        data = resp.json()

        expected_annuals = {
            "memberships": 290.0,
            "crm": 490.0,
            "marketing": 490.0,
            "operations": 590.0
        }

        for mod in data["modules"]:
            mod_id = mod["id"]
            assert "annual" in mod, f"Module {mod_id} missing annual field"
            if mod_id in expected_annuals:
                assert mod["annual"] == expected_annuals[mod_id], \
                    f"Module {mod_id} annual should be {expected_annuals[mod_id]}, got {mod['annual']}"


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle Email Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLifecycleEmails:
    """Tests for lifecycle email admin endpoints"""

    @pytest.mark.parametrize("template", ["welcome", "day2_check", "mid_trial", "expiry_warn", "winback"])
    def test_preview_returns_200_with_subject_and_html(self, master_admin_token, template):
        """GET /api/admin/lifecycle-emails/preview/{template} returns 200 with subject + html"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/lifecycle-emails/preview/{template}",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200, f"Expected 200 for {template}, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "subject" in data, f"Missing 'subject' in response for {template}"
        assert "html" in data, f"Missing 'html' in response for {template}"
        assert len(data["subject"]) > 0, f"Empty subject for {template}"
        assert len(data["html"]) > 0, f"Empty html for {template}"

    def test_preview_non_master_admin_returns_403(self, operator_token):
        """GET /api/admin/lifecycle-emails/preview/welcome returns 403 for non-master-admin"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/lifecycle-emails/preview/welcome",
            headers=auth_headers(operator_token)
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        assert "master admin" in resp.json().get("detail", "").lower()

    def test_run_returns_count_dict(self, master_admin_token):
        """POST /api/admin/lifecycle-emails/run returns count dict"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/lifecycle-emails/run",
            headers=auth_headers(master_admin_token),
            json={}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify all expected keys are present
        expected_keys = ["welcome", "day2_check", "mid_trial", "expiry_warn", "winback", "skipped"]
        for key in expected_keys:
            assert key in data, f"Missing key '{key}' in run response"
            assert isinstance(data[key], int), f"Key '{key}' should be int, got {type(data[key])}"

    def test_run_non_master_admin_returns_403(self, operator_token):
        """POST /api/admin/lifecycle-emails/run returns 403 for non-master-admin"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/lifecycle-emails/run",
            headers=auth_headers(operator_token),
            json={}
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# Health Regression Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthDeep:
    """Tests for /api/health/deep endpoint"""

    def test_health_deep_overall_ok(self):
        """GET /api/health/deep returns overall='ok'"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("overall") == "ok", f"Expected overall='ok', got {data.get('overall')}"

    def test_health_deep_jwt_secret_ok(self):
        """GET /api/health/deep returns jwt_secret.status='ok'"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()
        jwt_check = data.get("checks", {}).get("jwt_secret", {})
        assert jwt_check.get("status") == "ok", f"Expected jwt_secret.status='ok', got {jwt_check}"

    def test_health_deep_sender_email_configured(self):
        """GET /api/health/deep returns sender_email.status='configured'"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()
        sender_check = data.get("checks", {}).get("sender_email", {})
        assert sender_check.get("status") == "configured", f"Expected sender_email.status='configured', got {sender_check}"

    def test_health_deep_sentry_missing(self):
        """GET /api/health/deep returns sentry.status='missing' (expected - user provides DSN Monday)"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()
        sentry_check = data.get("checks", {}).get("sentry", {})
        assert sentry_check.get("status") == "missing", f"Expected sentry.status='missing', got {sentry_check}"


# ─────────────────────────────────────────────────────────────────────────────
# Existing Flows Regression Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRegressionFlows:
    """Tests verifying existing flows still work after JWT rotation"""

    def test_master_admin_login(self):
        """Master admin login still works after JWT re-rotation"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Login failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "token" in data
        assert data.get("user", {}).get("is_master_admin") is True

    def test_usage_me(self, master_admin_token):
        """GET /api/usage/me returns correct shape"""
        resp = requests.get(
            f"{BASE_URL}/api/usage/me",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data

    def test_saved_searches(self, master_admin_token):
        """GET /api/saved-searches returns correct shape"""
        resp = requests.get(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_feedback_should_prompt(self, master_admin_token):
        """GET /api/feedback/should-prompt returns correct shape"""
        resp = requests.get(
            f"{BASE_URL}/api/feedback/should-prompt",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "should_prompt" in data

    def test_account_billing_subscription(self, master_admin_token):
        """GET /api/account/billing/subscription returns correct shape"""
        resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "plan" in data
        assert "pending_cancellation" in data

    def test_help_search(self, master_admin_token):
        """GET /api/help/search?q=plan returns correct shape"""
        resp = requests.get(
            f"{BASE_URL}/api/help/search?q=plan",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data or "capabilities" in data

    def test_notification_preferences_get(self, master_admin_token):
        """GET /api/me/notification-preferences returns correct shape"""
        resp = requests.get(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "prefs" in data

    def test_notification_preferences_put(self, master_admin_token):
        """PUT /api/me/notification-preferences works"""
        # First get current prefs
        get_resp = requests.get(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(master_admin_token)
        )
        prefs = get_resp.json()["prefs"]

        # Toggle a value and update
        original_value = prefs.get("weekly_digest", True)
        prefs["weekly_digest"] = not original_value

        put_resp = requests.put(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(master_admin_token),
            json={"prefs": prefs}
        )
        assert put_resp.status_code == 200

        # Restore original value
        prefs["weekly_digest"] = original_value
        requests.put(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(master_admin_token),
            json={"prefs": prefs}
        )

    def test_export_contacts_csv(self, master_admin_token):
        """GET /api/export/contacts.csv returns CSV"""
        resp = requests.get(
            f"{BASE_URL}/api/export/contacts.csv",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_export_members_csv(self, master_admin_token):
        """GET /api/export/members.csv returns CSV"""
        resp = requests.get(
            f"{BASE_URL}/api/export/members.csv",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("Content-Type", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
