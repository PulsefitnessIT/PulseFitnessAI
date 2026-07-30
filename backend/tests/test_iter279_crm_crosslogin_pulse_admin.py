"""Iter 279 — Pulse Master Admin CRM cross-login lock-out (recurring P0).

The People-drawer diagnostic shows a Pulse Master Admin (Lee Somers) as
"Full access — Pulse Master Admin" because it computes ``privileged`` with an
inline check — that does NOT prove the entitlement *resolver* used by the
cross-login gate returns True. The cross-login gate (`POST /crm/auth/cross-login`)
historically computed ``is_master`` WITHOUT recognising Pulse admins, so it
depended entirely on ``has_module()``; any resolver/deployment skew re-locked
the admin out with "CRM is not enabled for your account".

Fix: the cross-login gate now recognises Pulse Master Admins directly, so the
exchange never depends on the module resolver for them — even if the org's CRM
module is toggled OFF. Ordinary staff in a CRM-disabled org are still denied.

Integration test against the live preview API (seeds via motor, mints a real
main JWT, exercises the HTTP endpoint, then cleans up).
"""
import asyncio
import os
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://mod-hq-email.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG_ID = f"iter279-org-{uuid.uuid4().hex[:8]}"
_PULSE_ADMIN_ID = f"iter279-pulse-{uuid.uuid4().hex[:8]}"
_STAFF_ID = f"iter279-staff-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    # Org with CRM module explicitly DISABLED — the production scenario.
    await db.organizations.delete_one({"id": _ORG_ID})
    await db.organizations.insert_one({
        "id": _ORG_ID,
        "name": "Iter279 Lockout Test Org",
        "account_type": "pulse_pro",
        "modules": {"crm": {"enabled": False}},
    })
    # Pulse Master Admin (is_master_admin False, role pulse_master_admin).
    for uid, role, flags in (
        (_PULSE_ADMIN_ID, "pulse_master_admin", {"is_pulse_admin": True}),
        (_STAFF_ID, "manager", {}),
    ):
        await db.users.delete_one({"id": uid})
        await db.users.insert_one({
            "id": uid,
            "email": f"{uid}@iter279.local",
            "full_name": "Iter279 User",
            "role": role,
            "is_master_admin": False,
            "account_type": "pulse_pro",
            "organization_id": _ORG_ID,
            **flags,
        })
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await db.organizations.delete_one({"id": _ORG_ID})
    await db.users.delete_many({"id": {"$in": [_PULSE_ADMIN_ID, _STAFF_ID]}})
    await db.crm_users.delete_many({"email": {"$in": [
        f"{_PULSE_ADMIN_ID}@iter279.local", f"{_STAFF_ID}@iter279.local",
    ]}})
    c.close()


def _cross_login(user_id: str, *, use_cookie: bool = False, bogus_bearer: bool = False):
    """Drive the cross-login. By default sends a valid bearer for `user_id`.

    - use_cookie: send the token as the `ga_session` cookie instead of the
      Authorization header (simulates a cookie-only session).
    - bogus_bearer: ALSO send a bearer for a non-existent user_id (simulates
      the stale localStorage['token'] that points at an old/deleted record).
    """
    token = create_token(user_id)
    headers = {}
    cookies = {}
    if bogus_bearer:
        headers["Authorization"] = f"Bearer {create_token('iter279-nonexistent-user-id')}"
    if use_cookie:
        cookies["ga_session"] = token
        if not bogus_bearer:
            # cookie-only: no Authorization header at all
            pass
    else:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(
        f"{API}/api/crm/auth/cross-login",
        headers=headers,
        cookies=cookies,
        timeout=20,
    )


def setup_module(module):
    _run(_seed())


def teardown_module(module):
    _run(_cleanup())


def test_pulse_admin_cross_login_succeeds_even_when_org_crm_disabled():
    """The exact lock-out scenario: org CRM toggle OFF, user is a Pulse
    Master Admin. Cross-login must still return a CRM token (200)."""
    r = _cross_login(_PULSE_ADMIN_ID)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("token"), "no CRM token returned"
    assert body["user"]["is_master_admin"] is True


def test_regular_staff_in_crm_disabled_org_still_denied():
    """Regression: an ordinary manager in a CRM-disabled org must still be
    rejected with 403 (no silent open gate)."""
    r = _cross_login(_STAFF_ID)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_stale_bearer_falls_back_to_current_cookie_session():
    """THE production bug: the localStorage bearer is STALE (points at a
    deleted/old user_id) while the httpOnly ga_session cookie holds the
    real, current Pulse Master Admin login. Cross-login must resolve the
    cookie session and return a CRM token (200) — not 401/403."""
    r = _cross_login(_PULSE_ADMIN_ID, use_cookie=True, bogus_bearer=True)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("token"), "no CRM token returned"


def test_cookie_only_session_works():
    """A cookie-only session (no Authorization header) for a Pulse admin
    also exchanges successfully."""
    r = _cross_login(_PULSE_ADMIN_ID, use_cookie=True)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"


def test_no_credentials_returns_401():
    r = requests.post(f"{API}/api/crm/auth/cross-login", timeout=20)
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"
