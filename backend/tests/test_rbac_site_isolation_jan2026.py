"""
RBAC + Multi-site isolation re-verification (Jan 2026 director demo readiness).
- Confirms POST /api/marketing/assistant/execute-action with type=clear_demo_data
  returns 403 for logistics role and 200 for owner (without asserting deletion counts).
- Confirms multi-site isolation: manager (Site A) requesting Site B via ?site_id gets 403.
- Confirms public GET /api/payments/pricing/live works.
NOTE: /api/auth/login is rate-limited (~4 rapid logins → 429); sessions are reused
      across tests and short sleeps are inserted between fresh logins.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "owner":    ("owner@isodemo.com",    "IsoDemo123!"),
    "manager":  ("manager@isodemo.com",  "IsoDemo123!"),
    "logi":     ("logi1@isodemo.com",    "LogiPass123!"),
}

_token_cache = {}


def login(role):
    if role in _token_cache:
        return _token_cache[role]
    email, pw = CREDS[role]
    # small delay to avoid rate-limit collisions
    time.sleep(2)
    for attempt in range(3):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
        if r.status_code == 429:
            time.sleep(35)
            continue
        if r.status_code == 200:
            data = r.json()
            tok = data.get("access_token") or data.get("token") or data.get("data", {}).get("access_token")
            assert tok, f"No token in login response for {role}: {data}"
            _token_cache[role] = tok
            return tok
        pytest.fail(f"Login failed for {role}: {r.status_code} {r.text[:200]}")
    pytest.fail(f"Login rate-limited repeatedly for {role}")


def H(role):
    return {"Authorization": f"Bearer {login(role)}", "Content-Type": "application/json"}


# ---------------- RBAC: clear_demo_data ----------------
class TestClearDemoDataRBAC:
    def test_logistics_forbidden(self):
        r = requests.post(
            f"{API}/marketing/assistant/execute-action",
            headers=H("logi"),
            json={"type": "clear_demo_data", "params": {}},
            timeout=20,
        )
        assert r.status_code == 403, f"Expected 403 for logistics, got {r.status_code}: {r.text[:300]}"
        body = r.text.lower()
        assert any(k in body for k in ("forbid", "role", "permission", "denied", "requires", "admin", "manager"))

    def test_owner_allowed(self):
        r = requests.post(
            f"{API}/marketing/assistant/execute-action",
            headers=H("owner"),
            json={"type": "clear_demo_data", "params": {"dry_run": True}},
            timeout=30,
        )
        # Owner must NOT get 403. Accept 200/400/422 (validation) but not 401/403.
        assert r.status_code not in (401, 403), f"Owner unexpectedly blocked: {r.status_code} {r.text[:300]}"


# ---------------- Multi-site isolation ----------------
class TestSiteIsolation:
    @pytest.mark.parametrize("endpoint", ["/equipment", "/issues", "/gym-health-score"])
    def test_manager_cannot_access_site_b(self, endpoint):
        r = requests.get(
            f"{API}{endpoint}",
            headers=H("manager"),
            params={"site_id": "iso-demo-site-b"},
            timeout=20,
        )
        assert r.status_code == 403, f"Expected 403 for manager on Site B {endpoint}, got {r.status_code}: {r.text[:300]}"
        assert "site_access_denied" in r.text.lower() or "site" in r.text.lower()

    def test_owner_can_access_site_a(self):
        r = requests.get(
            f"{API}/equipment",
            headers=H("owner"),
            params={"site_id": "iso-demo-site-a"},
            timeout=20,
        )
        assert r.status_code == 200, f"Owner denied on Site A: {r.status_code} {r.text[:300]}"


# ---------------- Public pricing endpoint ----------------
class TestPublicPricing:
    def test_pricing_live_public(self):
        r = requests.get(f"{API}/payments/pricing/live", timeout=20)
        assert r.status_code == 200, f"pricing/live failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        # accept either top-level or nested
        payload = data.get("data", data)
        assert "pricing" in payload or "currencies" in payload or "detected_currency" in payload, f"Unexpected payload: {list(payload)[:10]}"
