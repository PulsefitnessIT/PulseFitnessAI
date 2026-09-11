"""Aftersales alert emails + quote send-email (Task 3 enhancement, Jan 2026).

Tests:
- PUT/GET /aftersales/settings persists alert_email; empty PUT is no-op
- POST /aftersales/alerts/run produces a digest email_send_events row on new alerts
- Re-running with nothing new returns digests_sent == 0
- POST /quotes/{id}/send-email returns url/shortcode/to and records email_send_events
- Send-email with invalid email returns 400
"""
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"
ORG_ID = "iso-demo-org"
ALERT_EMAIL = "coordinator@isodemo.com"


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


# ── SETTINGS ────────────────────────────────────────────────────────────
class TestAfsSettings:
    def test_put_alert_email_persists(self, h):
        r = requests.put(f"{BASE_URL}/api/crm/v2/aftersales/settings",
                         headers=h, json={"alert_email": ALERT_EMAIL}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("alert_email") == ALERT_EMAIL

        g = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/settings", headers=h, timeout=30)
        assert g.status_code == 200
        assert g.json().get("alert_email") == ALERT_EMAIL

    def test_put_empty_body_no_op(self, h):
        before = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/settings", headers=h, timeout=30).json()
        r = requests.put(f"{BASE_URL}/api/crm/v2/aftersales/settings", headers=h, json={}, timeout=30)
        assert r.status_code == 200
        after = r.json()
        assert after.get("alert_email") == before.get("alert_email")
        assert after.get("vat_pct") == before.get("vat_pct")


# ── DIGEST ────────────────────────────────────────────────────────────
class TestAfsDigest:
    def test_digest_sent_on_new_alerts_and_idempotent(self, h, mongo):
        # 1) Ensure alert_email configured
        requests.put(f"{BASE_URL}/api/crm/v2/aftersales/settings",
                     headers=h, json={"alert_email": ALERT_EMAIL}, timeout=30)

        # 2) Clear existing afs_alerts so new ones will be created
        mongo.crm2_activities.delete_many({"organization_id": ORG_ID, "source": "afs_alerts"})
        mongo.crm2_notifications.delete_many({"organization_id": ORG_ID, "type": "aftersales_alert"})

        # 3) Run scan
        r = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/alerts/run", headers=h, timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "digests_sent" in j, f"missing digests_sent: {j}"
        assert j["digests_sent"] >= 1, f"expected digest sent, got: {j}"
        assert (j.get("warranty_tasks", 0) + j.get("rpi_tasks", 0)) >= 1

        # 4) Verify email_send_events row exists for the digest
        evt = mongo.email_send_events.find_one(
            {"to": ALERT_EMAIL, "subject": {"$regex": "Pulse Aftersales:.*new maintenance reminder"}},
            sort=[("created_at", -1)],
        )
        assert evt is not None, "No digest email_send_events row found"
        assert evt.get("to") == ALERT_EMAIL
        assert "maintenance reminder" in (evt.get("subject") or "")
        # Preview: status may be 'failed'/'no_api_key' — that's fine, feature-level pass is TRIGGER+AUDIT
        assert evt.get("status") in ("sent", "failed", "no_api_key", "bad_sender"), evt

        # 5) Second run with nothing new → digests_sent == 0
        r2 = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/alerts/run", headers=h, timeout=90)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2.get("warranty_tasks", 0) == 0 and j2.get("rpi_tasks", 0) == 0, j2
        assert j2.get("digests_sent", 0) == 0, f"digest sent when nothing new: {j2}"


# ── QUOTE SEND-EMAIL ────────────────────────────────────────────────────
def _ensure_quote(h, mongo):
    q = mongo.crm2_afs_quotes.find_one({"organization_id": ORG_ID}, {"_id": 0, "id": 1})
    if q:
        return q["id"]
    # Build one
    r = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/build-quote-from-estate", headers=h,
                      json={"company_id": "iso-cA", "contract_type": "gold",
                            "pricing_level": "standard", "term_years": 1, "save": True}, timeout=60)
    assert r.status_code == 200, f"build-quote failed: {r.status_code} {r.text}"
    j = r.json()
    qid = j.get("quote_id") or j.get("id") or (j.get("quote") or {}).get("id")
    assert qid, f"No quote_id in build response: {j}"
    return qid


class TestQuoteSendEmail:
    def test_send_quote_email_triggers_and_audits(self, h, mongo):
        qid = _ensure_quote(h, mongo)
        payload = {"contact_email": "dan.hayes@alphaco.test", "contact_name": "Dan Hayes"}
        r = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/quotes/{qid}/send-email",
                          headers=h, json=payload, timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "sent" in j and isinstance(j["sent"], bool)
        assert j.get("to") == "dan.hayes@alphaco.test"
        assert j.get("shortcode"), f"no shortcode: {j}"
        assert j.get("url", "").endswith(f"/aq/{j['shortcode']}"), j

        # email_send_events audit row exists
        evt = mongo.email_send_events.find_one(
            {"to": "dan.hayes@alphaco.test",
             "subject": {"$regex": "Pulse Fitness maintenance quote"}},
            sort=[("created_at", -1)])
        assert evt is not None, "No email_send_events row recorded for quote email"
        assert evt.get("status") in ("sent", "failed", "no_api_key", "bad_sender"), evt

    def test_send_quote_invalid_email_400(self, h, mongo):
        qid = _ensure_quote(h, mongo)
        # Clear stored portal_contact_email so validation triggers
        mongo.crm2_afs_quotes.update_one(
            {"id": qid, "organization_id": ORG_ID},
            {"$set": {"portal_contact_email": ""}})
        r = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/quotes/{qid}/send-email",
                          headers=h, json={"contact_email": "notanemail"}, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        assert "email" in r.text.lower()
