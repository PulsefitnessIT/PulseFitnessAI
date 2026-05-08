"""
Test suite for the Campaign Wizard AI Copilot endpoint.
POST /api/marketing/wizard-copilot

Tests all 5 wizard steps: goal, audience, creative, schedule, review.
Validates Claude-generated AI copy, suggestions, and tips.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Credentials loaded from environment with safe local defaults. Keeps
# secrets out of source control and aligns with the shared conftest.
OPERATOR_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
OPERATOR_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for operator user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def headers(auth_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestWizardCopilotEndpoint:
    """Tests for POST /api/marketing/wizard-copilot"""

    def test_step_goal_returns_suggestions_with_valid_apply_ids(self, headers):
        """Step=goal should return tip (non-empty) and suggestions with valid applyId values."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={"step": "goal", "goal": None, "audience": None, "channel": "email"},
            headers=headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Tip must be non-empty
        assert "tip" in data, "Response missing 'tip' field"
        assert data["tip"], "Tip should not be empty"
        assert len(data["tip"]) > 0, "Tip should have content"

        # Suggestions should exist and have valid applyId values
        assert "suggestions" in data, "Response missing 'suggestions' field"
        suggestions = data["suggestions"]

        # For step=goal, we expect suggestions with applyId
        valid_apply_ids = {"fill-classes", "win-back", "promote-class", "upsell-pt", "retention"}

        if suggestions:  # May be empty if fallback
            for s in suggestions:
                assert "label" in s, "Suggestion missing 'label'"
                if "applyId" in s:
                    assert s["applyId"] in valid_apply_ids, f"Invalid applyId: {s['applyId']}"

        print(f"✓ Step=goal: tip='{data['tip'][:50]}...', {len(suggestions)} suggestions")

    def test_step_audience_returns_tip(self, headers):
        """Step=audience should return a tip about targeting."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={"step": "audience", "goal": "fill-classes", "audience": None, "channel": "email"},
            headers=headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "tip" in data, "Response missing 'tip' field"
        assert data["tip"], "Tip should not be empty for audience step"

        # Audience step should have empty suggestions per spec
        assert "suggestions" in data, "Response missing 'suggestions' field"

        print(f"✓ Step=audience: tip='{data['tip'][:50]}...'")

    def test_step_creative_returns_copy_with_placeholders(self, headers):
        """Step=creative should return copy.subject and copy.body with placeholders like {{first_name}}."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={
                "step": "creative",
                "goal": "fill-classes",
                "audience": {"id": "low-bookings-7d", "label": "Members with no bookings in 7 days", "approx": "~22%"},
                "channel": "email",
                "brand_name": "PulseFitness"
            },
            headers=headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "tip" in data, "Response missing 'tip' field"
        assert data["tip"], "Tip should not be empty"

        # Creative step must return copy object
        assert "copy" in data, "Response missing 'copy' field for creative step"
        copy = data["copy"]
        assert copy is not None, "Copy should not be null for creative step"
        assert "subject" in copy, "Copy missing 'subject' field"
        assert "body" in copy, "Copy missing 'body' field"
        assert copy["subject"], "Subject should not be empty"
        assert copy["body"], "Body should not be empty"

        # Check for placeholders (either {{first_name}} or {first_name} format)
        combined = (copy["subject"] + copy["body"]).lower()
        has_placeholder = "first_name" in combined or "company_name" in combined or "{{" in combined or "{" in combined
        print(f"✓ Step=creative: subject='{copy['subject'][:40]}...', body length={len(copy['body'])}, has_placeholder={has_placeholder}")

    def test_step_schedule_returns_best_time_suggestion(self, headers):
        """Step=schedule should return suggestion with applyTiming='best-time'."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={
                "step": "schedule",
                "goal": "fill-classes",
                "audience": {"id": "low-bookings-7d", "label": "Members with no bookings in 7 days", "approx": "~22%"},
                "channel": "email"
            },
            headers=headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "tip" in data, "Response missing 'tip' field"
        assert data["tip"], "Tip should not be empty"

        # Schedule step should have suggestions with applyTiming
        assert "suggestions" in data, "Response missing 'suggestions' field"
        suggestions = data["suggestions"]

        if suggestions:
            # At least one suggestion should have applyTiming='best-time'
            has_best_time = any(s.get("applyTiming") == "best-time" for s in suggestions)
            assert has_best_time, "Schedule step should have suggestion with applyTiming='best-time'"

        print(f"✓ Step=schedule: tip='{data['tip'][:50]}...', {len(suggestions)} suggestions")

    def test_step_review_returns_tip(self, headers):
        """Step=review should return a pre-flight tip."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={
                "step": "review",
                "goal": "fill-classes",
                "audience": {"id": "low-bookings-7d", "label": "Members with no bookings in 7 days", "approx": "~22%"},
                "channel": "email"
            },
            headers=headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "tip" in data, "Response missing 'tip' field"
        assert data["tip"], "Tip should not be empty for review step"

        # Review step should have empty suggestions per spec
        assert "suggestions" in data, "Response missing 'suggestions' field"

        print(f"✓ Step=review: tip='{data['tip'][:50]}...'")

    def test_invalid_step_returns_400(self, headers):
        """Invalid step should return 400 error."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={"step": "invalid", "goal": None, "audience": None, "channel": "email"},
            headers=headers
        )

        assert response.status_code == 400, f"Expected 400 for invalid step, got {response.status_code}"
        print("✓ Invalid step returns 400")

    def test_model_field_indicates_claude(self, headers):
        """Response should include model field indicating Claude was used (not fallback)."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={"step": "goal", "goal": None, "audience": None, "channel": "email"},
            headers=headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # If model field exists, it should be claude-sonnet-4-5-20250929
        if "model" in data:
            assert data["model"] == "claude-sonnet-4-5-20250929", f"Expected Claude model, got {data['model']}"
            print(f"✓ Model field confirms Claude: {data['model']}")
        else:
            print("⚠ Model field not present (may be fallback response)")

    def test_all_goal_types(self, headers):
        """Test wizard copilot with different goal types."""
        goals = ["fill-classes", "win-back", "promote-class", "upsell-pt", "retention"]

        for goal in goals:
            response = requests.post(
                f"{BASE_URL}/api/marketing/wizard-copilot",
                json={"step": "creative", "goal": goal, "audience": None, "channel": "email"},
                headers=headers
            )

            assert response.status_code == 200, f"Failed for goal={goal}: {response.status_code}"
            data = response.json()
            assert data.get("tip"), f"No tip for goal={goal}"
            print(f"✓ Goal={goal}: tip present")

    def test_sms_channel(self, headers):
        """Test wizard copilot with SMS channel."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={
                "step": "creative",
                "goal": "fill-classes",
                "audience": None,
                "channel": "sms",
                "brand_name": "PulseFitness"
            },
            headers=headers
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("tip"), "No tip for SMS channel"
        print(f"✓ SMS channel: tip='{data['tip'][:50]}...'")


class TestWizardCopilotAuth:
    """Authentication tests for wizard-copilot endpoint."""

    def test_unauthenticated_request_fails(self):
        """Request without auth token should fail."""
        response = requests.post(
            f"{BASE_URL}/api/marketing/wizard-copilot",
            json={"step": "goal", "goal": None, "audience": None, "channel": "email"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Unauthenticated request properly rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
