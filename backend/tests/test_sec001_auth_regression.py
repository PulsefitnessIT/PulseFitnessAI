"""SEC-001 auth regression: operator-strict get_current_user + portal variant."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine-1.preview.emergentagent.com").rstrip("/")

CREDS = {
    "owner":    ("owner@isodemo.com",           "IsoDemo123!"),
    "admin":    ("admin@pulsefitness.com",      "C2s9yJ3YAhydB4d34-Bykg"),
    "dealer":   ("portal2@fitline.test",        "DealerDemo123!"),
    "logistics":("logi1@isodemo.com",           "LogiPass123!"),
    "staff":    ("portal.staff@pulsedemo.test", "Staff123!"),
}

_token_cache = {}

def _login(role):
    if role in _token_cache:
        return _token_cache[role]
    email, pw = CREDS[role]
    # Retry with backoff for rate limits
    for attempt in range(4):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": pw},
                          timeout=30)
        if r.status_code == 429:
            time.sleep(35)
            continue
        break
    assert r.status_code == 200, f"Login failed for {role}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token for {role}: {r.json()}"
    _token_cache[role] = tok
    time.sleep(2)
    return tok

def _hdr(role):
    return {"Authorization": f"Bearer {_login(role)}"}


# ---------- LOGIN + /auth/me (all roles must bootstrap) ----------
@pytest.mark.parametrize("role", ["owner", "admin", "dealer", "logistics", "staff"])
def test_login_and_auth_me(role):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(role), timeout=20)
    assert r.status_code == 200, f"/auth/me broken for {role}: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("email") or body.get("user", {}).get("email"), f"No email in /auth/me for {role}"


# ---------- OPERATOR REGRESSION ----------
def test_operator_equipment_ok():
    r = requests.get(f"{BASE_URL}/api/equipment", headers=_hdr("owner"), timeout=30)
    assert r.status_code == 200, f"owner should access equipment: {r.status_code} {r.text[:200]}"

def test_admin_equipment_ok():
    r = requests.get(f"{BASE_URL}/api/equipment", headers=_hdr("admin"), timeout=30)
    assert r.status_code == 200, f"admin should access equipment: {r.status_code}"


# ---------- BLOCK VERIFICATION: portal users forbidden on operator endpoints ----------
@pytest.mark.parametrize("role", ["dealer", "logistics", "staff"])
def test_portal_blocked_from_operator_equipment(role):
    r = requests.get(f"{BASE_URL}/api/equipment", headers=_hdr(role), timeout=20)
    assert r.status_code == 403, f"{role} should be 403 on /equipment, got {r.status_code}: {r.text[:200]}"


# ---------- PORTAL FLOWS ----------
def test_dealer_portal_overview():
    r = requests.get(f"{BASE_URL}/api/dealer-parts/portal/me/overview", headers=_hdr("dealer"), timeout=30)
    assert r.status_code == 200, f"dealer portal overview broken: {r.status_code} {r.text[:300]}"

def test_logistics_installs_list():
    r = requests.get(f"{BASE_URL}/api/inventory/logistics/installs", headers=_hdr("logistics"), timeout=30)
    assert r.status_code == 200, f"logistics installs broken: {r.status_code} {r.text[:300]}"

@pytest.mark.parametrize("path", [
    "/api/new-starter/portal/rota",
    "/api/new-starter/portal/timesheet?week_start=2026-01-06",
    "/api/new-starter/portal/holidays",
    "/api/new-starter/portal/documents",
    "/api/new-starter/portal/access",
])
def test_staff_portal_endpoints(path):
    r = requests.get(f"{BASE_URL}{path}", headers=_hdr("staff"), timeout=30)
    # Some endpoints may return 200 with empty list; accept 200. 404 is acceptable ONLY if endpoint truly absent.
    assert r.status_code == 200, f"staff portal {path} broken: {r.status_code} {r.text[:300]}"


# ---------- Operator NOT blocked from portal-accessible endpoints unnecessarily ----------
# (operator should still have /auth/me working; already covered)
