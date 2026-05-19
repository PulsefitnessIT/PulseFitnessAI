"""Regression tests for iter 216h113f — MOD portal-scope isolation.

Ensures the MODService login surface is its own auth boundary:
  * MOD accounts on portal=mod → success
  * MOD accounts on standard login → 403 with redirect message
  * Non-MOD accounts on portal=mod → 403 with "not registered" message
  * Non-MOD accounts on standard login → success (unchanged)
"""
from __future__ import annotations

import pytest
import requests

from tests.conftest import _test_backend_url

API = _test_backend_url() + "/api"


def _master_seed():
    try:
        r = requests.post(
            f"{API}/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
            timeout=10,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        pytest.skip(f"Live API unreachable ({type(e).__name__}) — skipping live-server test")
    r.raise_for_status()
    tok = r.json()["token"]
    try:
        requests.post(
            f"{API}/mod/demo/seed-army-catterick",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=20,
        ).raise_for_status()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        pytest.skip(f"Live API unreachable ({type(e).__name__}) — skipping live-server test")


def test_mod_account_on_mod_portal_succeeds():
    _master_seed()
    r = requests.post(
        f"{API}/auth/login",
        json={
            "email": "daniel.hayes@army.mod.local",
            "password": "ArmyDemo2026!",
            "portal": "mod",
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("token")


def test_mod_account_on_standard_portal_blocked_with_clear_message():
    _master_seed()
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "daniel.hayes@army.mod.local", "password": "ArmyDemo2026!"},
        timeout=15,
    )
    assert r.status_code == 403, r.text
    detail = r.json()["detail"].lower()
    assert "mod service portal" in detail or "/modservice" in detail


def test_non_mod_account_on_mod_portal_blocked():
    """Master admin (account_type=full / is_master_admin) trying to
    sign in via the MOD page must be rejected with the not-registered
    message. This is the Lee-Somers-from-Third-Space leak guard."""
    r = requests.post(
        f"{API}/auth/login",
        json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!",
            "portal": "mod",
        },
        timeout=15,
    )
    assert r.status_code == 403, r.text
    assert "not registered" in r.json()["detail"].lower()


def test_non_mod_account_on_standard_portal_succeeds():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json().get("token")
