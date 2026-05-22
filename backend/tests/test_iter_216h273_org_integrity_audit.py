"""Iter 216h273 — Master Admin Org Integrity Audit (continuation of h272).

Follow-on to h272 — h272 self-heals the master admin's own home org
specifically. This iter ships a **generalised** read-only audit so
the master admin can catch orphan users (e.g. left behind by a
half-completed tenant deletion) before they show up as user-facing
errors.

Endpoints:
  GET    /api/master-admin/integrity/org-integrity
  DELETE /api/master-admin/integrity/orphan-users/{user_id}
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _async_iter(items):
    """Tiny helper that mimics a motor cursor: `async for x in ...`.
    Each yield is the dict at that index."""

    class _Cur:
        def __init__(self, xs):
            self._xs = list(xs)

        def __aiter__(self):
            self._i = 0
            return self

        async def __anext__(self):
            if self._i >= len(self._xs):
                raise StopAsyncIteration
            x = self._xs[self._i]
            self._i += 1
            return x

    return _Cur(items)


# ─── 1. Endpoint registration ──────────────────────────────────────


def test_routes_registered():
    from routes.master_admin_integrity import router
    paths = {r.path for r in router.routes}
    assert "/master-admin/integrity/org-integrity" in paths
    assert "/master-admin/integrity/orphan-users/{user_id}" in paths


def test_router_wired_into_admin_bundle():
    """The router must be imported AND included in the admin
    `register_admin()` tuple, else the endpoint is unreachable."""
    import pathlib
    src = pathlib.Path("/app/backend/route_registry/admin.py").read_text()
    assert "master_admin_integrity" in src
    assert "master_admin_integrity_router" in src


# ─── 2. org_integrity_report behaviour ─────────────────────────────


def test_integrity_report_classifies_orphans_correctly():
    """Users either have:
      (a) a valid org pointer  → not an orphan
      (b) a pointer at a missing org doc → orphan, reason: org_doc_missing
      (c) NO organization_id at all      → orphan, reason: no_organization_id
    """
    from routes.master_admin_integrity import org_integrity_report

    orgs = [{"id": "org-A"}, {"id": "org-B"}]
    users = [
        {"id": "u1", "email": "ok@a.test", "organization_id": "org-A"},
        {"id": "u2", "email": "ok@b.test", "organization_id": "org-B"},
        {"id": "u3", "email": "ghost@a.test", "organization_id": "deleted-org"},
        {"id": "u4", "email": "no-org@x.test", "organization_id": None},
        {"id": "u5", "email": "no-org@y.test"},  # field entirely missing
    ]
    fake_db = MagicMock()
    fake_db.organizations.find = MagicMock(return_value=_async_iter(orgs))
    fake_db.users.find = MagicMock(return_value=_async_iter(users))

    with patch("routes.master_admin_integrity.db", fake_db), \
         patch("routes.master_admin_integrity.require_master_admin", return_value=None):
        out = _run(org_integrity_report(user={"is_master_admin": True}))

    assert out["total_users"] == 5
    assert out["total_orgs"] == 2
    assert out["orphan_users_count"] == 3
    by_email = {o["email"]: o for o in out["orphan_users"]}
    assert by_email["ghost@a.test"]["missing_reason"] == "org_doc_missing"
    assert by_email["no-org@x.test"]["missing_reason"] == "no_organization_id"
    assert by_email["no-org@y.test"]["missing_reason"] == "no_organization_id"
    # The two healthy users are NOT in the orphan list
    assert "ok@a.test" not in by_email
    assert "ok@b.test" not in by_email
    # Timestamp is present so dashboards can show "last checked"
    assert "checked_at" in out


def test_integrity_report_requires_master_admin():
    """Surface is privileged — every cross-tenant user record."""
    from routes.master_admin_integrity import org_integrity_report

    def deny(_):
        raise HTTPException(403, "Master admin access required")

    fake_db = MagicMock()
    fake_db.organizations.find = MagicMock(return_value=_async_iter([]))
    fake_db.users.find = MagicMock(return_value=_async_iter([]))

    with patch("routes.master_admin_integrity.db", fake_db), \
         patch("routes.master_admin_integrity.require_master_admin", side_effect=deny), pytest.raises(HTTPException) as exc:
        _run(org_integrity_report(user={"is_master_admin": False}))
    assert exc.value.status_code == 403


# ─── 3. delete_orphan_user safety guards ─────────────────────────────


def test_delete_orphan_refuses_when_org_actually_exists():
    """Belt + braces — if the audit was stale and the org has since
    been re-created, the delete endpoint must REFUSE so we don't
    nuke a now-valid user."""
    from routes.master_admin_integrity import delete_orphan_user

    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value={
        "id": "u1", "email": "x@x.test", "organization_id": "now-exists",
    })
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "now-exists"})

    with patch("routes.master_admin_integrity.db", fake_db), \
         patch("routes.master_admin_integrity.require_master_admin", return_value=None), pytest.raises(HTTPException) as exc:
        _run(delete_orphan_user(user_id="u1", user={"is_master_admin": True}))
    assert exc.value.status_code == 409
    assert "NOT an orphan" in exc.value.detail
    # No delete call was issued
    assert not fake_db.users.delete_one.called


def test_delete_orphan_refuses_to_delete_a_master_admin():
    """Even if a master admin's pointer broke, we don't allow the
    audit endpoint to delete master admins — h272 self-heals their
    org for us, and accidentally deleting a master locks the
    operator out of the platform."""
    from routes.master_admin_integrity import delete_orphan_user

    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value={
        "id": "m1", "email": "admin@gymaxisai.com",
        "organization_id": "missing-org", "is_master_admin": True,
    })

    with patch("routes.master_admin_integrity.db", fake_db), \
         patch("routes.master_admin_integrity.require_master_admin", return_value=None), pytest.raises(HTTPException) as exc:
        _run(delete_orphan_user(user_id="m1", user={"is_master_admin": True}))
    assert exc.value.status_code == 403
    assert "master admin" in exc.value.detail.lower()


def test_delete_orphan_happy_path_removes_user():
    from routes.master_admin_integrity import delete_orphan_user

    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value={
        "id": "u9", "email": "ghost@x.test", "organization_id": "deleted-org",
    })
    # Org pointer doesn't resolve → genuinely an orphan
    fake_db.organizations.find_one = AsyncMock(return_value=None)
    delete_result = MagicMock(deleted_count=1)
    fake_db.users.delete_one = AsyncMock(return_value=delete_result)

    with patch("routes.master_admin_integrity.db", fake_db), \
         patch("routes.master_admin_integrity.require_master_admin", return_value=None):
        out = _run(delete_orphan_user(user_id="u9", user={"is_master_admin": True}))
    assert out["deleted"] is True
    assert out["user_id"] == "u9"
    assert out["email"] == "ghost@x.test"
    fake_db.users.delete_one.assert_awaited_once()


def test_delete_orphan_404s_on_unknown_user():
    from routes.master_admin_integrity import delete_orphan_user

    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value=None)
    with patch("routes.master_admin_integrity.db", fake_db), \
         patch("routes.master_admin_integrity.require_master_admin", return_value=None), pytest.raises(HTTPException) as exc:
        _run(delete_orphan_user(user_id="nope", user={"is_master_admin": True}))
    assert exc.value.status_code == 404
