"""Iter 250 — Pulse Fitness Service Desk role nomination + straight-to-desk sign-in.

Process under test (end-to-end, no gaps):
 1. A Pulse Master Admin nominates a Service Desk user from
    Master Admin → Roles → "Service Desk team" (create new OR grant
    existing). Brand is FORCED to "pulse" for pulse admins, and the
    member list / revoke are pulse-brand-scoped.
 2. The nominated user signs in with the emailed temp password →
    forced password change (`/api/auth/force-change-password`).
 3. After sign-in they are routed straight to `/service-desk`
    (LoginPage / LoginRedirectPage / ForceChangePasswordPage fallbacks)
    and the backend desk guard + org-scoped svc surfaces work
    (service_org_id inherited from the granting admin).
"""

import asyncio
import os
import uuid

import pytest
import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
PULSE_ADMIN = ("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")
OWNER = ("owner@apexfitness.group", "ApexDemo2026!")

NOMINEE = f"pytest.desk.nominee.{uuid.uuid4().hex[:8]}@pulsefitness.com"
GYMAXIS_SCRATCH = f"pytest.desk.gymaxis.{uuid.uuid4().hex[:8]}@gymaxisai.com"
NEW_PASSWORD = "DeskNominee123!"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"{email}: {r.text}"
    return s


def _db():
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv("/app/backend/.env")
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _cleanup():
    async def run():
        db = _db()
        await db.users.delete_many({"email": {"$in": [NOMINEE, GYMAXIS_SCRATCH]}})
    _run(run())


@pytest.fixture(scope="module", autouse=True)
def clean_slate():
    _cleanup()
    yield
    _cleanup()


# Created once in test 1, reused by the sign-in flow tests.
_state: dict = {}


# ── Nomination by a Pulse Master Admin ───────────────────────────

def test_pulse_admin_nominates_desk_user_brand_forced_to_pulse():
    pulse = _login(*PULSE_ADMIN)
    r = pulse.post(f"{BASE_URL}/api/master-admin/service-desk/users", json={
        "email": NOMINEE, "full_name": "Pytest Desk Nominee",
        "brand": "gymaxis",  # pulse admins must NOT be able to pick gymaxis
    }, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["brand"] == "pulse", "brand must be forced to pulse for pulse admins"
    assert body.get("temp_password"), "temp password must be echoed for manual handover"
    _state["temp_password"] = body["temp_password"]

    async def doc():
        return await _db().users.find_one({"email": NOMINEE}, {"_id": 0})
    u = _run(doc())
    assert u["is_service_desk"] is True
    assert u["service_desk_brand"] == "pulse"
    assert u["must_change_password"] is True
    assert u.get("service_org_id"), "nominee must inherit a working service org"


def test_member_list_is_brand_scoped_for_pulse_admins():
    # seed a gymaxis-brand desk member via the master admin grant path
    async def seed():
        from utils.auth import hash_password
        await _db().users.insert_one({
            "id": str(uuid.uuid4()), "email": GYMAXIS_SCRATCH,
            "full_name": "Pytest Gymaxis Desk", "password": hash_password("Scratch123!"),
            "role": "service_desk", "is_service_desk": True,
            "service_desk_brand": "gymaxis", "organization_id": None,
            "active": True, "created_at": "2026-06-12T00:00:00+00:00",
        })
    _run(seed())

    pulse = _login(*PULSE_ADMIN)
    r = pulse.get(f"{BASE_URL}/api/master-admin/service-desk/members", timeout=20)
    assert r.status_code == 200, r.text
    members = r.json()["members"]
    emails = [m["email"] for m in members]
    assert NOMINEE in emails
    assert GYMAXIS_SCRATCH not in emails, "pulse admins must not see gymaxis-brand members"
    assert all((m.get("service_desk_brand") or "") == "pulse" for m in members)

    master = _login(*MASTER_ADMIN)
    r = master.get(f"{BASE_URL}/api/master-admin/service-desk/members", timeout=20)
    assert GYMAXIS_SCRATCH in [m["email"] for m in r.json()["members"]]


def test_pulse_admin_cannot_revoke_out_of_brand_member():
    pulse = _login(*PULSE_ADMIN)
    r = pulse.post(f"{BASE_URL}/api/master-admin/service-desk/members/revoke",
                   json={"email": GYMAXIS_SCRATCH}, timeout=20)
    assert r.status_code == 404, f"out-of-brand revoke must 404: {r.status_code}"


def test_plain_owner_cannot_nominate():
    owner = _login(*OWNER)
    r = owner.get(f"{BASE_URL}/api/master-admin/service-desk/members", timeout=20)
    assert r.status_code == 403


# ── First sign-in: temp password → forced change → straight to desk ─

def test_nominee_first_login_forces_password_change_then_desk_access():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": NOMINEE, "password": _state["temp_password"]}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["must_change_password"] is True

    token = r.json().get("token")
    r = s.post(f"{BASE_URL}/api/auth/force-change-password",
               json={"current_password": _state["temp_password"], "new_password": NEW_PASSWORD},
               headers={"Authorization": f"Bearer {token}"}, timeout=20)
    assert r.status_code == 200, r.text

    desk = _login(NOMINEE, NEW_PASSWORD)
    me = desk.get(f"{BASE_URL}/api/auth/me", timeout=20).json()
    me_user = me.get("user") or me
    assert me_user["is_service_desk"] is True
    assert me_user.get("must_change_password") in (False, None)

    # The desk itself opens (guard) and the org-scoped case board resolves
    # via the inherited service_org_id.
    assert desk.get(f"{BASE_URL}/api/service-desk/summary", timeout=20).status_code == 200
    r = desk.get(f"{BASE_URL}/api/svc/cases?limit=1", timeout=20)
    assert r.status_code == 200, r.text


def test_pulse_admin_can_revoke_their_own_nominee():
    pulse = _login(*PULSE_ADMIN)
    r = pulse.post(f"{BASE_URL}/api/master-admin/service-desk/members/revoke",
                   json={"email": NOMINEE}, timeout=20)
    assert r.status_code == 200, r.text
    # access gone immediately
    desk = _login(NOMINEE, NEW_PASSWORD)
    assert desk.get(f"{BASE_URL}/api/service-desk/summary", timeout=20).status_code == 403


# ── Frontend wiring: straight-to-desk routing ────────────────────

def test_login_flows_route_desk_users_straight_to_service_desk():
    for f in ("LoginPage.js", "LoginRedirectPage.js", "ForceChangePasswordPage.js"):
        src = open(f"/app/frontend/src/pages/{f}", encoding="utf-8").read()
        assert "is_service_desk" in src and "'/service-desk'" in src, (
            f"{f} must route Service-Desk-nominated users straight to /service-desk"
        )
    roles = open("/app/frontend/src/pages/MasterAdmin/AdminRoles.js", encoding="utf-8").read()
    assert "isPulseAdmin={isPulseAdmin}" in roles
    panel = open("/app/frontend/src/pages/MasterAdmin/AdminServiceDesk.js", encoding="utf-8").read()
    assert "isPulseAdmin" in panel and "!isPulseAdmin || b.v === 'pulse'" in panel, (
        "pulse admins must be locked to the pulse brand in the nomination UI"
    )
