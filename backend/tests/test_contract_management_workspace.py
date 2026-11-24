"""Contract Management workspace — roles, flags and backend permission gates.

Uses the fictional cm.*@pulsefitness.test staff seeded by
scripts/seed_cm_workspace_test_users.py (run automatically below).
Tokens are minted directly so the login rate-limit never interferes.
"""
import os
import subprocess

import pytest
import requests

from utils.auth import create_token

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
USERS = {
    "coord": "cm-test-coord", "sales": "cm-test-sales", "asm": "cm-test-asm",
    "fin": "cm-test-fin", "none": "cm-test-none", "admin": "cm-test-admin",
}


@pytest.fixture(scope="module", autouse=True)
def seed():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd="/app/backend",
                   env={**os.environ, "PYTHONPATH": "/app/backend"}, check=True)


def _main(key):
    return create_token(USERS[key])


def _crm(key):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {_main(key)}"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _me(key):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {_main(key)}"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("key,role,crm,cm", [
    ("coord", "contract_coordinator", False, True),
    ("sales", "sales_manager", True, False),
    ("asm", "aftersales_manager", True, True),
    ("fin", "finance", False, True),
    ("none", "sales_manager", False, False),
    ("admin", "admin", True, True),
])
def test_workspace_flags_on_auth_me(key, role, crm, cm):
    me = _me(key)
    assert me["crm_workspace_role"] == role
    assert me["crm_workspaces"] == {"crm": crm, "contract_management": cm}


def test_no_crm_user_cannot_cross_login():
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {_main('none')}"})
    assert r.status_code == 403


def _call(tok, method, path):
    return requests.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {tok}"}, json={}).status_code


GATES = [
    ("PUT", "/crm/v2/aftersales/settings", {"admin"}),
    ("POST", "/crm/v2/aftersales/build-custom-quote", {"coord", "asm", "admin"}),
    ("POST", "/crm/v2/aftersales/finance/sync/none/mark-synced", {"fin", "admin"}),
    ("POST", "/crm/v2/aftersales/rpi/reviews/none/approve", {"asm", "admin"}),
    ("POST", "/crm/mod-quote/ai-match", {"sales", "asm", "admin"}),
    ("PUT", "/crm/mod-quote/rate-card/none", {"admin"}),
    ("GET", "/crm/workspace/roles", {"admin"}),
    ("POST", "/crm/quotes/none/send", {"sales", "asm", "admin"}),
]


@pytest.mark.parametrize("method,path,allowed", GATES)
def test_action_permissions(method, path, allowed):
    for key in ("coord", "sales", "asm", "fin", "admin"):
        code = _call(_crm(key), method, path)
        if key in allowed:
            assert code != 403, f"{key} should pass {path} (got 403)"
        else:
            assert code == 403, f"{key} must be blocked on {path} (got {code})"


def test_shared_records_visible_in_both_workspaces():
    sales = requests.get(f"{API}/crm/v2/companies?limit=5", headers={"Authorization": f"Bearer {_crm('sales')}"})
    coord = requests.get(f"{API}/crm/v2/companies?limit=5", headers={"Authorization": f"Bearer {_crm('coord')}"})
    assert sales.status_code == coord.status_code == 200


def test_admin_assigns_and_clears_role_with_audit():
    tok = _crm("admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.put(f"{API}/crm/workspace/roles/cm-test-sales", headers=h, json={"role": "contract_coordinator"})
    assert r.status_code == 200 and r.json()["effective_role"] == "contract_coordinator"
    assert _me("sales")["crm_workspaces"]["contract_management"] is True
    r = requests.put(f"{API}/crm/workspace/roles/cm-test-sales", headers=h, json={"role": None})
    assert r.json()["effective_role"] == "sales_manager"
    hist = requests.get(f"{API}/crm/workspace/roles/cm-test-sales/audit", headers=h).json()["history"]
    assert len(hist) >= 2
    bad = requests.put(f"{API}/crm/workspace/roles/cm-test-sales", headers=h, json={"role": "superuser"})
    assert bad.status_code == 400


def test_coordinator_cannot_assign_roles():
    r = requests.put(f"{API}/crm/workspace/roles/cm-test-sales",
                     headers={"Authorization": f"Bearer {_crm('coord')}"}, json={"role": "admin"})
    assert r.status_code == 403


def test_cm_role_crm_grant_is_reverted():
    h = {"Authorization": f"Bearer {_crm('admin')}"}
    assert requests.put(f"{API}/crm/workspace/roles/cm-test-none", headers=h, json={"role": "contract_coordinator"}).status_code == 200
    assert _me("none")["crm_workspaces"]["contract_management"] is True
    assert requests.put(f"{API}/crm/workspace/roles/cm-test-none", headers=h, json={"role": None}).status_code == 200
    assert _me("none")["crm_workspaces"] == {"crm": False, "contract_management": False}
