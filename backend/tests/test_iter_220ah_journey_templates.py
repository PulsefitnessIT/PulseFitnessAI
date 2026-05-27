"""Iter 220ah — B2B Journey Templates launcher tests.

Pins:
  * All endpoints master-admin gated.
  * Template catalogue ships the 4 canonical templates.
  * Each template materialises into a real ``marketing_journeys`` row
    with ``send_email`` leaf nodes the omni-channel dispatcher already
    knows how to fire.
  * ``launch`` is idempotent: re-running returns the existing journey.
  * ``recreate`` archives the previous journey and inserts a fresh one.
  * Unknown template ids return 404 (not 500).
  * The list endpoint surfaces ``existing_journey`` per template so
    the UI can flip Launch ↔ Open + Re-create.
  * ``_master_admin_org_id`` resolves from the first master-admin
    user's ``organization_id`` (the canonical home for self-promo
    journeys).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_db_for_launch():
    fdb = MagicMock()
    # users.find_one resolves the master-admin user → organization_id
    fdb.users.find_one = AsyncMock(return_value={
        "organization_id": "org-master-1",
    })
    fdb.organizations.find_one = AsyncMock(return_value=None)

    # marketing_journeys defaults — no existing rows, accept inserts +
    # updates.
    fdb.marketing_journeys.find_one = AsyncMock(return_value=None)
    fdb.marketing_journeys.insert_one = AsyncMock()
    fdb.marketing_journeys.update_many = AsyncMock()
    return fdb


# ── Catalogue ─────────────────────────────────────────────────────

def test_template_catalogue_ships_canonical_four():
    from routes import master_admin_growth_hub as m
    assert set(m.JOURNEY_TEMPLATES.keys()) == {
        "cold-to-demo", "demo-booked", "trial-conversion", "lost-revival",
    }
    # Every template has at least 2 send_email nodes (B2B journeys
    # without follow-ups don't move deals).
    for tid, t in m.JOURNEY_TEMPLATES.items():
        nodes = t.get("nodes") or []
        assert len(nodes) >= 2, f"{tid} has too few nodes"
        assert all(n.get("type") == "send_email" for n in nodes), tid
        assert all(n.get("subject") for n in nodes), tid
        assert all(n.get("body") for n in nodes), tid


# ── Gating ─────────────────────────────────────────────────────────

def test_list_templates_requires_master_admin():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    async def go():
        try:
            await m.list_journey_templates({"id": "u", "is_master_admin": False})
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


def test_launch_requires_master_admin():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    async def go():
        try:
            await m.launch_journey_template(
                "cold-to-demo", {"id": "u", "is_master_admin": False},
            )
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


def test_recreate_requires_master_admin():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    async def go():
        try:
            await m.recreate_journey_template(
                "cold-to-demo", {"id": "u", "is_master_admin": False},
            )
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


# ── List ──────────────────────────────────────────────────────────

def test_list_returns_all_templates_with_existing_flag():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()
    # `cold-to-demo` already has a journey; others don't.
    async def _find_one(filter_, _proj=None):
        if filter_.get("template_id") == "cold-to-demo":
            return {"id": "j-1", "status": "draft",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "metrics": {"entered": 5}}
        return None
    fdb.marketing_journeys.find_one = AsyncMock(side_effect=_find_one)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.list_journey_templates(
                {"id": "u", "is_master_admin": True},
            )
    out = _run(go())
    assert len(out["templates"]) == 4
    by_id = {t["id"]: t for t in out["templates"]}
    assert by_id["cold-to-demo"]["existing_journey"] is not None
    assert by_id["cold-to-demo"]["existing_journey"]["metrics"]["entered"] == 5
    assert by_id["demo-booked"]["existing_journey"] is None
    # Every template surfaces the node_count for the UI badge.
    for t in out["templates"]:
        assert t["node_count"] >= 2


# ── Launch (happy path) ───────────────────────────────────────────

def test_launch_creates_journey_with_send_email_nodes():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()

    async def go():
        with patch.object(m, "db", fdb):
            return await m.launch_journey_template(
                "cold-to-demo", {"id": "admin-1", "is_master_admin": True},
            )
    out = _run(go())
    assert out["created"] is True
    j = out["journey"]
    assert j["template_id"] == "cold-to-demo"
    assert j["organization_id"] == "org-master-1"
    assert j["status"] == "draft"
    assert j["scope"] == "gymaxis_self_promo"
    assert j["created_by"] == "admin-1"
    assert len(j["nodes"]) >= 5
    assert all(n["type"] == "send_email" for n in j["nodes"])
    # Mongo write happened with the same doc.
    fdb.marketing_journeys.insert_one.assert_awaited_once()


def test_launch_unknown_template_returns_404():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.launch_journey_template(
                    "no-such-template",
                    {"id": "u", "is_master_admin": True},
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_launch_is_idempotent():
    """Re-running the launch endpoint MUST NOT spawn duplicate
    journeys for the same (org, template). It returns the existing
    row with ``created=False``."""
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()
    existing = {
        "id": "j-existing", "organization_id": "org-master-1",
        "template_id": "demo-booked", "status": "draft",
        "nodes": [{"type": "send_email", "subject": "x", "body": "y"}],
    }
    fdb.marketing_journeys.find_one = AsyncMock(return_value=existing)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.launch_journey_template(
                "demo-booked", {"id": "admin-1", "is_master_admin": True},
            )
    out = _run(go())
    assert out["created"] is False
    assert out["journey"]["id"] == "j-existing"
    fdb.marketing_journeys.insert_one.assert_not_called()


# ── Recreate ──────────────────────────────────────────────────────

def test_recreate_archives_previous_and_inserts_fresh():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()

    async def go():
        with patch.object(m, "db", fdb):
            return await m.recreate_journey_template(
                "lost-revival", {"id": "admin-1", "is_master_admin": True},
            )
    out = _run(go())
    assert out["created"] is True
    assert out["journey"]["template_id"] == "lost-revival"

    # Archive write fired with status -> archived.
    fdb.marketing_journeys.update_many.assert_awaited_once()
    call = fdb.marketing_journeys.update_many.await_args
    filter_arg, update_arg = call.args[0], call.args[1]
    assert filter_arg["template_id"] == "lost-revival"
    assert update_arg["$set"]["status"] == "archived"
    fdb.marketing_journeys.insert_one.assert_awaited_once()


def test_recreate_unknown_template_returns_404():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()
    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.recreate_journey_template(
                    "ghost", {"id": "u", "is_master_admin": True},
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


# ── Org resolution ───────────────────────────────────────────────

def test_master_admin_org_id_prefers_user_organization_id():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()
    async def go():
        with patch.object(m, "db", fdb):
            return await m._master_admin_org_id()
    assert _run(go()) == "org-master-1"


def test_master_admin_org_id_falls_back_to_organisation_row():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()
    fdb.users.find_one = AsyncMock(return_value=None)
    fdb.organizations.find_one = AsyncMock(return_value={"id": "org-fallback"})

    async def go():
        with patch.object(m, "db", fdb):
            return await m._master_admin_org_id()
    assert _run(go()) == "org-fallback"


def test_master_admin_org_id_500_when_nothing_resolvable():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    fdb = _fake_db_for_launch()
    fdb.users.find_one = AsyncMock(return_value=None)
    fdb.organizations.find_one = AsyncMock(return_value=None)
    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m._master_admin_org_id()
                return False
            except HTTPException as exc:
                return exc.status_code == 500
    assert _run(go())
