"""
Iteration 174 Tests - Referral Campaign Widget + Mobile Responsiveness

Tests:
1. GET /api/member/referral-progress - member-auth only, returns campaign progress
2. POST /api/member/referral-progress/dismiss - persists dismissal timestamp
3. Auth checks: 401 without token, 403 with operator token
4. Emma (mbr-emma) with 3 earned referrals: gap=2, next_goal.threshold=5, percent≈60
5. Regression tests for iteration-173 features
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
MEMBER_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_PASSWORD = "Member2026!"
BRAG_SLUG = "pulse-leeds"


class TestReferralProgressEndpoint:
    """Tests for GET /api/member/referral-progress"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get member token for Emma"""
        # Login as member
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert resp.status_code == 200, f"Member login failed: {resp.text}"
        self.member_token = resp.json()["token"]
        self.member_headers = {"Authorization": f"Bearer {self.member_token}"}

    def test_referral_progress_returns_expected_fields(self):
        """GET /api/member/referral-progress returns all expected fields"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        # Check all required fields exist
        assert "code" in data, "Missing 'code' field"
        assert "earned" in data, "Missing 'earned' field"
        assert "total" in data, "Missing 'total' field"
        assert "goals" in data, "Missing 'goals' field"
        assert "next_goal" in data, "Missing 'next_goal' field"
        assert "gap" in data, "Missing 'gap' field"
        assert "percent" in data, "Missing 'percent' field"
        assert "campaign_dismissed_at" in data, "Missing 'campaign_dismissed_at' field"

        # Check goals structure (default ladder 1/3/5)
        assert isinstance(data["goals"], list), "goals should be a list"
        assert len(data["goals"]) >= 3, "Should have at least 3 goals in default ladder"

        # Check goal structure
        for goal in data["goals"]:
            assert "threshold" in goal, "Goal missing 'threshold'"
            assert "reward" in goal, "Goal missing 'reward'"
            assert "reward_pence" in goal, "Goal missing 'reward_pence'"

        print(f"Referral progress response: {data}")

    def test_emma_has_3_earned_referrals(self):
        """Emma (mbr-emma) should have 3 earned referrals based on seed data"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200
        data = resp.json()

        # Emma should have 3 earned referrals per seed data
        assert data["earned"] == 3, f"Expected 3 earned referrals, got {data['earned']}"
        print(f"Emma's earned referrals: {data['earned']}")

    def test_emma_gap_is_2(self):
        """With 3 earned, next goal is 5, so gap should be 2"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200
        data = resp.json()

        # With 3 earned, next goal threshold is 5, gap = 5 - 3 = 2
        assert data["gap"] == 2, f"Expected gap=2, got {data['gap']}"
        print(f"Emma's gap to next goal: {data['gap']}")

    def test_emma_next_goal_threshold_is_5(self):
        """Emma's next goal should be threshold=5 (£20 credit)"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["next_goal"] is not None, "next_goal should not be None"
        assert data["next_goal"]["threshold"] == 5, f"Expected next_goal.threshold=5, got {data['next_goal']['threshold']}"
        assert "£20" in data["next_goal"]["reward"], f"Expected £20 credit reward, got {data['next_goal']['reward']}"
        print(f"Emma's next goal: {data['next_goal']}")

    def test_emma_percent_is_60(self):
        """With 3 earned out of 5 target, percent should be 60"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200
        data = resp.json()

        # percent = 100 * 3 / 5 = 60
        assert data["percent"] == 60, f"Expected percent=60, got {data['percent']}"
        print(f"Emma's progress percent: {data['percent']}%")

    def test_401_without_token(self):
        """GET /api/member/referral-progress returns 401 without token"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("401 without token: PASS")


class TestReferralProgressAuthWithOperator:
    """Tests for auth rejection with operator token - separate class to avoid rate limit issues"""

    def test_401_with_operator_token(self):
        """GET /api/member/referral-progress returns 401 with operator token (not member token)"""
        # Skip if rate limited - this is a secondary test
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited - skipping operator token test")
        assert resp.status_code == 200, f"Operator login failed: {resp.text}"
        operator_headers = {"Authorization": f"Bearer {resp.json()['token']}"}

        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=operator_headers)
        # Operator tokens have kind != 'member', so should fail
        assert resp.status_code == 401, f"Expected 401 with operator token, got {resp.status_code}"
        print("401 with operator token: PASS")


class TestReferralProgressDismiss:
    """Tests for POST /api/member/referral-progress/dismiss"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get member token for Emma"""
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert resp.status_code == 200
        self.member_token = resp.json()["token"]
        self.member_headers = {"Authorization": f"Bearer {self.member_token}"}

    def test_dismiss_returns_ok(self):
        """POST /api/member/referral-progress/dismiss returns {ok: true}"""
        resp = requests.post(f"{BASE_URL}/api/member/referral-progress/dismiss", json={}, headers=self.member_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True, f"Expected ok=true, got {data}"
        print("Dismiss returns ok: PASS")

    def test_dismiss_persists_timestamp(self):
        """After dismiss, campaign_dismissed_at should be set"""
        # First dismiss
        resp = requests.post(f"{BASE_URL}/api/member/referral-progress/dismiss", json={}, headers=self.member_headers)
        assert resp.status_code == 200

        # Then check progress
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["campaign_dismissed_at"] is not None, "campaign_dismissed_at should be set after dismiss"
        print(f"Dismiss persisted at: {data['campaign_dismissed_at']}")

    def test_dismiss_401_without_token(self):
        """POST /api/member/referral-progress/dismiss returns 401 without token"""
        resp = requests.post(f"{BASE_URL}/api/member/referral-progress/dismiss", json={})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("Dismiss 401 without token: PASS")


class TestDefaultReferralGoals:
    """Tests for default referral goals ladder (1/3/5)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert resp.status_code == 200
        self.member_headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    def test_default_ladder_thresholds(self):
        """Default ladder should be 1, 3, 5"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200
        data = resp.json()

        thresholds = [g["threshold"] for g in data["goals"]]
        assert 1 in thresholds, "Missing threshold 1"
        assert 3 in thresholds, "Missing threshold 3"
        assert 5 in thresholds, "Missing threshold 5"
        print(f"Default ladder thresholds: {thresholds}")

    def test_default_ladder_rewards(self):
        """Default ladder rewards: £5 credit, 1 month free, £20 credit"""
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress", headers=self.member_headers)
        assert resp.status_code == 200
        data = resp.json()

        rewards = {g["threshold"]: g["reward"] for g in data["goals"]}
        assert "£5" in rewards.get(1, ""), f"Threshold 1 should have £5 credit, got {rewards.get(1)}"
        assert "month" in rewards.get(3, "").lower(), f"Threshold 3 should have month free, got {rewards.get(3)}"
        assert "£20" in rewards.get(5, ""), f"Threshold 5 should have £20 credit, got {rewards.get(5)}"
        print(f"Default ladder rewards: {rewards}")


class TestIteration173Regression:
    """Regression tests for iteration-173 features"""

    @pytest.fixture(autouse=True)
    def setup(self):
        # Operator login - skip if rate limited
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited - skipping regression tests")
        assert resp.status_code == 200
        self.operator_headers = {"Authorization": f"Bearer {resp.json()['token']}"}

        # Member login
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert resp.status_code == 200
        self.member_headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    def test_analytics_referrals_endpoint(self):
        """GET /api/memberships/analytics/referrals still works"""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=self.operator_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "kpis" in data
        assert "top_referrers" in data
        print("Analytics referrals endpoint: PASS")

    def test_member_referrals_endpoint(self):
        """GET /api/member/referrals still works"""
        resp = requests.get(f"{BASE_URL}/api/member/referrals", headers=self.member_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "code" in data
        assert "stats" in data
        print("Member referrals endpoint: PASS")

    def test_brag_page_endpoint(self):
        """GET /api/m/{slug}/brag still works"""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/brag")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        # Check for organization.name or name at top level
        assert "organization" in data or "name" in data, "Missing organization/name in brag response"
        if "organization" in data:
            assert "name" in data["organization"], "Missing name in organization"
        print("Brag page endpoint: PASS")

    def test_dashboard_endpoint(self):
        """GET /api/memberships/dashboard still works"""
        resp = requests.get(f"{BASE_URL}/api/memberships/dashboard", headers=self.operator_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "active_members" in data
        print("Dashboard endpoint: PASS")

    def test_analytics_overview(self):
        """GET /api/memberships/analytics/overview still works"""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/overview", headers=self.operator_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("Analytics overview: PASS")

    def test_analytics_retention(self):
        """GET /api/memberships/analytics/retention still works"""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/retention", headers=self.operator_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("Analytics retention: PASS")

    def test_analytics_classes(self):
        """GET /api/memberships/analytics/classes still works"""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/classes", headers=self.operator_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("Analytics classes: PASS")

    def test_analytics_operations(self):
        """GET /api/memberships/analytics/operations still works"""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/operations", headers=self.operator_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("Analytics operations: PASS")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
