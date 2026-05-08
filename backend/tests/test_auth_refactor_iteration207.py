"""Auth + CRM cross-login regression tests.

Locks in the behaviour of the refactored ``auth.login`` and
``crm_cross_login`` endpoints (iteration 207). Each of the 5 phases of
``login`` and the 4 phases of ``cross-login`` is covered by at least one
test so future edits can't silently break the contract.
"""
import requests

from tests.conftest import (
    _test_backend_url, rate_limit_bypass_headers,
    MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD,
    PULSE_PRO_EMAIL, PULSE_PRO_PASSWORD,
)


BASE = _test_backend_url()


def _login(email: str, password: str) -> requests.Response:
    return requests.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )


# ── /api/auth/login ────────────────────────────────────────────────


def test_login_master_admin_succeeds():
    r = _login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token")
    assert body["user"]["is_master_admin"] is True


def test_login_pulse_pro_owner_succeeds():
    r = _login(PULSE_PRO_EMAIL, PULSE_PRO_PASSWORD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token")
    assert body["user"]["role"] == "owner"


def test_login_wrong_password_returns_401():
    r = _login(MASTER_ADMIN_EMAIL, "definitely-wrong-password")
    assert r.status_code == 401


def test_login_unknown_user_returns_401():
    r = _login("ghost@nowhere.local", "irrelevant")
    assert r.status_code == 401


def test_login_email_is_lowercased_and_trimmed():
    """The login orchestrator strips + lowercases the identifier before
    looking the user up. Verifies the helper kept that behaviour."""
    r = _login(f"  {MASTER_ADMIN_EMAIL.upper()}  ", MASTER_ADMIN_PASSWORD)
    assert r.status_code == 200, r.text


def test_login_response_contains_module_access_keys():
    """``_build_login_user_payload`` enriches the user with feature flags +
    module access. Refactor must not drop these fields."""
    r = _login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD)
    assert r.status_code == 200
    user = r.json()["user"]
    for k in ("module_access", "modules", "module_overrides", "timetable_view_only"):
        assert k in user, f"missing key {k} in login response"


# ── /api/crm/auth/cross-login ─────────────────────────────────────


def test_cross_login_master_admin_gets_admin_role():
    main_token = _login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD).json()["token"]
    r = requests.post(
        f"{BASE}/api/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main_token}", **rate_limit_bypass_headers()},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token")
    assert body["user"]["role"] == "admin"
    # Master admin → GymAxis brand by default.
    assert body["user"]["crm_brand"] == "gymaxis"


def test_cross_login_pulse_owner_gets_pulse_brand():
    """Owner of a `pulse_pro` org should land in the Pulse-branded CRM."""
    main_token = _login(PULSE_PRO_EMAIL, PULSE_PRO_PASSWORD).json()["token"]
    r = requests.post(
        f"{BASE}/api/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main_token}", **rate_limit_bypass_headers()},
        timeout=10,
    )
    # CRM module may be off for this org → 403 is acceptable. We only
    # care that the brand-resolution helper picks "pulse" when 200.
    if r.status_code == 200:
        assert r.json()["user"]["crm_brand"] == "pulse"
    else:
        assert r.status_code == 403


def test_cross_login_invalid_token_returns_401():
    r = requests.post(
        f"{BASE}/api/crm/auth/cross-login",
        headers={"Authorization": "Bearer garbage-not-a-jwt", **rate_limit_bypass_headers()},
        timeout=10,
    )
    assert r.status_code == 401


def test_cross_login_already_crm_token_returns_400():
    """A CRM-domain token must not be re-used for cross-login."""
    main_token = _login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD).json()["token"]
    crm_token_resp = requests.post(
        f"{BASE}/api/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main_token}", **rate_limit_bypass_headers()},
        timeout=10,
    )
    assert crm_token_resp.status_code == 200
    crm_token = crm_token_resp.json()["token"]
    # Round-trip the CRM token back through cross-login.
    r = requests.post(
        f"{BASE}/api/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {crm_token}", **rate_limit_bypass_headers()},
        timeout=10,
    )
    assert r.status_code == 400


def test_cross_login_idempotent_for_same_user():
    """Calling cross-login twice for the same operator must not duplicate
    the CRM user — the second call refreshes brand flags only."""
    main_token = _login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD).json()["token"]
    h = {"Authorization": f"Bearer {main_token}", **rate_limit_bypass_headers()}
    r1 = requests.post(f"{BASE}/api/crm/auth/cross-login", headers=h, timeout=10)
    r2 = requests.post(f"{BASE}/api/crm/auth/cross-login", headers=h, timeout=10)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["user"]["id"] == r2.json()["user"]["id"], "cross-login created a duplicate CRM user"
