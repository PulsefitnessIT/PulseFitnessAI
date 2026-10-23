"""Iter 279e — CRM team members show a read-only company JOB TITLE
(drawn from the shared staffing catalogue) that is SEPARATE from the CRM
permission role.

GET /api/crm/users enriches each member with `job_title`, derived from the
linked platform user's staffing primary_role (which itself syncs from the
role set in Master Admin — iter 279c). So an Engineer on the platform shows
"Engineer" in the CRM team list while keeping their CRM role (e.g. sales_rep).

Integration test: seeds an org + linked platform engineer + CRM user, logs in
as the org's CRM owner via cross-login, then asserts the enrichment.
"""
import asyncio
import os
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token
from routes.crm_core import _humanize_role

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://sicon-sync-hub.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG = f"iter279e-org-{uuid.uuid4().hex[:8]}"
_OWNER_U = f"iter279e-owner-{uuid.uuid4().hex[:8]}"
_ENG_U = f"iter279e-eng-{uuid.uuid4().hex[:8]}"
_OWNER_CRM = f"iter279e-ocrm-{uuid.uuid4().hex[:8]}"
_ENG_CRM = f"iter279e-ecrm-{uuid.uuid4().hex[:8]}"
_ENG_EMAIL = f"{_ENG_U}@iter279e.local"
_OWNER_EMAIL = f"{_OWNER_U}@iter279e.local"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await db.organizations.insert_one({
        "id": _ORG, "name": "Iter279e Co", "account_type": "pulse_pro",
        "modules": {"crm": {"enabled": True}},
    })
    # Platform users: an owner (for CRM cross-login) and an engineer.
    await db.users.insert_many([
        {"id": _OWNER_U, "email": _OWNER_EMAIL, "full_name": "Owner Person",
         "role": "owner", "account_type": "pulse_pro", "organization_id": _ORG},
        {"id": _ENG_U, "email": _ENG_EMAIL, "full_name": "Eng Person",
         "role": "engineer", "account_type": "pulse_pro", "organization_id": _ORG},
    ])
    # Engineer's staffing record carries primary_role 'engineer'.
    await db.staff_members.insert_one({
        "id": str(uuid.uuid4()), "organization_id": _ORG, "user_id": _ENG_U,
        "email": _ENG_EMAIL, "full_name": "Eng Person",
        "primary_role": "engineer", "active": True,
    })
    # CRM users: owner (admin role) + engineer (sales_rep CRM role).
    await db.crm_users.insert_many([
        {"id": _OWNER_CRM, "organization_id": _ORG, "email": _OWNER_EMAIL,
         "full_name": "Owner Person", "role": "owner", "status": "active"},
        {"id": _ENG_CRM, "organization_id": _ORG, "email": _ENG_EMAIL,
         "full_name": "Eng Person", "role": "sales_rep", "status": "active"},
    ])
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await db.organizations.delete_one({"id": _ORG})
    await db.users.delete_many({"id": {"$in": [_OWNER_U, _ENG_U]}})
    await db.staff_members.delete_many({"organization_id": _ORG})
    await db.crm_users.delete_many({"organization_id": _ORG})
    c.close()


def setup_module(module):
    _run(_seed())


def teardown_module(module):
    _run(_cleanup())


def _crm_token():
    main = create_token(_OWNER_U)
    r = requests.post(f"{API}/api/crm/auth/cross-login",
                      headers={"Authorization": f"Bearer {main}"}, timeout=20)
    assert r.status_code == 200, f"cross-login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def test_humanize_helper():
    assert _humanize_role("sales_manager") == "Sales Manager"
    assert _humanize_role("engineer") == "Engineer"
    assert _humanize_role(None) is None


def test_crm_users_carry_job_title_from_staffing():
    crm = _crm_token()
    r = requests.get(f"{API}/api/crm/users", headers={"Authorization": f"Bearer {crm}"}, timeout=20)
    assert r.status_code == 200, r.text
    users = {u["email"]: u for u in r.json().get("users", [])}
    eng = users.get(_ENG_EMAIL)
    assert eng is not None, "engineer CRM user missing"
    # Job title pulls through from staffing, SEPARATE from the CRM role.
    assert eng["job_title"] == "Engineer", f"expected Engineer, got {eng.get('job_title')}"
    assert eng["role"] == "sales_rep", "CRM permission role must be unchanged"
    # Every user has the job_title key present (even if None).
    assert all("job_title" in u for u in r.json()["users"])
