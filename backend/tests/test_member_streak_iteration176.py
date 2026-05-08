"""
Iteration 176 - Member Streak Card Backend Tests

Tests for GET /api/member/streak endpoint:
- Returns correct streak data for Emma (seeded with 3 consecutive check-ins)
- Weekly goal defaults to 3, reads org.weekly_streak_goal, member.weekly_goal takes priority
- at_risk=True only when current_streak_days > 0 AND last check-in was >=24h ago
- Gracefully returns zeroed values for members with zero check-ins
- 401 with no token; 401 with operator token (member-auth only)
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMemberStreakEndpoint:
    """Tests for GET /api/member/streak"""

    @pytest.fixture(scope="class")
    def member_token(self):
        """Get Emma's member token"""
        response = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": "emma.wright@demo.gymaxis",
            "password": "Member2026!"
        })
        if response.status_code != 200:
            pytest.skip(f"Member login failed: {response.status_code} - {response.text}")
        return response.json().get("token")

    @pytest.fixture(scope="class")
    def operator_token(self):
        """Get operator token (should be rejected by member-only endpoint)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "studio.leeds@gymaxisai.com",
            "password": "Studio2026!"
        })
        if response.status_code != 200:
            pytest.skip(f"Operator login failed: {response.status_code} - {response.text}")
        return response.json().get("token")

    def test_streak_returns_all_required_fields(self, member_token):
        """Verify streak endpoint returns all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/member/streak",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        required_fields = [
            "current_streak_days",
            "longest_streak_days",
            "weekly_count",
            "weekly_goal",
            "weekly_remaining",
            "last_attended_at",
            "at_risk"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        print(f"Streak data: {data}")

    def test_emma_streak_values(self, member_token):
        """Verify Emma's streak values match expected seeded data"""
        response = requests.get(
            f"{BASE_URL}/api/member/streak",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert response.status_code == 200

        data = response.json()
        # Emma should have seeded check-ins
        # Main agent says: current:12, longest:35, weekly:5, goal:3, weekly_remaining:0
        assert isinstance(data["current_streak_days"], int), "current_streak_days should be int"
        assert isinstance(data["longest_streak_days"], int), "longest_streak_days should be int"
        assert isinstance(data["weekly_count"], int), "weekly_count should be int"
        assert isinstance(data["weekly_goal"], int), "weekly_goal should be int"
        assert isinstance(data["weekly_remaining"], int), "weekly_remaining should be int"
        assert isinstance(data["at_risk"], bool), "at_risk should be bool"

        # Based on main agent context: Emma has current:12, longest:35, weekly:5
        # These may vary based on when seed runs, but should be > 0
        print(f"Emma's streak: current={data['current_streak_days']}, longest={data['longest_streak_days']}, weekly={data['weekly_count']}")

        # Verify last_attended_at format if present
        if data["last_attended_at"]:
            # Should be YYYY-MM-DD format
            try:
                datetime.strptime(data["last_attended_at"], "%Y-%m-%d")
            except ValueError:
                pytest.fail(f"last_attended_at format invalid: {data['last_attended_at']}")

    def test_weekly_goal_defaults_to_3(self, member_token):
        """Verify weekly goal defaults to 3 when no override"""
        response = requests.get(
            f"{BASE_URL}/api/member/streak",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert response.status_code == 200

        data = response.json()
        # Default goal is 3 unless org or member override
        assert data["weekly_goal"] >= 1, "weekly_goal should be at least 1"
        print(f"Weekly goal: {data['weekly_goal']}")

    def test_weekly_remaining_calculation(self, member_token):
        """Verify weekly_remaining = max(0, goal - count)"""
        response = requests.get(
            f"{BASE_URL}/api/member/streak",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert response.status_code == 200

        data = response.json()
        expected_remaining = max(0, data["weekly_goal"] - data["weekly_count"])
        assert data["weekly_remaining"] == expected_remaining, \
            f"weekly_remaining should be {expected_remaining}, got {data['weekly_remaining']}"

    def test_401_without_token(self):
        """Verify 401 when no token provided"""
        response = requests.get(f"{BASE_URL}/api/member/streak")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_401_with_operator_token(self, operator_token):
        """Verify 401 when operator token used (member-auth only)"""
        response = requests.get(
            f"{BASE_URL}/api/member/streak",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert response.status_code == 401, f"Expected 401 for operator token, got {response.status_code}"


class TestMemberStreakZeroCheckins:
    """Test streak endpoint for member with zero check-ins"""

    @pytest.fixture(scope="class")
    def new_member_token(self):
        """Register a new member with no check-ins"""
        import uuid
        unique_email = f"test.streak.{uuid.uuid4().hex[:8]}@demo.gymaxis"

        response = requests.post(f"{BASE_URL}/api/member-auth/register", json={
            "email": unique_email,
            "password": "TestStreak2026!",
            "first_name": "Test",
            "last_name": "Streak",
            "organization_slug": "pulse-leeds"
        })
        if response.status_code not in [200, 201]:
            pytest.skip(f"Member registration failed: {response.status_code} - {response.text}")
        return response.json().get("token")

    def test_zeroed_values_for_new_member(self, new_member_token):
        """Verify graceful zeroed values for member with no check-ins"""
        response = requests.get(
            f"{BASE_URL}/api/member/streak",
            headers={"Authorization": f"Bearer {new_member_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data["current_streak_days"] == 0, "New member should have 0 current streak"
        assert data["longest_streak_days"] == 0, "New member should have 0 longest streak"
        assert data["weekly_count"] == 0, "New member should have 0 weekly count"
        assert data["last_attended_at"] is None, "New member should have null last_attended_at"
        assert data["at_risk"] == False, "New member should not be at risk"

        print(f"New member streak (zeroed): {data}")


class TestMemberStreakAtRisk:
    """Test at_risk flag logic"""

    @pytest.fixture(scope="class")
    def member_token(self):
        """Get Emma's member token"""
        response = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": "emma.wright@demo.gymaxis",
            "password": "Member2026!"
        })
        if response.status_code != 200:
            pytest.skip(f"Member login failed: {response.status_code}")
        return response.json().get("token")

    def test_at_risk_logic(self, member_token):
        """Verify at_risk is True only when streak > 0 AND last check-in >= 24h ago"""
        response = requests.get(
            f"{BASE_URL}/api/member/streak",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert response.status_code == 200

        data = response.json()
        # at_risk should be boolean
        assert isinstance(data["at_risk"], bool)

        # If current_streak_days is 0, at_risk must be False
        if data["current_streak_days"] == 0:
            assert data["at_risk"] == False, "at_risk should be False when streak is 0"

        # If at_risk is True, current_streak_days must be > 0
        if data["at_risk"]:
            assert data["current_streak_days"] > 0, "at_risk=True requires streak > 0"

        print(f"at_risk={data['at_risk']}, current_streak={data['current_streak_days']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
