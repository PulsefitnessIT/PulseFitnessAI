"""End-to-end tests for Memberships Phase 6 — CRM Integration loop.

Covers the 4-signal detector, default rules, per-org overrides, manual
scan endpoint, and the dashboard / signals / sends views.

Run with:  cd /app/backend && python -m pytest tests/test_memberships_phase6.py -v
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


# ───────── auth ─────────


def test_rules_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/crm-loop/rules", timeout=30)
    assert r.status_code in (401, 403)


def test_dashboard_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/crm-loop/dashboard", timeout=30)
    assert r.status_code in (401, 403)


def test_scan_unauthenticated_blocked():
    r = requests.post(f"{API}/memberships/crm-loop/scan", timeout=30)
    assert r.status_code in (401, 403)


# ───────── rules ─────────


def test_rules_default_set(hdr):
    r = requests.get(f"{API}/memberships/crm-loop/rules", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    rules = r.json()["rules"]
    kinds = {x["kind"] for x in rules}
    # Four canonical signals
    assert kinds == {"missed_class", "inactive_30d",
                     "low_attendance", "high_engagement"}
    for r0 in rules:
        assert "label" in r0 and "description" in r0
        assert isinstance(r0["enabled"], bool)
        assert isinstance(r0["cooldown_hours"], int)
        assert 1 <= r0["cooldown_hours"] <= 24 * 90


def test_rule_update_unknown_kind(hdr):
    r = requests.put(
        f"{API}/memberships/crm-loop/rules/garbage",
        headers=hdr, json={"enabled": False}, timeout=30,
    )
    assert r.status_code == 404


def test_rule_update_empty_body_400(hdr):
    r = requests.put(
        f"{API}/memberships/crm-loop/rules/missed_class",
        headers=hdr, json={}, timeout=30,
    )
    assert r.status_code == 400


def test_rule_update_validates_cooldown_bounds(hdr):
    # ge=1 → 0 should fail
    r = requests.put(
        f"{API}/memberships/crm-loop/rules/missed_class",
        headers=hdr, json={"cooldown_hours": 0}, timeout=30,
    )
    assert r.status_code == 422
    # le=24*90 → 9999 should fail
    r = requests.put(
        f"{API}/memberships/crm-loop/rules/missed_class",
        headers=hdr, json={"cooldown_hours": 9999}, timeout=30,
    )
    assert r.status_code == 422


def test_rule_update_persists(hdr):
    # Set cooldown to 48
    r = requests.put(
        f"{API}/memberships/crm-loop/rules/missed_class",
        headers=hdr, json={"cooldown_hours": 48}, timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.json()["rule"]["cooldown_hours"] == 48
    # Re-list and confirm override applied
    r = requests.get(f"{API}/memberships/crm-loop/rules",
                     headers=hdr, timeout=30)
    assert r.status_code == 200
    rule = next((x for x in r.json()["rules"] if x["kind"] == "missed_class"), None)
    assert rule and rule["cooldown_hours"] == 48
    # Toggle off
    r = requests.put(
        f"{API}/memberships/crm-loop/rules/missed_class",
        headers=hdr, json={"enabled": False}, timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["rule"]["enabled"] is False
    # Restore for any other tests downstream
    requests.put(
        f"{API}/memberships/crm-loop/rules/missed_class",
        headers=hdr, json={"enabled": True, "cooldown_hours": 72}, timeout=30,
    )


# ───────── dashboard ─────────


def test_dashboard_returns_kind_breakdown(hdr):
    r = requests.get(f"{API}/memberships/crm-loop/dashboard?days=14",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 14
    assert set(body["by_kind"].keys()) == {
        "missed_class", "inactive_30d",
        "low_attendance", "high_engagement",
    }
    for stats in body["by_kind"].values():
        assert "signals" in stats and "sends" in stats and "last_sent_at" in stats


def test_dashboard_window_bounds(hdr):
    r = requests.get(f"{API}/memberships/crm-loop/dashboard?days=0",
                     headers=hdr, timeout=30)
    assert r.status_code == 422
    r = requests.get(f"{API}/memberships/crm-loop/dashboard?days=999",
                     headers=hdr, timeout=30)
    assert r.status_code == 422


# ───────── scan ─────────


def test_scan_returns_count(hdr):
    r = requests.post(f"{API}/memberships/crm-loop/scan",
                      headers=hdr, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert "members_scanned" in body
    assert "signals_fired" in body


# ───────── signals + sends ─────────


def test_signals_listing(hdr):
    r = requests.get(f"{API}/memberships/crm-loop/signals?days=14",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "signals" in body and isinstance(body["signals"], list)


def test_signals_filter_by_kind(hdr):
    r = requests.get(
        f"{API}/memberships/crm-loop/signals?kind=missed_class",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 200
    for s in r.json()["signals"]:
        assert s["kind"] == "missed_class"


def test_signals_filter_invalid_kind(hdr):
    r = requests.get(
        f"{API}/memberships/crm-loop/signals?kind=bogus",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 400


def test_sends_listing(hdr):
    r = requests.get(f"{API}/memberships/crm-loop/sends?days=14",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sends" in body and isinstance(body["sends"], list)


def test_sends_window_bounds(hdr):
    r = requests.get(f"{API}/memberships/crm-loop/sends?days=999",
                     headers=hdr, timeout=30)
    assert r.status_code == 422
