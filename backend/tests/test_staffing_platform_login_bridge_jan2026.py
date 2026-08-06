"""Backend tests for Staffing ↔ Platform user bridge (Jan 2026).

Covers:
- Role mapping engineer/manager on issue-credentials
- Delivery: temp_password vs reset_link
- PATCH /staffing/staff/{id} role propagation
- POST /staffing/reconcile-roles
- GET /master-admin/users surfaces no-login staff (login_status='none')
"""
import os
import uuid
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.strip().split("=", 1)[1].rstrip("/")

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PW = "IsoDemo123!"
MA_EMAIL = "admin@pulsefitness.com"
MA_PW = "C2s9yJ3YAhydB4d34-Bykg"

created_staff_ids: list[str] = []
created_user_emails: list[str] = []


def _login(email: str, pw: str) -> str:
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_token():
    return _login(OWNER_EMAIL, OWNER_PW)


@pytest.fixture(scope="module")
def ma_token():
    return _login(MA_EMAIL, MA_PW)


def _mk_staff(token: str, primary_role: str, email: str | None = None) -> dict:
    tag = uuid.uuid4().hex[:8]
    payload = {
        "full_name": f"TEST Staff {tag}",
        "email": email or f"TEST_staff_{tag}@example.com",
        "primary_role": primary_role,
    }
    r = requests.post(
        f"{BASE}/api/staffing/staff",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30,
    )
    assert r.status_code in (200, 201), f"create staff failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    sid = data.get("id") or data.get("staff", {}).get("id")
    assert sid, f"no id in response: {data}"
    created_staff_ids.append(sid)
    created_user_emails.append(payload["email"])
    return {"id": sid, "email": payload["email"], "full_name": payload["full_name"]}


# ---------- Role mapping ----------

def test_issue_credentials_engineer_maps_to_engineer(owner_token):
    staff = _mk_staff(owner_token, "engineer")
    r = requests.post(
        f"{BASE}/api/staffing/staff/{staff['id']}/issue-credentials",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"delivery": "temp_password", "send_email": False},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["role"] == "engineer", body
    assert body["delivery"] == "temp_password"
    assert body["temp_password"], "temp_password expected"
    assert body.get("invite_url") in (None, "")


def test_issue_credentials_manager_maps_to_manager(owner_token):
    staff = _mk_staff(owner_token, "manager")
    r = requests.post(
        f"{BASE}/api/staffing/staff/{staff['id']}/issue-credentials",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"delivery": "temp_password", "send_email": False},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:400]
    assert r.json()["role"] == "manager"


# ---------- Delivery options ----------

def test_issue_credentials_reset_link_returns_invite_url(owner_token):
    staff = _mk_staff(owner_token, "engineer")
    r = requests.post(
        f"{BASE}/api/staffing/staff/{staff['id']}/issue-credentials",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"delivery": "reset_link", "send_email": False},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["delivery"] == "reset_link"
    assert body["temp_password"] is None
    assert body.get("invite_url"), f"invite_url expected: {body}"
    assert "reset" in body["invite_url"].lower() or "token" in body["invite_url"].lower() or body["invite_url"].startswith("http")


# ---------- PATCH role propagation ----------

def test_patch_staff_role_propagates_to_login(owner_token):
    staff = _mk_staff(owner_token, "engineer")
    # First issue credentials so a linked login exists
    r = requests.post(
        f"{BASE}/api/staffing/staff/{staff['id']}/issue-credentials",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"delivery": "temp_password", "send_email": False},
        timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "engineer"

    # PATCH primary_role → manager
    r = requests.patch(
        f"{BASE}/api/staffing/staff/{staff['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"primary_role": "manager"},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:400]

    # Verify via master admin users endpoint that the linked login's role is now 'manager'
    ma = _login(MA_EMAIL, MA_PW)
    r2 = requests.get(
        f"{BASE}/api/master-admin/users",
        headers={"Authorization": f"Bearer {ma}"},
        timeout=60,
    )
    assert r2.status_code == 200
    users = r2.json() if isinstance(r2.json(), list) else r2.json().get("users", [])
    match = [u for u in users if (u.get("email") or "").lower() == staff["email"].lower()]
    assert match, f"login not found for {staff['email']}"
    assert match[0].get("role") == "manager", f"role not propagated: {match[0]}"


# ---------- Reconcile ----------

def test_reconcile_roles_returns_counts(owner_token):
    r = requests.post(
        f"{BASE}/api/staffing/reconcile-roles",
        headers={"Authorization": f"Bearer {owner_token}"},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["ok"] is True
    assert "checked" in body and isinstance(body["checked"], int)
    assert "updated" in body and isinstance(body["updated"], int)


# ---------- Master Admin surfacing no-login staff ----------

def test_master_admin_surfaces_no_login_staff(owner_token, ma_token):
    # Create a no-login staff (do NOT issue credentials)
    staff = _mk_staff(owner_token, "engineer")
    r = requests.get(
        f"{BASE}/api/master-admin/users",
        headers={"Authorization": f"Bearer {ma_token}"},
        timeout=60,
    )
    assert r.status_code == 200
    users = r.json() if isinstance(r.json(), list) else r.json().get("users", [])
    # Existing users should be tagged login_status='active'
    active_users = [u for u in users if u.get("login_status") == "active"]
    assert len(active_users) > 0, "expected some login_status=active users"

    # No-login staff appear tagged 'none' and is_staff_record True
    none_rows = [u for u in users if u.get("login_status") == "none"]
    assert len(none_rows) > 0, "expected at least one login_status=none row"
    match = [u for u in none_rows if (u.get("email") or "").lower() == staff["email"].lower()]
    assert match, f"seeded no-login staff not surfaced: {staff['email']}"
    assert match[0].get("is_staff_record") is True
    assert match[0].get("role") == "engineer"


# ---------- Cleanup ----------

def test_zzz_cleanup(owner_token):
    """Best-effort cleanup of test staff + users."""
    from pymongo import MongoClient
    mongo = os.environ.get("MONGO_URL")
    dbn = os.environ.get("DB_NAME")
    if not (mongo and dbn):
        pytest.skip("no mongo env")
    cli = MongoClient(mongo)
    d = cli[dbn]
    if created_staff_ids:
        d.staff_members.delete_many({"id": {"$in": created_staff_ids}})
    if created_user_emails:
        d.users.delete_many({"email": {"$in": [e.lower() for e in created_user_emails]}})
