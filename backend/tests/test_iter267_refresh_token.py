"""Iter 267 — long-lived REFRESH token (idle-gap session resume).

Verifies the backend contract for the `ga_refresh` recovery cookie:
  • /auth/login sets BOTH `ga_session` (access) and `ga_refresh` (refresh).
  • When the access token is gone (cookie dropped), /auth/me 401s but
    /auth/refresh mints a fresh access token from the refresh cookie, after
    which /auth/me authenticates again (idle/sleep resume).
  • /auth/logout revokes the refresh token, so replaying it afterwards 401s
    (no session resurrection).
  • The happy-path refresh (valid access token) still rotates as before
    (backward compatible).
"""
import requests
import pytest

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
MASTER = ("admin@gymaxisai.com", "MasterAdmin123!")


def _login():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": MASTER[0], "password": MASTER[1]},
               headers=rate_limit_bypass_headers(), timeout=15)
    if r.status_code != 200:
        pytest.skip("master login unavailable")
    return s


def test_login_sets_both_access_and_refresh_cookies():
    s = _login()
    assert "ga_session" in s.cookies, "login must set the access cookie"
    assert "ga_refresh" in s.cookies, "login must set the long-lived refresh cookie"


def test_refresh_cookie_recovers_expired_access():
    s = _login()
    refresh_val = s.cookies.get("ga_refresh")
    assert refresh_val, "no refresh cookie issued"

    # Simulate the access token having fully lapsed: drop ga_session, keep refresh.
    only_refresh = requests.Session()
    only_refresh.cookies.set("ga_refresh", refresh_val)

    # Without an access token, /auth/me is unauthenticated.
    r_me = only_refresh.get(f"{BASE}/api/auth/me", headers=rate_limit_bypass_headers(), timeout=15)
    assert r_me.status_code == 401, f"expected 401 without access cookie, got {r_me.status_code}"

    # /auth/refresh recovers via the refresh cookie and mints a new access cookie.
    r_ref = only_refresh.post(f"{BASE}/api/auth/refresh", headers=rate_limit_bypass_headers(), timeout=15)
    assert r_ref.status_code == 200, f"refresh recovery failed: {r_ref.text}"
    assert "ga_session" in only_refresh.cookies, "recovery must set a fresh access cookie"

    # Session is resumed.
    r_me2 = only_refresh.get(f"{BASE}/api/auth/me", headers=rate_limit_bypass_headers(), timeout=15)
    assert r_me2.status_code == 200, f"session not resumed after recovery: {r_me2.text}"


def test_logout_revokes_refresh_token():
    s = _login()
    refresh_val = s.cookies.get("ga_refresh")
    assert refresh_val

    # Log out (kills access jti + revokes the refresh token).
    r_lo = s.post(f"{BASE}/api/auth/logout", headers=rate_limit_bypass_headers(), timeout=15)
    assert r_lo.status_code == 200 and r_lo.json().get("success") is True, r_lo.text

    # Replaying the pre-logout refresh cookie must NOT resurrect the session.
    replay = requests.Session()
    replay.cookies.set("ga_refresh", refresh_val)
    r_ref = replay.post(f"{BASE}/api/auth/refresh", headers=rate_limit_bypass_headers(), timeout=15)
    assert r_ref.status_code == 401, f"revoked refresh token must 401, got {r_ref.status_code}"


def test_happy_path_refresh_still_rotates():
    s = _login()
    r = s.post(f"{BASE}/api/auth/refresh", headers=rate_limit_bypass_headers(), timeout=15)
    assert r.status_code == 200, r.text
    # Cookie session still authenticates after rotation.
    r_me = s.get(f"{BASE}/api/auth/me", headers=rate_limit_bypass_headers(), timeout=15)
    assert r_me.status_code == 200, r_me.text


def test_issue_refresh_token_is_non_fatal(monkeypatch):
    """Iter 267 hotfix — the refresh-token write must NEVER break login. If the
    DB insert/index fails (e.g. restricted prod DB perms), issue_refresh_token
    must swallow the error and return None so login still succeeds."""
    import asyncio
    import utils.refresh_tokens as rt

    class _BoomColl:
        async def insert_one(self, *a, **k):
            raise RuntimeError("not authorized on db to execute command insert")
        async def create_index(self, *a, **k):
            raise RuntimeError("not authorized on db to execute command createIndexes")

    class _BoomDB:
        refresh_tokens = _BoomColl()

    class _FakeResp:
        def __init__(self):
            self.cookies_set = []
        def set_cookie(self, **kw):
            self.cookies_set.append(kw)

    monkeypatch.setattr(rt, "db", _BoomDB())
    rt._indexes_ready = False
    resp = _FakeResp()
    # Must NOT raise, and must return None (no cookie set) when the DB is broken.
    out = asyncio.run(rt.issue_refresh_token(resp, "user-123", None, mfa_verified=False))
    assert out is None, "issue_refresh_token should return None on DB failure"
    assert resp.cookies_set == [], "no refresh cookie should be set when the write fails"

