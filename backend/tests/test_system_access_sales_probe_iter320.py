"""Iter 320 probe — explicit contracts_role 'sales_manager' via System Access on cm.noaccess (CRM module off): is CRM reachable? Reverted."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import os
import subprocess
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _clear():
    subprocess.run(["python", "tests/_clear_login_ratelimit.py"], cwd=REPO + "/backend", check=True, capture_output=True)


def test_sales_manager_assignment_reaches_crm():
    _clear()
    t = requests.post(f"{BASE}/auth/login", json={"email": "admin@pulsefitness.com", "password": os.environ["MASTER_ADMIN_PASSWORD"]}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    try:
        assert requests.put(f"{BASE}/staffing/system-access/cm-test-none", json={"contracts_role": "sales_manager"}, headers=h).status_code == 200
        _clear()
        r = requests.post(f"{BASE}/auth/login", json={"email": "cm.noaccess@pulsefitness.test", "password": "CmTest2026!"})
        u = r.json()["user"]
        print("role", u["crm_workspace_role"], "workspaces", u["crm_workspaces"])
        assert u["crm_workspace_role"] == "sales_manager"
        assert u["crm_workspaces"]["crm"] is True, "explicit Sales Manager role assigned but CRM module still off"
    finally:
        requests.put(f"{BASE}/staffing/system-access/cm-test-none", json={"contracts_role": None}, headers=h)
