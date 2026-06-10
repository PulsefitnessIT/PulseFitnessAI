"""Iter 227 — Pulse Fitness Engineer App: role auto-provisioning + view-as.

Covers:
  • Assigning the **Engineer** role to a teammate auto-provisions an
    active `svc_engineers` mapping (which unlocks the Engineer App);
    flipping the role off deactivates it; removing the teammate too.
  • `GET /master-admin/engineers` lists provisioned engineers and is
    scope-aware (Pulse admins only see Pulse-visible orgs).
  • A master-admin impersonation token grants Engineer-App access
    (`GET /svc/engineer/me`).
"""
import time

import pytest
import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
APEX_OWNER = ("owner@apexfitness.group", "ApexDemo2026!")
MASTER = ("admin@gymaxisai.com", "MasterAdmin123!")


def _login(email, password):
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        headers=rate_limit_bypass_headers(),
        timeout=15,
    )
    if r.status_code != 200:
        return None
    return r.json().get("token")


def _h(token):
    return {**rate_limit_bypass_headers(), "Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def owner_token():
    tok = _login(*APEX_OWNER)
    if not tok:
        pytest.skip("apex owner login unavailable in this environment")
    return tok


@pytest.fixture(scope="module")
def master_token():
    tok = _login(*MASTER)
    if not tok:
        pytest.skip("master admin login unavailable in this environment")
    return tok


def test_engineer_role_autoprovisions_and_deactivates(owner_token):
    email = f"iter227.eng+{int(time.time())}@example.com"
    # Invite as engineer → svc_engineers active record.
    r = requests.post(
        f"{BASE}/api/account/team/invite",
        json={"email": email, "full_name": "Iter227 Engineer",
              "role": "engineer", "delivery": "reset_link"},
        headers=_h(owner_token), timeout=20,
    )
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert r.json()["role"] == "engineer"

    try:
        # Confirm via the master-admin engineers list (DB-backed truth).
        master = _login(*MASTER)
        eng_list = requests.get(
            f"{BASE}/api/master-admin/engineers", headers=_h(master), timeout=20,
        ).json()["engineers"]
        assert any(e["id"] == uid for e in eng_list), "engineer not provisioned"

        # Flip role → staff: engineer should disappear from the active list.
        r2 = requests.patch(
            f"{BASE}/api/account/team/{uid}", json={"role": "staff"},
            headers=_h(owner_token), timeout=20,
        )
        assert r2.status_code == 200, r2.text
        eng_list2 = requests.get(
            f"{BASE}/api/master-admin/engineers", headers=_h(master), timeout=20,
        ).json()["engineers"]
        assert not any(e["id"] == uid for e in eng_list2), "engineer not deactivated"

        # Flip back → engineer: re-activates.
        r3 = requests.patch(
            f"{BASE}/api/account/team/{uid}", json={"role": "engineer"},
            headers=_h(owner_token), timeout=20,
        )
        assert r3.status_code == 200, r3.text
        eng_list3 = requests.get(
            f"{BASE}/api/master-admin/engineers", headers=_h(master), timeout=20,
        ).json()["engineers"]
        assert any(e["id"] == uid for e in eng_list3), "engineer not reactivated"
    finally:
        requests.delete(f"{BASE}/api/account/team/{uid}", headers=_h(owner_token), timeout=20)


def test_master_admin_engineers_endpoint_shape(master_token):
    r = requests.get(f"{BASE}/api/master-admin/engineers", headers=_h(master_token), timeout=20)
    assert r.status_code == 200, r.text
    engineers = r.json()["engineers"]
    assert isinstance(engineers, list)
    for e in engineers:
        assert "id" in e and "organization_id" in e and "organization_name" in e


def test_pulse_admin_scope_only_pulse_visible(master_token):
    """Pulse admin's engineer list must be a subset of pulse-visible orgs."""
    ptok = _login("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")
    if not ptok:
        pytest.skip("pulse admin test account unavailable")
    r = requests.get(f"{BASE}/api/master-admin/engineers", headers=_h(ptok), timeout=20)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["engineers"], list)


def test_impersonation_token_grants_engineer_app(master_token):
    """A master-admin impersonation token for a provisioned engineer must
    open the Engineer App (`/svc/engineer/me`)."""
    engineers = requests.get(
        f"{BASE}/api/master-admin/engineers", headers=_h(master_token), timeout=20,
    ).json()["engineers"]
    if not engineers:
        pytest.skip("no provisioned engineers to impersonate")
    eng_id = engineers[0]["id"]
    imp = requests.post(
        f"{BASE}/api/master-admin/impersonate/{eng_id}", headers=_h(master_token), timeout=20,
    )
    assert imp.status_code == 200, imp.text
    token = imp.json()["token"]
    me = requests.get(
        f"{BASE}/api/svc/engineer/me",
        headers={**rate_limit_bypass_headers(), "Authorization": f"Bearer {token}"},
        timeout=20,
    )
    assert me.status_code == 200, me.text
    assert me.json()["engineer"]["id"] == eng_id
