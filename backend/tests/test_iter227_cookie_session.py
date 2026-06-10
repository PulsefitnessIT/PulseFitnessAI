"""Iter 227 — P3 security: localStorage JWT → HttpOnly cookie (main session).

Verifies the scoped migration's backend contract:
  • /auth/login sets the HttpOnly `ga_session` cookie.
  • The session authenticates via cookie alone (no Authorization header).
  • A literal `Authorization: Bearer cookie` / `null` / `undefined` sentinel
    is IGNORED and falls through to the cookie (so legacy call-sites that
    read the now-sentinel localStorage token don't 401 the main session).
  • /auth/refresh rotates the cookie for a cookie/sentinel session, but
    does NOT touch the cookie for a real header token (impersonation safety).
  • /auth/logout clears the cookie.
"""
import requests
import pytest

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
MASTER = ("admin@gymaxisai.com", "MasterAdmin123!")


@pytest.fixture
def session_cookie():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": MASTER[0], "password": MASTER[1]},
               headers=rate_limit_bypass_headers(), timeout=15)
    if r.status_code != 200:
        pytest.skip("master login unavailable")
    assert "ga_session" in s.cookies, "login did not set ga_session cookie"
    return s


def test_login_sets_cookie_and_cookie_only_auth(session_cookie):
    # No Authorization header — cookie alone must authenticate.
    r = session_cookie.get(f"{BASE}/api/auth/me", headers=rate_limit_bypass_headers(), timeout=15)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("sentinel", ["cookie", "null", "undefined"])
def test_bearer_sentinel_falls_through_to_cookie(session_cookie, sentinel):
    r = session_cookie.get(
        f"{BASE}/api/auth/me",
        headers={**rate_limit_bypass_headers(), "Authorization": f"Bearer {sentinel}"},
        timeout=15,
    )
    assert r.status_code == 200, f"sentinel '{sentinel}' should fall through to cookie: {r.text}"


def test_sentinel_without_cookie_is_401():
    r = requests.get(
        f"{BASE}/api/auth/me",
        headers={**rate_limit_bypass_headers(), "Authorization": "Bearer cookie"},
        timeout=15,
    )
    assert r.status_code == 401


def test_main_refresh_rotates_cookie(session_cookie):
    r = session_cookie.post(
        f"{BASE}/api/auth/refresh",
        headers={**rate_limit_bypass_headers(), "Authorization": "Bearer cookie"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    # Set-Cookie for ga_session must be present on a cookie/sentinel refresh.
    sc = r.headers.get("set-cookie", "")
    assert "ga_session" in sc, "main refresh should rotate the cookie"


def test_impersonation_refresh_does_not_touch_cookie(session_cookie):
    # Mint an impersonation token (real header token) and refresh it.
    token = session_cookie.cookies.get("ga_session")
    eng = requests.get(f"{BASE}/api/master-admin/engineers",
                       headers={**rate_limit_bypass_headers(), "Authorization": f"Bearer {token}"},
                       timeout=15).json().get("engineers", [])
    if not eng:
        pytest.skip("no engineers to impersonate")
    imp = requests.post(f"{BASE}/api/master-admin/impersonate/{eng[0]['id']}",
                        headers={**rate_limit_bypass_headers(), "Authorization": f"Bearer {token}"},
                        timeout=15)
    assert imp.status_code == 200, imp.text
    imp_token = imp.json()["token"]
    r = requests.post(f"{BASE}/api/auth/refresh",
                      headers={**rate_limit_bypass_headers(), "Authorization": f"Bearer {imp_token}"},
                      timeout=15)
    assert r.status_code == 200, r.text
    assert "ga_session" not in r.headers.get("set-cookie", ""), \
        "impersonation refresh must NOT overwrite the operator cookie"


def test_logout_clears_cookie(session_cookie):
    r = session_cookie.post(f"{BASE}/api/auth/logout", headers=rate_limit_bypass_headers(), timeout=15)
    assert r.status_code == 200, r.text
    sc = r.headers.get("set-cookie", "")
    assert "ga_session" in sc and ("Max-Age=0" in sc or "max-age=0" in sc.lower() or "01 Jan 1970" in sc or "expires=" in sc.lower())
