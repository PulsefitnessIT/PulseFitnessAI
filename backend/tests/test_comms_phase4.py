"""Phase 4 — Pulse Fitness AI Comms Centre: ESP import, webhooks, API keys, public REST API, Resend inbound."""
import io
import json
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ops-parts-request.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

CREATED = {"webhooks": [], "api_keys": [], "contacts_emails": set(), "optouts_emails": set()}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:300]}"
    j = r.json()
    return j.get("access_token") or j.get("token") or j.get("data", {}).get("access_token")


@pytest.fixture(scope="module")
def auth_headers(token):
    assert token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def api_key(auth_headers):
    r = requests.post(f"{BASE_URL}/api/comms/api-keys", headers=auth_headers, json={"name": "TEST_phase4_key"}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["key"].startswith("pfa_")
    CREATED["api_keys"].append(j["id"])
    return j["key"]


# ─────────────────────── ESP Import ───────────────────────
class TestImport:
    CSV = (
        "Email Address,First Name,Last Name,Company,Member Rating\n"
        "TEST_phase4_a@example.com,Alice,Adams,Acme,subscribed\n"
        "TEST_phase4_b@example.com,Bob,Brown,Beta Co,unsubscribed\n"
        "not-an-email,Bad,Row,X,subscribed\n"
        "TEST_phase4_c@example.com,Cara,Clark,,cleaned\n"
    )

    def test_preview(self, auth_headers):
        files = {"file": ("import.csv", self.CSV, "text/csv")}
        r = requests.post(f"{BASE_URL}/api/comms/import/preview", headers=auth_headers, files=files, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["total_rows"] == 4
        sm = j["suggested_mapping"]
        assert sm["email"] == "Email Address"
        assert sm["first_name"] == "First Name"
        assert sm["last_name"] == "Last Name"
        assert sm["company"] == "Company"
        assert sm["status"] == "Member Rating"
        assert len(j["sample_rows"]) <= 5

    def test_commit_with_suppression(self, auth_headers):
        mapping = {"email": "Email Address", "first_name": "First Name",
                   "last_name": "Last Name", "company": "Company", "status": "Member Rating"}
        files = {"file": ("import.csv", self.CSV, "text/csv")}
        data = {"mapping": json.dumps(mapping)}
        r = requests.post(f"{BASE_URL}/api/comms/import/commit", headers=auth_headers, files=files, data=data, timeout=30)
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        assert j["total"] == 4
        assert j["skipped"] >= 1  # the not-an-email row
        assert (j["created"] + j["updated"]) == 3
        assert j["suppressed"] >= 2  # b (unsub) + c (cleaned)
        for e in ("TEST_phase4_a@example.com", "TEST_phase4_b@example.com", "TEST_phase4_c@example.com"):
            CREATED["contacts_emails"].add(e)
        CREATED["optouts_emails"].update({"TEST_phase4_b@example.com", "TEST_phase4_c@example.com"})

    def test_commit_missing_email_mapping_400(self, auth_headers):
        files = {"file": ("import.csv", self.CSV, "text/csv")}
        data = {"mapping": json.dumps({"first_name": "First Name"})}
        r = requests.post(f"{BASE_URL}/api/comms/import/commit", headers=auth_headers, files=files, data=data, timeout=20)
        assert r.status_code == 400


# ─────────────────────── Webhooks CRUD ───────────────────────
class TestWebhooks:
    def test_create_bad_url_400(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/comms/webhooks", headers=auth_headers,
                          json={"url": "not-a-url", "events": []}, timeout=20)
        assert r.status_code == 400

    def test_create_and_secret(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/comms/webhooks", headers=auth_headers,
                          json={"url": "https://example.com/hook-test-phase4", "events": ["campaign.sent", "email.opened"]},
                          timeout=20)
        assert r.status_code == 200, r.text[:300]
        wh = r.json()["webhook"]
        assert wh["secret"].startswith("whsec_")
        assert wh["active"] is True
        assert set(wh["events"]) == {"campaign.sent", "email.opened"}
        CREATED["webhooks"].append(wh["id"])

    def test_list_includes_events_catalog(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/comms/webhooks", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert len(j["events"]) == 6
        for e in ["campaign.sent", "email.opened", "email.clicked", "email.unsubscribed", "email.bounced", "conversion.recorded"]:
            assert e in j["events"]
        assert any(w["id"] == CREATED["webhooks"][0] for w in j["webhooks"])

    def test_update_toggle(self, auth_headers):
        wid = CREATED["webhooks"][0]
        r = requests.put(f"{BASE_URL}/api/comms/webhooks/{wid}", headers=auth_headers,
                         json={"active": False, "events": ["email.bounced"]}, timeout=20)
        assert r.status_code == 200

    def test_test_delivery(self, auth_headers):
        wid = CREATED["webhooks"][0]
        r = requests.post(f"{BASE_URL}/api/comms/webhooks/{wid}/test", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        time.sleep(2)  # let fire-and-forget complete
        r = requests.get(f"{BASE_URL}/api/comms/webhooks/{wid}/deliveries", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "deliveries" in j
        # at least one delivery row should exist
        assert len(j["deliveries"]) >= 1


# ─────────────────────── API keys ───────────────────────
class TestApiKeys:
    def test_list_keys_masked(self, auth_headers, api_key):
        r = requests.get(f"{BASE_URL}/api/comms/api-keys", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert len(j["api_keys"]) >= 1
        for k in j["api_keys"]:
            assert "key" not in k  # raw key never returned
            assert "key_masked" in k
            assert k["key_masked"].startswith("pfa_")

    def test_revoke_key(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/comms/api-keys", headers=auth_headers, json={"name": "TEST_revoke_key"}, timeout=20)
        assert r.status_code == 200
        kid = r.json()["id"]
        CREATED["api_keys"].append(kid)
        r = requests.delete(f"{BASE_URL}/api/comms/api-keys/{kid}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        r = requests.get(f"{BASE_URL}/api/comms/api-keys", headers=auth_headers, timeout=20)
        rows = r.json()["api_keys"]
        rev = next((x for x in rows if x["id"] == kid), None)
        assert rev is not None
        assert rev["active"] is False


# ─────────────────────── Public REST API (X-API-Key) ───────────────────────
class TestPublicAPI:
    def test_missing_key_401(self):
        r = requests.get(f"{BASE_URL}/api/v1/comms/contacts", timeout=20)
        assert r.status_code == 401

    def test_invalid_key_401(self):
        r = requests.get(f"{BASE_URL}/api/v1/comms/contacts", headers={"X-API-Key": "pfa_invalid_xxx"}, timeout=20)
        assert r.status_code == 401

    def test_upsert_contact_created_then_updated(self, api_key):
        h = {"X-API-Key": api_key}
        email = "TEST_phase4_api_contact@example.com"
        CREATED["contacts_emails"].add(email)
        r = requests.post(f"{BASE_URL}/api/v1/comms/contacts", headers=h,
                          json={"email": email, "first_name": "Api", "last_name": "User"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["ok"] is True
        assert j["created"] is True
        # second call → updated
        r = requests.post(f"{BASE_URL}/api/v1/comms/contacts", headers=h,
                          json={"email": email, "first_name": "Api2"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["created"] is False

    def test_list_contacts(self, api_key):
        h = {"X-API-Key": api_key}
        r = requests.get(f"{BASE_URL}/api/v1/comms/contacts", headers=h, timeout=20)
        assert r.status_code == 200
        emails = {c["email"] for c in r.json()["contacts"]}
        assert "test_phase4_api_contact@example.com" in emails  # API lowercases on insert

    def test_suppression_unsub_and_resub(self, api_key):
        h = {"X-API-Key": api_key}
        email = "TEST_phase4_supp@example.com"
        CREATED["optouts_emails"].add(email)
        r = requests.post(f"{BASE_URL}/api/v1/comms/suppression", headers=h,
                          json={"email": email, "action": "unsubscribe"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["action"] == "unsubscribe"
        # send should return suppressed=True
        r = requests.post(f"{BASE_URL}/api/v1/comms/send", headers=h,
                          json={"to": email, "subject": "Hi", "html": "<p>Hi</p>"}, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert j.get("suppressed") is True and j.get("ok") is False
        # resubscribe
        r = requests.post(f"{BASE_URL}/api/v1/comms/suppression", headers=h,
                          json={"email": email, "action": "resubscribe"}, timeout=20)
        assert r.status_code == 200

    def test_send_validation_400(self, api_key):
        h = {"X-API-Key": api_key}
        r = requests.post(f"{BASE_URL}/api/v1/comms/send", headers=h,
                          json={"to": "", "subject": "", "html": ""}, timeout=20)
        assert r.status_code == 400


# ─────────────────────── Resend inbound webhook ───────────────────────
class TestResendInbound:
    def test_bounce_returns_200(self):
        r = requests.post(f"{BASE_URL}/api/webhooks/resend",
                          json={"type": "email.bounced", "data": {"to": ["TEST_phase4_bounce@example.com"]}}, timeout=20)
        assert r.status_code == 200

    def test_delivered_returns_200(self):
        r = requests.post(f"{BASE_URL}/api/webhooks/resend",
                          json={"type": "email.delivered", "data": {"to": ["TEST_phase4_deliv@example.com"]}}, timeout=20)
        assert r.status_code == 200

    def test_invalid_payload_400(self):
        r = requests.post(f"{BASE_URL}/api/webhooks/resend", data="not-json",
                          headers={"Content-Type": "application/json"}, timeout=20)
        assert r.status_code == 400

    def test_no_recipient_still_200(self):
        r = requests.post(f"{BASE_URL}/api/webhooks/resend",
                          json={"type": "email.bounced", "data": {}}, timeout=20)
        assert r.status_code == 200


# ─────────────────────── Cleanup ───────────────────────
def test_zzz_cleanup(auth_headers):
    """Module-level cleanup: delete webhooks, revoke api keys, purge test contacts and optouts via direct mongo."""
    # delete webhooks
    for wid in CREATED["webhooks"]:
        requests.delete(f"{BASE_URL}/api/comms/webhooks/{wid}", headers=auth_headers, timeout=10)
    # revoke api keys (best effort)
    for kid in CREATED["api_keys"]:
        requests.delete(f"{BASE_URL}/api/comms/api-keys/{kid}", headers=auth_headers, timeout=10)
    # purge test contacts + optouts directly in mongo
    try:
        import asyncio
        import sys
        sys.path.insert(0, "/app/backend")
        from utils.database import db  # noqa

        async def _purge():
            await db.crm_contacts.delete_many({"email": {"$regex": "^test_phase4_"}})
            await db.comms_optouts.delete_many({"email": {"$regex": "^test_phase4_"}})
            await db.comms_webhook_deliveries.delete_many({"webhook_id": {"$in": CREATED["webhooks"]}})
            await db.comms_webhooks.delete_many({"url": {"$regex": "phase4"}})
            await db.api_keys.delete_many({"name": {"$regex": "^TEST_"}})
        asyncio.run(_purge())
    except Exception as e:
        print("cleanup mongo step skipped:", e)
