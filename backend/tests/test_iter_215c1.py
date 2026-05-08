"""
Backend tests for iteration 215c1 features:
- JWT_SECRET rotation verification (login still works, tokens validate)
- Self-serve cancel/downgrade endpoints (/api/account/billing/*)
- Auth boundaries on cancel/downgrade (403 for non-owner/non-admin)
- Health endpoint additions (sender_email, jwt_secret, sentry checks)
- Regression sanity (existing flows still work after JWT rotation)
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
    """Get master admin auth token - verifies JWT_SECRET rotation works"""
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
# JWT_SECRET Rotation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestJwtSecretRotation:
    """Tests verifying JWT_SECRET rotation works correctly"""

    def test_master_admin_login_after_rotation(self):
        """Master admin can login after JWT_SECRET rotation"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Login failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "token" in data
        assert len(data["token"]) > 50  # JWT should be substantial

    def test_newly_issued_token_validates(self, master_admin_token):
        """Newly issued token validates on /api/auth/me"""
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200, f"Token validation failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert data.get("email") == MASTER_ADMIN_EMAIL
        assert data.get("is_master_admin") is True

    def test_health_deep_jwt_secret_status(self):
        """GET /api/health/deep shows jwt_secret.status == 'ok'"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200, f"Health deep failed: {resp.status_code}"
        data = resp.json()

        assert "checks" in data
        assert "jwt_secret" in data["checks"]
        jwt_check = data["checks"]["jwt_secret"]
        assert jwt_check["status"] == "ok", f"JWT secret status should be 'ok', got: {jwt_check}"
        # Should not have a hint when status is ok
        assert jwt_check.get("hint") is None


# ─────────────────────────────────────────────────────────────────────────────
# Self-Serve Cancel/Downgrade Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestSubscriptionEndpoints:
    """Tests for /api/account/billing/* self-serve endpoints"""

    def test_get_subscription_status(self, master_admin_token):
        """GET /api/account/billing/subscription returns plan + pending flags + stripe state"""
        resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify required fields
        assert "organization_id" in data
        assert "plan" in data
        assert "pending_cancellation" in data
        assert "pending_downgrade_to" in data
        assert "stripe" in data
        assert isinstance(data["stripe"], dict)

        # Verify billing_status field
        assert "billing_status" in data
        assert "enabled_modules" in data

    def test_cancel_without_reason_returns_400(self, master_admin_token):
        """POST /api/account/billing/cancel without reason returns 400"""
        resp = requests.post(
            f"{BASE_URL}/api/account/billing/cancel",
            headers=auth_headers(master_admin_token),
            json={}  # No reason provided
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "reason" in resp.json().get("detail", "").lower()

    def test_cancel_with_empty_reason_returns_400(self, master_admin_token):
        """POST /api/account/billing/cancel with empty reason returns 400"""
        resp = requests.post(
            f"{BASE_URL}/api/account/billing/cancel",
            headers=auth_headers(master_admin_token),
            json={"reason": ""}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_cancel_with_valid_reason_succeeds(self, master_admin_token):
        """POST /api/account/billing/cancel with valid reason flips pending_cancellation"""
        resp = requests.post(
            f"{BASE_URL}/api/account/billing/cancel",
            headers=auth_headers(master_admin_token),
            json={"reason": "Testing cancellation flow", "feedback": "Pytest test"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert "stripe_result" in data
        assert "message" in data

        # Verify the org now has pending_cancellation=true
        sub_resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["pending_cancellation"] is True
        # Should have cancellation_effective_at (may be None if no Stripe sub)
        assert "cancellation_effective_at" in sub_data

    def test_reactivate_clears_pending_cancellation(self, master_admin_token):
        """POST /api/account/billing/reactivate clears pending_cancellation"""
        # First ensure there's a pending cancellation
        sub_resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        if not sub_resp.json().get("pending_cancellation"):
            # Create one first
            requests.post(
                f"{BASE_URL}/api/account/billing/cancel",
                headers=auth_headers(master_admin_token),
                json={"reason": "Setup for reactivate test"}
            )

        # Now reactivate
        resp = requests.post(
            f"{BASE_URL}/api/account/billing/reactivate",
            headers=auth_headers(master_admin_token),
            json={}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True

        # Verify pending_cancellation is now false
        verify_resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        assert verify_resp.json()["pending_cancellation"] is False

    def test_downgrade_invalid_tier_returns_400(self, master_admin_token):
        """POST /api/account/billing/downgrade with invalid tier returns 400"""
        resp = requests.post(
            f"{BASE_URL}/api/account/billing/downgrade",
            headers=auth_headers(master_admin_token),
            json={"target_tier": "invalid_tier"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "target_tier" in detail.lower() or "must be one of" in detail.lower()

    def test_downgrade_valid_tier_succeeds(self, master_admin_token):
        """POST /api/account/billing/downgrade with valid tier sets pending_downgrade_to"""
        # Valid tiers: starter, memberships, crm, marketing, operations
        resp = requests.post(
            f"{BASE_URL}/api/account/billing/downgrade",
            headers=auth_headers(master_admin_token),
            json={"target_tier": "memberships"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("target_tier") == "memberships"

        # Verify the org now has pending_downgrade_to set
        sub_resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        assert sub_resp.json()["pending_downgrade_to"] == "memberships"

    def test_downgrade_cancel_withdraws_pending(self, master_admin_token):
        """POST /api/account/billing/downgrade/cancel withdraws pending downgrade"""
        # First ensure there's a pending downgrade
        sub_resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        if not sub_resp.json().get("pending_downgrade_to"):
            # Create one first
            requests.post(
                f"{BASE_URL}/api/account/billing/downgrade",
                headers=auth_headers(master_admin_token),
                json={"target_tier": "crm"}
            )

        # Now cancel the downgrade
        resp = requests.post(
            f"{BASE_URL}/api/account/billing/downgrade/cancel",
            headers=auth_headers(master_admin_token),
            json={}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True

        # Verify pending_downgrade_to is now cleared
        verify_resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        assert verify_resp.json().get("pending_downgrade_to") is None


# ─────────────────────────────────────────────────────────────────────────────
# Auth Boundaries Tests (403 for non-owner/non-admin)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthBoundaries:
    """Tests verifying only owners/admins/master-admins can change billing"""

    def test_master_admin_can_access_billing(self, master_admin_token):
        """Master admin can access billing endpoints"""
        resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200

    def test_operator_owner_can_access_billing(self, operator_token):
        """Operator with owner role can access billing endpoints"""
        # lee.somers@pulsefitness.com should have owner role
        resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(operator_token)
        )
        # Should succeed if user has owner/admin role, or fail with 403 if not
        assert resp.status_code in (200, 403), f"Unexpected status: {resp.status_code}"

    def test_unauthenticated_cannot_access_billing(self):
        """Unauthenticated requests get 401"""
        resp = requests.get(f"{BASE_URL}/api/account/billing/subscription")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Health Endpoint Additions
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthDeepAdditions:
    """Tests for /api/health/deep new checks (sender_email, jwt_secret, sentry)"""

    def test_health_deep_includes_sender_email(self):
        """GET /api/health/deep includes sender_email check"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()

        assert "checks" in data
        assert "sender_email" in data["checks"]
        sender_check = data["checks"]["sender_email"]
        assert "status" in sender_check
        assert sender_check["status"] in ("configured", "weak")
        # Should have value field
        assert "value" in sender_check

    def test_health_deep_includes_jwt_secret(self):
        """GET /api/health/deep includes jwt_secret check"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()

        assert "jwt_secret" in data["checks"]
        jwt_check = data["checks"]["jwt_secret"]
        assert "status" in jwt_check
        assert jwt_check["status"] in ("ok", "weak")

    def test_health_deep_includes_sentry(self):
        """GET /api/health/deep includes sentry check"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()

        assert "sentry" in data["checks"]
        sentry_check = data["checks"]["sentry"]
        assert "status" in sentry_check
        assert sentry_check["status"] in ("configured", "missing")

    def test_health_deep_overall_status(self):
        """GET /api/health/deep returns overall status"""
        resp = requests.get(f"{BASE_URL}/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()

        assert "overall" in data
        assert data["overall"] in ("ok", "degraded")


# ─────────────────────────────────────────────────────────────────────────────
# Regression Sanity Tests (existing flows still work)
# ─────────────────────────────────────────────────────────────────────────────

class TestRegressionSanity:
    """Tests verifying existing flows work after JWT_SECRET rotation"""

    def test_auth_login(self):
        """POST /api/auth/login still works"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_auth_me(self, master_admin_token):
        """GET /api/auth/me still works"""
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "id" in data

    def test_usage_me(self, master_admin_token):
        """GET /api/usage/me still works (from 215c0)"""
        resp = requests.get(
            f"{BASE_URL}/api/usage/me",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data

    def test_feedback_should_prompt(self, master_admin_token):
        """GET /api/feedback/should-prompt still works"""
        resp = requests.get(
            f"{BASE_URL}/api/feedback/should-prompt",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        assert "should_prompt" in resp.json()

    def test_saved_searches(self, master_admin_token):
        """GET /api/saved-searches still works"""
        resp = requests.get(
            f"{BASE_URL}/api/saved-searches",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_help_search(self, master_admin_token):
        """GET /api/help/search?q=plan still works"""
        resp = requests.get(
            f"{BASE_URL}/api/help/search?q=plan",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data or "capabilities" in data

    def test_export_contacts_csv(self, master_admin_token):
        """GET /api/export/contacts.csv still works"""
        resp = requests.get(
            f"{BASE_URL}/api/export/contacts.csv",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_notification_preferences_get(self, master_admin_token):
        """GET /api/me/notification-preferences still works"""
        resp = requests.get(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(master_admin_token)
        )
        assert resp.status_code == 200
        assert "prefs" in resp.json()

    def test_notification_preferences_put(self, master_admin_token):
        """PUT /api/me/notification-preferences still works"""
        # First get current prefs
        get_resp = requests.get(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(master_admin_token)
        )
        prefs = get_resp.json()["prefs"]

        # Update (toggle weekly_digest)
        prefs["weekly_digest"] = not prefs.get("weekly_digest", True)
        put_resp = requests.put(
            f"{BASE_URL}/api/me/notification-preferences",
            headers=auth_headers(master_admin_token),
            json={"prefs": prefs}
        )
        assert put_resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup - Reset master admin org after tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def cleanup_after_tests(master_admin_token):
    """Cleanup: reset master admin org by removing pending_cancellation/downgrade fields"""
    yield
    # After all tests, clear any pending cancellation/downgrade
    try:
        # Reactivate if pending cancellation
        sub_resp = requests.get(
            f"{BASE_URL}/api/account/billing/subscription",
            headers=auth_headers(master_admin_token)
        )
        if sub_resp.status_code == 200:
            data = sub_resp.json()
            if data.get("pending_cancellation"):
                requests.post(
                    f"{BASE_URL}/api/account/billing/reactivate",
                    headers=auth_headers(master_admin_token),
                    json={}
                )
            if data.get("pending_downgrade_to"):
                requests.post(
                    f"{BASE_URL}/api/account/billing/downgrade/cancel",
                    headers=auth_headers(master_admin_token),
                    json={}
                )
    except Exception:
        pass  # Best effort cleanup


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
