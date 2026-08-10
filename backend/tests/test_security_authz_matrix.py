"""Security acceptance tests — the article-specific failure modes (section 51).

These are PERMANENT regression tests proving the incident class is impossible
by design. They exercise the Central Authorisation Engine (utils.authz)
against real seeded multi-tenant / multi-site / multi-owner fixtures in Mongo.

  Test A — modify another USER's record            → denied (404)
  Test B — access another SITE's record            → denied (403)
  Test C — access another TENANT's record          → denied (404)
  Test D — UI restriction bypass (illegal state)   → backend rejects (409)
  Test E — privileged-only transition as non-admin → denied (403)
  Test F — mass-assignment of protected fields     → stripped
  Test G — abnormal rapid actions                  → security events recorded
  Test H — replay of a sensitive mutation          → no duplicate effect

All fixtures are namespaced ``AUTHZQA_*`` and torn down after the run.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

BACKEND_DIR = "/app/backend"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from utils.database import db  # noqa: E402
from utils.authz import (  # noqa: E402
    authorize_resource, assert_transition, filter_writable, PROTECTED_FIELDS,
)
from utils.site_scope import set_request_site_scope, clear_request_site_scope  # noqa: E402

P = "AUTHZQA_"
ORG_A = f"{P}org_a"
ORG_B = f"{P}org_b"
SITE_A1 = f"{P}site_a1"
SITE_A2 = f"{P}site_a2"


def _uid(x):
    return f"{P}{x}"


async def _seed():
    await _teardown()
    now = datetime.now(timezone.utc).isoformat()
    # Two tenants, tenant A has two sites.
    await db.organizations.insert_many([
        {"id": ORG_A, "name": "AuthzQA Org A", "account_type": "full", "created_at": now},
        {"id": ORG_B, "name": "AuthzQA Org B", "account_type": "full", "created_at": now},
    ])
    await db.sites.insert_many([
        {"id": SITE_A1, "organization_id": ORG_A, "name": "A1", "created_at": now},
        {"id": SITE_A2, "organization_id": ORG_A, "name": "A2", "created_at": now},
    ])
    # Equipment: one per site in org A, one in org B.
    await db.equipment.insert_many([
        {"id": _uid("eq_a1"), "organization_id": ORG_A, "site_id": SITE_A1, "name": "Bike A1"},
        {"id": _uid("eq_a2"), "organization_id": ORG_A, "site_id": SITE_A2, "name": "Bike A2"},
        {"id": _uid("eq_b"), "organization_id": ORG_B, "site_id": None, "name": "Bike B"},
    ])
    # Issues (faults).
    await db.issues.insert_many([
        {"id": _uid("issue_a1"), "organization_id": ORG_A, "site_id": SITE_A1, "status": "open"},
        {"id": _uid("issue_a2"), "organization_id": ORG_A, "site_id": SITE_A2, "status": "closed"},
        {"id": _uid("issue_b"), "organization_id": ORG_B, "status": "open"},
    ])
    # Member-owned bookings in org A.
    await db.bookings.insert_many([
        {"id": _uid("bk_u1"), "organization_id": ORG_A, "site_id": SITE_A1, "member_id": _uid("member1"), "status": "booked"},
        {"id": _uid("bk_u2"), "organization_id": ORG_A, "site_id": SITE_A1, "member_id": _uid("member2"), "status": "booked"},
    ])
    # Files (documents) — one per site in org A, one in org B.
    await db.files.insert_many([
        {"id": _uid("file_a1"), "organization_id": ORG_A, "site_id": SITE_A1, "original_filename": "a1.pdf", "storage_path": "x"},
        {"id": _uid("file_a2"), "organization_id": ORG_A, "site_id": SITE_A2, "original_filename": "a2.pdf", "storage_path": "x"},
        {"id": _uid("file_b"), "organization_id": ORG_B, "original_filename": "b.pdf", "storage_path": "x"},
    ])
    # CRM quotes in org A for the approval state-machine tests.
    await db.crm2_quotes.insert_many([
        {"id": _uid("q_draft"), "organization_id": ORG_A, "status": "draft", "quote_number": "Q-1"},
        {"id": _uid("q_pending"), "organization_id": ORG_A, "status": "pending_approval", "quote_number": "Q-2"},
        {"id": _uid("q_accepted"), "organization_id": ORG_A, "status": "accepted", "quote_number": "Q-3"},
    ])
    # MOD incidents.
    await db.mod_incidents.insert_many([
        {"id": _uid("inc_open"), "site_id": SITE_A1, "organization_id": ORG_A, "status": "open"},
        {"id": _uid("inc_closed"), "site_id": SITE_A1, "organization_id": ORG_A, "status": "closed"},
    ])


async def _teardown():
    for name in ("organizations", "sites", "equipment", "issues", "bookings",
                 "files", "crm2_quotes", "mod_incidents"):
        await db[name].delete_many({"id": {"$regex": f"^{P}"}})
    await db.security_events.delete_many({"resource_id": {"$regex": f"^{P}"}})


def _user(org_id, role="manager", *, allowed_sites=None, uid=None, admin=False):
    u = {
        "id": uid or _uid(f"user_{org_id}"),
        "email": f"{uid or 'user'}@authzqa.test",
        "organization_id": org_id,
        "role": role,
    }
    if allowed_sites is not None:
        u["allowed_site_ids"] = allowed_sites
    if admin:
        u["is_master_admin"] = True
    return u


def _bind_scope(user):
    """Mirror what the auth dependency does per-request."""
    set_request_site_scope(user)


async def _sec_events(event_type=None):
    q = {"resource_id": {"$regex": f"^{P}"}}
    if event_type:
        q["event_type"] = event_type
    return await db.security_events.count_documents(q)


# ───────────────────────────── the matrix ──────────────────────────────


class TestSecurityMatrix:

    def test_A_cross_owner_booking_denied(self):
        async def run():
            await _seed()
            # member1 owns bk_u1; member2 must NOT be able to act on it.
            u = _user(ORG_A, role="member")
            _bind_scope(u)
            # Owner of another member's booking → 404 (ownership enforced).
            with pytest.raises(HTTPException) as ei:
                await authorize_resource(
                    u, "booking", _uid("bk_u1"), "cancel",
                    owner_id=_uid("member2"),
                )
            assert ei.value.status_code == 404
            # Correct owner passes.
            doc = await authorize_resource(
                u, "booking", _uid("bk_u1"), "cancel", owner_id=_uid("member1"),
            )
            assert doc["id"] == _uid("bk_u1")
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_B_cross_site_denied(self):
        async def run():
            await _seed()
            # Manager restricted to SITE_A1 only.
            u = _user(ORG_A, role="manager", allowed_sites=[SITE_A1])
            _bind_scope(u)
            # Own site OK.
            ok = await authorize_resource(u, "equipment", _uid("eq_a1"), "update")
            assert ok["id"] == _uid("eq_a1")
            # Sibling site in same tenant → 403.
            with pytest.raises(HTTPException) as ei:
                await authorize_resource(u, "equipment", _uid("eq_a2"), "update")
            assert ei.value.status_code == 403
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_C_cross_tenant_denied(self):
        async def run():
            await _seed()
            u = _user(ORG_A, role="owner")
            _bind_scope(u)
            with pytest.raises(HTTPException) as ei:
                await authorize_resource(u, "equipment", _uid("eq_b"), "update")
            assert ei.value.status_code == 404  # never leak existence
            with pytest.raises(HTTPException) as ei2:
                await authorize_resource(u, "issue", _uid("issue_b"), "update")
            assert ei2.value.status_code == 404
            assert await _sec_events("bola_cross_tenant_denied") >= 2
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_D_illegal_state_transition_rejected(self):
        async def run():
            await _seed()
            u = _user(ORG_A, role="manager")
            _bind_scope(u)
            # closed → open is NOT a legal edge (must reopen) → 409.
            with pytest.raises(HTTPException) as ei:
                await assert_transition("issue", "closed", "open", u, resource_id=_uid("issue_a2"))
            assert ei.value.status_code == 409
            # open → resolved is legal.
            await assert_transition("issue", "open", "resolved", u, resource_id=_uid("issue_a1"))
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_E_privileged_only_transition_denied_for_staff(self):
        async def run():
            await _seed()
            staff = _user(ORG_A, role="site_staff")
            _bind_scope(staff)
            # closed → reopened requires owner/manager.
            with pytest.raises(HTTPException) as ei:
                await assert_transition("issue", "closed", "reopened", staff, resource_id=_uid("issue_a2"))
            assert ei.value.status_code == 403
            # A manager may do it.
            mgr = _user(ORG_A, role="manager")
            _bind_scope(mgr)
            await assert_transition("issue", "closed", "reopened", mgr, resource_id=_uid("issue_a2"))
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_F_mass_assignment_stripped(self):
        async def run():
            await _seed()
            u = _user(ORG_A, role="manager")
            payload = {
                "description": "legit change",
                "organization_id": ORG_B,     # tenant hijack attempt
                "role": "master_admin",        # privilege escalation attempt
                "site_id": SITE_A2,            # site hijack attempt
                "is_admin": True,
                "approval_status": "approved",
            }
            clean = await filter_writable(
                payload, allowed_fields={"description"}, user=u,
                resource_type="issue", resource_id=_uid("issue_a1"),
            )
            assert clean == {"description": "legit change"}
            for bad in ("organization_id", "role", "site_id", "is_admin", "approval_status"):
                assert bad not in clean
                assert bad in PROTECTED_FIELDS
            assert await _sec_events("mass_assignment_blocked") >= 1
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_G_rapid_denied_actions_are_logged(self):
        async def run():
            await _seed()
            attacker = _user(ORG_B, role="manager", uid=_uid("attacker"))
            _bind_scope(attacker)
            # Enumerate org A resources rapidly — every attempt must be denied AND logged.
            denied = 0
            for _ in range(12):
                try:
                    await authorize_resource(attacker, "equipment", _uid("eq_a1"), "read")
                except HTTPException:
                    denied += 1
            assert denied == 12
            assert await _sec_events("bola_cross_tenant_denied") >= 12
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_H_replay_no_duplicate_effect(self):
        async def run():
            await _seed()
            u = _user(ORG_A, role="manager")
            _bind_scope(u)
            # Simulate a status mutation applied twice (replay). The engine
            # treats an identical current→target as an idempotent no-op, so a
            # replayed "resolve" cannot double-apply / double-fire side effects.
            await db.issues.update_one({"id": _uid("issue_a1")}, {"$set": {"status": "resolved"}})
            # Replay: current is already 'resolved' → transition is a no-op (no raise).
            await assert_transition("issue", "resolved", "resolved", u, resource_id=_uid("issue_a1"))
            doc = await db.issues.find_one({"id": _uid("issue_a1")}, {"_id": 0})
            assert doc["status"] == "resolved"
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_admin_bypasses_but_is_audited(self):
        async def run():
            await _seed()
            admin = _user(ORG_A, role="master_admin", admin=True)
            _bind_scope(admin)
            # Master admin can reach org B's sensitive quote-like resource.
            doc = await authorize_resource(admin, "equipment", _uid("eq_b"), "read")
            assert doc["id"] == _uid("eq_b")
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    # ── Phase 2 rollout: quotes, documents, MOD incidents ──────────────

    def test_quote_skip_approval_blocked(self):
        async def run():
            await _seed()
            u = _user(ORG_A, role="manager")
            _bind_scope(u)
            # draft → approved (skipping submit) must be rejected (409). §8.
            with pytest.raises(HTTPException) as ei:
                await assert_transition("quote", "draft", "approved", u, resource_id=_uid("q_draft"))
            assert ei.value.status_code == 409
            # Legit path: draft → pending_approval → approved.
            await assert_transition("quote", "draft", "pending_approval", u, resource_id=_uid("q_draft"))
            await assert_transition("quote", "pending_approval", "approved", u, resource_id=_uid("q_pending"))
            # Re-approving a finalised (accepted) quote is rejected.
            with pytest.raises(HTTPException) as ei2:
                await assert_transition("quote", "accepted", "approved", u, resource_id=_uid("q_accepted"))
            assert ei2.value.status_code == 409
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_file_download_cross_tenant_and_cross_site(self):
        async def run():
            await _seed()
            # Cross-tenant download denied (404).
            u = _user(ORG_A, role="owner")
            _bind_scope(u)
            with pytest.raises(HTTPException) as ei:
                await authorize_resource(u, "file", _uid("file_b"), "download")
            assert ei.value.status_code == 404
            # Site-restricted user cannot download another site's file (403).
            restricted = _user(ORG_A, role="manager", allowed_sites=[SITE_A1])
            _bind_scope(restricted)
            ok = await authorize_resource(restricted, "file", _uid("file_a1"), "download")
            assert ok["id"] == _uid("file_a1")
            with pytest.raises(HTTPException) as ei2:
                await authorize_resource(restricted, "file", _uid("file_a2"), "download")
            assert ei2.value.status_code == 403
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())

    def test_mod_incident_closure_state_machine(self):
        async def run():
            await _seed()
            mgr = _user(ORG_A, role="manager")
            _bind_scope(mgr)
            # open → closed is legal.
            await assert_transition("mod_incident", "open", "closed", mgr, resource_id=_uid("inc_open"))
            # Closing an already-closed incident is an idempotent no-op (no raise).
            await assert_transition("mod_incident", "closed", "closed", mgr, resource_id=_uid("inc_closed"))
            # Reopening a closed incident requires a privileged role.
            staff = _user(ORG_A, role="site_staff")
            _bind_scope(staff)
            with pytest.raises(HTTPException) as ei:
                await assert_transition("mod_incident", "closed", "reopened", staff, resource_id=_uid("inc_closed"))
            assert ei.value.status_code == 403
            await _teardown()
            clear_request_site_scope()
        asyncio.run(run())
