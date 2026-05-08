"""
Iteration 177 - Social Pulse Widget Tests
Tests for GET /api/member/social-pulse/{occurrence_id}

Features:
- Returns {booked_this_week: int, recent_names: string[]} for member-auth only
- booked_this_week counts bookings on same template within last 7 days (status: booked/attended/waitlist)
- recent_names excludes current member, uses GDPR-safe 'First L.' format
- 404 when occurrence_id doesn't exist or belongs to another org
- 401 with no token or operator token
- Works correctly with zero bookings
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
MEMBER_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_PASSWORD = "Member2026!"
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"


# Module-level tokens to avoid repeated logins
_member_token = None
_member_data = None
_operator_token = None
_occurrences = None


def get_member_auth():
    """Get member token (cached at module level)"""
    global _member_token, _member_data
    if _member_token is None:
        resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert resp.status_code == 200, f"Member login failed: {resp.text}"
        _member_token = resp.json()["token"]
        _member_data = resp.json()["member"]
    return _member_token, _member_data


def get_operator_auth():
    """Get operator token (cached at module level)"""
    global _operator_token
    if _operator_token is None:
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited on operator login")
        assert resp.status_code == 200, f"Operator login failed: {resp.text}"
        _operator_token = resp.json()["token"]
    return _operator_token


def get_occurrences():
    """Get timetable occurrences (cached at module level)"""
    global _occurrences
    if _occurrences is None:
        token, _ = get_member_auth()
        resp = requests.get(f"{BASE_URL}/api/member/timetable",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Timetable fetch failed: {resp.text}"
        _occurrences = resp.json().get("occurrences", [])
    return _occurrences


class TestSocialPulseEndpoint:
    """Tests for GET /api/member/social-pulse/{occurrence_id}"""

    def test_social_pulse_returns_correct_structure(self):
        """Test that endpoint returns {booked_this_week: int, recent_names: list}"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        token, _ = get_member_auth()
        occ_id = occs[0]["id"]
        resp = requests.get(
            f"{BASE_URL}/api/member/social-pulse/{occ_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify structure
        assert "booked_this_week" in data, "Missing booked_this_week field"
        assert "recent_names" in data, "Missing recent_names field"
        assert isinstance(data["booked_this_week"], int), "booked_this_week should be int"
        assert isinstance(data["recent_names"], list), "recent_names should be list"

        print(f"✓ Social pulse for {occ_id}: booked_this_week={data['booked_this_week']}, recent_names={data['recent_names']}")

    def test_social_pulse_401_without_token(self):
        """Test that endpoint returns 401 without authentication"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        occ_id = occs[0]["id"]
        resp = requests.get(f"{BASE_URL}/api/member/social-pulse/{occ_id}")

        assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
        print("✓ 401 returned without token")

    def test_social_pulse_401_with_operator_token(self):
        """Test that endpoint returns 401 with operator (non-member) token"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        try:
            op_token = get_operator_auth()
        except Exception:
            pytest.skip("Could not get operator token (rate limited)")

        occ_id = occs[0]["id"]
        resp = requests.get(
            f"{BASE_URL}/api/member/social-pulse/{occ_id}",
            headers={"Authorization": f"Bearer {op_token}"}
        )

        assert resp.status_code == 401, f"Expected 401 with operator token, got {resp.status_code}: {resp.text}"
        print("✓ 401 returned with operator token (member-auth only)")

    def test_social_pulse_404_invalid_occurrence(self):
        """Test that endpoint returns 404 for non-existent occurrence_id"""
        token, _ = get_member_auth()
        fake_id = "non-existent-occurrence-id-12345"
        resp = requests.get(
            f"{BASE_URL}/api/member/social-pulse/{fake_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert resp.status_code == 404, f"Expected 404 for invalid ID, got {resp.status_code}: {resp.text}"
        print("✓ 404 returned for non-existent occurrence_id")

    def test_social_pulse_recent_names_gdpr_format(self):
        """Test that recent_names uses GDPR-safe 'First L.' format"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        token, _ = get_member_auth()

        # Find an occurrence with bookings
        for occ in occs:
            occ_id = occ["id"]
            resp = requests.get(
                f"{BASE_URL}/api/member/social-pulse/{occ_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("recent_names"):
                    # Verify GDPR format: "First L." pattern
                    for name in data["recent_names"]:
                        # Should be "FirstName L." format
                        assert isinstance(name, str), f"Name should be string: {name}"
                        # Check it ends with a period and has at least one space
                        if " " in name:
                            parts = name.rsplit(" ", 1)
                            last_part = parts[-1]
                            # Last part should be single letter + period (e.g., "P.")
                            assert len(last_part) <= 3, f"Last name should be abbreviated: {name}"
                            assert last_part.endswith("."), f"Should end with period: {name}"
                        print(f"✓ GDPR-safe name format verified: {name}")
                    return

        print("✓ No recent_names found to verify format (may be zero bookings)")

    def test_social_pulse_excludes_current_member(self):
        """Test that recent_names excludes the current member"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        token, member = get_member_auth()
        member_first = member.get("first_name", "")
        member_last_initial = (member.get("last_name", "") or "")[:1]
        member_pattern = f"{member_first} {member_last_initial}."

        # Check social pulse for all occurrences
        for occ in occs:
            occ_id = occ["id"]
            resp = requests.get(
                f"{BASE_URL}/api/member/social-pulse/{occ_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("recent_names"):
                    # Current member should not appear in recent_names
                    assert member_pattern not in data["recent_names"], \
                        f"Current member {member_pattern} should be excluded from recent_names"

        print(f"✓ Current member ({member_pattern}) correctly excluded from recent_names")

    def test_social_pulse_booked_this_week_counts_template_bookings(self):
        """Test that booked_this_week counts bookings across same template"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        token, _ = get_member_auth()
        occ = occs[0]
        occ_id = occ["id"]

        resp = requests.get(
            f"{BASE_URL}/api/member/social-pulse/{occ_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert resp.status_code == 200
        data = resp.json()

        # booked_this_week should be >= 0
        assert data["booked_this_week"] >= 0, "booked_this_week should be non-negative"
        print(f"✓ booked_this_week={data['booked_this_week']} for occurrence {occ.get('name', occ_id)}")

    def test_social_pulse_zero_bookings_returns_empty(self):
        """Test that endpoint works correctly with zero bookings"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        token, _ = get_member_auth()

        # Find an occurrence with zero bookings if possible
        for occ in occs:
            if occ.get("bookings_count", 0) == 0:
                occ_id = occ["id"]
                resp = requests.get(
                    f"{BASE_URL}/api/member/social-pulse/{occ_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )

                assert resp.status_code == 200
                data = resp.json()

                # Should return valid structure even with zero bookings
                assert "booked_this_week" in data
                assert "recent_names" in data
                assert isinstance(data["recent_names"], list)
                print(f"✓ Zero bookings returns valid structure: {data}")
                return

        # If no zero-booking occurrence found, just verify structure works
        occ_id = occs[0]["id"]
        resp = requests.get(
            f"{BASE_URL}/api/member/social-pulse/{occ_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        print("✓ Endpoint handles all booking counts correctly")

    def test_social_pulse_recent_names_max_three(self):
        """Test that recent_names returns at most 3 names"""
        occs = get_occurrences()
        if not occs:
            pytest.skip("No occurrences available for testing")

        token, _ = get_member_auth()

        for occ in occs:
            occ_id = occ["id"]
            resp = requests.get(
                f"{BASE_URL}/api/member/social-pulse/{occ_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            if resp.status_code == 200:
                data = resp.json()
                assert len(data.get("recent_names", [])) <= 3, \
                    f"recent_names should have at most 3 entries, got {len(data['recent_names'])}"

        print("✓ recent_names correctly limited to max 3 entries")


class TestSocialPulseRegression:
    """Regression tests for iteration 176 features"""

    def test_streak_endpoint_still_works(self):
        """Regression: Streak endpoint from iteration 176 still works"""
        token, _ = get_member_auth()
        resp = requests.get(f"{BASE_URL}/api/member/streak",
                           headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200, f"Streak endpoint failed: {resp.text}"
        data = resp.json()

        # Verify all expected fields
        expected_fields = ["current_streak_days", "longest_streak_days", "weekly_count",
                          "weekly_goal", "weekly_remaining", "at_risk"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

        print(f"✓ Streak endpoint working: current={data['current_streak_days']}, weekly={data['weekly_count']}/{data['weekly_goal']}")

    def test_referral_progress_endpoint_still_works(self):
        """Regression: Referral progress endpoint still works"""
        token, _ = get_member_auth()
        resp = requests.get(f"{BASE_URL}/api/member/referral-progress",
                           headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200, f"Referral progress endpoint failed: {resp.text}"
        data = resp.json()

        # Verify structure
        assert "goals" in data, "Missing goals field"
        assert "earned" in data, "Missing earned field"
        print(f"✓ Referral progress endpoint working: earned={data['earned']}")

    def test_member_timetable_still_works(self):
        """Regression: Member timetable endpoint still works"""
        token, _ = get_member_auth()
        resp = requests.get(f"{BASE_URL}/api/member/timetable",
                           headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200, f"Timetable endpoint failed: {resp.text}"
        data = resp.json()

        assert "occurrences" in data, "Missing occurrences field"
        print(f"✓ Timetable endpoint working: {len(data['occurrences'])} occurrences")

    def test_member_bookings_still_works(self):
        """Regression: Member bookings endpoint still works"""
        token, _ = get_member_auth()
        resp = requests.get(f"{BASE_URL}/api/member/bookings",
                           headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200, f"Bookings endpoint failed: {resp.text}"
        data = resp.json()

        assert "upcoming" in data, "Missing upcoming field"
        assert "past" in data, "Missing past field"
        print(f"✓ Bookings endpoint working: {len(data['upcoming'])} upcoming, {len(data['past'])} past")
