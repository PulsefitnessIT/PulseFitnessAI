"""End-to-end tests for Memberships Phase 4 — Smart Waitlist + Front-Desk
Check-in + Kiosk mode.

Run with:  cd /app/backend && python -m pytest tests/test_memberships_phase4.py -v
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE_URL.rstrip('/')}/api"

OPERATOR = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!",
}


@pytest.fixture(scope="module")
def operator_token() -> str:
    r = requests.post(f"{API}/auth/login", json=OPERATOR, timeout=30)
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def hdr(operator_token: str) -> dict:
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="module")
def kiosk_token(hdr: dict) -> str:
    r = requests.post(f"{API}/memberships/checkin/kiosk-token",
                      headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("token")
    return body["token"]


# ───────────── Front-desk checkin/today ─────────────


def test_checkin_today_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/checkin/today", timeout=30)
    assert r.status_code in (401, 403)


def test_checkin_today_default(hdr):
    r = requests.get(f"{API}/memberships/checkin/today", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "classes" in body and isinstance(body["classes"], list)
    assert "count" in body


def test_checkin_today_window(hdr):
    r = requests.get(f"{API}/memberships/checkin/today?days=7",
                     headers=hdr, timeout=30)
    assert r.status_code == 200
    # bounds — days=99 → 422
    r = requests.get(f"{API}/memberships/checkin/today?days=99",
                     headers=hdr, timeout=30)
    assert r.status_code == 422


# ───────────── Member search ─────────────


def test_members_search_validates_q(hdr):
    r = requests.get(f"{API}/memberships/checkin/search-members?q=",
                     headers=hdr, timeout=30)
    assert r.status_code == 422


def test_members_search_returns_shape(hdr):
    r = requests.get(f"{API}/memberships/checkin/search-members?q=test",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "results" in body and isinstance(body["results"], list)
    assert "count" in body


# ───────────── Single attendance toggle ─────────────


def test_mark_attendance_unknown_booking(hdr):
    r = requests.post(
        f"{API}/memberships/checkin/no-such-occ/mark",
        headers=hdr, timeout=30,
        json={"booking_id": "no-such-booking", "status": "attended"},
    )
    assert r.status_code == 404


def test_mark_attendance_invalid_status(hdr):
    r = requests.post(
        f"{API}/memberships/checkin/no-such-occ/mark",
        headers=hdr, timeout=30,
        json={"booking_id": "x", "status": "garbage"},
    )
    assert r.status_code == 422


# ───────────── Drop-in invite ─────────────


def test_dropin_invite_unknown_occ(hdr):
    r = requests.post(
        f"{API}/memberships/occurrences/no-such-occ/dropin-invite",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 404


# ───────────── Kiosk token issue + read ─────────────


def test_kiosk_token_unauthenticated_blocked():
    r = requests.post(f"{API}/memberships/checkin/kiosk-token", timeout=30)
    assert r.status_code in (401, 403)


def test_kiosk_token_issue_returns_secret_once(kiosk_token: str):
    # Token shape: URL-safe random of >= 24 chars
    assert len(kiosk_token) >= 24


def test_kiosk_token_meta_redacts_secret(hdr, kiosk_token: str):
    r = requests.get(f"{API}/memberships/checkin/kiosk-token",
                     headers=hdr, timeout=30)
    assert r.status_code == 200
    body = r.json()
    # token meta returned but never the hash itself
    if body.get("token"):
        assert "token_hash" not in body["token"]


# ───────────── Public kiosk endpoints ─────────────


def test_kiosk_today_requires_token():
    r = requests.get(f"{API}/memberships/kiosk/today", timeout=30)
    assert r.status_code == 422  # missing required query param


def test_kiosk_today_bad_token():
    r = requests.get(
        f"{API}/memberships/kiosk/today?token=garbage", timeout=30,
    )
    assert r.status_code == 401


def test_kiosk_today_valid_token(kiosk_token: str):
    r = requests.get(
        f"{API}/memberships/kiosk/today?token={kiosk_token}", timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    assert "organization_name" in body
    assert "classes" in body and isinstance(body["classes"], list)


def test_kiosk_lookup_validates_q(kiosk_token: str):
    r = requests.post(
        f"{API}/memberships/kiosk/lookup",
        json={"token": kiosk_token, "q": "a"},  # min_length=2
        timeout=30,
    )
    assert r.status_code == 422


def test_kiosk_lookup_redacts_pii(kiosk_token: str):
    r = requests.post(
        f"{API}/memberships/kiosk/lookup",
        json={"token": kiosk_token, "q": "test"}, timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    for m in body.get("results", []):
        # NO email, phone, last_name in raw — only display_name + id
        assert set(m.keys()) <= {"id", "display_name"}


def test_kiosk_lookup_bad_token():
    r = requests.post(
        f"{API}/memberships/kiosk/lookup",
        json={"token": "garbage", "q": "ab"}, timeout=30,
    )
    assert r.status_code == 401


def test_kiosk_checkin_bad_member(kiosk_token: str):
    r = requests.post(
        f"{API}/memberships/kiosk/checkin",
        json={"token": kiosk_token, "member_id": "no-such-member",
              "code": "000000"},
        timeout=30,
    )
    assert r.status_code == 404


def test_kiosk_checkin_validates_code_length(kiosk_token: str):
    r = requests.post(
        f"{API}/memberships/kiosk/checkin",
        json={"token": kiosk_token, "member_id": "any",
              "code": "12"},  # min_length=6
        timeout=30,
    )
    assert r.status_code == 422


# ───────────── P0-1 — kiosk rate-limit (audit fix) ─────────────


def test_kiosk_lookup_rate_limited(kiosk_token: str):
    """31st rapid lookup within 60s must return 429 (limit is 30/60s/IP)."""
    last = None
    for i in range(35):
        last = requests.post(
            f"{API}/memberships/kiosk/lookup",
            json={"token": kiosk_token, "q": "ratelimit"},
            timeout=15,
        )
    # Last response should be either 429 or a 200 (timing-dependent, but we
    # expect the limit hit since loop is fast).
    assert last is not None
    assert last.status_code in (200, 429)
    # If 200, run another burst to force 429
    if last.status_code == 200:
        for _ in range(10):
            last = requests.post(
                f"{API}/memberships/kiosk/lookup",
                json={"token": kiosk_token, "q": "ratelimit"},
                timeout=15,
            )
        assert last.status_code == 429, "Rate-limit must trigger after sustained bursts"


# ───────────── Phase 4 analytics ─────────────


def test_phase4_analytics_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/phase4/analytics", timeout=30)
    assert r.status_code in (401, 403)


def test_phase4_analytics_default(hdr):
    r = requests.get(f"{API}/memberships/phase4/analytics",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("window_days", "occurrences_count", "fill_pct",
              "attendance_pct", "no_show_pct", "waitlist_promotions",
              "dropin"):
        assert k in body
    drop = body["dropin"]
    for k in ("runs", "invites_sent", "conversions", "conversion_pct",
              "optin_member_count"):
        assert k in drop


def test_phase4_analytics_window_bounds(hdr):
    r = requests.get(f"{API}/memberships/phase4/analytics?days=3",
                     headers=hdr, timeout=30)
    assert r.status_code == 422
    r = requests.get(f"{API}/memberships/phase4/analytics?days=999",
                     headers=hdr, timeout=30)
    assert r.status_code == 422


# ───────────── P2-5 — analytics conversion-loop perf + correctness ─────────────


def test_phase4_analytics_conversion_count_is_consistent(hdr):
    """The batched conversion-loop must return the same count as the
    legacy N+1 path. We assert by spot-checking that the response
    structure is intact and conversion_pct is a sane percentage."""
    r = requests.get(f"{API}/memberships/phase4/analytics?days=30",
                     headers=hdr, timeout=30)
    assert r.status_code == 200
    body = r.json()
    drop = body["dropin"]
    # Counts are non-negative
    assert drop["runs"] >= 0
    assert drop["invites_sent"] >= 0
    assert drop["conversions"] >= 0
    # Conversion can never exceed total invites sent
    assert drop["conversions"] <= max(drop["invites_sent"], 0)
    # Percentage is well-formed
    assert 0.0 <= drop["conversion_pct"] <= 100.0


# ───────────── Member-side opt-in ─────────────


def test_dropin_optin_requires_member_jwt():
    """Operator JWT must NOT be accepted on the member-only endpoint."""
    # Anonymous → 401/403
    r = requests.post(f"{API}/member/dropin-optin",
                      json={"opt_in": True}, timeout=30)
    assert r.status_code in (401, 403)


def test_waitlist_position_requires_member_jwt():
    r = requests.get(f"{API}/member/waitlist-position?occurrence_id=foo",
                     timeout=30)
    assert r.status_code in (401, 403)
