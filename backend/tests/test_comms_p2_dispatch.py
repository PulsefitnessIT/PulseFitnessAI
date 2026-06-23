"""Comms Phase 2 — Dispatch worker, schedule API, pause/resume, AI segment suggest."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _new_campaign(api, name_suffix="dispatch"):
    name = f"TEST_p2_{name_suffix}_{uuid.uuid4().hex[:6]}"
    r = api.post(f"{BASE_URL}/api/comms/campaigns", json={"name": name, "campaign_type": "regular"})
    assert r.status_code == 200, r.text
    return r.json()["campaign"]


# ── Schedule endpoint validation ──────────────────────────────────────────────

class TestScheduleValidation:
    def test_schedule_rejects_without_content(self, api):
        c = _new_campaign(api, "noc")
        r = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/schedule", json={"strategy": "immediate"})
        assert r.status_code == 400
        assert "content" in r.text.lower()
        api.delete(f"{BASE_URL}/api/comms/campaigns/{c['id']}")

    def test_schedule_rejects_without_audience(self, api):
        c = _new_campaign(api, "noa")
        api.put(f"{BASE_URL}/api/comms/campaigns/{c['id']}", json={
            "content": {"subject": "Hi", "blocks": [{"type": "text", "props": {"text": "Body"}}]}
        })
        r = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/schedule", json={"strategy": "immediate"})
        assert r.status_code == 400
        assert "audience" in r.text.lower() or "segment" in r.text.lower()
        api.delete(f"{BASE_URL}/api/comms/campaigns/{c['id']}")

    def test_schedule_scheduled_requires_send_at(self, api):
        c = _new_campaign(api, "noat")
        api.put(f"{BASE_URL}/api/comms/campaigns/{c['id']}", json={
            "content": {"subject": "Hi", "blocks": [{"type": "text", "props": {"text": "Body"}}]},
            "audience_inline": ["a@example.com"],
        })
        r = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/schedule",
                     json={"strategy": "scheduled"})
        assert r.status_code == 400
        api.delete(f"{BASE_URL}/api/comms/campaigns/{c['id']}")


# ── Immediate dispatch via worker ─────────────────────────────────────────────

class TestImmediateDispatch:
    def test_immediate_send_goes_sending_then_sent(self, api):
        c = _new_campaign(api, "imm")
        api.put(f"{BASE_URL}/api/comms/campaigns/{c['id']}", json={
            "content": {"subject": "TEST p2", "blocks": [{"type": "text", "props": {"text": "Hi {{first_name}}"}}]},
            "audience_inline": [f"test+{uuid.uuid4().hex[:6]}@example.com"],
        })
        r = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/schedule", json={"strategy": "immediate"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") == "sending"
        assert body.get("recipients") == 1

        # Poll dispatch up to ~50s for worker to drain
        final = None
        for _ in range(25):
            d = api.get(f"{BASE_URL}/api/comms/campaigns/{c['id']}/dispatch")
            assert d.status_code == 200
            dj = d.json()
            if dj.get("status") == "sent":
                final = dj
                break
            time.sleep(2)
        assert final is not None, f"campaign did not reach 'sent' within 50s, last: {dj}"
        assert final["queued"] == 0
        assert final["total"] == 1
        assert (final["sent"] + final["bounced"]) == 1
        api.delete(f"{BASE_URL}/api/comms/campaigns/{c['id']}")


# ── Scheduled + pause/resume ──────────────────────────────────────────────────

class TestScheduledAndPause:
    def test_scheduled_then_pause_resume(self, api):
        c = _new_campaign(api, "sch")
        api.put(f"{BASE_URL}/api/comms/campaigns/{c['id']}", json={
            "content": {"subject": "Later", "blocks": [{"type": "text", "props": {"text": "Body"}}]},
            "audience_inline": ["future@example.com"],
        })
        # 1h in future
        future = "2099-01-01T10:00:00+00:00"
        r = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/schedule",
                     json={"strategy": "scheduled", "send_at": future, "batch_size": 100, "batch_interval_minutes": 5})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "scheduled"

        # Verify GET dispatch
        d = api.get(f"{BASE_URL}/api/comms/campaigns/{c['id']}/dispatch").json()
        assert d["status"] == "scheduled"
        assert d["schedule"]["batch_size"] == 100
        assert d["schedule"]["batch_interval_minutes"] == 5

        # Pause
        p = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/pause-send")
        assert p.status_code == 200, p.text
        assert p.json()["status"] == "paused"

        # Pause again should fail (not sending/scheduled anymore)
        p2 = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/pause-send")
        assert p2.status_code == 400

        # Resume (no queue exists → scheduled)
        rs = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/resume-send")
        assert rs.status_code == 200, rs.text
        assert rs.json()["status"] == "scheduled"

        # Resume when not paused should fail
        rs2 = api.post(f"{BASE_URL}/api/comms/campaigns/{c['id']}/resume-send")
        assert rs2.status_code == 400

        api.delete(f"{BASE_URL}/api/comms/campaigns/{c['id']}")


# ── AI suggest segment ────────────────────────────────────────────────────────

class TestAISegmentSuggest:
    def test_ai_suggest_returns_validated_rules(self, api):
        r = api.post(f"{BASE_URL}/api/comms/segments/ai-suggest",
                     json={"description": "lapsed members in the last 90 days"})
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("name", "source", "rules", "count", "sample"):
            assert k in body, f"missing key {k} in {body}"
        assert body["source"] in ("members", "contacts")
        assert isinstance(body["rules"], dict)
        # validated against catalogue → must have conditions list
        conds = body["rules"].get("conditions") or body["rules"].get("rules") or []
        assert isinstance(conds, list)
        assert isinstance(body["count"], int)
        assert isinstance(body["sample"], list)

    def test_ai_suggest_empty_description(self, api):
        r = api.post(f"{BASE_URL}/api/comms/segments/ai-suggest", json={"description": ""})
        # Either 400 (validation) or 200 with empty rules — both acceptable; assert no 500
        assert r.status_code != 500, r.text
