"""Iter 320 — Staffing & HR ↔ Contract Management / MOD permissions: derive_role fix, CM role matrix,
System Access API (list/filter/PUT/audit/authz), job-role catalogue, MOD commitments authz.
Only fictional *.test accounts are modified and every change is reverted."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import os
import subprocess

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = "CmTest2026!"
ADMIN = ("admin@pulsefitness.com", os.environ["MASTER_ADMIN_PASSWORD"])


def _clear():
    subprocess.run(["python", "tests/_clear_login_ratelimit.py"], cwd=REPO + "/backend", check=True, capture_output=True)


def _plat(email, pw=PW):
    _clear()
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, (r.json().get("user") or {})


def _crm(email, pw=PW):
    _clear()
    r = requests.post(f"{BASE}/crm/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        return None, r
    return {"Authorization": f"Bearer {r.json()['token']}"}, r


def _ws(email):
    h, r = _crm(email)
    assert h, f"CRM login failed for {email}: {r.status_code} {r.text[:200]}"
    me = requests.get(f"{BASE}/crm/workspace/me", headers=h)
    assert me.status_code == 200, me.text
    return me.json()


@pytest.fixture(scope="module")
def admin_h():
    return _plat(*ADMIN)[0]


# ── derive_role fix ──
def test_vc_driver_auth_me_no_role():
    h, _ = _plat("vc.driver@pulsefitness.test", "Driver123!")
    me = requests.get(f"{BASE}/auth/me", headers=h).json()
    me = me.get("user", me)
    assert me["crm_workspace_role"] == "none"
    assert me["crm_permissions"] == []
    assert me["crm_workspaces"] == {"crm": False, "contract_management": False}


def test_cm_sales_still_sales_manager():
    h, _ = _plat("cm.sales@pulsefitness.test")
    me = requests.get(f"{BASE}/auth/me", headers=h).json()
    me = me.get("user", me)
    assert me["crm_workspace_role"] == "sales_manager"
    assert me["crm_workspaces"]["crm"] is True


# ── Role matrix ──
def test_matrix_coordinator():
    p = set(_ws("cm.coordinator@pulsefitness.test")["permissions"])
    assert {"workspace.contract_management", "contracts.manage", "quotes.maintenance", "renewals.review",
            "agreements.process", "billing.prepare"} <= p
    assert not p & {"exceptions.approve", "renewals.approve", "billing.reconcile", "finance.post",
                    "permissions.admin", "pricing.manage"}


def test_matrix_aftersales():
    p = set(_ws("cm.aftersales@pulsefitness.test")["permissions"])
    assert {"exceptions.approve", "renewals.approve"} <= p
    assert not p & {"finance.post", "permissions.admin"}


def test_matrix_finance():
    p = set(_ws("cm.finance@pulsefitness.test")["permissions"])
    assert {"billing.reconcile", "finance.sync"} <= p
    assert "finance.post" not in p and "quotes.mod" not in p


def test_matrix_admin():
    from utils.crm_workspace import ALL_PERMISSIONS
    assert set(_ws("cm.admin@pulsefitness.test")["permissions"]) == set(ALL_PERMISSIONS)


# ── System Access list / filters / authz ──
def test_system_access_admin_list(admin_h):
    r = requests.get(f"{BASE}/staffing/system-access", headers=admin_h)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("ok", "needs_review", "no_login", "inactive", "not_authorised", "total"):
        assert k in d["summary"]
    assert d["rows"] and all(x["status"] in ("ok", "needs_review", "no_login", "inactive", "not_authorised") for x in d["rows"])
    emails = {x["email"] for x in d["rows"]}
    assert "cm.noaccess@pulsefitness.test" in emails
    st = requests.get(f"{BASE}/staffing/system-access?status=not_authorised", headers=admin_h).json()["rows"]
    assert all(x["status"] == "not_authorised" for x in st)
    dept = next((x["department"] for x in d["rows"] if x["department"]), None)
    if dept:
        rows = requests.get(f"{BASE}/staffing/system-access", params={"department": dept}, headers=admin_h).json()["rows"]
        assert rows and all(x["department"] == dept for x in rows)


def test_system_access_coordinator_forbidden():
    h, _ = _plat("cm.coordinator@pulsefitness.test")
    assert requests.get(f"{BASE}/staffing/system-access", headers=h).status_code == 403


def test_system_access_cm_admin_allowed():
    h, _ = _plat("cm.admin@pulsefitness.test")
    assert requests.get(f"{BASE}/staffing/system-access", headers=h).status_code == 200


# ── PUT round-trips on fictional test users (always reverted) ──
def test_put_contracts_role_roundtrip(admin_h):
    uid = "cm-test-none"
    try:
        r = requests.put(f"{BASE}/staffing/system-access/{uid}", json={"contracts_role": "contract_coordinator"}, headers=admin_h)
        assert r.status_code == 200 and "contracts_role" in r.json()["changed"], r.text
        ws = _ws("cm.noaccess@pulsefitness.test")
        assert ws["role"] == "contract_coordinator" and ws["workspaces"]["contract_management"] is True
        assert "contracts.manage" in ws["permissions"]
        aud = requests.get(f"{BASE}/staffing/system-access/{uid}/audit", headers=admin_h).json()["history"]
        assert aud and aud[0].get("to_role") == "contract_coordinator"
    finally:
        r = requests.put(f"{BASE}/staffing/system-access/{uid}", json={"contracts_role": None}, headers=admin_h)
        assert r.status_code == 200
    h, resp = _crm("cm.noaccess@pulsefitness.test")
    if h:
        ws = requests.get(f"{BASE}/crm/workspace/me", headers=h).json()
        assert ws["role"] == "none" and ws["permissions"] == []
    else:
        assert resp.status_code in (401, 403)


def test_put_extra_finance_post_roundtrip(admin_h):
    uid = "cm-test-fin"
    try:
        r = requests.put(f"{BASE}/staffing/system-access/{uid}", json={"extra_permissions": ["finance.post"]}, headers=admin_h)
        assert r.status_code == 200, r.text
        assert "finance.post" in _ws("cm.finance@pulsefitness.test")["permissions"]
    finally:
        requests.put(f"{BASE}/staffing/system-access/{uid}", json={"extra_permissions": []}, headers=admin_h)
    assert "finance.post" not in _ws("cm.finance@pulsefitness.test")["permissions"]


def test_put_mod_ops_roundtrip(admin_h):
    uid = "cm-test-none"
    try:
        r = requests.put(f"{BASE}/staffing/system-access/{uid}", json={"mod_operations": True, "mod_quote_role": "manager"}, headers=admin_h)
        assert r.status_code == 200 and set(r.json()["changed"]) == {"mod_operations", "mod_quote_role"}, r.text
        row = next(x for x in requests.get(f"{BASE}/staffing/system-access", headers=admin_h).json()["rows"] if x["user_id"] == uid)
        assert row["mod_operations_access"] is True and row["mod_quote_role"] == "manager"
    finally:
        requests.put(f"{BASE}/staffing/system-access/{uid}", json={"mod_operations": False, "mod_quote_role": ""}, headers=admin_h)
    row = next(x for x in requests.get(f"{BASE}/staffing/system-access", headers=admin_h).json()["rows"] if x["user_id"] == uid)
    assert row["mod_operations_access"] is False and row["mod_quote_role"] == ""


def test_put_unknown_role_400(admin_h):
    assert requests.put(f"{BASE}/staffing/system-access/cm-test-none", json={"contracts_role": "god"}, headers=admin_h).status_code == 400
    assert requests.put(f"{BASE}/staffing/system-access/cm-test-none", json={"mod_quote_role": "god"}, headers=admin_h).status_code == 400


def test_put_coordinator_forbidden():
    h, _ = _plat("cm.coordinator@pulsefitness.test")
    r = requests.put(f"{BASE}/staffing/system-access/cm-test-coord", json={"contracts_role": "admin"}, headers=h)
    assert r.status_code == 403


# ── Job-role catalogue ──
def test_staffing_roles_catalogue(admin_h):
    r = requests.get(f"{BASE}/staffing/roles", headers=admin_h)
    assert r.status_code == 200
    txt = str(r.json())
    for t in ("contract_coordinator", "senior_contract_coordinator", "service_aftersales_manager", "service_administrator",
              "service_desk_coordinator", "field_service_engineer", "finance_manager"):
        assert t in txt, t


# ── MOD commitments (read-only) ──
def test_mod_commitments_authz():
    h, _ = _crm("cm.coordinator@pulsefitness.test")
    r = requests.get(f"{BASE}/crm/workspace/mod-commitments", headers=h)
    assert r.status_code == 200 and isinstance(r.json()["items"], list)
    h2, resp = _crm("cm.noaccess@pulsefitness.test")
    if h2:
        assert requests.get(f"{BASE}/crm/workspace/mod-commitments", headers=h2).status_code == 403
    else:
        assert resp.status_code in (401, 403)
