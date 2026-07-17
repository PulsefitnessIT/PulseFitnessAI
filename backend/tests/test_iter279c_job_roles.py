"""Iter 279c — Custom Job Roles + Master Admin → Operations role sync.

Covers:
  • the platform-role → staffing primary_role mapping (engineer pulls
    through instead of defaulting to "reception");
  • the auto-reconcile on the staff list (an auto-synced staff member's
    role follows the Master Admin role, but a manager's manual override is
    never clobbered);
  • the custom Job Roles catalogue CRUD (add / rename / delete) shared per
    company.

Integration test: seeds via motor, mints a real owner JWT, drives the live
preview API, then cleans up.
"""
import asyncio
import os
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token
from routes.staffing import _staff_role_from_platform_role, BUSINESS_DEFAULT_ROLES, VALID_ROLES

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://dealer-parts-engine.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG = f"iter279c-org-{uuid.uuid4().hex[:8]}"
_OWNER = f"iter279c-owner-{uuid.uuid4().hex[:8]}"
_ENG = f"iter279c-eng-{uuid.uuid4().hex[:8]}"
_MGR = f"iter279c-mgr-{uuid.uuid4().hex[:8]}"
_STAFF_ENG = f"iter279c-staff-eng-{uuid.uuid4().hex[:8]}"
_STAFF_MANUAL = f"iter279c-staff-manual-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await db.organizations.delete_one({"id": _ORG})
    await db.organizations.insert_one({
        "id": _ORG, "name": "Iter279c Co", "account_type": "pulse_pro",
        "modules": {}, "custom_staff_roles": [],
    })
    await db.users.insert_many([
        {"id": _OWNER, "email": f"{_OWNER}@iter279c.local", "full_name": "Owner",
         "role": "owner", "account_type": "pulse_pro", "organization_id": _ORG},
        {"id": _ENG, "email": f"{_ENG}@iter279c.local", "full_name": "Ryan Engineer",
         "role": "engineer", "account_type": "pulse_pro", "organization_id": _ORG},
        {"id": _MGR, "email": f"{_MGR}@iter279c.local", "full_name": "Manual Manager",
         "role": "manager", "account_type": "pulse_pro", "organization_id": _ORG},
    ])
    # Engineer already has an AUTO-synced staff row stuck on "reception"
    # (the production symptom) — must reconcile to "engineer".
    await db.staff_members.insert_one({
        "id": _STAFF_ENG, "organization_id": _ORG, "user_id": _ENG,
        "email": f"{_ENG}@iter279c.local", "full_name": "Ryan Engineer",
        "primary_role": "reception", "auto_synced_from_users": True,
        "active": True, "secondary_roles": [],
    })
    # Manually overridden staff row — must NOT be clobbered by the sync.
    await db.staff_members.insert_one({
        "id": _STAFF_MANUAL, "organization_id": _ORG, "user_id": _MGR,
        "email": f"{_MGR}@iter279c.local", "full_name": "Manual Manager",
        "primary_role": "director", "primary_role_source": "manual",
        "auto_synced_from_users": True, "active": True, "secondary_roles": [],
    })
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await db.organizations.delete_one({"id": _ORG})
    await db.users.delete_many({"id": {"$in": [_OWNER, _ENG, _MGR]}})
    await db.staff_members.delete_many({"organization_id": _ORG})
    c.close()


def _h():
    return {"Authorization": f"Bearer {create_token(_OWNER)}"}


def setup_module(module):
    _run(_seed())


def teardown_module(module):
    _run(_cleanup())


# ── pure logic ────────────────────────────────────────────────────
def test_platform_role_maps_through():
    allowed = set(BUSINESS_DEFAULT_ROLES)
    assert _staff_role_from_platform_role("engineer", allowed) == "engineer"
    assert _staff_role_from_platform_role("sales_manager", allowed) == "sales_manager"
    assert _staff_role_from_platform_role("owner", allowed) == "manager"
    assert _staff_role_from_platform_role("staff", allowed) == "other"
    assert _staff_role_from_platform_role("unknown_thing", allowed) == "other"
    # legacy gym roles remain valid for back-compat
    assert "instructor" in VALID_ROLES and "engineer" in VALID_ROLES


# ── catalogue is the neutral business set ─────────────────────────
def test_roles_catalogue_is_business_neutral():
    r = requests.get(f"{API}/api/staffing/roles", headers=_h(), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["platform_defaults"][:3] == ["manager", "engineer", "technician"]
    assert "engineer" in body["all"]


# ── the headline fix: Master Admin role pulls through to Operations ─
def test_engineer_role_reconciles_on_staff_list():
    r = requests.get(f"{API}/api/staffing/staff", headers=_h(), timeout=20)
    assert r.status_code == 200, r.text
    staff = r.json().get("staff") or r.json()
    eng = next((s for s in staff if s.get("id") == _STAFF_ENG), None)
    assert eng is not None, "engineer staff row missing"
    assert eng["primary_role"] == "engineer", f"expected engineer, got {eng['primary_role']}"


def test_manual_override_not_clobbered():
    r = requests.get(f"{API}/api/staffing/staff", headers=_h(), timeout=20)
    staff = r.json().get("staff") or r.json()
    mgr = next((s for s in staff if s.get("id") == _STAFF_MANUAL), None)
    assert mgr is not None
    assert mgr["primary_role"] == "director", "manual override was clobbered by sync"


# ── custom catalogue CRUD ─────────────────────────────────────────
def test_custom_role_add_rename_delete():
    add = requests.post(f"{API}/api/staffing/roles", headers=_h(), json={"role": "Field Supervisor"}, timeout=20)
    assert add.status_code == 200, add.text
    assert "Field Supervisor" in add.json()["custom"]

    ren = requests.put(f"{API}/api/staffing/roles/Field%20Supervisor", headers=_h(), json={"new_name": "Site Supervisor"}, timeout=20)
    assert ren.status_code == 200, ren.text
    assert "Site Supervisor" in ren.json()["custom"]

    # cannot rename a platform default
    bad = requests.put(f"{API}/api/staffing/roles/engineer", headers=_h(), json={"new_name": "X"}, timeout=20)
    assert bad.status_code == 400

    dele = requests.delete(f"{API}/api/staffing/roles/Site%20Supervisor", headers=_h(), timeout=20)
    assert dele.status_code == 200, dele.text
