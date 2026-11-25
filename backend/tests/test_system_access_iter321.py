"""Iter 321 — retest of iter320 fixes: derive_role (no job-title/dept grants), sales_manager enables CRM,
MOD ops untick clears mod_quote_role, extra_permissions validation, offboarding by email, Master Admin row,
/system-access/can, and MOD/CM regressions. Only fictional *.test / TEST_ synthetic records are touched."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import asyncio
import os
import subprocess
import time
import uuid

import pytest
import requests

from utils.auth import hash_password
from utils.crm_workspace import resolve_workspace_role, set_explicit_role
from utils.database import db

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = "CmTest2026!"
ADMIN = ("admin@pulsefitness.com", os.environ["MASTER_ADMIN_PASSWORD"])
OWNER = ("portal@pulsefitness.ltd", "PulseFleet123!")
OP_ORG = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
NOACCESS = "cm-test-none"
LOOP = asyncio.new_event_loop()


def run(c):
    async def _w():
        return await c
    return LOOP.run_until_complete(_w())


async def _get(uid, proj=None):
    return await db.users.find_one({"id": uid}, proj or {"_id": 0})


def _clear():
    subprocess.run(["python", "tests/_clear_login_ratelimit.py"], cwd=REPO + "/backend", check=True, capture_output=True)


def _plat(email, pw=PW):
    _clear()
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    assert r.json().get("token"), r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _crm(email, pw=PW):
    _clear()
    r = requests.post(f"{BASE}/crm/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _rows(h):
    r = requests.get(f"{BASE}/staffing/system-access", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["rows"]


def _row_for(h, uid):
    return next(r for r in _rows(h) if r["user_id"] == uid)


@pytest.fixture(scope="module")
def admin_h():
    return _plat(*ADMIN)


@pytest.fixture(scope="module", autouse=True)
def restore_noaccess():
    yield
    subprocess.run(["python", "tests/_restore_cm_test_users_iter320.py"], cwd=REPO + "/backend", capture_output=True)

    code = ("import asyncio\nfrom utils.database import db\nasync def m():\n"
            "    await db.users.update_one({'id': 'cm-test-fin'}, {'$set': {'crm_workspace_extra_permissions': []}})\n"
            f"    await db.users.update_one({{'id': '{NOACCESS}'}}, {{'$set': {{'module_overrides.mod_operations': False}}}})\n"
            "asyncio.run(m())")
    subprocess.run(["python", "-c", code], cwd=REPO + "/backend", env={**os.environ, "PYTHONPATH": REPO + "/backend"}, capture_output=True)


# ── synthetic helpers (in-process) ──
async def _mk(title, dept=None, role="staff", crm=False):
    uid = f"TEST_i321_{uuid.uuid4().hex[:8]}"
    u = {"id": uid, "email": f"{uid.lower()}@example.test", "full_name": f"TEST {title}", "organization_id": OP_ORG,
         "role": role, "module_overrides": {"crm": crm}}
    await db.users.insert_one(dict(u))
    await db.staff_members.insert_one({"id": f"{uid}_st", "user_id": uid, "organization_id": OP_ORG, "email": u["email"],
                                       "primary_role": title, "department": dept, "status": "active",
                                       "full_name": u["full_name"]})
    return u


async def _rm(uid):
    await db.users.delete_one({"id": uid})
    await db.staff_members.delete_one({"id": f"{uid}_st"})
    await db.crm_workspace_role_audit.delete_many({"user_id": uid})


# 1. job title containing sales/manager grants nothing
@pytest.mark.parametrize("title,prole", [("sales_manager", "manager"), ("service_aftersales_manager", "manager"),
                                         ("sales_coordinator", "staff"), ("manager", "manager")])
def test_title_never_grants(title, prole):
    async def go():
        u = await _mk(title, role=prole)
        try:
            return await resolve_workspace_role(await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        finally:
            await _rm(u["id"])
    assert run(go()) == "none"


# 1b. HR department alone should not grant a Contracts role (requirement: never from departments)
@pytest.mark.parametrize("dept", ["Sales", "sales", "Sales Admin"])
def test_department_never_grants(dept):
    async def go():
        u = await _mk("administrator", dept=dept)
        try:
            return await resolve_workspace_role(await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        finally:
            await _rm(u["id"])
    assert run(go()) == "none", f"HR department {dept!r} granted a Contracts role"


# 1c. vc.driver via CRM workspace/me (if CRM login allowed) has no privileged role
def test_vc_driver_workspace_me():
    _clear()
    r = requests.post(f"{BASE}/crm/auth/login", json={"email": "vc.driver@pulsefitness.test", "password": "Driver123!"})
    if r.status_code != 200:
        assert r.status_code in (401, 403)
        return
    me = requests.get(f"{BASE}/crm/workspace/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    if me.status_code == 200:
        assert me.json().get("role") in ("none", None)
    else:
        assert me.status_code in (401, 403)


# 2. sales_manager assignment turns CRM on (fresh user)
def test_sales_manager_enables_crm_fresh():
    async def go():
        u = await _mk("administrator")
        try:
            fresh = await db.users.find_one({"id": u["id"]}, {"_id": 0})
            await set_explicit_role(fresh, "sales_manager", actor="TEST")
            return await db.users.find_one({"id": u["id"]}, {"_id": 0})
        finally:
            await _rm(u["id"])
    after = run(go())
    assert after["module_overrides"]["crm"] is True


# 2b. switching coordinator -> sales_manager must keep CRM on
def test_coordinator_to_sales_manager_keeps_crm():
    async def go():
        u = await _mk("administrator")
        try:
            await set_explicit_role(await db.users.find_one({"id": u["id"]}, {"_id": 0}), "contract_coordinator", actor="TEST")
            await set_explicit_role(await db.users.find_one({"id": u["id"]}, {"_id": 0}), "sales_manager", actor="TEST")
            return await db.users.find_one({"id": u["id"]}, {"_id": 0})
        finally:
            await _rm(u["id"])
    after = run(go())
    assert after["crm_workspace_role"] == "sales_manager"
    assert after["module_overrides"]["crm"] is True, "CRM was switched OFF when moving coordinator -> sales_manager"


# 2c. HTTP: assign sales_manager to cm.noaccess -> CRM workspace usable
def test_http_sales_manager_opens_crm(admin_h):
    r = requests.put(f"{BASE}/staffing/system-access/{NOACCESS}", headers=admin_h, json={"contracts_role": "sales_manager"})
    assert r.status_code == 200, r.text
    try:
        me = requests.get(f"{BASE}/crm/workspace/me", headers=_crm("cm.noaccess@pulsefitness.test"))
        assert me.status_code == 200, me.text
        j = me.json()
        assert j["role"] == "sales_manager"
        assert j["workspaces"]["crm"] is True
        assert j["workspaces"]["contract_management"] is False
    finally:
        requests.put(f"{BASE}/staffing/system-access/{NOACCESS}", headers=admin_h, json={"contracts_role": None})
    u = run(_get(NOACCESS))
    assert u["crm_workspace_role"] is None and u["module_overrides"]["crm"] is False


# 3. unticking MOD Operations clears mod_quote_role
def test_untick_mod_ops_clears_quote_role(admin_h):
    r = requests.put(f"{BASE}/staffing/system-access/{NOACCESS}", headers=admin_h,
                     json={"mod_operations": True, "mod_quote_role": "manager"})
    assert r.status_code == 200, r.text
    row = _row_for(admin_h, NOACCESS)
    assert row["mod_operations_access"] is True and row["mod_quote_role"] == "manager"
    r = requests.put(f"{BASE}/staffing/system-access/{NOACCESS}", headers=admin_h, json={"mod_operations": False})
    assert r.status_code == 200 and "mod_operations" in r.json()["changed"]
    row = _row_for(admin_h, NOACCESS)
    assert row["mod_operations_access"] is False
    assert row["mod_quote_role"] == ""
    assert "Has a MOD quotation role but no MOD Operations access" not in row["issues"]


# 4. extra_permissions must be a list; access_changed_at not written
@pytest.mark.parametrize("bad", ["finance.post", {"a": 1}, 5])
def test_extra_permissions_not_list(admin_h, bad):
    r = requests.put(f"{BASE}/staffing/system-access/cm-test-fin", headers=admin_h, json={"extra_permissions": bad})
    assert r.status_code in (400, 422), r.text


def test_access_changed_at_not_written(admin_h):
    before = run(_get("cm-test-fin", {"_id": 0, "access_changed_at": 1}))
    r = requests.put(f"{BASE}/staffing/system-access/cm-test-fin", headers=admin_h, json={"extra_permissions": ["finance.post"]})
    assert r.status_code == 200, r.text
    requests.put(f"{BASE}/staffing/system-access/cm-test-fin", headers=admin_h, json={"extra_permissions": []})
    after = run(_get("cm-test-fin", {"_id": 0, "access_changed_at": 1}))
    assert after.get("access_changed_at") == before.get("access_changed_at")


# 5. offboarding by email (staff has no user_id) disables login, revokes sessions, removes MOD ops
def test_offboarding_by_email_revokes():
    uid = f"TEST_i321_off_{uuid.uuid4().hex[:6]}"
    email, sid = f"{uid.lower()}@example.test", f"{uid}_st"
    pw = "TestLeaver123!"
    pw_hash = hash_password(pw)

    async def setup():
        await db.users.insert_one({"id": uid, "email": email, "full_name": "TEST Leaver", "organization_id": OP_ORG,
                                   "role": "staff", "password": pw_hash, "password_hash": pw_hash, "hashed_password": pw_hash, "active": True,
                                   "is_active": True, "email_verified": True, "crm_workspace_role": "contract_coordinator",
                                   "module_overrides": {"crm": True, "mod_operations": True}, "mod_quote_role": "manager",
                                   "crm_override_from_workspace": True})
        await db.staff_members.insert_one({"id": sid, "organization_id": OP_ORG, "email": email.upper(),
                                           "full_name": "TEST Leaver", "primary_role": "contract_coordinator", "status": "active"})

    async def cleanup():
        await db.users.delete_one({"id": uid})
        await db.staff_members.delete_one({"id": sid})
        await db.staff_offboarding_cases.delete_many({"staff_id": sid})
        await db.crm_workspace_role_audit.delete_many({"user_id": uid})
    run(setup())
    try:
        _clear()
        lr = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
        leaver_h = {"Authorization": f"Bearer {lr.json()['token']}"} if lr.status_code == 200 and lr.json().get("token") else None
        if leaver_h:
            assert requests.get(f"{BASE}/auth/me", headers=leaver_h).status_code == 200
        time.sleep(1.2)
        oh = _plat(*OWNER)
        r = requests.post(f"{BASE}/staffing/offboarding/{sid}/start", headers=oh,
                          json={"reason": "TEST", "last_working_day": "2026-01-31"})
        assert r.status_code == 200, r.text
        r = requests.post(f"{BASE}/staffing/offboarding/{sid}/complete", headers=oh)
        assert r.status_code == 200, r.text
        assert r.json()["access_revoked"] is True
        u = run(_get(uid))
        assert u["active"] is False and u.get("tokens_revoked_before")
        assert u["module_overrides"].get("mod_operations") is False and not u.get("mod_quote_role")
        assert u.get("crm_workspace_role") is None
        if leaver_h:
            assert requests.get(f"{BASE}/auth/me", headers=leaver_h).status_code == 401
        else:
            print("leaver login not possible (", lr.status_code, ") - session revocation checked only via DB")
    finally:
        run(cleanup())


# 6. Master Admin staff record row has no 'No login account linked'
def test_master_admin_row(admin_h):
    rows = [r for r in _rows(admin_h) if (r["email"] or "").lower() == "admin@pulsefitness.com"]
    assert rows, "no Master Admin row"
    for r in rows:
        assert "No login account linked" not in r["issues"]
        assert r["status"] != "no_login"


# 7. /can
@pytest.mark.parametrize("who,expected", [("admin", True), ("owner", True), ("vc", False), ("craig", False),
                                          ("modmgr", False), ("coord", False)])
def test_can(who, expected):
    creds = {"admin": ADMIN, "owner": OWNER, "vc": ("vc.driver@pulsefitness.test", "Driver123!"),
             "craig": ("craig.henshall@pulsefitness.com", "PulseMOD123!"),
             "modmgr": ("modsales.manager@pulsedemo.test", "ModSales123!"),
             "coord": ("cm.coordinator@pulsefitness.test", PW)}[who]
    _clear()
    lr = requests.post(f"{BASE}/auth/login", json={"email": creds[0], "password": creds[1]})
    if lr.status_code != 200 or not lr.json().get("token"):
        pytest.skip(f"login unavailable for {who}: {lr.status_code}")
    r = requests.get(f"{BASE}/staffing/system-access/can", headers={"Authorization": f"Bearer {lr.json()['token']}"})
    assert r.status_code == 200 and r.json() == {"allowed": expected}
    if not expected:
        assert requests.get(f"{BASE}/staffing/system-access", headers={"Authorization": f"Bearer {lr.json()['token']}"}).status_code == 403


def test_can_unauthenticated():
    assert requests.get(f"{BASE}/staffing/system-access/can").status_code == 401


# Regression: coordinator CM only; noaccess denied
def test_regression_coordinator_and_noaccess():
    j = requests.get(f"{BASE}/crm/workspace/me", headers=_crm("cm.coordinator@pulsefitness.test")).json()
    assert j["role"] == "contract_coordinator"
    assert j["workspaces"] == {"crm": False, "contract_management": True}
    _clear()
    r = requests.post(f"{BASE}/crm/auth/login", json={"email": "cm.noaccess@pulsefitness.test", "password": PW})
    if r.status_code == 200:
        me = requests.get(f"{BASE}/crm/workspace/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
        assert me.status_code in (401, 403) or me.json()["workspaces"] == {"crm": False, "contract_management": False}
    else:
        assert r.status_code in (401, 403)


# Regression: rep / cm.finance cannot approve MOD quotes or change pricing; staff can't see rate source/version
@pytest.mark.parametrize("email,pw", [("modsales.rep@pulsedemo.test", "ModSales123!"), ("cm.finance@pulsefitness.test", PW)])
def test_regression_no_approve_no_pricing(email, pw):
    _clear()
    lr = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert lr.status_code == 200 and lr.json().get("token"), lr.text
    h = {"Authorization": f"Bearer {lr.json()['token']}"}
    mq = f"{BASE}/mod-ops/quotes"
    a = requests.post(f"{mq}/groups/TEST_nonexistent/approve", headers=h, json={"approve": True, "exceptions": []})
    assert a.status_code in (401, 403), f"approve {a.status_code} {a.text[:150]}"
    p = requests.post(f"{mq}/rates/TEST_nonexistent/approve", headers=h, json={"effective_from": "2026-11-25", "confirm": True})
    assert p.status_code in (401, 403), f"pricing {p.status_code} {p.text[:150]}"
    c = requests.get(f"{mq}/rates/current", headers=h)
    if c.status_code == 200:
        d = c.json()
        assert "version" not in d.get("live_price_list", {})
        assert not any("source" in r for r in d["rows"]), "rate source leaked"
        by = {r["label"]: r for r in d["rows"]}
        assert by["Treadmill"]["a"]["price"] == 255.0 and by["Treadmill"]["b"]["price"] == 24.0
        assert by["Radiant Trainer"]["a"]["price"] == 145.12 and by["Freedom Trainer"]["a"]["price"] == 145.12
    else:
        assert c.status_code in (401, 403)
