"""Regression tests for the four Master Admin → Sicon Integration panel bugs
(iteration Jan 2026):

Bug1 Credentials persistence — non-secret fields survive save/reload;
     credentials_set map reports which secrets are stored; masked sentinel
     ('••••••') is preserved so a Save without retyping the API key doesn't
     wipe the stored secret.
Bug2 POST /api/integrations/sicon/test-connection exists, returns a
     descriptive error banner (never crashes) and appends to the event log.
Bug3 GET /api/sicon/field-mapping returns grouped mappings for all
     entities with a total (~237 rows).
Bug4 Sicon integration_logs are queryable (Event Log expand renders payload
     or fallback on the frontend; backend just needs to expose entries).
"""

import os
import asyncio
import pytest
import pyotp
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # tests rely on the preview URL from frontend/.env — fail fast if missing
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

EMAIL = "admin@pulsefitness.com"
PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


def _mfa_code() -> str:
    """Return a fresh TOTP code for the enrolled master admin."""
    import sys
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # type: ignore
    from utils.mfa import decrypt_secret  # type: ignore

    async def fetch():
        d = await db.user_mfa.find_one({})
        return decrypt_secret(d["secret_encrypted"])

    secret = asyncio.get_event_loop().run_until_complete(fetch())
    return pyotp.TOTP(secret).now()


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("requires_mfa"):
        temp = body["temp_token"]
        # try up to 2 codes in case of clock rollover
        for _ in range(2):
            code = _mfa_code()
            r2 = requests.post(
                f"{BASE_URL}/api/auth/mfa/verify",
                json={"temp_token": temp, "code": code},
                timeout=15,
            )
            if r2.status_code == 200:
                return r2.json().get("access_token") or r2.json().get("token")
        pytest.fail(f"MFA verify failed: {r2.status_code} {r2.text}")
    return body.get("access_token") or body.get("token")


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- Bug 3: field mapping list -----------------
def test_bug3_field_mapping_returns_all_rows(auth):
    r = requests.get(f"{BASE_URL}/api/sicon/field-mapping", headers=auth, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "mappings" in data and "grouped" in data
    assert isinstance(data["mappings"], list)
    # spec says ~237
    assert data["total"] >= 200, f"expected ~237 rows, got {data['total']}"
    assert len(data["mappings"]) == data["total"]
    assert "entities" in data and len(data["entities"]) >= 7
    # sanity: expected entity groups present
    for ent in ("Case", "ContractLine", "Resource", "Customer"):
        assert ent in data["grouped"], f"missing entity group {ent}"
    # each row exposes the required columns
    row = data["mappings"][0]
    # 'pulse_field' is exposed by the backend as 'gymaxis_field' (internal name)
    for key in ("gymaxis_field", "sicon_field", "direction", "entity"):
        assert key in row, f"row missing key {key}: {row}"


# ---------------- Bug 1: credentials persistence -----------------
def test_bug1_credentials_persistence_and_mask(auth):
    # Save non-secret + secret creds
    payload = {
        "base_url": "https://sicon-test.example.com",
        "credentials": {
            "api_key": "TEST_KEY_123",
            "username": "TEST_USER",
            "company_id": "TEST_CO",
            "sage_customer_account_id": "TEST_SLC",
            "sub_location_id": "TEST_SUB",
        },
    }
    r = requests.put(
        f"{BASE_URL}/api/integrations/sicon", headers=auth, json=payload, timeout=15
    )
    assert r.status_code == 200, r.text

    # Read back — non-secret should be visible, secret masked, credentials_set present
    r2 = requests.get(f"{BASE_URL}/api/integrations/sicon", headers=auth, timeout=15)
    assert r2.status_code == 200, r2.text
    data = r2.json()
    creds = data.get("credentials") or {}
    assert creds.get("username") == "TEST_USER"
    assert creds.get("company_id") == "TEST_CO"
    assert creds.get("sage_customer_account_id") == "TEST_SLC"
    assert creds.get("sub_location_id") == "TEST_SUB"
    # api_key must be masked (••••••) but PRESENT
    assert creds.get("api_key") == "••••••", f"api_key not masked: {creds.get('api_key')}"
    cs = data.get("credentials_set") or {}
    assert cs.get("api_key") is True
    assert cs.get("username") is True
    assert data.get("base_url") == "https://sicon-test.example.com"


def test_bug1_save_with_masked_apikey_preserves_secret(auth):
    """Second save without retyping the API key must NOT wipe the stored key."""
    # Save again, resubmitting the masked sentinel for api_key
    payload = {
        "credentials": {
            "api_key": "••••••",           # keep-existing sentinel
            "username": "TEST_USER_2",
        },
    }
    r = requests.put(
        f"{BASE_URL}/api/integrations/sicon", headers=auth, json=payload, timeout=15
    )
    assert r.status_code == 200, r.text

    r2 = requests.get(f"{BASE_URL}/api/integrations/sicon", headers=auth, timeout=15)
    data = r2.json()
    creds = data.get("credentials") or {}
    assert creds.get("username") == "TEST_USER_2"
    # api_key still stored → mask still returned + credentials_set true
    assert creds.get("api_key") == "••••••"
    assert (data.get("credentials_set") or {}).get("api_key") is True


# ---------------- Bug 2: test-connection endpoint -----------------
def test_bug2_test_connection_returns_descriptive_result(auth):
    r = requests.post(
        f"{BASE_URL}/api/integrations/sicon/test-connection", headers=auth, timeout=20
    )
    # Endpoint must exist and never 5xx; preview has no live host, so an error
    # banner with a descriptive message is the expected correct behaviour.
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") in ("connected", "error"), body
    assert isinstance(body.get("message"), str) and body["message"], body
    # If unreachable, message must mention the base_url we saved
    if body["status"] == "error":
        assert "sicon-test.example.com" in body["message"] or "Base URL" in body["message"], body


def test_bug2_test_connection_no_base_url(auth):
    """With no base_url configured the endpoint returns a clear error, not a crash."""
    # Wipe base_url
    r = requests.put(
        f"{BASE_URL}/api/integrations/sicon",
        headers=auth,
        json={"base_url": ""},
        timeout=15,
    )
    assert r.status_code == 200
    r2 = requests.post(
        f"{BASE_URL}/api/integrations/sicon/test-connection", headers=auth, timeout=15
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body.get("status") == "error"
    assert "Base URL" in body["message"] or "base_url" in body["message"].lower()

    # Restore base_url so other tests have a value
    requests.put(
        f"{BASE_URL}/api/integrations/sicon",
        headers=auth,
        json={"base_url": "https://sicon-test.example.com"},
        timeout=15,
    )


# ---------------- Bug 4: event log entries exist for expand -----------------
def test_bug4_event_log_contains_recent_entries(auth):
    # trigger at least one event via test-connection (already fired above but
    # do one more for safety) then list logs
    requests.post(
        f"{BASE_URL}/api/integrations/sicon/test-connection", headers=auth, timeout=20
    )
    r = requests.get(
        f"{BASE_URL}/api/integrations/sicon/logs?limit=20", headers=auth, timeout=15
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "logs" in data and isinstance(data["logs"], list)
    assert data["total"] >= 1
    # Each log row exposes the fields the frontend expand block relies on
    log = data["logs"][0]
    for key in ("event_type", "direction", "success", "timestamp"):
        assert key in log, f"log missing key {key}: {log}"
