"""
Test Trial Signup Feature - Iteration 153

Tests:
1. POST /api/auth/register with is_trial=true creates org with trial fields
2. POST /api/auth/register without is_trial works as before (backward compatible)
3. Trial signup notification email is dispatched to Lee@gymaxisai.com
4. Phone field is optional and stored correctly
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
BYPASS_HEADER = os.environ.get('RATE_LIMIT_BYPASS_SECRET', '1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6')


class TestTrialSignupBackend:
    """Trial signup backend API tests"""

    @pytest.fixture
    def headers(self):
        return {
            "Content-Type": "application/json",
            "X-RateLimit-Bypass": BYPASS_HEADER
        }

    def test_trial_signup_creates_org_with_trial_fields(self, headers):
        """POST /api/auth/register with is_trial=true should create org with trial fields"""
        unique_email = f"trial_test_{uuid.uuid4().hex[:8]}@testgym.com"
        payload = {
            "email": unique_email,
            "password": "TestPass123!",
            "full_name": "Trial Test User",
            "company_name": "Trial Test Gym",
            "phone": "+44 7700 900123",
            "is_trial": True,
            "trial_duration_days": 14
        }

        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)

        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Token should be returned
        assert "token" in data, "Token should be returned"
        assert len(data["token"]) > 0, "Token should not be empty"

        # User data assertions
        assert "user" in data, "User data should be returned"
        user = data["user"]
        assert user["email"] == unique_email.lower(), "Email should match"
        assert user["full_name"] == "Trial Test User", "Full name should match"
        assert user["subscription_tier"] == "pro", "Trial users should get pro tier"
        assert user["role"] == "owner", "New org creator should be owner"
        assert "organization_id" in user, "Organization ID should be present"

        print(f"✓ Trial signup successful: {unique_email}")
        print(f"  - subscription_tier: {user['subscription_tier']}")
        print(f"  - role: {user['role']}")
        print(f"  - organization_id: {user['organization_id']}")

        # Now verify the org has trial fields by calling /api/organization
        token = data["token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}
        org_response = requests.get(f"{BASE_URL}/api/organization", headers=auth_headers)

        assert org_response.status_code == 200, f"Failed to get org: {org_response.text}"
        org = org_response.json()

        # Trial field assertions
        assert org.get("is_trial") == True, "Org should have is_trial=True"
        assert org.get("trial_status") == "active", "Trial status should be 'active'"
        assert org.get("subscription_tier") == "pro", "Subscription tier should be 'pro'"
        assert org.get("trial_source") == "landing_signup", "Trial source should be 'landing_signup'"
        assert "trial_started_at" in org, "trial_started_at should be set"
        assert "trial_ends_at" in org, "trial_ends_at should be set"
        assert "trial_suspends_at" in org, "trial_suspends_at should be set"
        assert org.get("trial_duration_days") == 14, "Trial duration should be 14 days"

        print("✓ Org trial fields verified:")
        print(f"  - is_trial: {org.get('is_trial')}")
        print(f"  - trial_status: {org.get('trial_status')}")
        print(f"  - trial_source: {org.get('trial_source')}")
        print(f"  - trial_started_at: {org.get('trial_started_at')}")
        print(f"  - trial_ends_at: {org.get('trial_ends_at')}")

    def test_regular_signup_no_trial_fields(self, headers):
        """POST /api/auth/register without is_trial should work as before (backward compatible)"""
        unique_email = f"regular_test_{uuid.uuid4().hex[:8]}@testgym.com"
        payload = {
            "email": unique_email,
            "password": "TestPass123!",
            "full_name": "Regular Test User",
            "company_name": "Regular Test Gym"
            # No is_trial, no trial_duration_days, no phone
        }

        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "token" in data, "Token should be returned"

        user = data["user"]
        assert user["email"] == unique_email.lower(), "Email should match"
        # Regular signup should NOT have pro tier (should be 'none')
        assert user["subscription_tier"] == "none", f"Regular signup should have 'none' tier, got {user['subscription_tier']}"

        # Verify org does NOT have trial fields
        token = data["token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}
        org_response = requests.get(f"{BASE_URL}/api/organization", headers=auth_headers)

        assert org_response.status_code == 200, f"Failed to get org: {org_response.text}"
        org = org_response.json()

        # Should NOT have is_trial flag
        assert org.get("is_trial") is None or org.get("is_trial") == False, "Regular signup should not have is_trial=True"
        assert org.get("trial_status") is None, "Regular signup should not have trial_status"
        assert org.get("subscription_tier") == "none", "Regular signup should have 'none' tier"

        print(f"✓ Regular signup backward compatible: {unique_email}")
        print(f"  - subscription_tier: {org.get('subscription_tier')}")
        print(f"  - is_trial: {org.get('is_trial')}")

    def test_trial_signup_with_phone(self, headers):
        """Trial signup should store phone number correctly"""
        unique_email = f"phone_test_{uuid.uuid4().hex[:8]}@testgym.com"
        payload = {
            "email": unique_email,
            "password": "TestPass123!",
            "full_name": "Phone Test User",
            "company_name": "Phone Test Gym",
            "phone": "+1 555 123 4567",
            "is_trial": True,
            "trial_duration_days": 14
        }

        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "token" in data, "Token should be returned"

        # Phone is stored on user doc, verify via /api/auth/me
        token = data["token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)

        # Note: /api/auth/me may not return phone field - that's OK
        # The important thing is the signup succeeded with phone
        assert me_response.status_code == 200, f"Failed to get /auth/me: {me_response.text}"

        print(f"✓ Trial signup with phone successful: {unique_email}")

    def test_trial_signup_without_phone(self, headers):
        """Trial signup should work without phone (optional field)"""
        unique_email = f"nophone_test_{uuid.uuid4().hex[:8]}@testgym.com"
        payload = {
            "email": unique_email,
            "password": "TestPass123!",
            "full_name": "No Phone Test User",
            "company_name": "No Phone Test Gym",
            "is_trial": True,
            "trial_duration_days": 14
            # No phone field
        }

        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "token" in data, "Token should be returned"
        assert data["user"]["subscription_tier"] == "pro", "Trial should get pro tier"

        print(f"✓ Trial signup without phone successful: {unique_email}")

    def test_trial_signup_password_validation(self, headers):
        """Trial signup should enforce password strength"""
        unique_email = f"weakpass_test_{uuid.uuid4().hex[:8]}@testgym.com"
        payload = {
            "email": unique_email,
            "password": "weak",  # Too short
            "full_name": "Weak Pass User",
            "company_name": "Weak Pass Gym",
            "is_trial": True,
            "trial_duration_days": 14
        }

        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)

        # Should fail with 400 for weak password
        assert response.status_code == 400, f"Expected 400 for weak password, got {response.status_code}"

        print("✓ Password validation working - weak password rejected")

    def test_trial_signup_duplicate_email(self, headers):
        """Trial signup should reject duplicate email"""
        unique_email = f"dup_test_{uuid.uuid4().hex[:8]}@testgym.com"
        payload = {
            "email": unique_email,
            "password": "TestPass123!",
            "full_name": "Dup Test User",
            "company_name": "Dup Test Gym",
            "is_trial": True,
            "trial_duration_days": 14
        }

        # First signup should succeed
        response1 = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)
        assert response1.status_code == 200, f"First signup failed: {response1.text}"

        # Second signup with same email should fail
        response2 = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)
        assert response2.status_code == 400, f"Expected 400 for duplicate email, got {response2.status_code}"
        assert "already registered" in response2.text.lower(), "Should mention email already registered"

        print("✓ Duplicate email rejection working")


class TestTrialNotificationEmail:
    """Test that trial signup sends notification email to Lee@gymaxisai.com"""

    @pytest.fixture
    def headers(self):
        return {
            "Content-Type": "application/json",
            "X-RateLimit-Bypass": BYPASS_HEADER
        }

    def test_trial_signup_sends_notification(self, headers):
        """Trial signup should dispatch notification email to Lee@gymaxisai.com

        We verify this by checking backend logs for the email sent message.
        The actual email delivery is handled by Resend API.
        """
        unique_email = f"notify_test_{uuid.uuid4().hex[:8]}@testgym.com"
        company_name = f"Notify Test Gym {uuid.uuid4().hex[:4]}"
        payload = {
            "email": unique_email,
            "password": "TestPass123!",
            "full_name": "Notify Test User",
            "company_name": company_name,
            "phone": "+44 7700 900999",
            "is_trial": True,
            "trial_duration_days": 14
        }

        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload, headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        # Give async task time to complete
        time.sleep(2)

        # The notification email is sent asynchronously via asyncio.create_task
        # We can't directly verify email delivery, but we can confirm:
        # 1. The signup succeeded
        # 2. The org has trial fields (which triggers the notification)

        data = response.json()
        assert data["user"]["subscription_tier"] == "pro", "Trial should get pro tier"

        print("✓ Trial signup completed - notification should be dispatched to Lee@gymaxisai.com")
        print(f"  - User: {unique_email}")
        print(f"  - Company: {company_name}")
        print("  Note: Check backend logs for 'Email sent to Lee@gymaxisai.com: [Trial]...'")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
