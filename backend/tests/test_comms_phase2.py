"""Comms Phase 2 — intelligence, deliverability, AI, dedup endpoints."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # local fallback for CI inside container — only when env missing
    BASE_URL = "http://localhost:8001"

EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.com")
PASSWORD = os.environ.get("MASTER_ADMIN_PASSWORD", "C2s9yJ3YAhydB4d34-Bykg")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        sess.headers["Authorization"] = f"Bearer {tok}"
    return sess


# ── Engagement ────────────────────────────────────────────────────────
def test_engagement_contacts_default(s):
    r = s.get(f"{BASE_URL}/api/comms/engagement/contacts?bots=exclude", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "contacts" in d and isinstance(d["contacts"], list)
    assert "bands" in d and isinstance(d["bands"], dict)
    valid_bands = {"highly_engaged", "engaged", "neutral", "disengaged", "inactive"}
    for c in d["contacts"]:
        assert 0 <= c["score"] <= 100
        assert c["band"] in valid_bands


@pytest.mark.parametrize("module", ["all", "marketing", "memberships", "crm"])
def test_engagement_contacts_module_scope(s, module):
    r = s.get(f"{BASE_URL}/api/comms/engagement/contacts?module={module}", timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert "contacts" in r.json()


def test_engagement_companies(s):
    r = s.get(f"{BASE_URL}/api/comms/engagement/companies", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "companies" in d and isinstance(d["companies"], list)
    assert "total" in d


# ── Inactive / best-time / benchmarks ────────────────────────────────
def test_inactive(s):
    r = s.get(f"{BASE_URL}/api/comms/insights/inactive?days=60", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "inactive" in d
    assert d.get("cutoff_days") == 60


def test_best_send_time(s):
    r = s.get(f"{BASE_URL}/api/comms/insights/best-send-time", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "enough_data" in d
    assert "recommendation" in d
    rec = d["recommendation"]
    assert "day" in rec and "hour" in rec and "label" in rec
    assert len(d.get("grid", [])) == 7
    assert all(len(row) == 24 for row in d["grid"])
    # When enough_data is False, ensure a safe starter and a note
    if not d["enough_data"]:
        assert "note" in d


def test_benchmarks(s):
    r = s.get(f"{BASE_URL}/api/comms/insights/benchmarks", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "campaigns" in d and "averages" in d
    a = d["averages"]
    assert {"open_rate", "click_rate", "unsub_rate"}.issubset(a.keys())


# ── Deliverability ───────────────────────────────────────────────────
def test_deliverability(s):
    r = s.get(f"{BASE_URL}/api/comms/deliverability", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d.get("provider") == "Resend"
    assert d.get("health") in {"good", "warning", "at_risk"}
    assert isinstance(d.get("domains"), list)
    assert len(d["domains"]) >= 1
    for dom in d["domains"]:
        for k in ("domain", "category", "sender", "verified", "spf", "dkim", "dmarc"):
            assert k in dom
    assert "rates" in d and "suppression_count" in d and "warnings" in d


# ── Campaign analytics (need a campaign id) ──────────────────────────
@pytest.fixture(scope="module")
def campaign_id(s):
    # try list first
    r = s.get(f"{BASE_URL}/api/comms/campaigns", timeout=30)
    if r.status_code == 200:
        items = r.json().get("campaigns") or r.json().get("items") or r.json()
        if isinstance(items, list) and items:
            return items[0].get("id")
    # create a TEST campaign
    payload = {"name": f"TEST_phase2_{int(time.time())}", "campaign_type": "newsletter"}
    r = s.post(f"{BASE_URL}/api/comms/campaigns", json=payload, timeout=30)
    if r.status_code in (200, 201):
        return r.json().get("id") or r.json().get("campaign", {}).get("id")
    pytest.skip(f"could not get campaign id (list+create both failed): {r.status_code}")


def test_campaign_analytics_exclude(s, campaign_id):
    r = s.get(f"{BASE_URL}/api/comms/campaigns/{campaign_id}/analytics?bots=exclude", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["bot_filtering"] == "exclude"
    assert "totals" in d and "rates" in d
    for k in ("open_rate", "click_rate", "bounce_rate", "ctor"):
        assert k in d["rates"]
    assert "click_map" in d
    assert "conversions" in d


def test_campaign_analytics_include(s, campaign_id):
    r = s.get(f"{BASE_URL}/api/comms/campaigns/{campaign_id}/analytics?bots=include", timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["bot_filtering"] == "include"


# ── AI endpoints (live Emergent LLM key) ─────────────────────────────
def test_ai_subjects(s):
    r = s.post(
        f"{BASE_URL}/api/comms/ai/subjects",
        json={"topic": "TEST_phase2 spring class promo with merge tag {{first_name}}", "audience": "members", "tone": "warm", "n": 4},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    subs = r.json().get("subjects")
    assert isinstance(subs, list) and len(subs) >= 1


def test_ai_write(s):
    r = s.post(
        f"{BASE_URL}/api/comms/ai/write",
        json={"brief": "Invite TEST members to a free trial class", "campaign_type": "newsletter", "tone": "friendly"},
        timeout=90,
    )
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert "subject" in d
    blocks = d.get("blocks") or []
    assert isinstance(blocks, list) and len(blocks) >= 1
    for b in blocks:
        assert b["type"] in ("heading", "text", "button")


def test_ai_improve(s):
    r = s.post(
        f"{BASE_URL}/api/comms/ai/improve",
        json={"text": "join our gym its very good", "goal": "make it more compelling"},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    assert isinstance(r.json().get("text"), str) and len(r.json()["text"]) > 0


def test_ai_analyse_campaign(s, campaign_id):
    r = s.post(f"{BASE_URL}/api/comms/campaigns/{campaign_id}/ai-analyse", timeout=90)
    assert r.status_code == 200, r.text[:400]
    a = r.json().get("analysis") or {}
    for k in ("summary", "what_worked", "what_to_improve", "recommendations"):
        assert k in a, f"missing key in analysis: {k} -> got {list(a.keys())}"
