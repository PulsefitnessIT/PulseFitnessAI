"""
Staffing (/pulse People > Module access) grant/revoke for the mod_operations
platform per-user override, plus bulk. Also regression on 'operations' (org-
gated core) and 'service_desk' (flag).

We invoke the route handlers IN-PROCESS with the org owner user dict,
mirroring the main agent's self-test approach (HTTP auth is rate-limited &
requires cookies + MFA-free path). This is the pattern used by the earlier
iteration's test file for master_admin_users.
"""
import asyncio
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, "/app/backend")

from utils.database import db  # noqa: E402
from routes.staffing import (  # noqa: E402
    staff_module_grant,
    staff_module_revoke,
    staff_module_access,
    staff_module_bulk,
    BulkModuleAccess,
)

ORG_ID = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
OWNER_USER_ID = "63cfe3e1-14d1-4001-9018-e098715d7bd9"
# Craig Henshall — role=manager (non-privileged) in Pulse Fitness Ltd
STAFF_ID = "0a279c7a-ce4c-4b2b-8bef-c7028471ffb9"
TARGET_USER_ID = "221876bf-e6ba-4e5c-a8d1-f4bfa6bce292"

OWNER_USER = {
    "id": OWNER_USER_ID,
    "email": "portal@pulsefitness.ltd",
    "role": "owner",
    "organization_id": ORG_ID,
    "is_master_admin": False,
    "_jwt_mfa_verified": True,
}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _get_row(payload, key):
    return next((m for m in payload["modules"] if m["key"] == key), None)


def _cleanup():
    """Clear any mod_operations override we may have set on the target."""
    _run(db.users.update_one(
        {"id": TARGET_USER_ID},
        {"$unset": {"module_overrides.mod_operations": ""}}))
    _run(db.crm_users.update_one(
        {"id": TARGET_USER_ID},
        {"$unset": {"module_overrides.mod_operations": ""}}))


@pytest.fixture(autouse=True)
def _clean_around():
    _cleanup()
    yield
    _cleanup()


# ─────────────────────────────────────────────────────────────
# Fix under test: staffing single grant/revoke for mod_operations
# ─────────────────────────────────────────────────────────────
class TestStaffingModOperations:

    def test_target_is_non_privileged(self):
        # Sanity: user_access flip is only visible if is_privileged is False.
        payload = _run(staff_module_access(STAFF_ID, user=OWNER_USER))
        assert payload["is_privileged"] is False, (
            "Target must be non-privileged for user_access flip to be visible")
        row = _get_row(payload, "mod_operations")
        assert row is not None, "mod_operations row missing from staffing payload"
        assert row["label"] == "MOD Operations"
        assert row["user_access"] is False

    def test_grant_mod_operations_no_longer_400s(self):
        p = _run(staff_module_grant(STAFF_ID, "mod_operations", user=OWNER_USER))
        assert p.get("result") == "granted"
        row = _get_row(p, "mod_operations")
        assert row["user_access"] is True
        assert row["fix_action"] == "revoke_flag"
        # DB check on BOTH collections
        u = _run(db.users.find_one({"id": TARGET_USER_ID},
                                   {"_id": 0, "module_overrides": 1}))
        assert (u.get("module_overrides") or {}).get("mod_operations") is True
        cu = _run(db.crm_users.find_one({"id": TARGET_USER_ID},
                                        {"_id": 0, "module_overrides": 1}))
        # crm_users row may not exist for every staff — only assert if it does
        if cu is not None:
            assert (cu.get("module_overrides") or {}).get("mod_operations") is True

    def test_grant_bypasses_org_enablement_gate(self):
        # Org has no explicit modules_enabled/module_access for mod_operations.
        # If the org-gate were being applied, this would raise 400 with the
        # "This module isn't enabled for your organisation" message.
        try:
            p = _run(staff_module_grant(STAFF_ID, "mod_operations", user=OWNER_USER))
        except HTTPException as e:
            pytest.fail(
                f"mod_operations grant hit org-gate: {e.status_code} {e.detail}")
        assert "org" not in (p.get("result") or "").lower()

    def test_revoke_mod_operations_flips_row_false(self):
        # Grant first, then revoke.
        _run(staff_module_grant(STAFF_ID, "mod_operations", user=OWNER_USER))
        p = _run(staff_module_revoke(STAFF_ID, "mod_operations", user=OWNER_USER))
        assert p.get("result") == "revoked"
        row = _get_row(p, "mod_operations")
        assert row["user_access"] is False
        assert row["fix_action"] == "grant_flag"
        u = _run(db.users.find_one({"id": TARGET_USER_ID},
                                   {"_id": 0, "module_overrides": 1}))
        assert (u.get("module_overrides") or {}).get("mod_operations") is False

    def test_bogus_module_key_returns_400_grant(self):
        with pytest.raises(HTTPException) as ei:
            _run(staff_module_grant(STAFF_ID, "bogus", user=OWNER_USER))
        assert ei.value.status_code == 400
        assert "Unknown module" in str(ei.value.detail)

    def test_bogus_module_key_returns_400_revoke(self):
        with pytest.raises(HTTPException) as ei:
            _run(staff_module_revoke(STAFF_ID, "bogus", user=OWNER_USER))
        assert ei.value.status_code == 400
        assert "Unknown module" in str(ei.value.detail)


# ─────────────────────────────────────────────────────────────
# Bulk endpoint
# ─────────────────────────────────────────────────────────────
class TestStaffingBulkModOperations:

    def test_bulk_grant_mod_operations(self):
        body = BulkModuleAccess(
            staff_ids=[STAFF_ID], grant=["mod_operations"], revoke=[])
        res = _run(staff_module_bulk(body, user=OWNER_USER))
        assert res["updated"] == 1
        assert "mod_operations" not in res.get("skipped_org_off", []), (
            f"mod_operations should NOT be skipped as org-off: {res}")
        u = _run(db.users.find_one({"id": TARGET_USER_ID},
                                   {"_id": 0, "module_overrides": 1}))
        assert (u.get("module_overrides") or {}).get("mod_operations") is True

    def test_bulk_revoke_mod_operations(self):
        # grant then revoke through bulk
        _run(staff_module_bulk(
            BulkModuleAccess(staff_ids=[STAFF_ID], grant=["mod_operations"]),
            user=OWNER_USER))
        res = _run(staff_module_bulk(
            BulkModuleAccess(staff_ids=[STAFF_ID], revoke=["mod_operations"]),
            user=OWNER_USER))
        assert res["updated"] == 1
        u = _run(db.users.find_one({"id": TARGET_USER_ID},
                                   {"_id": 0, "module_overrides": 1}))
        assert (u.get("module_overrides") or {}).get("mod_operations") is False


# ─────────────────────────────────────────────────────────────
# Regression: operations (org-gated) + service_desk (flag)
# ─────────────────────────────────────────────────────────────
class TestStaffingRegression:

    def _org_has_operations(self) -> bool:
        from utils.module_access import org_module_access
        org = _run(db.organizations.find_one({"id": ORG_ID}, {"_id": 0}))
        return bool(org_module_access(org).get("operations"))

    def test_operations_still_org_gated(self):
        """If org doesn't have operations enabled, grant must 400 with the
        org-enablement message. If it IS enabled, grant must succeed (no
        regression from the mod_operations fix)."""
        # Ensure clean override state
        _run(db.users.update_one({"id": TARGET_USER_ID},
                                 {"$unset": {"module_overrides.operations": ""}}))
        try:
            if self._org_has_operations():
                p = _run(staff_module_grant(STAFF_ID, "operations", user=OWNER_USER))
                assert p.get("result") == "granted"
                u = _run(db.users.find_one({"id": TARGET_USER_ID},
                                           {"_id": 0, "module_overrides": 1}))
                assert (u.get("module_overrides") or {}).get("operations") is True
            else:
                with pytest.raises(HTTPException) as ei:
                    _run(staff_module_grant(STAFF_ID, "operations", user=OWNER_USER))
                assert ei.value.status_code == 400
                assert "organisation" in str(ei.value.detail).lower()
        finally:
            _run(db.users.update_one({"id": TARGET_USER_ID},
                                     {"$unset": {"module_overrides.operations": ""}}))
            _run(db.crm_users.update_one({"id": TARGET_USER_ID},
                                         {"$unset": {"module_overrides.operations": ""}}))

    def test_service_desk_flag_grant_revoke(self):
        # Preserve existing state
        u0 = _run(db.users.find_one({"id": TARGET_USER_ID},
                                    {"_id": 0, "is_service_desk": 1}))
        original = bool((u0 or {}).get("is_service_desk"))
        try:
            p = _run(staff_module_grant(STAFF_ID, "service_desk", user=OWNER_USER))
            row = _get_row(p, "service_desk")
            assert row["user_access"] is True
            u = _run(db.users.find_one({"id": TARGET_USER_ID},
                                       {"_id": 0, "is_service_desk": 1}))
            assert u.get("is_service_desk") is True

            p2 = _run(staff_module_revoke(STAFF_ID, "service_desk", user=OWNER_USER))
            row2 = _get_row(p2, "service_desk")
            assert row2["user_access"] is False
            u2 = _run(db.users.find_one({"id": TARGET_USER_ID},
                                        {"_id": 0, "is_service_desk": 1}))
            assert u2.get("is_service_desk") is False
        finally:
            _run(db.users.update_one({"id": TARGET_USER_ID},
                                     {"$set": {"is_service_desk": original}}))
            _run(db.crm_users.update_one({"id": TARGET_USER_ID},
                                         {"$set": {"is_service_desk": original}}))


# ─────────────────────────────────────────────────────────────
# Regression: master-admin path still works for mod_operations
# ─────────────────────────────────────────────────────────────
class TestMasterAdminRegression:

    def test_master_admin_grant_revoke_mod_operations(self):
        from routes.master_admin_users import (
            grant_user_module_access, revoke_user_module_access)
        LEE_USER_ID = "3355e0bb-e71a-4811-85e9-1c08c06dc362"
        ADMIN = {"id": "master-admin", "email": "admin@pulsefitness.com",
                 "is_master_admin": True, "_jwt_mfa_verified": True}
        _run(db.users.update_one({"id": LEE_USER_ID},
                                 {"$unset": {"module_overrides.mod_operations": ""}}))
        try:
            p = _run(grant_user_module_access(LEE_USER_ID, "mod_operations", user=ADMIN))
            assert p.get("result") == "granted_flag"
            u = _run(db.users.find_one({"id": LEE_USER_ID},
                                       {"_id": 0, "module_overrides": 1}))
            assert (u.get("module_overrides") or {}).get("mod_operations") is True
            p2 = _run(revoke_user_module_access(LEE_USER_ID, "mod_operations",
                                                body={}, user=ADMIN))
            row = _get_row(p2, "mod_operations")
            assert row["user_access"] is False
        finally:
            _run(db.users.update_one({"id": LEE_USER_ID},
                                     {"$unset": {"module_overrides.mod_operations": ""}}))
