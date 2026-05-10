"""
Test suite for Phase 1 Online Member Self-Signup (iteration 216g)

Tests:
- Public signup endpoints (no auth): branding, plans, draft, parq, checkout
- Stripe Connect endpoints (master admin only): status, onboarding-link, link-existing, disconnect

Note: Stripe Connect calls hit the real Stripe API. If POST /onboarding-link returns 400 with a 
Stripe error message, that's NOT a backend bug — it's expected. The bug would be a 500 / unhandled exception.
"""

import os
import pytest
import requests
import uuid

# Get BASE_URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

# Test org IDs
STRONG_FITNESS_ORG_ID = "6e2b80c5-05b0-4a8a-a06a-2af52ee7cd8c"  # Bob's org with slug
STRONG_FITNESS_SLUG = "strong-fitness-test"
GYMAXIS_MASTER_ORG_ID = "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"  # Master admin org

# Credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
BOB_EMAIL = "bob@knockers.com"
BOB_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Master admin login failed: {response.status_code} - {response.text}")
    return response.json()["token"]


@pytest.fixture(scope="module")
def bob_token():
    """Get Bob's JWT token (non-master-admin)"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": BOB_EMAIL, "password": BOB_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Bob login failed: {response.status_code} - {response.text}")
    return response.json()["token"]


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    """Headers with master admin auth"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {master_admin_token}"
    }


@pytest.fixture(scope="module")
def bob_headers(bob_token):
    """Headers with Bob's auth (non-master-admin)"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bob_token}"
    }


# ============================================================================
# PUBLIC SIGNUP ENDPOINTS (NO AUTH REQUIRED)
# ============================================================================

class TestPublicSignupBranding:
    """GET /api/public/signup/{slug}/branding — returns 200 with gym info + 7 PARQ questions"""
    
    def test_branding_returns_200_with_gym_info(self):
        """Test branding endpoint returns gym info and PARQ questions"""
        response = requests.get(f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/branding")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "gym" in data, "Response should contain 'gym' key"
        assert "parq_questions" in data, "Response should contain 'parq_questions' key"
        
        gym = data["gym"]
        assert "id" in gym, "Gym should have 'id'"
        assert "name" in gym, "Gym should have 'name'"
        assert "stripe_ready" in gym, "Gym should have 'stripe_ready' boolean"
        
        parq = data["parq_questions"]
        assert isinstance(parq, list), "PARQ questions should be a list"
        assert len(parq) == 7, f"Expected 7 PARQ questions, got {len(parq)}"
        
        # Verify PARQ question structure
        for q in parq:
            assert "id" in q, "Each PARQ question should have 'id'"
            assert "q" in q, "Each PARQ question should have 'q' (question text)"
        
        print(f"✓ Branding returned for gym: {gym.get('name')}, PARQ count: {len(parq)}")
    
    def test_branding_with_slug(self):
        """Test branding endpoint works with slug instead of org_id"""
        response = requests.get(f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_SLUG}/branding")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["gym"]["id"] == STRONG_FITNESS_ORG_ID, "Slug should resolve to correct org"
        print(f"✓ Slug '{STRONG_FITNESS_SLUG}' resolved correctly")
    
    def test_branding_invalid_slug_returns_404(self):
        """Test branding endpoint returns 404 for invalid slug"""
        response = requests.get(f"{BASE_URL}/api/public/signup/nonexistent-gym-xyz/branding")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Invalid slug returns 404")


class TestPublicSignupPlans:
    """GET /api/public/signup/{slug}/plans — returns published plans for the gym"""
    
    def test_plans_returns_200(self):
        """Test plans endpoint returns 200 (even if empty)"""
        response = requests.get(f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/plans")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "plans" in data, "Response should contain 'plans' key"
        assert "count" in data, "Response should contain 'count' key"
        assert isinstance(data["plans"], list), "Plans should be a list"
        assert data["count"] == len(data["plans"]), "Count should match plans length"
        
        print(f"✓ Plans endpoint returned {data['count']} plans")
        
        # If plans exist, verify structure
        if data["plans"]:
            plan = data["plans"][0]
            expected_fields = ["id", "name", "monthly_price_pence", "joining_fee_pence", "contract_months"]
            for field in expected_fields:
                assert field in plan, f"Plan should have '{field}'"
            print(f"  First plan: {plan.get('name')} - £{plan.get('monthly_price_pence', 0)/100:.2f}/month")
    
    def test_plans_invalid_slug_returns_404(self):
        """Test plans endpoint returns 404 for invalid slug"""
        response = requests.get(f"{BASE_URL}/api/public/signup/nonexistent-gym-xyz/plans")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Invalid slug returns 404")


class TestPublicSignupDraft:
    """POST /api/public/signup/{slug}/draft — saves partial signup with email + step + plan_id"""
    
    def test_draft_creates_new_draft(self):
        """Test creating a new signup draft"""
        test_email = f"test.signup.{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": test_email,
            "step": "details",
            "plan_id": "test-plan-123",
            "first_name": "Test",
            "last_name": "User"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json=payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("ok") is True, "Response should have ok=true"
        assert "draft_id" in data, "Response should contain draft_id"
        
        draft_id = data["draft_id"]
        print(f"✓ Draft created with id: {draft_id}")
        return draft_id
    
    def test_draft_idempotent_on_same_draft_id(self):
        """Test that subsequent calls with same draft_id update instead of create"""
        test_email = f"test.idempotent.{uuid.uuid4().hex[:8]}@example.com"
        draft_id = str(uuid.uuid4())
        
        # First call
        payload1 = {
            "email": test_email,
            "draft_id": draft_id,
            "step": "details",
            "first_name": "First"
        }
        response1 = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json=payload1
        )
        assert response1.status_code == 200
        assert response1.json()["draft_id"] == draft_id
        
        # Second call with same draft_id (should update)
        payload2 = {
            "email": test_email,
            "draft_id": draft_id,
            "step": "parq",
            "first_name": "Updated"
        }
        response2 = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json=payload2
        )
        assert response2.status_code == 200
        assert response2.json()["draft_id"] == draft_id
        
        print(f"✓ Draft idempotent update works for draft_id: {draft_id}")
    
    def test_draft_requires_valid_email(self):
        """Test that draft requires a valid email"""
        payload = {
            "email": "invalid-email",
            "step": "details"
        }
        response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json=payload
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Invalid email rejected with 400")
    
    def test_draft_requires_email(self):
        """Test that draft requires email field"""
        payload = {
            "step": "details"
        }
        response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json=payload
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Missing email rejected with 400")


class TestPublicSignupParq:
    """POST /api/public/signup/{slug}/parq — saves PARQ answers, sets clearance_required=true if any 'yes'"""
    
    def test_parq_saves_answers_no_flags(self):
        """Test PARQ submission with all 'no' answers"""
        # First create a draft
        test_email = f"test.parq.{uuid.uuid4().hex[:8]}@example.com"
        draft_response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json={"email": test_email, "step": "parq"}
        )
        draft_id = draft_response.json()["draft_id"]
        
        # Submit PARQ with all false
        parq_payload = {
            "draft_id": draft_id,
            "answers": {
                "heart": False,
                "chest_pain": False,
                "dizzy": False,
                "bone_joint": False,
                "medication": False,
                "other": False,
                "pregnancy": False
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/parq",
            json=parq_payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("ok") is True
        assert data.get("clearance_required") is False, "No flags should mean clearance_required=false"
        print("✓ PARQ with all 'no' answers: clearance_required=false")
    
    def test_parq_flags_when_yes_answer(self):
        """Test PARQ submission with at least one 'yes' answer sets clearance_required=true"""
        # First create a draft
        test_email = f"test.parq.flagged.{uuid.uuid4().hex[:8]}@example.com"
        draft_response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json={"email": test_email, "step": "parq"}
        )
        draft_id = draft_response.json()["draft_id"]
        
        # Submit PARQ with one true answer
        parq_payload = {
            "draft_id": draft_id,
            "answers": {
                "heart": True,  # This should flag
                "chest_pain": False,
                "dizzy": False,
                "bone_joint": False,
                "medication": False,
                "other": False,
                "pregnancy": False
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/parq",
            json=parq_payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("ok") is True
        assert data.get("clearance_required") is True, "Any 'yes' should mean clearance_required=true"
        print("✓ PARQ with 'yes' answer: clearance_required=true")
    
    def test_parq_requires_draft_id(self):
        """Test PARQ requires draft_id"""
        parq_payload = {
            "answers": {"heart": False}
        }
        response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/parq",
            json=parq_payload
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Missing draft_id rejected with 400")


class TestPublicSignupCheckout:
    """POST /api/public/signup/{slug}/checkout — fails 400 when org has no stripe_account_id"""
    
    def test_checkout_fails_without_stripe_account(self):
        """Test checkout returns 400 when gym has not connected payments"""
        # First create a draft
        test_email = f"test.checkout.{uuid.uuid4().hex[:8]}@example.com"
        draft_response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json={"email": test_email, "step": "payment"}
        )
        draft_id = draft_response.json()["draft_id"]
        
        # Try to create checkout session
        checkout_payload = {
            "draft_id": draft_id,
            "plan_id": "some-plan-id"
        }
        response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/checkout",
            json=checkout_payload
        )
        
        # Should fail with 400 because org has no stripe_account_id
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        # Verify error message mentions payments not connected
        error_text = response.text.lower()
        assert "not connected" in error_text or "payment" in error_text, \
            f"Error should mention payments not connected: {response.text}"
        
        print("✓ Checkout correctly fails 400 when gym has no stripe_account_id")
    
    def test_checkout_requires_draft_id_and_plan_id(self):
        """Test checkout requires both draft_id and plan_id"""
        # Missing plan_id
        response1 = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/checkout",
            json={"draft_id": "some-draft"}
        )
        assert response1.status_code == 400, f"Expected 400 for missing plan_id, got {response1.status_code}"
        
        # Missing draft_id
        response2 = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/checkout",
            json={"plan_id": "some-plan"}
        )
        assert response2.status_code == 400, f"Expected 400 for missing draft_id, got {response2.status_code}"
        
        print("✓ Checkout requires both draft_id and plan_id")


class TestPublicSignupStatus:
    """GET /api/public/signup/status/{session_id} — returns 404 for non-existent session"""
    
    def test_status_returns_404_for_fake_session(self):
        """Test status endpoint returns 404 for non-existent session"""
        fake_session_id = "cs_test_fake_session_12345"
        response = requests.get(f"{BASE_URL}/api/public/signup/status/{fake_session_id}")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Status returns 404 for non-existent session")


# ============================================================================
# STRIPE CONNECT ENDPOINTS (MASTER ADMIN ONLY)
# ============================================================================

class TestStripeConnectStatus:
    """GET /api/stripe-connect/orgs/{org}/status — master admin only"""
    
    def test_status_returns_connected_false_for_unconnected_org(self, master_admin_headers):
        """Test status returns connected:false for org without stripe_account_id"""
        response = requests.get(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/status",
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "connected" in data, "Response should have 'connected' field"
        assert "platform_fee_percent" in data, "Response should have 'platform_fee_percent' field"
        assert data["platform_fee_percent"] == 1.0, f"Platform fee should be 1.0%, got {data['platform_fee_percent']}"
        
        # Org likely not connected yet
        if not data["connected"]:
            assert data.get("account") is None, "Unconnected org should have null account"
            print(f"✓ Status: connected=false, platform_fee_percent=1.0%")
        else:
            print(f"✓ Status: connected=true, platform_fee_percent=1.0%")
    
    def test_status_requires_master_admin(self, bob_headers):
        """Test status endpoint requires master admin"""
        response = requests.get(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/status",
            headers=bob_headers
        )
        # Should be 403 Forbidden for non-master-admin
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Status endpoint requires master admin (403 for non-admin)")
    
    def test_status_returns_404_for_invalid_org(self, master_admin_headers):
        """Test status returns 404 for non-existent org"""
        fake_org_id = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/stripe-connect/orgs/{fake_org_id}/status",
            headers=master_admin_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Status returns 404 for non-existent org")


class TestStripeConnectOnboardingLink:
    """POST /api/stripe-connect/orgs/{org}/onboarding-link — master admin only"""
    
    def test_onboarding_link_creates_express_account(self, master_admin_headers):
        """Test onboarding-link creates Stripe Express account or returns Stripe error (not 500)"""
        response = requests.post(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/onboarding-link",
            headers=master_admin_headers,
            json={"country": "GB"}
        )
        
        # Accept 200 (success) or 400 (Stripe error) - NOT 500
        assert response.status_code in [200, 400], \
            f"Expected 200 or 400, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "url" in data, "Success response should have 'url'"
            assert "account_id" in data, "Success response should have 'account_id'"
            assert data["account_id"].startswith("acct_"), "Account ID should start with 'acct_'"
            print(f"✓ Onboarding link created: account_id={data['account_id']}")
        else:
            # 400 with Stripe error is acceptable (rate limits, test key restrictions, etc.)
            error_text = response.text.lower()
            assert "stripe" in error_text or "error" in error_text, \
                f"400 should contain Stripe error message: {response.text}"
            print(f"✓ Onboarding link returned 400 with Stripe error (expected): {response.text[:200]}")
    
    def test_onboarding_link_requires_master_admin(self, bob_headers):
        """Test onboarding-link requires master admin"""
        response = requests.post(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/onboarding-link",
            headers=bob_headers,
            json={}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Onboarding-link requires master admin (403 for non-admin)")


class TestStripeConnectLinkExisting:
    """POST /api/stripe-connect/orgs/{org}/link-existing — accepts acct_… id or rejects invalid format"""
    
    def test_link_existing_rejects_invalid_format(self, master_admin_headers):
        """Test link-existing rejects account_id not starting with 'acct_'"""
        response = requests.post(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/link-existing",
            headers=master_admin_headers,
            json={"account_id": "invalid_account_123"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        error_text = response.text.lower()
        assert "acct_" in error_text, f"Error should mention 'acct_' format: {response.text}"
        print("✓ Link-existing rejects invalid format (must start with 'acct_')")
    
    def test_link_existing_with_fake_acct_returns_stripe_error(self, master_admin_headers):
        """Test link-existing with fake acct_id returns 400 with Stripe error"""
        response = requests.post(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/link-existing",
            headers=master_admin_headers,
            json={"account_id": "acct_fake_12345"}
        )
        # Should be 400 with Stripe error (account not found)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        error_text = response.text.lower()
        assert "could not retrieve" in error_text or "stripe" in error_text or "account" in error_text, \
            f"Error should mention Stripe retrieval failure: {response.text}"
        print("✓ Link-existing with fake acct_id returns 400 with Stripe error")
    
    def test_link_existing_requires_master_admin(self, bob_headers):
        """Test link-existing requires master admin"""
        response = requests.post(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/link-existing",
            headers=bob_headers,
            json={"account_id": "acct_test123"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Link-existing requires master admin (403 for non-admin)")


class TestStripeConnectDisconnect:
    """DELETE /api/stripe-connect/orgs/{org}/disconnect — clears stripe_account_id"""
    
    def test_disconnect_clears_stripe_account(self, master_admin_headers):
        """Test disconnect endpoint clears stripe_account_id"""
        # Note: We don't actually want to disconnect if an account was created
        # Just verify the endpoint works and returns 200
        response = requests.delete(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/disconnect",
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("ok") is True, "Response should have ok=true"
        print("✓ Disconnect endpoint returns 200 with ok=true")
        
        # Verify status now shows disconnected
        status_response = requests.get(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/status",
            headers=master_admin_headers
        )
        assert status_response.status_code == 200
        assert status_response.json().get("connected") is False, "After disconnect, connected should be false"
        print("✓ After disconnect, status shows connected=false")
    
    def test_disconnect_requires_master_admin(self, bob_headers):
        """Test disconnect requires master admin"""
        response = requests.delete(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/disconnect",
            headers=bob_headers
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Disconnect requires master admin (403 for non-admin)")


class TestStripeConnectDashboardLink:
    """POST /api/stripe-connect/orgs/{org}/dashboard-link — requires connected account"""
    
    def test_dashboard_link_fails_without_connected_account(self, master_admin_headers):
        """Test dashboard-link returns 400 when org has no connected account"""
        # First ensure org is disconnected
        requests.delete(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/disconnect",
            headers=master_admin_headers
        )
        
        response = requests.post(
            f"{BASE_URL}/api/stripe-connect/orgs/{STRONG_FITNESS_ORG_ID}/dashboard-link",
            headers=master_admin_headers
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        error_text = response.text.lower()
        assert "no connected" in error_text or "stripe" in error_text, \
            f"Error should mention no connected account: {response.text}"
        print("✓ Dashboard-link fails 400 when org has no connected account")


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestFullSignupFlow:
    """Test the complete signup flow (without actual payment)"""
    
    def test_full_flow_up_to_checkout(self):
        """Test complete flow: branding → plans → draft → parq → checkout (fails at payment)"""
        # 1. Get branding
        branding_response = requests.get(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/branding"
        )
        assert branding_response.status_code == 200
        gym_name = branding_response.json()["gym"]["name"]
        parq_count = len(branding_response.json()["parq_questions"])
        print(f"Step 1: Got branding for '{gym_name}', {parq_count} PARQ questions")
        
        # 2. Get plans
        plans_response = requests.get(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/plans"
        )
        assert plans_response.status_code == 200
        plans = plans_response.json()["plans"]
        print(f"Step 2: Got {len(plans)} plans")
        
        # 3. Create draft
        test_email = f"test.fullflow.{uuid.uuid4().hex[:8]}@example.com"
        draft_response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/draft",
            json={
                "email": test_email,
                "step": "details",
                "first_name": "Test",
                "last_name": "Flow",
                "phone": "+447700900123"
            }
        )
        assert draft_response.status_code == 200
        draft_id = draft_response.json()["draft_id"]
        print(f"Step 3: Created draft {draft_id}")
        
        # 4. Submit PARQ
        parq_response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/parq",
            json={
                "draft_id": draft_id,
                "answers": {
                    "heart": False,
                    "chest_pain": False,
                    "dizzy": False,
                    "bone_joint": False,
                    "medication": False,
                    "other": False,
                    "pregnancy": False
                }
            }
        )
        assert parq_response.status_code == 200
        clearance = parq_response.json()["clearance_required"]
        print(f"Step 4: PARQ submitted, clearance_required={clearance}")
        
        # 5. Try checkout (should fail because no stripe account)
        checkout_response = requests.post(
            f"{BASE_URL}/api/public/signup/{STRONG_FITNESS_ORG_ID}/checkout",
            json={
                "draft_id": draft_id,
                "plan_id": plans[0]["id"] if plans else "test-plan"
            }
        )
        assert checkout_response.status_code == 400, "Checkout should fail without Stripe account"
        print("Step 5: Checkout correctly failed (no Stripe account connected)")
        
        print("✓ Full signup flow test complete (up to payment)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
