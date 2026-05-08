"""Member-app builder regression tests.

Verifies the three endpoints exposed by `routes/member_app_builder.py`:
  - GET  /api/member-app/cards   → registry filtered by brand
  - GET  /api/member-app/layout  → fall-back default + persisted layout
  - PUT  /api/member-app/layout  → persists, validates unknown types
  - POST /api/member-app/layout/reset → resets to defaults

Tests run end-to-end against the live backend so they also catch routing
regressions (e.g. router not registered).
"""
import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers, _login_for_token


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_cards_registry_returns_pulse_card_for_pulse_user(pulse_pro_token):
    assert pulse_pro_token, "pulse pro login failed"
    base = _test_backend_url()
    r = requests.get(f"{base}/api/member-app/cards", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 200, r.text
    cards = r.json().get("cards", [])
    ids = [c["id"] for c in cards]
    # Pulse-only cards must be present for a pulse_pro tenant
    assert "pulse_brag_share" in ids
    # Sanity: standard card always returned
    assert "class_booking" in ids


def test_layout_get_returns_default_when_unset(pulse_pro_token):
    base = _test_backend_url()
    # Reset first so we start from a known state.
    requests.post(f"{base}/api/member-app/layout/reset", json={}, headers=_h(pulse_pro_token), timeout=10)
    r = requests.get(f"{base}/api/member-app/layout", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("layout") is not None
    assert isinstance(body["layout"]["cards"], list)
    assert len(body["layout"]["cards"]) > 0


def test_layout_save_and_reload_round_trips(pulse_pro_token):
    base = _test_backend_url()
    payload = {
        "name": "Default",
        "cards": [
            {"type": "membership_card", "enabled": True},
            {"type": "class_booking", "enabled": False},
            {"type": "my_bookings", "enabled": True, "settings": {"lookahead_days": 30}},
        ],
    }
    r = requests.put(f"{base}/api/member-app/layout", json=payload, headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 200, r.text
    saved = r.json()["layout"]["cards"]
    assert [c["type"] for c in saved] == ["membership_card", "class_booking", "my_bookings"]
    # Reload to confirm persistence
    r = requests.get(f"{base}/api/member-app/layout", headers=_h(pulse_pro_token), timeout=10)
    again = r.json()["layout"]["cards"]
    assert [c["type"] for c in again] == ["membership_card", "class_booking", "my_bookings"]
    # Settings were merged with schema defaults
    bookings_card = next(c for c in again if c["type"] == "my_bookings")
    assert bookings_card["settings"]["lookahead_days"] == 30
    # Disabled flag round-trips
    cb = next(c for c in again if c["type"] == "class_booking")
    assert cb["enabled"] is False


def test_layout_save_rejects_unknown_card_type(pulse_pro_token):
    base = _test_backend_url()
    payload = {"cards": [{"type": "nonexistent_card", "enabled": True}]}
    r = requests.put(f"{base}/api/member-app/layout", json=payload, headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 400, r.text


def test_layout_reset_restores_defaults(pulse_pro_token):
    base = _test_backend_url()
    # Save a tiny custom layout first
    requests.put(
        f"{base}/api/member-app/layout",
        json={"cards": [{"type": "membership_card", "enabled": True}]},
        headers=_h(pulse_pro_token),
        timeout=10,
    )
    r = requests.post(f"{base}/api/member-app/layout/reset", json={}, headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("reset") is True
    # Defaults include several cards, not just one
    assert len(body["layout"]["cards"]) > 1


# ── Additional tests for non-Pulse user and owner/manager requirement ──

def test_cards_registry_excludes_pulse_card_for_non_pulse_user(master_admin_token_session):
    """Non-Pulse user (master admin) should NOT see pulse_brag_share card."""
    assert master_admin_token_session, "master admin login failed"
    base = _test_backend_url()
    r = requests.get(f"{base}/api/member-app/cards", headers=_h(master_admin_token_session), timeout=10)
    assert r.status_code == 200, r.text
    cards = r.json().get("cards", [])
    ids = [c["id"] for c in cards]
    # Pulse-only cards must NOT be present for a non-pulse tenant
    assert "pulse_brag_share" not in ids, f"pulse_brag_share should not be in non-Pulse registry: {ids}"
    # Sanity: standard card always returned
    assert "class_booking" in ids


def test_layout_put_works_for_owner(pulse_pro_token):
    """Verify PUT /api/member-app/layout works for owner (happy path)."""
    assert pulse_pro_token, "pulse pro login failed"
    base = _test_backend_url()
    payload = {
        "name": "Owner Test Layout",
        "cards": [
            {"type": "class_booking", "enabled": True},
            {"type": "my_bookings", "enabled": True},
        ],
    }
    r = requests.put(f"{base}/api/member-app/layout", json=payload, headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 200, f"Owner should be able to save layout: {r.text}"
    saved = r.json()["layout"]["cards"]
    assert len(saved) == 2
    assert [c["type"] for c in saved] == ["class_booking", "my_bookings"]
