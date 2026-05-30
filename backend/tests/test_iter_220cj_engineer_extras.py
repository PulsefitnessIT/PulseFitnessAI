"""Iter 220cj — 5-feature batch tests.

Covers the backend pieces of the user-reported items shipped in this
iter (the frontend wiring is pinned in
``test_iter_220cj_engineer_extras_frontend.py``):

  * ``GET  /api/svc/engineer/queue/{case_id}/preview`` — only returns
    *unassigned* cases for the engineer's org, with site equipment +
    potential value + photo/event counters.
  * ``GET  /api/svc/engineer/jobs/{case_id}/site-equipment`` — equipment
    catalogue for the case's site annotated with
    ``already_on_job``.
  * ``POST /api/svc/engineer/jobs/{case_id}/machines/bulk-from-site``
    — bulk-attach by equipment_ids OR ``select_all=true``; idempotent
    against ``svc_work_visit_machines``.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(org="org-1", uid="eng-1"):
    return {"id": uid, "organization_id": org}


def _chain(default):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=default)
    return cur


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "equipment", "sites", "svc_cases", "svc_work_visit_machines",
        "svc_engineer_photos", "svc_case_events", "engineer_quotes",
    ):
        for op in ("insert_one", "insert_many", "update_one", "delete_one"):
            setattr(getattr(fdb, coll), op, AsyncMock())
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
        getattr(fdb, coll).count_documents = AsyncMock(return_value=0)
        getattr(fdb, coll).find = MagicMock(return_value=_chain([]))
        getattr(fdb, coll).create_index = AsyncMock()
    return fdb


# ── 1 · Queue preview endpoint ────────────────────────────────────────


def test_preview_404s_when_case_not_unassigned():
    """Already-claimed or out-of-org cases must 404 — engineers can't
    use this endpoint to snoop on each other's work."""
    from fastapi import HTTPException
    from routes.svc.engineer_queue import preview_unassigned_case
    fdb = _fake_db()
    # svc_cases.find_one returns None (no match) — simulates either a
    # case not in the org, or one already assigned to someone.

    async def go():
        with patch("routes.svc.engineer_queue.db", fdb):
            try:
                await preview_unassigned_case("case-X", _user())
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_preview_returns_site_equipment_and_counters():
    from routes.svc.engineer_queue import preview_unassigned_case
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "site_id": "site-A", "title": "Treadmill down",
        "site_name": "Acme Leeds", "site_address": "12 Industrial Way",
        "site_postcode": "LS10 1AB", "description": "Belt slipping",
        "priority": "P2", "reference": "GA-100",
    })
    fdb.equipment.find = MagicMock(return_value=_chain([
        {"id": "e-1", "name": "Treadmill 1", "equipment_type": "Treadmill"},
        {"id": "e-2", "name": "Treadmill 2", "equipment_type": "Treadmill"},
    ]))
    fdb.engineer_quotes.find_one = AsyncMock(return_value={
        "id": "q-1", "status": "sent", "total": 425.5, "currency": "GBP",
    })
    fdb.svc_engineer_photos.count_documents = AsyncMock(return_value=3)
    fdb.svc_case_events.count_documents = AsyncMock(return_value=7)

    async def go():
        with patch("routes.svc.engineer_queue.db", fdb):
            return await preview_unassigned_case("case-1", _user())
    out = _run(go())
    assert out["case"]["id"] == "case-1"
    assert out["site_equipment_count"] == 2
    assert out["photos_count"] == 3
    assert out["events_count"] == 7
    assert out["potential_value"]["total"] == 425.5
    assert out["potential_value"]["currency"] == "GBP"
    assert out["potential_value"]["quote_status"] == "sent"


def test_preview_handles_case_with_no_site():
    """Case with neither ``site_id`` nor ``asset_id`` returns an empty
    equipment list (not a 500)."""
    from routes.svc.engineer_queue import preview_unassigned_case
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-2", "title": "Phone-in", "priority": "P3",
    })

    async def go():
        with patch("routes.svc.engineer_queue.db", fdb):
            return await preview_unassigned_case("case-2", _user())
    out = _run(go())
    assert out["site_equipment"] == []
    assert out["site_equipment_count"] == 0
    assert out["potential_value"] is None


def test_preview_swallows_quote_errors():
    """Quote lookup is analytics-only — a DB error must not break the
    primary preview response (used to be a 500)."""
    from routes.svc.engineer_queue import preview_unassigned_case
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "c-3"})
    fdb.engineer_quotes.find_one = AsyncMock(side_effect=Exception("boom"))

    async def go():
        with patch("routes.svc.engineer_queue.db", fdb):
            return await preview_unassigned_case("c-3", _user())
    out = _run(go())
    assert out["potential_value"] is None


# ── 2 · Site equipment list ───────────────────────────────────────────


def test_site_equipment_404s_for_unknown_case():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import list_site_equipment_for_case
    fdb = _fake_db()

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await list_site_equipment_for_case("case-X", _user())
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_site_equipment_returns_empty_when_case_has_no_site():
    from routes.svc.engineer_equipment import list_site_equipment_for_case
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "c-no-site"})

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await list_site_equipment_for_case("c-no-site", _user())
    out = _run(go())
    assert out["site_equipment"] == []
    assert out["site_id"] is None


def test_site_equipment_annotates_already_on_job():
    """Equipment whose id appears in svc_work_visit_machines for this
    case must be flagged so the UI can ghost it in the picker."""
    from routes.svc.engineer_equipment import list_site_equipment_for_case
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "c-1", "site_id": "site-A",
    })
    fdb.equipment.find = MagicMock(return_value=_chain([
        {"id": "e-1", "name": "Treadmill 1"},
        {"id": "e-2", "name": "Treadmill 2"},
        {"id": "e-3", "name": "Bike 1"},
    ]))
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([
        {"asset_id": "e-2"}, {"asset_id": "e-3"},
    ]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await list_site_equipment_for_case("c-1", _user())
    out = _run(go())
    by_id = {r["id"]: r for r in out["site_equipment"]}
    assert by_id["e-1"]["already_on_job"] is False
    assert by_id["e-2"]["already_on_job"] is True
    assert by_id["e-3"]["already_on_job"] is True
    assert set(out["already_on_job"]) == {"e-2", "e-3"}


# ── 3 · Bulk-attach endpoint ──────────────────────────────────────────


def test_bulk_attach_validates_body():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import (
        bulk_attach_site_equipment, _BulkFromSiteBody,
    )
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "c-1", "site_id": "site-A",
    })
    payload = _BulkFromSiteBody(equipment_ids=[], select_all=False)

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await bulk_attach_site_equipment("c-1", payload, _user())
                return False
            except HTTPException as exc:
                return exc.status_code == 400
    assert _run(go())


def test_bulk_attach_select_all_requires_site_id():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import (
        bulk_attach_site_equipment, _BulkFromSiteBody,
    )
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "c-1"})  # no site
    payload = _BulkFromSiteBody(equipment_ids=[], select_all=True)

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await bulk_attach_site_equipment("c-1", payload, _user())
                return False
            except HTTPException as exc:
                return exc.status_code == 400 and "no site_id" in exc.detail
    assert _run(go())


def test_bulk_attach_inserts_rows_and_skips_duplicates():
    from routes.svc.engineer_equipment import (
        bulk_attach_site_equipment, _BulkFromSiteBody,
    )
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "c-1", "site_id": "site-A",
    })
    # 3 candidates; e-2 is already on the job → should be skipped.
    fdb.equipment.find = MagicMock(return_value=_chain([
        {"id": "e-1", "name": "Treadmill 1", "manufacturer": "Life", "model": "DX"},
        {"id": "e-2", "name": "Treadmill 2"},
        {"id": "e-3", "name": "Bike 1", "manufacturer": "Wattbike", "model": "Atom"},
    ]))
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([
        {"asset_id": "e-2"},
    ]))
    fdb.svc_work_visit_machines.count_documents = AsyncMock(return_value=4)

    payload = _BulkFromSiteBody(
        equipment_ids=["e-1", "e-2", "e-3"], select_all=False,
    )

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await bulk_attach_site_equipment("c-1", payload, _user())
    out = _run(go())
    assert out["inserted"] == 2
    assert out["skipped"] == 1
    fdb.svc_work_visit_machines.insert_many.assert_awaited_once()
    inserted_rows = fdb.svc_work_visit_machines.insert_many.await_args.args[0]
    assert len(inserted_rows) == 2
    inserted_ids = {r["asset_id"] for r in inserted_rows}
    assert inserted_ids == {"e-1", "e-3"}
    # order_index respects the existing rows count.
    assert {r["order_index"] for r in inserted_rows} == {4, 5}
    # All rows tagged so audit knows they came from the picker.
    for r in inserted_rows:
        assert r["source"] == "site_equipment_bulk"
        assert r["organization_id"] == "org-1"
        assert r["case_id"] == "c-1"


def test_bulk_attach_select_all_pulls_full_catalogue():
    from routes.svc.engineer_equipment import (
        bulk_attach_site_equipment, _BulkFromSiteBody,
    )
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "c-1", "site_id": "site-A",
    })
    fdb.equipment.find = MagicMock(return_value=_chain([
        {"id": "e-1", "name": "A"},
        {"id": "e-2", "name": "B"},
    ]))

    payload = _BulkFromSiteBody(equipment_ids=[], select_all=True)

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await bulk_attach_site_equipment("c-1", payload, _user())
    out = _run(go())
    # With select_all the filter must be {organization, site_id: …}.
    flt = fdb.equipment.find.call_args.args[0]
    assert flt.get("site_id") == "site-A"
    assert "id" not in flt
    assert out["inserted"] == 2


def test_bulk_attach_returns_zero_for_no_candidates():
    from routes.svc.engineer_equipment import (
        bulk_attach_site_equipment, _BulkFromSiteBody,
    )
    fdb = _fake_db()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "c-1", "site_id": "site-A",
    })
    fdb.equipment.find = MagicMock(return_value=_chain([]))
    payload = _BulkFromSiteBody(equipment_ids=["e-X"], select_all=False)

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await bulk_attach_site_equipment("c-1", payload, _user())
    out = _run(go())
    assert out == {"inserted": 0, "skipped": 0, "machine_ids": []}
    fdb.svc_work_visit_machines.insert_many.assert_not_awaited()


# ── 4 · Module exports ────────────────────────────────────────────────


def test_module_exports_iter_220cj_helpers():
    from routes.svc import engineer_equipment as m
    from routes.svc import engineer_queue as q
    assert hasattr(m, "list_site_equipment_for_case")
    assert hasattr(m, "bulk_attach_site_equipment")
    assert hasattr(m, "_BulkFromSiteBody")
    assert hasattr(q, "preview_unassigned_case")


def test_routes_registered_on_router():
    from routes.svc.engineer_equipment import router as eq_router
    from routes.svc.engineer_queue import router as q_router
    eq_paths = {r.path for r in eq_router.routes}
    q_paths = {r.path for r in q_router.routes}
    assert "/svc/engineer/jobs/{case_id}/site-equipment" in eq_paths
    assert "/svc/engineer/jobs/{case_id}/machines/bulk-from-site" in eq_paths
    assert "/svc/engineer/queue/{case_id}/preview" in q_paths
