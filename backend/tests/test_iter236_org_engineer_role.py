"""Iter 236 — Master Admin → Organisation → Add User: "Engineer" role.

User report: "Production - Organisation - Pulse Fitness - Add User - I
don't have an option to choose Engineer within the role selector?"

The platform already supports internal engineers (Iter 227): role
`engineer` + an active `svc_engineers` row unlocks the Engineer App via
the internal_engineer bypass. The master-admin Add/Edit User dialogs
simply never offered the role.

Covers:
1. POST /master-admin/organizations/{org_id}/users with role=engineer
   creates the user in the service-portal `users` collection (even for
   a CRM-portal org like Pulse Fitness) and the engineer can sign in.
2. The new engineer gets Engineer App access (reason=internal_engineer).
3. Demoting the engineer to staff via /users/{id}/edit deactivates the
   svc_engineers row → Engineer App access revoked.
4. Source pins — both master-admin dialogs offer the Engineer option.
"""

import time
import uuid

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()
PASSWORD = "EngineerIter236!xyz"


def _admin() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
               timeout=20)
    assert r.status_code == 200, r.text
    return s


def _pulse_org_id(s: requests.Session) -> str:
    orgs = s.get(f"{BASE_URL}/api/master-admin/organizations", timeout=30).json()
    rows = orgs.get("organizations", orgs if isinstance(orgs, list) else [])
    for o in rows:
        if o.get("name") == "Pulse Fitness":
            return o["id"]
    raise AssertionError("Pulse Fitness org not found")


def test_add_engineer_to_crm_org_full_lifecycle():
    admin = _admin()
    org_id = _pulse_org_id(admin)
    email = f"iter236.eng+{uuid.uuid4().hex[:8]}@example.com"

    # 1. Add the engineer (explicit password so we can log in as them).
    r = admin.post(
        f"{BASE_URL}/api/master-admin/organizations/{org_id}/users",
        json={"email": email, "full_name": "Iter236 Engineer",
              "role": "engineer", "password": PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    created = r.json()
    user_id = created["id"]
    assert created["role"] == "engineer"
    # Engineers must land in the service-portal collection — Pulse
    # Fitness is portal_type='crm'; without the iter-236 special-case
    # they'd be created in crm_users and could never sign into the
    # Engineer App (get_current_user only reads db.users).
    assert created["portal"] == "Service Portal", created

    try:
        # 2. Engineer can sign in + has Engineer App access.
        eng = requests.Session()
        r = eng.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": PASSWORD}, timeout=20)
        assert r.status_code == 200, f"engineer cannot sign in: {r.text}"
        access = eng.get(f"{BASE_URL}/api/partners/me/engineer-access", timeout=30).json()
        assert access["allowed"] is True, access
        assert access["reason"] == "internal_engineer", access

        # 3. Demote to staff → svc_engineers deactivated → access revoked.
        r = admin.put(f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
                      json={"role": "staff"}, timeout=30)
        assert r.status_code == 200, r.text
        time.sleep(0.3)
        eng2 = requests.Session()
        r = eng2.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PASSWORD}, timeout=20)
        assert r.status_code == 200, r.text
        access = eng2.get(f"{BASE_URL}/api/partners/me/engineer-access", timeout=30).json()
        assert access["allowed"] is False, (
            f"demoted engineer must lose Engineer App access: {access}"
        )

        # 4. Promote back via edit → access restored (sync is two-way).
        r = admin.put(f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
                      json={"role": "engineer"}, timeout=30)
        assert r.status_code == 200, r.text
        eng3 = requests.Session()
        r = eng3.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PASSWORD}, timeout=20)
        assert r.status_code == 200, r.text
        access = eng3.get(f"{BASE_URL}/api/partners/me/engineer-access", timeout=30).json()
        assert access["allowed"] is True and access["reason"] == "internal_engineer", access
    finally:
        # Hard delete requires archive-first + email confirmation.
        admin.put(f"{BASE_URL}/api/master-admin/users/{user_id}/archive",
                  json={"archived": True}, timeout=30)
        r = admin.delete(f"{BASE_URL}/api/master-admin/users/{user_id}",
                         json={"confirm_email": email}, timeout=30)
        assert r.status_code == 200, f"cleanup failed: {r.text}"
        # Cascade must also remove the svc_engineers provisioning row —
        # the engineer must NOT keep Engineer App access after deletion.
        engs = admin.get(f"{BASE_URL}/api/master-admin/engineers", timeout=30).json()
        emails = [e.get("email") for e in engs.get("engineers", [])]
        assert email not in emails, "svc_engineers row must be cascaded on hard delete"


def test_dialogs_offer_engineer_role():
    """Source pins — both the Add User and Edit User master-admin dialogs
    must offer the Engineer option."""
    src = open("/app/frontend/src/pages/MasterAdmin/AdminOrganizations.js", encoding="utf-8").read()
    assert src.count('value="engineer"') >= 2, (
        "Engineer must be selectable in BOTH the Add User and Edit User dialogs"
    )
    assert 'data-testid="add-user-engineer-hint"' in src
