"""Regression tests for the deploy P0 healthfix (Jan 2026):
- Backend boots cleanly (no crash-loop)
- /health and /api/health return 200
- Master admin analytics endpoints (refactored sync pymongo -> async motor) return 200
- Non-admin / unauth on those endpoints is rejected (401/403)
- Email-health + ui-errors (TTL reconciliation targets) still work
- General smoke: /api/master-admin/organizations, /api/auth/me
- Boot log cleanliness: no pymongo OperationFailure traceback, TTL conflicts
  logged as INFO 'already satisfied', libmagic message is WARNING (not ERROR)
"""

import os
import re
import pytest
import requests

def _load_backend_url():
    u = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not u:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        u = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return u.rstrip("/")


BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

ANALYTICS_ENDPOINTS = [
    "/api/master-admin/analytics/dashboard",
    "/api/master-admin/analytics/equipment",
    "/api/master-admin/analytics/faults",
    "/api/master-admin/analytics/checksheets",
    "/api/master-admin/analytics/ai",
]


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    tok = body.get("access_token") or body.get("token")
    assert tok, f"no token in login response: {body}"
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Health ----------
def test_health_root(s):
    r = s.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200, r.text[:300]


def test_health_api(s):
    r = s.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200, r.text[:300]


# ---------- Auth ----------
def test_login_returns_token(admin_token):
    assert isinstance(admin_token, str) and len(admin_token) > 10


def test_auth_me(s, admin_headers):
    r = s.get(f"{BASE_URL}/api/auth/me", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert (data.get("email") or "").lower() == ADMIN_EMAIL


# ---------- Analytics (refactor: sync pymongo -> async motor) ----------
@pytest.mark.parametrize("path", ANALYTICS_ENDPOINTS)
def test_analytics_authorized_ok(s, admin_headers, path):
    r = s.get(f"{BASE_URL}{path}", headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:400]}"
    # Must be valid JSON (dict or list)
    body = r.json()
    assert isinstance(body, (dict, list)), f"{path} returned non-JSON-object: {type(body)}"


@pytest.mark.parametrize("path", ANALYTICS_ENDPOINTS)
def test_analytics_unauthenticated_rejected(path):
    # Use a fresh session so no cookies from admin login leak in
    fresh = requests.Session()
    r = fresh.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code in (401, 403), f"{path} unauth -> {r.status_code}"


def test_analytics_non_admin_rejected(s):
    # Register a fresh non-admin user and confirm they cannot hit analytics
    import uuid
    email = f"regress_{uuid.uuid4().hex[:10]}@example.com"
    reg_sess = requests.Session()
    reg_sess.headers.update({"Content-Type": "application/json"})
    reg = reg_sess.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!", "full_name": "Regress User"},
        timeout=20,
    )
    if reg.status_code not in (200, 201):
        pytest.skip(f"register unavailable: {reg.status_code} {reg.text[:200]}")
    login = reg_sess.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip(f"login of new user failed: {login.status_code}")
    tok = login.json().get("access_token") or login.json().get("token")
    if not tok:
        pytest.skip("no token for new user")
    # Fresh session (bearer only) so we don't reuse admin cookie
    plain = requests.Session()
    plain.headers.update({"Authorization": f"Bearer {tok}"})
    r = plain.get(f"{BASE_URL}{ANALYTICS_ENDPOINTS[0]}", timeout=15)
    assert r.status_code in (401, 403), f"non-admin got {r.status_code}"


# ---------- Email health + UI errors (TTL reconciliation) ----------
def test_email_health(s, admin_headers):
    r = s.get(f"{BASE_URL}/api/master-admin/email-health", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text[:300]


def test_ui_errors_post_anonymous(s):
    r = s.post(
        f"{BASE_URL}/api/ui-errors",
        json={
            "title": "regression test error",
            "detail": "Error: regression",
            "path": "/test",
            "module": "regression",
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("ok") is True, body


def test_ui_errors_summary(s, admin_headers):
    r = s.get(f"{BASE_URL}/api/ui-errors/summary", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text[:300]


# ---------- General smoke ----------
def test_organizations(s, admin_headers):
    r = s.get(
        f"{BASE_URL}/api/master-admin/organizations?limit=1",
        headers=admin_headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]


# ---------- Boot log cleanliness ----------
def _read_backend_logs_latest_boot():
    """Return only the most recent boot's log section (after the last
    'Application startup complete.' line). This avoids flagging errors
    from previous crash-looped boots that pre-date the fix."""
    paths = [
        "/var/log/supervisor/backend.err.log",
        "/var/log/supervisor/backend.out.log",
    ]
    text = ""
    for p in paths:
        try:
            with open(p) as f:
                text += f.read()
        except Exception:
            pass
    marker = "Application startup complete."
    idx = text.rfind(marker)
    if idx == -1:
        return text
    return text[idx:]


def test_no_pymongo_operationfailure_traceback():
    log = _read_backend_logs_latest_boot()
    bad = re.findall(r"pymongo\.errors\.OperationFailure", log)
    assert not bad, f"pymongo OperationFailure traceback present in latest boot: {len(bad)}"


def test_ttl_conflicts_logged_as_info_already_satisfied():
    log = _read_backend_logs_latest_boot()
    for m in re.finditer(r"^(.*already satisfied.*)$", log, re.MULTILINE):
        line = m.group(1)
        assert " - INFO - " in line or "INFO:" in line, f"non-INFO 'already satisfied': {line}"


def test_libmagic_message_is_warning_not_error():
    log = _read_backend_logs_latest_boot()
    for m in re.finditer(r"^(.*libmagic.*)$", log, re.MULTILINE):
        line = m.group(1)
        assert " - ERROR - " not in line and "uploads will fail" not in line.lower(), (
            f"libmagic reported as ERROR in latest boot: {line}"
        )
