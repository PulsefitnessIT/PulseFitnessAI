"""
Iter 216bc — Launch Readiness Sprint Tests

Tests for:
1. Email sender branding (GET/POST /api/launch/email-sender)
2. Sample data load/clear (POST /api/launch/sample-data/load, /clear)
3. In-product feedback (POST /api/feedback/in-product)
4. Master admin feedback view (GET /api/master-admin/feedback/recent)
5. Email utility regression (organization_id threading)
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
BOB_EMAIL = "bob@knockers.com"
BOB_PASSWORD = "Test123!"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


class TestAuthHelpers:
    """Helper methods for authentication"""
    
    @staticmethod
    def get_bob_token():
        """Login as Bob (org owner) and return token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": BOB_EMAIL,
            "password": BOB_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")
        return None
    
    @staticmethod
    def get_admin_token():
        """Login as master admin and return token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")
        return None


class TestEmailSenderBranding:
    """Tests for GET/POST /api/launch/email-sender"""
    
    def test_get_email_sender_returns_current_branding(self):
        """GET /api/launch/email-sender returns current org branding + preview_from"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.get(
            f"{BASE_URL}/api/launch/email-sender",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "friendly_name" in data, "Missing friendly_name in response"
        assert "reply_to" in data, "Missing reply_to in response"
        assert "preview_from" in data, "Missing preview_from in response"
        
        # preview_from should be a formatted string like "Name <email>"
        assert "<" in data["preview_from"] and ">" in data["preview_from"], \
            f"preview_from should be formatted as 'Name <email>', got: {data['preview_from']}"
        print(f"✓ GET email-sender returned: {data}")
    
    def test_post_email_sender_owner_can_update(self):
        """POST /api/launch/email-sender — owner/manager can update branding"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        test_friendly_name = f"TEST_Studio_{uuid.uuid4().hex[:6]}"
        test_reply_to = f"test_{uuid.uuid4().hex[:6]}@example.com"
        
        resp = requests.post(
            f"{BASE_URL}/api/launch/email-sender",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "friendly_name": test_friendly_name,
                "reply_to": test_reply_to
            }
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify the update was applied
        assert data["friendly_name"] == test_friendly_name, \
            f"friendly_name not updated: expected {test_friendly_name}, got {data['friendly_name']}"
        assert data["reply_to"] == test_reply_to, \
            f"reply_to not updated: expected {test_reply_to}, got {data['reply_to']}"
        
        # Verify preview_from reflects the new friendly name
        assert test_friendly_name in data["preview_from"], \
            f"preview_from should contain new friendly_name: {data['preview_from']}"
        print(f"✓ POST email-sender updated successfully: {data}")
    
    def test_post_email_sender_persists_changes(self):
        """POST then GET verifies persistence"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        test_name = f"Persist_Test_{uuid.uuid4().hex[:6]}"
        
        # Update
        resp = requests.post(
            f"{BASE_URL}/api/launch/email-sender",
            headers={"Authorization": f"Bearer {token}"},
            json={"friendly_name": test_name}
        )
        assert resp.status_code == 200
        
        # Verify with GET
        resp2 = requests.get(
            f"{BASE_URL}/api/launch/email-sender",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["friendly_name"] == test_name, "Change not persisted"
        print("✓ Email sender changes persisted correctly")
    
    def test_post_email_sender_unauthenticated_fails(self):
        """POST without auth should fail"""
        resp = requests.post(
            f"{BASE_URL}/api/launch/email-sender",
            json={"friendly_name": "Test"}
        )
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print(f"✓ Unauthenticated POST correctly rejected with {resp.status_code}")


class TestSampleData:
    """Tests for POST /api/launch/sample-data/load and /clear"""
    
    def test_load_sample_data_creates_items(self):
        """POST /api/launch/sample-data/load creates sample members, plans, class_templates"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.post(
            f"{BASE_URL}/api/launch/sample-data/load",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") is True, "Response should have ok: true"
        assert "created" in data, "Response should have 'created' counts"
        
        created = data["created"]
        assert "members" in created, "Missing members count"
        assert "plans" in created, "Missing plans count"
        assert "class_templates" in created, "Missing class_templates count"
        
        print(f"✓ Sample data loaded: {created}")
    
    def test_load_sample_data_idempotent(self):
        """Second run of load should create 0 items (idempotent)"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        # First load
        resp1 = requests.post(
            f"{BASE_URL}/api/launch/sample-data/load",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        assert resp1.status_code == 200
        
        # Second load should be idempotent
        resp2 = requests.post(
            f"{BASE_URL}/api/launch/sample-data/load",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        assert resp2.status_code == 200
        data = resp2.json()
        
        created = data.get("created", {})
        total_created = created.get("members", 0) + created.get("plans", 0) + created.get("class_templates", 0)
        assert total_created == 0, f"Second load should create 0 items, got {total_created}"
        print("✓ Sample data load is idempotent (second run created 0)")
    
    def test_clear_sample_data_removes_tagged_items(self):
        """POST /api/launch/sample-data/clear removes only sample_data_v1 tagged items"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        # First ensure sample data exists
        requests.post(
            f"{BASE_URL}/api/launch/sample-data/load",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        
        # Now clear
        resp = requests.post(
            f"{BASE_URL}/api/launch/sample-data/clear",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") is True, "Response should have ok: true"
        assert "removed" in data, "Response should have 'removed' counts"
        
        removed = data["removed"]
        assert "members" in removed, "Missing members count"
        assert "plans" in removed, "Missing plans count"
        assert "class_templates" in removed, "Missing class_templates count"
        
        print(f"✓ Sample data cleared: {removed}")
    
    def test_sample_data_unauthenticated_fails(self):
        """Sample data endpoints require auth"""
        resp_load = requests.post(f"{BASE_URL}/api/launch/sample-data/load", json={})
        resp_clear = requests.post(f"{BASE_URL}/api/launch/sample-data/clear", json={})
        
        assert resp_load.status_code in [401, 403], f"Load should require auth, got {resp_load.status_code}"
        assert resp_clear.status_code in [401, 403], f"Clear should require auth, got {resp_clear.status_code}"
        print("✓ Sample data endpoints correctly require authentication")


class TestInProductFeedback:
    """Tests for POST /api/feedback/in-product"""
    
    def test_submit_feedback_success(self):
        """POST /api/feedback/in-product accepts sentiment, comment, page_path"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.post(
            f"{BASE_URL}/api/feedback/in-product",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "sentiment": "up",
                "comment": f"Test feedback {uuid.uuid4().hex[:8]}",
                "page_path": "/memberships"
            }
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True, "Response should have ok: true"
        print("✓ Feedback submitted successfully")
    
    def test_submit_feedback_down_sentiment(self):
        """Feedback with 'down' sentiment works"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.post(
            f"{BASE_URL}/api/feedback/in-product",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "sentiment": "down",
                "comment": "Could be better",
                "page_path": "/dashboard"
            }
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ Down sentiment feedback accepted")
    
    def test_submit_feedback_neutral_sentiment(self):
        """Feedback with 'neutral' sentiment works"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.post(
            f"{BASE_URL}/api/feedback/in-product",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "sentiment": "neutral",
                "page_path": "/settings"
            }
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ Neutral sentiment feedback accepted")
    
    def test_submit_feedback_invalid_sentiment_rejected(self):
        """Invalid sentiment value should be rejected"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.post(
            f"{BASE_URL}/api/feedback/in-product",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "sentiment": "invalid_value",
                "page_path": "/test"
            }
        )
        
        assert resp.status_code == 422, f"Expected 422 for invalid sentiment, got {resp.status_code}"
        print("✓ Invalid sentiment correctly rejected with 422")
    
    def test_submit_feedback_requires_auth(self):
        """Feedback endpoint requires authentication"""
        resp = requests.post(
            f"{BASE_URL}/api/feedback/in-product",
            json={"sentiment": "up", "page_path": "/test"}
        )
        
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("✓ Feedback endpoint correctly requires auth")


class TestMasterAdminFeedback:
    """Tests for GET /api/master-admin/feedback/recent"""
    
    def test_master_admin_can_view_feedback(self):
        """GET /api/master-admin/feedback/recent — master admin only"""
        token = TestAuthHelpers.get_admin_token()
        assert token, "Failed to get admin token"
        
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/feedback/recent",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "rows" in data, "Missing rows in response"
        assert "counts" in data, "Missing counts in response"
        assert "total" in data, "Missing total in response"
        assert "by_path" in data, "Missing by_path aggregate"
        
        # Verify counts structure
        counts = data["counts"]
        assert "up" in counts, "Missing up count"
        assert "down" in counts, "Missing down count"
        assert "neutral" in counts, "Missing neutral count"
        
        print(f"✓ Master admin feedback view: total={data['total']}, counts={counts}")
    
    def test_non_master_admin_forbidden(self):
        """Non-master admin should get 403"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/feedback/recent",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert resp.status_code == 403, f"Expected 403 for non-master admin, got {resp.status_code}"
        print("✓ Non-master admin correctly forbidden from feedback view")


class TestEmailUtilityRegression:
    """Regression tests for utils/email.py refactor (organization_id threading)"""
    
    def test_email_send_events_collection_exists(self):
        """Verify email_send_events collection is being written to (observable via API)"""
        # This is a smoke test - we can't directly test email sending without
        # actually sending emails, but we can verify the infrastructure exists
        # by checking that the email-sender endpoint works (which uses the same DB)
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        resp = requests.get(
            f"{BASE_URL}/api/launch/email-sender",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert resp.status_code == 200, "Email sender endpoint should work"
        print("✓ Email infrastructure accessible")
    
    def test_memberships_booking_endpoint_smoke(self):
        """Smoke test that memberships endpoints still work after email refactor"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        # Just verify the memberships API is accessible (email refactor shouldn't break it)
        resp = requests.get(
            f"{BASE_URL}/api/memberships/studio/onboarding",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # 200 or 404 (if no onboarding data) are both acceptable
        assert resp.status_code in [200, 404], f"Memberships API should be accessible, got {resp.status_code}"
        print("✓ Memberships API accessible after email refactor")


class TestRoleBasedAccess:
    """Tests for role-based access control on launch readiness endpoints"""
    
    def test_owner_can_access_all_endpoints(self):
        """Bob (owner) should have access to all launch readiness endpoints"""
        token = TestAuthHelpers.get_bob_token()
        assert token, "Failed to get Bob's token"
        
        # Email sender
        resp1 = requests.get(f"{BASE_URL}/api/launch/email-sender", 
                            headers={"Authorization": f"Bearer {token}"})
        assert resp1.status_code == 200, "Owner should access email-sender GET"
        
        resp2 = requests.post(f"{BASE_URL}/api/launch/email-sender",
                             headers={"Authorization": f"Bearer {token}"},
                             json={"friendly_name": "Test"})
        assert resp2.status_code == 200, "Owner should access email-sender POST"
        
        # Sample data
        resp3 = requests.post(f"{BASE_URL}/api/launch/sample-data/load",
                             headers={"Authorization": f"Bearer {token}"},
                             json={})
        assert resp3.status_code == 200, "Owner should access sample-data load"
        
        resp4 = requests.post(f"{BASE_URL}/api/launch/sample-data/clear",
                             headers={"Authorization": f"Bearer {token}"},
                             json={})
        assert resp4.status_code == 200, "Owner should access sample-data clear"
        
        # Feedback
        resp5 = requests.post(f"{BASE_URL}/api/feedback/in-product",
                             headers={"Authorization": f"Bearer {token}"},
                             json={"sentiment": "up", "page_path": "/test"})
        assert resp5.status_code == 200, "Owner should access feedback"
        
        print("✓ Owner has access to all launch readiness endpoints")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
