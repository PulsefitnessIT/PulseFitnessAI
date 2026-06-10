"""Iter 232 — Active sessions panel + "sign out everywhere".

Endpoints under test (routes/auth.py):
  * GET  /api/auth/sessions                      — list device sessions
  * POST /api/auth/sessions/{id}/revoke          — sign out ONE other device
  * POST /api/auth/sessions/revoke-others        — sign out everywhere else

Sessions are recorded at login/register/mfa-verify and rotated in-place
on /auth/refresh (utils/auth.py::record_user_session).
"""

import time
import uuid

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

# Iter 230 lesson — NEVER mutate token-revocation state on live seeded
# accounts (it cascades 401s through the rest of the suite). All tests
# here run against a dedicated throwaway user registered once per run.
_TEST_EMAIL = f"iter232-sessions-{uuid.uuid4().hex[:8]}@example.com"
_TEST_PASSWORD = "Sessions232!"
_registered = False


def _ensure_user():
    global _registered
    if _registered:
        return
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": _TEST_EMAIL, "password": _TEST_PASSWORD,
        "full_name": "Sessions Panel Tester",
    }, timeout=20)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    _registered = True


def _login(ua: str) -> requests.Session:
    _ensure_user()
    s = requests.Session()
    s.headers["User-Agent"] = ua
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    assert s.cookies.get("ga_session")
    return s


def test_sessions_requires_auth():
    r = requests.get(f"{BASE_URL}/api/auth/sessions", timeout=20)
    assert r.status_code == 401


def test_login_registers_session_with_current_flag_and_device():
    s = _login("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0")
    r = s.get(f"{BASE_URL}/api/auth/sessions", timeout=20)
    assert r.status_code == 200, r.text
    rows = r.json()["sessions"]
    assert rows, "login must register a session row"
    current = [x for x in rows if x["current"]]
    assert len(current) == 1, f"exactly one current session expected: {rows}"
    assert "Chrome" in current[0]["device"] and "Windows" in current[0]["device"]
    assert current[0]["last_seen_at"]
    # jti must never leak to the client
    assert "jti" not in current[0]


def test_refresh_rotates_session_in_place():
    s = _login("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1")
    before = [x for x in s.get(f"{BASE_URL}/api/auth/sessions", timeout=20).json()["sessions"] if x["current"]][0]
    r = s.post(f"{BASE_URL}/api/auth/refresh", json={}, timeout=20)
    assert r.status_code == 200
    after_rows = s.get(f"{BASE_URL}/api/auth/sessions", timeout=20).json()["sessions"]
    after = [x for x in after_rows if x["current"]]
    assert len(after) == 1, f"rotation must keep ONE current row: {after_rows}"
    assert after[0]["id"] == before["id"], "refresh must rotate the SAME session row, not add one"


def test_revoke_single_other_device():
    a = _login("Mozilla/5.0 (Macintosh) Chrome/126.0")        # device A (keeper)
    b = _login("Mozilla/5.0 (Linux; Android 14) Chrome/126.0")  # device B (victim)
    # B works pre-revoke
    assert b.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 200
    rows = a.get(f"{BASE_URL}/api/auth/sessions", timeout=20).json()["sessions"]
    android = [x for x in rows if not x["current"] and "Android" in x["device"]]
    assert android, f"device B row not visible from A: {rows}"
    r = a.post(f"{BASE_URL}/api/auth/sessions/{android[0]['id']}/revoke", timeout=20)
    assert r.status_code == 200, r.text
    time.sleep(0.3)
    assert b.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 401, \
        "revoked device must lose access"
    assert a.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 200, \
        "keeper device must stay signed in"


def test_cannot_revoke_current_session_via_panel():
    s = _login("Mozilla/5.0 (Windows NT 10.0) Chrome/126.0")
    cur = [x for x in s.get(f"{BASE_URL}/api/auth/sessions", timeout=20).json()["sessions"] if x["current"]][0]
    r = s.post(f"{BASE_URL}/api/auth/sessions/{cur['id']}/revoke", timeout=20)
    assert r.status_code == 400


def test_sign_out_everywhere_keeps_current_kills_others():
    a = _login("Mozilla/5.0 (Macintosh) Chrome/126.0")          # keeper
    b = _login("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1")
    c = _login("Mozilla/5.0 (Linux; Android 14) Firefox/127.0")
    assert b.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 200
    assert c.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 200

    r = a.post(f"{BASE_URL}/api/auth/sessions/revoke-others", timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["revoked"] >= 2

    time.sleep(0.3)
    assert a.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 200, \
        "current device must survive sign-out-everywhere"
    assert b.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 401
    assert c.get(f"{BASE_URL}/api/auth/me", timeout=20).status_code == 401

    rows = a.get(f"{BASE_URL}/api/auth/sessions", timeout=20).json()["sessions"]
    assert all(x["current"] for x in rows), f"only the current session should remain: {rows}"


def test_revoke_foreign_session_404():
    s = _login("Mozilla/5.0 (Windows NT 10.0) Chrome/126.0")
    r = s.post(f"{BASE_URL}/api/auth/sessions/not-a-real-session-id/revoke", timeout=20)
    assert r.status_code == 404
