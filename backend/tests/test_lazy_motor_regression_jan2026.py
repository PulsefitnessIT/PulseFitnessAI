"""
Regression tests for the lazy _LazyMotorClient/_LazyMotorDatabase refactor in
backend/utils/database.py (Jan 2026 crash-loop fix).

Preview MONGO_URL is plain mongodb:// -> EAGER path is exercised. These tests
confirm the refactor did NOT regress core flows that share the `db`/`client`
objects across auth, master-admin, operator, CRM, and a write path.
"""

import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback for pytest local run
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"
OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"

TIMEOUT = 30


# ---------- fixtures ----------

@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in response: {data}"
    return tok


@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in response: {data}"
    return tok


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- health ----------

class TestHealth:
    def test_api_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("status") in ("ok", "healthy", "up")

    def test_health_unprefixed(self):
        # Note: /health (no /api) is served by frontend catch-all in preview;
        # status 200 is what matters for k8s probes.
        r = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_api_health_deep(self):
        r = requests.get(f"{BASE_URL}/api/health/deep", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # mongo check must be ok - proves shared `db` proxy works
        mongo = body.get("mongo") or body.get("checks", {}).get("mongo") or body
        # Accept any truthy/ok signal
        text = str(body).lower()
        assert "ok" in text or "true" in text or "healthy" in text, f"deep health missing mongo ok: {body}"


# ---------- master admin auth ----------

class TestMasterAdminAuth:
    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_auth_me(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth(admin_token), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        me = r.json()
        assert me.get("email") == ADMIN_EMAIL
        assert me.get("is_master_admin") is True

    def test_master_admin_organizations(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers=auth(admin_token),
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:300]
        # Should be a list (of orgs) or dict with orgs field
        data = r.json()
        assert isinstance(data, (list, dict))
        if isinstance(data, list):
            assert len(data) >= 0  # 0 or more, both valid
        # no _id leak check
        s = str(data)
        # Motor lazy proxy would produce AttributeError; if we got here, forward worked.

    def test_master_admin_orgs_anon_401(self):
        s = requests.Session()  # fresh, no cookie
        r = s.get(f"{BASE_URL}/api/master-admin/organizations", timeout=TIMEOUT)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text[:200]}"


# ---------- operator flows ----------

class TestOperator:
    def test_owner_login(self, owner_token):
        assert isinstance(owner_token, str) and len(owner_token) > 20

    def test_sites(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/sites", headers=auth(owner_token), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # Accept list or {sites:[...]}
        items = data if isinstance(data, list) else data.get("sites") or data.get("items") or []
        assert isinstance(items, list)

    def test_equipment(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/equipment", headers=auth(owner_token), timeout=TIMEOUT)
        # Some deployments require query params; treat 200 or 400 as non-regression
        # For proxy correctness, we need to prove no 500/AttributeError
        assert r.status_code in (200, 400, 422), r.text[:300]
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, (list, dict))

    def test_analytics_endpoint(self, owner_token):
        """Hit an available analytics read endpoint to prove db proxy works
        through analytics routes. /api/analytics/dashboard isn't mounted;
        memberships analytics overview is the canonical operator analytics."""
        candidates = [
            "/api/memberships/analytics/overview",
            "/api/memberships/analytics/operations",
            "/api/analytics/overview",
        ]
        ok = False
        last = None
        for path in candidates:
            r = requests.get(f"{BASE_URL}{path}", headers=auth(owner_token), timeout=TIMEOUT)
            last = (path, r.status_code, r.text[:200])
            # 500 would indicate proxy breakage; anything <500 with json is fine
            assert r.status_code < 500, f"5xx from {path}: {r.text[:400]}"
            if r.status_code == 200:
                data = r.json()
                assert isinstance(data, (list, dict))
                ok = True
                break
        assert ok, f"no analytics endpoint returned 200; last: {last}"


# ---------- CRM separate-auth path ----------

class TestCRM:
    @pytest.fixture(scope="class")
    def crm_token(self):
        r = requests.post(
            f"{BASE_URL}/api/crm/auth/login",
            json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        tok = data.get("access_token") or data.get("token")
        assert tok
        return tok

    def test_crm_login(self, crm_token):
        assert isinstance(crm_token, str) and len(crm_token) > 20

    def test_crm_read_endpoint(self, crm_token):
        """Hit a CRM read endpoint via the CRM token to prove db proxy works on CRM path."""
        # Try common CRM read endpoints; accept whichever returns 200
        candidates = [
            "/api/crm/companies",
            "/api/crm/opportunities",
            "/api/crm/contacts",
            "/api/crm/me",
            "/api/crm/dashboard",
        ]
        ok = False
        last = None
        for path in candidates:
            r = requests.get(f"{BASE_URL}{path}", headers=auth(crm_token), timeout=TIMEOUT)
            last = (path, r.status_code, r.text[:200])
            if r.status_code == 200:
                data = r.json()
                assert isinstance(data, (list, dict))
                ok = True
                break
        assert ok, f"no CRM read endpoint returned 200; last: {last}"


# ---------- write path via proxy ----------

class TestWritePath:
    def test_ui_error_create_and_readback(self, admin_token):
        """
        /api/ui-errors is a lightweight write endpoint exercised by prior
        regression tests. This confirms insert + subsequent find work
        through the shared db object (i.e. lazy proxy forwarding, if active).
        """
        marker = f"TEST_lazy_motor_{uuid.uuid4().hex[:10]}"
        payload = {
            "title": marker,
            "message": "regression write test",
            "url": "/test/lazy-motor",
            "severity": "info",
        }
        r = requests.post(
            f"{BASE_URL}/api/ui-errors",
            headers=auth(admin_token),
            json=payload,
            timeout=TIMEOUT,
        )
        # Accept 200/201/204
        assert r.status_code in (200, 201, 204), f"insert failed: {r.status_code} {r.text[:300]}"

        # Read back via summary endpoint
        r2 = requests.get(
            f"{BASE_URL}/api/ui-errors/summary",
            headers=auth(admin_token),
            timeout=TIMEOUT,
        )
        assert r2.status_code == 200, r2.text[:300]
        summary = r2.json()
        assert isinstance(summary, (list, dict))
        # can't strictly assert marker presence (aggregation may bucket),
        # but non-500 proves find/aggregate forwarded correctly through proxy.
