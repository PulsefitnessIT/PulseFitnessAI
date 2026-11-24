"""Contract Management workspace — extended checks over the public URL:
real login payload flags, shared records, admin role assignment round-trip."""
import os
import subprocess

import pytest
import requests

from utils.auth import create_token

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = "CmTest2026!"


def _clear():
    subprocess.run(["python", "tests/_clear_login_ratelimit.py"], cwd="/app/backend", check=True, capture_output=True)


def _crm(uid):
    r = requests.post(f"{BASE}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# Login payload carries workspace flags
@pytest.mark.parametrize("email,crm,cm", [
    ("cm.coordinator@pulsefitness.test", False, True),
    ("cm.sales@pulsefitness.test", True, False),
])
def test_login_payload_flags(email, crm, cm):
    _clear()
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    u = r.json().get("user") or r.json()
    assert u["crm_workspaces"] == {"crm": crm, "contract_management": cm}


# Shared records: both sales + coordinator read companies
@pytest.mark.parametrize("uid", ["cm-test-sales", "cm-test-coord", "cm-test-asm"])
def test_companies_shared(uid):
    r = requests.get(f"{BASE}/crm/v2/companies", headers=_crm(uid))
    assert r.status_code == 200, r.text


def test_workspace_me_coord():
    r = requests.get(f"{BASE}/crm/workspace/me", headers=_crm("cm-test-coord"))
    assert r.status_code == 200
    d = r.json()
    assert d["role"] == "contract_coordinator"
    assert d["workspaces"]["contract_management"] is True
    assert "permissions.admin" not in d["permissions"]


# Admin role assignment round-trip
def test_admin_assign_roundtrip():
    h = _crm("cm-test-admin")
    r = requests.get(f"{BASE}/crm/workspace/roles", headers=h)
    assert r.status_code == 200
    ids = [u["id"] for u in r.json()["users"]]
    assert "cm-test-sales" in ids
    orig = next(u for u in r.json()["users"] if u["id"] == "cm-test-sales")["explicit_role"]
    try:
        r = requests.put(f"{BASE}/crm/workspace/roles/cm-test-sales", json={"role": "contract_coordinator"}, headers=h)
        assert r.status_code == 200 and r.json()["effective_role"] == "contract_coordinator"
        me = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {create_token('cm-test-sales')}"}).json()
        assert me["crm_workspace_role"] == "contract_coordinator"
        assert me["crm_workspaces"]["contract_management"] is True
        r = requests.put(f"{BASE}/crm/workspace/roles/cm-test-sales", json={"role": None}, headers=h)
        assert r.status_code == 200 and r.json()["effective_role"] == "sales_manager"
        audit = requests.get(f"{BASE}/crm/workspace/roles/cm-test-sales/audit", headers=h).json()["history"]
        assert len(audit) >= 2
    finally:
        requests.put(f"{BASE}/crm/workspace/roles/cm-test-sales", json={"role": orig}, headers=h)


def test_admin_assign_invalid_role():
    r = requests.put(f"{BASE}/crm/workspace/roles/cm-test-sales", json={"role": "superuser"}, headers=_crm("cm-test-admin"))
    assert r.status_code == 400


def test_admin_assign_unknown_user():
    r = requests.put(f"{BASE}/crm/workspace/roles/nope-xyz", json={"role": "finance"}, headers=_crm("cm-test-admin"))
    assert r.status_code == 404


def test_coord_cannot_assign():
    r = requests.put(f"{BASE}/crm/workspace/roles/cm-test-sales", json={"role": "admin"}, headers=_crm("cm-test-coord"))
    assert r.status_code == 403
