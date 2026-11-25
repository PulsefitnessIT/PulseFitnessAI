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
            "email": "catterick.demo.lead@army.mod.local",
            "password": "ArmyDemo2026!",
            "portal": "mod",
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # HQ/branch MOD accounts must enrol MFA; passing the portal gate is what matters here.
    assert body.get("token") or body.get("requires_mfa_enrolment") or body.get("requires_mfa")


def test_mod_account_on_standard_portal_blocked_with_clear_message():
    _master_seed()
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "catterick.demo.lead@army.mod.local", "password": "ArmyDemo2026!"},
        timeout=15,
    )
    assert r.status_code == 403, r.text
    detail = r.json()["detail"].lower()
    assert "mod service portal" in detail or "/modservice" in detail


def test_non_mod_account_on_mod_portal_blocked():
    """A standard (non-MOD, non-master) account signing in via the MOD page
    must be rejected with the not-registered message. Master admins are
    deliberately allowed through for support access."""
    import uuid
    email = f"nonmod-{uuid.uuid4().hex[:10]}@example.com"
    password = "Zq7!mPw2-" + uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "full_name": "Non MOD", "company_name": "Non MOD Org"},
        timeout=15,
    )
    assert reg.status_code == 200, reg.text
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "portal": "mod"},
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
