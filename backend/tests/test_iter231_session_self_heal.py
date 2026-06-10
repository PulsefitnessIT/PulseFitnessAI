"""Iter 231 — session self-healing (production "instant session expired" bug).

Root cause class: a STALE credential shadowing a HEALTHY HttpOnly
``ga_session`` cookie. Two concrete shadows were identified:

1. A legacy real JWT left in ``localStorage`` is sent as
   ``Authorization: Bearer <stale>`` and used to OVERRIDE the valid
   cookie → every call 401s right after a successful login.
2. A duplicate-scope cookie (e.g. historic ``Domain=.gymaxisai.com``)
   is serialised FIRST by the browser; ``request.cookies`` collapses
   same-named cookies to the first occurrence → the stale value wins.

The fix: ``get_current_user`` / ``try_get_current_user`` now try every
``ga_session`` candidate from the raw Cookie header before rejecting,
and login/refresh emit a delete for the domain-scoped variant.
"""

import os

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"

STALE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJ1c2VyX2lkIjoiZGVhZCIsImp0aSI6ImRlYWQiLCJleHAiOjE2MDAwMDAwMDB9."
    "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdee"
)


def _login_cookie() -> str:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    cookie = s.cookies.get("ga_session")
    assert cookie, "login must set the ga_session cookie"
    return cookie


def test_valid_cookie_authenticates_baseline():
    cookie = _login_cookie()
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Cookie": f"ga_session={cookie}"}, timeout=20)
    assert r.status_code == 200, r.text


def test_stale_bearer_header_no_longer_shadows_valid_cookie():
    """Authorization: Bearer <dead JWT> + valid cookie must be 200."""
    cookie = _login_cookie()
    r = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={
            "Authorization": f"Bearer {STALE_JWT}",
            "Cookie": f"ga_session={cookie}",
        },
        timeout=20,
    )
    assert r.status_code == 200, f"stale header shadowed healthy cookie: {r.status_code} {r.text[:200]}"
    assert r.json().get("email") == ADMIN_EMAIL


def test_duplicate_scope_stale_cookie_first_no_longer_shadows():
    """Cookie: ga_session=<stale>; ga_session=<valid> must be 200.

    Browsers serialise an older domain-scoped duplicate BEFORE the
    fresh host-only cookie; the first occurrence used to win and 401
    the whole session.
    """
    cookie = _login_cookie()
    r = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Cookie": f"ga_session={STALE_JWT}; ga_session={cookie}"},
        timeout=20,
    )
    assert r.status_code == 200, f"stale duplicate cookie shadowed session: {r.status_code} {r.text[:200]}"
    assert r.json().get("email") == ADMIN_EMAIL


def test_garbage_only_still_rejected():
    r = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Cookie": f"ga_session={STALE_JWT}"},
        timeout=20,
    )
    assert r.status_code == 401


def test_login_purges_domain_scoped_cookie_variant():
    """Login must emit a delete for the Domain=.<host> ga_session variant."""
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200
    set_cookies = r.headers.get("Set-Cookie", "")
    # requests folds multiple Set-Cookie headers; use raw headers when available.
    raw = getattr(r.raw, "headers", None)
    all_set = raw.getlist("Set-Cookie") if raw is not None and hasattr(raw, "getlist") else [set_cookies]
    ga = [h for h in all_set if h.strip().lower().startswith("ga_session=")]
    assert any("domain=" in h.lower() and ('max-age=0' in h.lower() or 'expires=' in h.lower())
               for h in ga), f"no domain-scoped purge in Set-Cookie: {ga}"
    assert any("domain=" not in h.lower() and "max-age=" in h.lower()
               for h in ga), f"host-only session cookie missing: {ga}"


def test_refresh_works_with_sentinel_and_stale_header():
    """/auth/refresh with a stale Bearer must still rotate via the cookie."""
    cookie = _login_cookie()
    r = requests.post(
        f"{BASE_URL}/api/auth/refresh", json={},
        headers={
            "Authorization": f"Bearer {STALE_JWT}",
            "Cookie": f"ga_session={cookie}",
        },
        timeout=20,
    )
    assert r.status_code == 200, f"refresh shadowed by stale header: {r.status_code} {r.text[:200]}"


_ = os
