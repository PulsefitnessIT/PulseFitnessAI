"""Iter 216h74 — Marketing Starter Pack Send/Launch wiring tests.

Each generated email has 3 launch actions:
    • Send test email to operator (Resend)
    • Create Campaign draft
    • Bundle 3 emails into a Welcome Journey

These tests exercise the wiring without re-running the LLM generation.
We seed/reuse whatever pack is already on the org and assert:
    • create-campaign creates a draft, is idempotent, and updates launches
    • create-journey wires 3 send_email + 2 wait nodes correctly
    • test-send hits Resend (success OR explicit 502 with friendly msg)
    • bad email id returns 400
"""
import os
import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://admin-setup-portal.preview.emergentagent.com"
).rstrip("/")

TEST_EMAIL = "e1.agent@gymaxisai.com"
TEST_PASSWORD = "E1Agent123!"


@pytest.fixture(scope="module")
def auth_headers():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def pack_present(auth_headers):
    """Ensure a pack exists on the org; if absent, generate one (slow)."""
    got = requests.get(f"{BASE_URL}/api/marketing/starter-pack", headers=auth_headers, timeout=10)
    if not (got.status_code == 200 and got.json().get("pack")):
        gen = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/generate",
            headers=auth_headers, json={}, timeout=60,
        )
        assert gen.status_code == 200, f"Pack generate failed: {gen.text}"
    return True


class TestCreateCampaign:
    def test_creates_campaign_draft(self, auth_headers, pack_present):
        # Cleanup any prior launch state for a clean assertion
        requests.delete(f"{BASE_URL}/api/marketing/starter-pack", headers=auth_headers, timeout=10)
        requests.post(f"{BASE_URL}/api/marketing/starter-pack/generate",
                      headers=auth_headers, json={}, timeout=60)

        r = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/welcome/create-campaign",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body.get("campaign_id")
        camp = body["campaign"]
        assert camp["status"] == "draft"
        assert camp["channel"] == "email"
        assert camp["source"]["kind"] == "starter_pack"
        assert camp["source"]["email_id"] == "welcome"
        assert camp["content"]["subject"]
        assert "<p" in camp["content"]["body_html"]
        # Single default variant
        assert len(camp["variants"]) == 1
        assert camp["variants"][0]["id"] == "default"

    def test_idempotent(self, auth_headers):
        r1 = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/welcome/create-campaign",
            headers=auth_headers, timeout=15,
        )
        assert r1.status_code == 200
        cid = r1.json()["campaign_id"]
        r2 = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/welcome/create-campaign",
            headers=auth_headers, timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json().get("already_exists") is True
        assert r2.json()["campaign_id"] == cid

    def test_unknown_email_id(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/garbage/create-campaign",
            headers=auth_headers, timeout=10,
        )
        assert r.status_code == 400

    def test_launches_state_persisted(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/marketing/starter-pack", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        launches = r.json().get("launches") or {}
        assert launches.get("emails", {}).get("welcome", {}).get("campaign_id")


class TestCreateJourney:
    def test_creates_3step_journey(self, auth_headers, pack_present):
        r = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/create-journey",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body.get("journey_id")
        j = body["journey"]
        assert j["status"] == "draft"
        assert j["source"]["kind"] == "starter_pack"
        types = [n["type"] for n in j["nodes"]]
        assert types == ["send_email", "wait", "send_email", "wait", "send_email"]
        # 4 edges connecting 5 nodes linearly
        assert len(j["edges"]) == 4
        # Wait nodes carry 3d / 7d in minutes
        wait_minutes = [n["config"]["duration_minutes"] for n in j["nodes"] if n["type"] == "wait"]
        assert wait_minutes == [3 * 24 * 60, 7 * 24 * 60]
        # Send-email nodes have a subject + body_html
        for n in j["nodes"]:
            if n["type"] == "send_email":
                assert n["config"]["subject"]
                assert "<p" in n["config"]["body_html"]

    def test_idempotent(self, auth_headers):
        r1 = requests.post(f"{BASE_URL}/api/marketing/starter-pack/create-journey",
                           headers=auth_headers, timeout=10)
        jid = r1.json()["journey_id"]
        r2 = requests.post(f"{BASE_URL}/api/marketing/starter-pack/create-journey",
                           headers=auth_headers, timeout=10)
        assert r2.json().get("already_exists") is True
        assert r2.json()["journey_id"] == jid


class TestTestSend:
    def test_unknown_email_id(self, auth_headers, pack_present):
        r = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/garbage/test-send",
            headers=auth_headers, timeout=10,
        )
        assert r.status_code == 400

    def test_send_dispatches_to_resend(self, auth_headers, pack_present):
        """Test send attempts a real Resend dispatch. In environments where
        the sender domain is unverified this returns 502 with a friendly
        error — both 200 and 502 are accepted as 'wiring is correct'."""
        r = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/welcome/test-send",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            assert "test send failed" in r.text.lower() or "resend" in r.text.lower()

    def test_bad_to_address(self, auth_headers, pack_present):
        r = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/welcome/test-send",
            headers=auth_headers, json={"to": "not-an-email"}, timeout=10,
        )
        assert r.status_code == 400


class TestAuth:
    def test_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/emails/welcome/create-campaign",
            timeout=10,
        )
        assert r.status_code in (401, 403)

        r2 = requests.post(
            f"{BASE_URL}/api/marketing/starter-pack/create-journey",
            timeout=10,
        )
        assert r2.status_code in (401, 403)
