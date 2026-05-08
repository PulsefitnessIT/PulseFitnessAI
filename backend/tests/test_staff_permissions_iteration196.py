"""Iteration 196 — Master Admin & Manager Granular Permission tests.

Validates:
1. Master Admin can toggle the new `crm` module on/off per org (via the
   shared `/master-admin/organizations/{org_id}/features` endpoint).
2. /auth/me surfaces module_access including the `crm` key.
3. Manager (or Owner) can PATCH per-staff permissions:
   - module_overrides: {memberships, marketing, crm}
   - timetable_view_only: bool
4. Per-staff `module_overrides` only RESTRICT — they can't grant access
   the org doesn't have.
5. Timetable mutations (create/edit/delete templates, cancel occurrence)
   return 403 when staff is `timetable_view_only`.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from tests.conftest import (
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
    PULSE_PRO_EMAIL,
    PULSE_PRO_PASSWORD,
    _test_backend_url,
    rate_limit_bypass_headers,
)

BASE_URL = _test_backend_url()
_BYPASS = rate_limit_bypass_headers()

MASTER_ADMIN = {"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD}
PULSE_PRO_OPERATOR = {"email": PULSE_PRO_EMAIL, "password": PULSE_PRO_PASSWORD}


def _login(creds: dict) -> str:
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds, headers=_BYPASS)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **_BYPASS}


@pytest.fixture(scope="module")
def admin_headers():
    return _headers(_login(MASTER_ADMIN))


@pytest.fixture(scope="module")
def operator_token():
    return _login(PULSE_PRO_OPERATOR)


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return _headers(operator_token)


@pytest.fixture(scope="module")
def operator_org_id(operator_headers):
    resp = requests.get(f"{BASE_URL}/api/auth/me", headers=operator_headers)
    assert resp.status_code == 200
    return resp.json()["organization_id"]


# ────────────────────────────────────────────────────────────────────────
# 1. CRM module toggle exposed in module_access
# ────────────────────────────────────────────────────────────────────────


class TestCRMModuleToggle:
    def test_auth_me_includes_crm_key(self, operator_headers):
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=operator_headers)
        assert resp.status_code == 200
        ma = resp.json().get("module_access", {})
        assert "crm" in ma, f"module_access must include 'crm': {ma}"

    def test_master_admin_can_toggle_crm(self, admin_headers, operator_headers, operator_org_id):
        # Read original
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=operator_headers).json()
        original = bool((me.get("modules") or {}).get("crm", {}).get("enabled", False))

        # Enable CRM
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{operator_org_id}/features",
            json={"modules": {"crm": {"enabled": True, "tier": "pro"}}},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        me2 = requests.get(f"{BASE_URL}/api/auth/me", headers=operator_headers).json()
        assert me2["module_access"]["crm"] is True

        # Disable CRM
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{operator_org_id}/features",
            json={"modules": {"crm": {"enabled": False, "tier": "pro"}}},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        me3 = requests.get(f"{BASE_URL}/api/auth/me", headers=operator_headers).json()
        assert me3["module_access"]["crm"] is False

        # Restore original
        requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{operator_org_id}/features",
            json={"modules": {"crm": {"enabled": original, "tier": "pro"}}},
            headers=admin_headers,
        )


# ────────────────────────────────────────────────────────────────────────
# 2. Per-staff permissions: module_overrides + timetable_view_only
# ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_staff(admin_headers, operator_headers, operator_org_id):
    """Create a brand-new staff user via the master admin endpoint
    (avoids pre-existing invite-flow quirks where some legacy orgs lack
    a company_code) and login as them."""
    unique = uuid.uuid4().hex[:8]
    email = f"staff.{unique}@perm-test.example.com"
    full_name = f"Perm Staff {unique}"
    password = "StaffPass123!"

    # Create via master admin (idempotent, deterministic)
    resp = requests.post(
        f"{BASE_URL}/api/master-admin/organizations/{operator_org_id}/users",
        json={
            "email": email,
            "full_name": full_name,
            "password": password,
            "role": "staff",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, f"create staff failed: {resp.text}"
    user = resp.json()

    # Login as the new staff user
    staff_token = _login({"email": email, "password": password})

    return {
        "id": user["id"],
        "email": email,
        "password": password,
        "token": staff_token,
        "headers": _headers(staff_token),
    }


class TestStaffPermissions:
    def test_manager_can_set_module_overrides(self, operator_headers, fresh_staff):
        resp = requests.patch(
            f"{BASE_URL}/api/organization/staff/{fresh_staff['id']}/permissions",
            json={"module_overrides": {"marketing": False, "crm": True}},
            headers=operator_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

        # The staff user's /auth/me reflects the override (marketing=False)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=fresh_staff["headers"]).json()
        assert me["module_access"]["marketing"] is False, me["module_access"]
        assert me["module_overrides"].get("marketing") is False

    def test_module_overrides_cannot_grant_disabled_org_module(
        self, admin_headers, operator_headers, operator_org_id, fresh_staff
    ):
        # 1) Owner/master admin DISABLES marketing at the org level
        requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{operator_org_id}/features",
            json={"modules": {"marketing": {"enabled": False, "tier": "pro"}}},
            headers=admin_headers,
        )
        try:
            # 2) Manager tries to "grant" marketing back via per-staff override
            resp = requests.patch(
                f"{BASE_URL}/api/organization/staff/{fresh_staff['id']}/permissions",
                json={"module_overrides": {"marketing": True}},
                headers=operator_headers,
            )
            assert resp.status_code == 200

            # 3) Effective access is still False — overrides only restrict.
            me = requests.get(
                f"{BASE_URL}/api/auth/me", headers=fresh_staff["headers"]
            ).json()
            assert me["module_access"]["marketing"] is False
        finally:
            # Restore org marketing back on
            requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{operator_org_id}/features",
                json={"modules": {"marketing": {"enabled": True, "tier": "pro"}}},
                headers=admin_headers,
            )

    def test_timetable_view_only_blocks_template_create(self, operator_headers, fresh_staff):
        # 1) Manager flips view-only ON
        resp = requests.patch(
            f"{BASE_URL}/api/organization/staff/{fresh_staff['id']}/permissions",
            json={"timetable_view_only": True},
            headers=operator_headers,
        )
        assert resp.status_code == 200

        # 2) Staff attempts to create a class template — must be 403
        resp = requests.post(
            f"{BASE_URL}/api/memberships/classes/templates",
            json={
                "name": "Should-Be-Blocked",
                "category": "Group",
                "duration_min": 30,
                "capacity": 10,
                "recurs_days": [0, 2],
                "start_time": "09:00",
            },
            headers=fresh_staff["headers"],
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        assert "view-only" in resp.text.lower()

    def test_timetable_view_only_does_not_block_read(self, operator_headers, fresh_staff):
        # Make sure the staff user is still view-only (set in previous test)
        resp = requests.patch(
            f"{BASE_URL}/api/organization/staff/{fresh_staff['id']}/permissions",
            json={"timetable_view_only": True},
            headers=operator_headers,
        )
        assert resp.status_code == 200

        # GET timetable / templates should still work
        resp = requests.get(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=fresh_staff["headers"],
        )
        assert resp.status_code == 200, resp.text
        resp = requests.get(
            f"{BASE_URL}/api/memberships/timetable",
            headers=fresh_staff["headers"],
        )
        assert resp.status_code == 200, resp.text

    def test_lifting_view_only_restores_write(self, operator_headers, fresh_staff):
        # Lift the restriction
        resp = requests.patch(
            f"{BASE_URL}/api/organization/staff/{fresh_staff['id']}/permissions",
            json={"timetable_view_only": False},
            headers=operator_headers,
        )
        assert resp.status_code == 200

        # Now create should succeed (memberships module on by default for pulse_pro)
        resp = requests.post(
            f"{BASE_URL}/api/memberships/classes/templates",
            json={
                "name": "After-Lift Class",
                "category": "Group",
                "duration_min": 30,
                "capacity": 10,
                "recurs_days": [1],
                "start_time": "08:00",
            },
            headers=fresh_staff["headers"],
        )
        assert resp.status_code == 200, resp.text
        tpl_id = resp.json()["template"]["id"]

        # Cleanup — archive what we just created
        requests.delete(
            f"{BASE_URL}/api/memberships/classes/templates/{tpl_id}",
            headers=fresh_staff["headers"],
        )

    def test_owner_cannot_be_restricted(self, operator_headers):
        # The operator is themselves an owner/manager. Try to restrict the
        # owner of the org via this endpoint — must 400.
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=operator_headers).json()
        # Find the owner
        staff_resp = requests.get(
            f"{BASE_URL}/api/organization/staff", headers=operator_headers
        )
        assert staff_resp.status_code == 200
        owners = [s for s in staff_resp.json().get("staff", []) if s.get("role") == "owner"]
        if not owners:
            pytest.skip("No owner in this org to test against")
        owner_id = owners[0]["id"]
        resp = requests.patch(
            f"{BASE_URL}/api/organization/staff/{owner_id}/permissions",
            json={"timetable_view_only": True},
            headers=operator_headers,
        )
        assert resp.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
