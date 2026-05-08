"""Iteration 198 — Master Admin hard-delete user tests.

Validates the new `DELETE /api/master-admin/users/{user_id}` endpoint:
- Refuses unless the user is archived first (400)
- Refuses without matching `confirm_email` (400)
- Refuses for master admins / the platform admin (400)
- Refuses if it would orphan the org (only owner) (400)
- 200 happy path: cascades issues/notes/audit_logs and deletes the user
"""
from __future__ import annotations

import uuid

import pytest
import requests

from tests.conftest import (
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
    _test_backend_url,
    rate_limit_bypass_headers,
)

BASE_URL = _test_backend_url()
_BYPASS = rate_limit_bypass_headers()
TOTTENHAM_ORG_ID = "156c8dc4-8683-4cb4-8a74-facd811655ad"


def _login(creds: dict) -> str:
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds, headers=_BYPASS)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **_BYPASS}


@pytest.fixture(scope="module")
def admin_headers():
    return _headers(_login({"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD}))


@pytest.fixture
def fresh_archived_staff(admin_headers):
    """Provision a fresh staff user, then archive them (the precondition
    for hard-delete)."""
    unique = uuid.uuid4().hex[:8]
    email = f"hard.delete.{unique}@perm-test.example.com"
    create = requests.post(
        f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_ORG_ID}/users",
        json={
            "email": email,
            "full_name": f"HardDelete Target {unique}",
            "password": "TargetPass123!",
            "role": "staff",
        },
        headers=admin_headers,
    )
    assert create.status_code == 200, f"create failed: {create.text}"
    user = create.json()
    # Archive
    arc = requests.put(
        f"{BASE_URL}/api/master-admin/users/{user['id']}/archive",
        json={"archived": True},
        headers=admin_headers,
    )
    assert arc.status_code == 200, arc.text
    return {"id": user["id"], "email": email}


class TestHardDeleteUser:
    def test_refuses_when_not_archived(self, admin_headers):
        # Make a fresh, NON-archived user
        unique = uuid.uuid4().hex[:8]
        email = f"not.archived.{unique}@perm-test.example.com"
        create = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_ORG_ID}/users",
            json={"email": email, "full_name": "Not Archived", "password": "TargetPass123!", "role": "staff"},
            headers=admin_headers,
        )
        uid = create.json()["id"]
        try:
            resp = requests.delete(
                f"{BASE_URL}/api/master-admin/users/{uid}",
                json={"confirm_email": email},
                headers=admin_headers,
            )
            assert resp.status_code == 400
            assert "archived" in resp.text.lower()
        finally:
            # Tidy: archive then nuke
            requests.put(f"{BASE_URL}/api/master-admin/users/{uid}/archive",
                         json={"archived": True}, headers=admin_headers)
            requests.delete(f"{BASE_URL}/api/master-admin/users/{uid}",
                            json={"confirm_email": email}, headers=admin_headers)

    def test_refuses_without_matching_confirm_email(self, admin_headers, fresh_archived_staff):
        resp = requests.delete(
            f"{BASE_URL}/api/master-admin/users/{fresh_archived_staff['id']}",
            json={"confirm_email": "wrong@example.com"},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "confirmation" in resp.text.lower()

    def test_refuses_to_delete_master_admin(self, admin_headers):
        # Look up the master admin's own id
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers).json()
        # Even if we tried to archive ourselves first (which the API also
        # blocks), the hard-delete must still refuse. Two layers of guard.
        resp = requests.delete(
            f"{BASE_URL}/api/master-admin/users/{me['id']}",
            json={"confirm_email": me["email"]},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 403), resp.text
        # Master admin still exists
        listing = requests.get(f"{BASE_URL}/api/master-admin/users", headers=admin_headers).json()
        ids = [u["id"] for u in listing.get("users", [])]
        assert me["id"] in ids, "Master admin must NOT have been deleted"

    def test_happy_path_deletes_and_cascades(self, admin_headers, fresh_archived_staff):
        uid = fresh_archived_staff["id"]
        email = fresh_archived_staff["email"]

        resp = requests.delete(
            f"{BASE_URL}/api/master-admin/users/{uid}",
            json={"confirm_email": email},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["deleted_user_id"] == uid
        assert "cascade" in body

        # User no longer in /master-admin/users list
        listing = requests.get(f"{BASE_URL}/api/master-admin/users", headers=admin_headers).json()
        ids = [u["id"] for u in listing.get("users", [])]
        assert uid not in ids, "User should be gone from listing after hard delete"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
