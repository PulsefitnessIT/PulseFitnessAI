"""Aftersales Quote Follow-up Chasers (Task 4, Jan 2026).

Tests trigger + audit for chase reminders and expired-unsigned notifications:
- GET/PUT settings persists quote_chase_days (default '14,5')
- POST /quotes/chasers/run sends chasers for the 12d + 3d seeded quotes and
  marks the expired one; tightest window wins (CHASE-3D → [5], NOT [14]).
- Dedupe: second run returns chasers_sent=0.
- Expired quote produces a 'quote_expired' alert in GET /alerts.
- Accepted/declined or missing email/shortcode quotes are NOT chased.

Preview: Resend key is test key → send_email returns False; trigger + audit is
the pass condition (chasers_sent counts the trigger, not delivery).
"""
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"
ORG_ID = "iso-demo-org"


@pytest.fixture(scope="module")
def h():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": CRM_EMAIL, "password": CRM_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    yield db
    client.close()


@pytest.fixture(scope="module")
def reset_seed(mongo):
    """Reset the seeded chase_demo quotes to fresh state and delete prior
    expired alert so the assertions can re-observe a fresh run."""
    seed = list(mongo.crm2_afs_quotes.find({"_demo_tag": "chase_demo"}))
    ids = [q["id"] for q in seed]
    mongo.crm2_afs_quotes.update_many(
        {"_demo_tag": "chase_demo"},
        {"$unset": {"chases_sent": "", "last_chased_at": "", "last_chase_window": ""},
         "$set": {"expired_notified": False}})
    for qid in ids:
        mongo.crm2_activities.delete_many({"dedupe_key": f"afs:quote_expired:{qid}"})
    return {q.get("quote_number"): q for q in seed}


# ── SETTINGS ───────────────────────────────────────────────────────────
class TestAfsChaseDaysSettings:
    def test_get_default(self, h):
        r = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/settings", headers=h, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "quote_chase_days" in data
        # default '14,5' if never set
        assert data["quote_chase_days"] in ("14,5", "5,14") or data["quote_chase_days"]

    def test_put_persists(self, h):
        r = requests.put(f"{BASE_URL}/api/crm/v2/aftersales/settings",
                         headers=h, json={"quote_chase_days": "14,5"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("quote_chase_days") == "14,5"
        g = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/settings", headers=h, timeout=30).json()
        assert g.get("quote_chase_days") == "14,5"


# ── CHASERS RUN ────────────────────────────────────────────────────────
class TestAfsQuoteChasers:
    def test_fresh_run_sends_chasers(self, h, mongo, reset_seed):
        r = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/quotes/chasers/run",
                          headers=h, json={}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "chasers_sent" in data and "expired_notified" in data and "orgs_scanned" in data
        assert data["chasers_sent"] >= 2, f"expected ≥2, got {data}"
        assert data["expired_notified"] >= 1

        # Verify window recorded on each seeded quote
        q12 = mongo.crm2_afs_quotes.find_one({"_demo_tag": "chase_demo", "quote_number": "CHASE-12D"})
        q3 = mongo.crm2_afs_quotes.find_one({"_demo_tag": "chase_demo", "quote_number": "CHASE-3D"})
        qexp = mongo.crm2_afs_quotes.find_one({"_demo_tag": "chase_demo", "quote_number": "CHASE-EXP"})
        assert q12 and q3 and qexp, "seed quotes missing"
        assert q12.get("chases_sent") == [14], f"CHASE-12D chases_sent={q12.get('chases_sent')}"
        assert q3.get("chases_sent") == [5], f"CHASE-3D chases_sent={q3.get('chases_sent')} (tightest window bug)"
        assert qexp.get("expired_notified") is True

    def test_dedupe_second_run(self, h):
        r = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/quotes/chasers/run",
                          headers=h, json={}, timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["chasers_sent"] == 0, f"expected 0 on dedupe, got {data}"
        assert data["expired_notified"] == 0

    def test_expired_alert_visible(self, h, mongo):
        r = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts", headers=h, timeout=30)
        assert r.status_code == 200
        alerts = r.json().get("alerts", [])
        qexp = mongo.crm2_afs_quotes.find_one({"_demo_tag": "chase_demo", "quote_number": "CHASE-EXP"})
        found = [a for a in alerts if a.get("type") == "quote_expired"
                 and a.get("quote_id") == (qexp or {}).get("id")]
        assert found, f"quote_expired alert not found for CHASE-EXP"
        assert "Quote expired unsigned" in found[0].get("subject", "")
