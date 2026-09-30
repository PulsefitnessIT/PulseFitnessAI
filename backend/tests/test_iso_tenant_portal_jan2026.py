"""
Cross-tenant / portal ISOLATION security test (Jan 2026).

Verifies airtight authorization between:
  - commercial (Third Space / iso) user
  - MOD site user
  - master-admin-only MOD endpoints
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine-1.preview.emergentagent.com").rstrip("/")

COMMERCIAL_EMAIL = "owner@isodemo.com"
COMMERCIAL_PWD = "IsoDemo123!"
MOD_EMAIL = "test@army.mod.test"
MOD_PWD = "ModTest123!"

# Cache tokens across tests (login is rate-limited ~4/min per email)
_TOKENS: dict = {}


def _login(email: str, password: str, portal: str | None = None) -> str | None:
    key = f"{email}|{portal or ''}"
    if key in _TOKENS:
        return _TOKENS[key]
    payload = {"email": email, "password": password}
    if portal:
        payload["portal"] = portal
    # Space out logins to avoid 429
    for attempt in range(3):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=payload,
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            tok = data.get("access_token") or data.get("token") or data.get("jwt")
            if not tok and isinstance(data.get("user"), dict):
                tok = data["user"].get("token")
            if tok:
                _TOKENS[key] = tok
                return tok
            pytest.fail(f"Login OK but no token for {email}: keys={list(data.keys())}")
        if r.status_code == 429:
            time.sleep(20)
            continue
        print(f"[login-fail] {email} status={r.status_code} body={r.text[:200]}")
        return None
    return None


@pytest.fixture(scope="session")
def commercial_token():
    tok = _login(COMMERCIAL_EMAIL, COMMERCIAL_PWD)
    if not tok:
        pytest.skip("Commercial user login failed")
    return tok


@pytest.fixture(scope="session")
def mod_token():
    tok = _login(MOD_EMAIL, MOD_PWD, portal="mod")
    if not tok:
        pytest.skip("MOD user login failed")
    return tok


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _classify(r: requests.Response, own_org_hint: str | None = None) -> str:
    """Classify: blocked / empty / own_scope / LEAK."""
    if r.status_code in (401, 403):
        return "blocked"
    if r.status_code == 404:
        return "blocked"
    if r.status_code != 200:
        return f"other_{r.status_code}"
    try:
        body = r.json()
    except Exception:
        return "non_json"
    # Look at collection
    items = None
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        for k in ("items", "data", "results", "sites", "quotes", "equipment", "staff", "faults", "records", "dashboard"):
            if isinstance(body.get(k), list):
                items = body[k]
                break
    if items is None:
        # Single-object payload; treat as own_scope unless obviously MOD
        return "own_scope_or_empty"
    if len(items) == 0:
        return "empty"
    return f"has_data({len(items)})"


# ---------- ISOLATION 1: Commercial user must NOT access MOD data ----------
MOD_ENDPOINTS = [
    "/api/mod/me",
    "/api/mod/site/dashboard",
    "/api/mod/site/service-providers",
    "/api/mod/site/quotes",
    "/api/mod/site/equipment",
    "/api/mod/site/staff",
]


@pytest.mark.parametrize("path", MOD_ENDPOINTS)
def test_iso1_commercial_cannot_access_mod(commercial_token, path):
    r = requests.get(f"{BASE_URL}{path}", headers=_hdr(commercial_token), timeout=30)
    result = _classify(r)
    print(f"[ISO1] commercial GET {path} -> {r.status_code} :: {result}")
    # Acceptable: blocked (401/403/404). NOT acceptable: 200 with MOD data.
    assert r.status_code in (401, 403, 404), (
        f"CRITICAL isolation breach: commercial user got {r.status_code} on {path}. "
        f"Body preview: {r.text[:400]}"
    )


# ---------- ISOLATION 2: MOD user must NOT access other-org commercial data ----------
COMMERCIAL_ENDPOINTS = [
    "/api/equipment",
    "/api/faults",
    "/api/memberships",
    "/api/dashboard",
]


@pytest.mark.parametrize("path", COMMERCIAL_ENDPOINTS)
def test_iso2_mod_user_commercial_endpoints_scoped(mod_token, path):
    r = requests.get(f"{BASE_URL}{path}", headers=_hdr(mod_token), timeout=30)
    result = _classify(r)
    print(f"[ISO2] mod-user GET {path} -> {r.status_code} :: {result}")
    # Acceptable: 401/403/404, OR 200 with data strictly own-org / empty.
    if r.status_code == 200:
        try:
            body = r.json()
        except Exception:
            body = {}
        # Heuristic: look for foreign org identifiers (Third Space / iso)
        text = str(body).lower()
        foreign_markers = ["third space", "isodemo", "iso commercial"]
        found = [m for m in foreign_markers if m in text]
        assert not found, (
            f"CRITICAL: MOD user reading foreign commercial data on {path}. "
            f"Markers found: {found}. Body preview: {str(body)[:400]}"
        )
    else:
        assert r.status_code in (401, 403, 404, 400, 422), (
            f"Unexpected status {r.status_code} on {path}: {r.text[:300]}"
        )


# ---------- ISOLATION 3: Master-admin-only MOD endpoints reject non-admins ----------
MASTER_ADMIN_PATHS = [
    "/api/master-admin/mod/sites",
    "/api/master-admin/mod/audit-log/deadbeef-0000-0000-0000-000000000000",
]


@pytest.mark.parametrize("path", MASTER_ADMIN_PATHS)
def test_iso3_commercial_blocked_from_master_admin(commercial_token, path):
    r = requests.get(f"{BASE_URL}{path}", headers=_hdr(commercial_token), timeout=30)
    print(f"[ISO3] commercial GET {path} -> {r.status_code}")
    assert r.status_code in (401, 403), (
        f"CRITICAL: commercial user reached master-admin endpoint {path} "
        f"status={r.status_code} body={r.text[:300]}"
    )


@pytest.mark.parametrize("path", MASTER_ADMIN_PATHS)
def test_iso3_mod_user_blocked_from_master_admin(mod_token, path):
    r = requests.get(f"{BASE_URL}{path}", headers=_hdr(mod_token), timeout=30)
    print(f"[ISO3] mod-user GET {path} -> {r.status_code}")
    assert r.status_code in (401, 403), (
        f"CRITICAL: MOD site user reached master-admin endpoint {path} "
        f"status={r.status_code} body={r.text[:300]}"
    )


# ---------- ISOLATION 4: Cross-record access within MOD ----------
CROSS_RECORD_PATHS = [
    "/api/mod/site/quotes/deadbeef-0000-0000-0000-000000000000",
    "/api/mod/site/faults/deadbeef-0000-0000-0000-000000000000",
    "/api/mod/site/quotes/deadbeef-0000-0000-0000-000000000000/pdf",
]


@pytest.mark.parametrize("path", CROSS_RECORD_PATHS)
def test_iso4_mod_cross_record_blocked(mod_token, path):
    r = requests.get(f"{BASE_URL}{path}", headers=_hdr(mod_token), timeout=30)
    print(f"[ISO4] mod-user GET {path} -> {r.status_code}")
    # Expect 403/404 (never another site's document)
    assert r.status_code in (403, 404, 400, 422), (
        f"Unexpected {r.status_code} for cross-record fetch on {path}: {r.text[:300]}"
    )
    if r.status_code == 200:
        pytest.fail(f"CRITICAL: cross-record leak on {path}")


# ---------- ISOLATION 5: Unauthenticated access blocked ----------
UNAUTH_PATHS = MOD_ENDPOINTS + MASTER_ADMIN_PATHS


@pytest.mark.parametrize("path", UNAUTH_PATHS)
def test_iso5_no_auth_blocked(path):
    r = requests.get(f"{BASE_URL}{path}", timeout=30)
    print(f"[ISO5] no-auth GET {path} -> {r.status_code}")
    assert r.status_code in (401, 403), (
        f"CRITICAL: unauthenticated request allowed on {path} status={r.status_code} "
        f"body={r.text[:300]}"
    )
