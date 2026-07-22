"""Iter Jan 2026 — Master Admin Service Desk fix verification.

Verifies:
 1. Master admin login works.
 2. GET /api/master-admin/users returns users (used for grant dropdown).
 3. Module-access payload includes service_desk + engineer informational rows.
 4. GET /api/master-admin/service-desk/members works.
 5. Grant + revoke flow works with an existing user.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    "https://platform-doctor.preview.emergentagent.com"
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PWD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    if r.status_code == 429:
        time.sleep(40)
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"No token returned: {r.json()}"
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def test_master_admin_users_list(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/master-admin/users", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "users" in data
    assert isinstance(data["users"], list)
    # We should have at least the master admin
    emails = [u.get("email", "").lower() for u in data["users"]]
    assert ADMIN_EMAIL in emails


def test_module_access_includes_service_desk_and_engineer(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/master-admin/users", timeout=30)
    users = r.json()["users"]
    # Pick any user (prefer non-admin one if exists)
    target = next((u for u in users if u.get("id")), None)
    assert target, "No users found"
    uid = target["id"]

    r2 = admin_session.get(
        f"{BASE_URL}/api/master-admin/users/{uid}/module-access", timeout=30)
    assert r2.status_code == 200, r2.text[:300]
    payload = r2.json()
    assert "modules" in payload
    keys = {m["key"]: m for m in payload["modules"]}
    assert "service_desk" in keys, f"Missing service_desk row. Keys: {list(keys)}"
    assert "engineer" in keys, f"Missing engineer row. Keys: {list(keys)}"

    sd = keys["service_desk"]
    assert sd.get("label") == "Service Desk"
    assert "org_enabled" in sd and isinstance(sd["org_enabled"], bool)
    assert "user_access" in sd and isinstance(sd["user_access"], bool)
    assert sd.get("informational") is True

    eng = keys["engineer"]
    assert eng.get("label") == "Engineer app"
    assert "org_enabled" in eng and isinstance(eng["org_enabled"], bool)
    assert "user_access" in eng and isinstance(eng["user_access"], bool)
    assert eng.get("informational") is True


def test_service_desk_members_list(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/master-admin/service-desk/members", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "members" in data
    assert "total" in data
    assert isinstance(data["members"], list)


def test_grant_and_revoke_flow(admin_session):
    # Pick a non-service-desk staff to grant
    users = admin_session.get(
        f"{BASE_URL}/api/master-admin/users", timeout=30).json()["users"]
    members = admin_session.get(
        f"{BASE_URL}/api/master-admin/service-desk/members", timeout=30).json()["members"]
    member_emails = {(m.get("email") or "").lower() for m in members}
    candidate = next(
        (u for u in users
         if u.get("email")
         and u["email"].lower() not in member_emails
         and not u.get("is_service_desk")
         and u["email"].lower() != ADMIN_EMAIL),
        None,
    )
    if not candidate:
        pytest.skip("No candidate non-desk user to grant/revoke")

    email = candidate["email"].lower()
    r = admin_session.post(
        f"{BASE_URL}/api/master-admin/service-desk/members/grant",
        json={"email": email, "brand": "pulse"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j.get("success") is True or j.get("email") == email

    # Verify appears in members
    members2 = admin_session.get(
        f"{BASE_URL}/api/master-admin/service-desk/members", timeout=30).json()["members"]
    assert any((m.get("email") or "").lower() == email for m in members2), \
        f"{email} not appearing in members after grant"

    # Revoke
    r2 = admin_session.post(
        f"{BASE_URL}/api/master-admin/service-desk/members/revoke",
        json={"email": email}, timeout=30)
    assert r2.status_code == 200, r2.text[:300]

    members3 = admin_session.get(
        f"{BASE_URL}/api/master-admin/service-desk/members", timeout=30).json()["members"]
    # Master admins can't actually be revoked; skip that check for master admins
    if not candidate.get("is_master_admin"):
        assert not any((m.get("email") or "").lower() == email for m in members3), \
            f"{email} still a member after revoke"
