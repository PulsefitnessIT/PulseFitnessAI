"""Phase 1 — Memberships multi-site isolation + RBAC leak proof.

Seeds TWO marker sites (A and B) and proves a restricted manager sees A's
records and NEVER B's, across members + dashboard, while an owner sees both.
Runs the real route handlers against the real DB.
"""
import asyncio
import uuid

import pytest

from utils.database import db
from utils.site_scope import set_request_site_scope, clear_request_site_scope
from routes.memberships.members import members_list
from routes.memberships.dashboard import operator_dashboard

ORG = f"test-iso-{uuid.uuid4().hex[:8]}"
SITE_A = f"siteA-{uuid.uuid4().hex[:6]}"
SITE_B = f"siteB-{uuid.uuid4().hex[:6]}"

OWNER = {"id": "owner1", "organization_id": ORG, "role": "owner", "account_type": "full"}
MANAGER_A = {"id": "mgrA", "organization_id": ORG, "role": "manager",
             "account_type": "full", "allowed_site_ids": [SITE_A]}


async def _seed():
    await db.sites.insert_many([
        {"id": SITE_A, "organization_id": ORG, "name": "Site A", "is_head_office": True, "created_at": "2026-01-01T00:00:00+00:00"},
        {"id": SITE_B, "organization_id": ORG, "name": "Site B", "created_at": "2026-01-02T00:00:00+00:00"},
    ])
    await db.members.insert_many([
        {"id": "mA1", "organization_id": ORG, "site_id": SITE_A, "email": "a1@x.com", "first_name": "MARKER_A", "last_name": "One", "status": "active", "created_at": "2026-06-01T00:00:00+00:00"},
        {"id": "mA2", "organization_id": ORG, "site_id": SITE_A, "email": "a2@x.com", "first_name": "MARKER_A", "last_name": "Two", "status": "active", "created_at": "2026-06-02T00:00:00+00:00"},
        {"id": "mB1", "organization_id": ORG, "site_id": SITE_B, "email": "b1@x.com", "first_name": "MARKER_B", "last_name": "One", "status": "active", "created_at": "2026-06-03T00:00:00+00:00"},
    ])


async def _cleanup():
    await db.sites.delete_many({"organization_id": ORG})
    await db.members.delete_many({"organization_id": ORG})
    clear_request_site_scope()


def _names(res):
    return {m["first_name"] for m in res["members"]}


@pytest.mark.asyncio
async def test_membership_site_isolation():
    await _cleanup()
    await _seed()
    try:
        # ── Owner sees BOTH sites ──
        set_request_site_scope(OWNER)
        res = await members_list(q=None, status_f=None, site_id=None, user=OWNER)
        assert _names(res) == {"MARKER_A", "MARKER_B"}, _names(res)
        # Owner can drill into B
        set_request_site_scope(OWNER)
        res_b = await members_list(q=None, status_f=None, site_id=SITE_B, user=OWNER)
        assert _names(res_b) == {"MARKER_B"}

        # ── Manager restricted to A: "all my sites" → A only, NEVER B ──
        set_request_site_scope(MANAGER_A)
        res = await members_list(q=None, status_f=None, site_id=None, user=MANAGER_A)
        assert _names(res) == {"MARKER_A"}, f"LEAK: {_names(res)}"
        assert "MARKER_B" not in _names(res)

        # ── Manager drilling into A → A only ──
        set_request_site_scope(MANAGER_A)
        res = await members_list(q=None, status_f=None, site_id=SITE_A, user=MANAGER_A)
        assert _names(res) == {"MARKER_A"}

        # ── Manager requesting disallowed site B → 403 ──
        from fastapi import HTTPException
        set_request_site_scope(MANAGER_A)
        with pytest.raises(HTTPException) as exc:
            await members_list(q=None, status_f=None, site_id=SITE_B, user=MANAGER_A)
        assert exc.value.status_code == 403
        assert exc.value.detail["error"] == "site_access_denied"

        # ── Dashboard active_members: owner=3, manager=2 (A only) ──
        set_request_site_scope(OWNER)
        d_owner = await operator_dashboard(site_id=None, user=OWNER)
        assert d_owner["active_members"] == 3, d_owner["active_members"]
        set_request_site_scope(MANAGER_A)
        d_mgr = await operator_dashboard(site_id=None, user=MANAGER_A)
        assert d_mgr["active_members"] == 2, f"LEAK in dashboard: {d_mgr['active_members']}"
    finally:
        await _cleanup()


if __name__ == "__main__":
    asyncio.run(test_membership_site_isolation())
    print("PASS: membership site isolation (no cross-site leak)")
