"""Iter 220cm — Per-equipment Service History rollup.

Pins the new ``GET /api/svc/engineer/equipment/{id}/service-history``
endpoint and the expandable timeline on ``EngineerEquipment.js``.

Backend assertions:
  * 404 for cross-tenant / unknown equipment id.
  * Empty machine-row list → returns empty visits + zero totals
    (no crash, no 500).
  * Joins ``svc_work_visit_machines`` to ``svc_cases`` and folds in
    a per-case photo count via aggregate.
  * Totals: ``visit_count``, ``serviced_count``, ``cleaned_count``,
    ``last_visit`` (max of completed_at/updated_at/created_at).
  * Visits sorted newest-first by ``visit_date``.

Frontend assertions:
  * The list row toggles open into an inline timeline.
  * Calls the new endpoint with the equipment id.
  * Renders the totals strip + per-visit cards with the canonical
    test IDs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(org="org-1", uid="u-1"):
    return {"id": uid, "organization_id": org}


def _chain(default):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.to_list = AsyncMock(return_value=default)
    return cur


def _async_iter(items):
    """Build an async iterator over ``items`` for Motor aggregate stubs."""

    class _It:
        def __init__(self, xs):
            self.xs = list(xs)
            self.i = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.i >= len(self.xs):
                raise StopAsyncIteration
            v = self.xs[self.i]
            self.i += 1
            return v

    return _It(items)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "equipment", "svc_work_visit_machines", "svc_cases",
        "svc_engineer_photos",
    ):
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
        getattr(fdb, coll).find = MagicMock(return_value=_chain([]))
        getattr(fdb, coll).aggregate = MagicMock(return_value=_async_iter([]))
    return fdb


# ── 1 · 404 + auth guard ──────────────────────────────────────────────


def test_service_history_404s_for_unknown_or_cross_tenant_equipment():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import get_equipment_service_history

    async def go():
        with patch("routes.svc.engineer_equipment.db", _fake_db()):
            try:
                await get_equipment_service_history(
                    "eq-X", user=_user(), limit=50,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_service_history_403s_without_org_context():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import get_equipment_service_history

    async def go():
        try:
            await get_equipment_service_history(
                "eq-1", user={"id": "u"}, limit=50,
            )
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


# ── 2 · Empty timeline ────────────────────────────────────────────────


def test_service_history_returns_empty_for_brand_new_asset():
    from routes.svc.engineer_equipment import get_equipment_service_history
    fdb = _fake_db()
    fdb.equipment.find_one = AsyncMock(return_value={
        "id": "eq-1", "name": "Treadmill 1",
    })
    # No machine rows yet.
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await get_equipment_service_history(
                "eq-1", user=_user(), limit=50,
            )
    out = _run(go())
    assert out["visits"] == []
    assert out["totals"]["visit_count"] == 0
    assert out["totals"]["last_visit"] is None
    # Equipment passed through.
    assert out["equipment"]["id"] == "eq-1"


# ── 3 · Joins + totals + sort ─────────────────────────────────────────


def test_service_history_joins_cases_and_returns_sorted_timeline():
    from routes.svc.engineer_equipment import get_equipment_service_history
    fdb = _fake_db()
    fdb.equipment.find_one = AsyncMock(return_value={
        "id": "eq-1", "name": "Treadmill 1",
    })
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([
        {
            "id": "m-1", "case_id": "case-A", "serviced": True,
            "cleaned": False, "notes": "Belt aligned",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T01:00:00Z",
        },
        {
            "id": "m-2", "case_id": "case-B", "serviced": True,
            "cleaned": True, "notes": "Full PPM",
            "created_at": "2025-12-15T00:00:00Z",
        },
        {
            "id": "m-3", "case_id": "case-C", "serviced": False,
            "cleaned": True, "notes": None,
            "created_at": "2025-11-01T00:00:00Z",
        },
    ]))
    fdb.svc_cases.find = MagicMock(return_value=_chain([
        {"id": "case-A", "reference": "GA-100", "title": "Treadmill check",
         "status": "completed", "assigned_engineer_name": "Sam",
         "completed_at": "2026-01-02T10:00:00Z"},
        {"id": "case-B", "reference": "GA-090", "title": "Quarterly PPM",
         "status": "completed", "assigned_engineer_name": "Sam",
         "completed_at": "2025-12-16T10:00:00Z"},
        {"id": "case-C", "reference": "GA-080", "title": "Cleaning",
         "status": "completed", "assigned_engineer_name": "Sam",
         "completed_at": "2025-11-02T10:00:00Z"},
    ]))
    fdb.svc_engineer_photos.aggregate = MagicMock(return_value=_async_iter([
        {"_id": "case-A", "n": 4},
        {"_id": "case-B", "n": 2},
    ]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await get_equipment_service_history(
                "eq-1", user=_user(), limit=50,
            )
    out = _run(go())
    assert out["totals"]["visit_count"] == 3
    assert out["totals"]["serviced_count"] == 2
    assert out["totals"]["cleaned_count"] == 2
    assert out["totals"]["last_visit"] == "2026-01-02T10:00:00Z"
    # Newest-first.
    visit_dates = [v["visit_date"] for v in out["visits"]]
    assert visit_dates == sorted(visit_dates, reverse=True)
    # Case context joined.
    first = out["visits"][0]
    assert first["case_reference"] == "GA-100"
    assert first["case_title"] == "Treadmill check"
    assert first["engineer_name"] == "Sam"
    # Photo count attached.
    assert first["photos_count"] == 4
    # Visit without a photos doc → 0.
    last = out["visits"][2]
    assert last["case_id"] == "case-C"
    assert last["photos_count"] == 0


def test_service_history_swallows_photo_aggregate_errors():
    """Photo counting is analytics-only — must not break the rollup."""
    from routes.svc.engineer_equipment import get_equipment_service_history
    fdb = _fake_db()
    fdb.equipment.find_one = AsyncMock(return_value={"id": "eq-1", "name": "X"})
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([
        {"id": "m-1", "case_id": "case-A", "created_at": "2026-01-01T00:00:00Z"},
    ]))
    fdb.svc_cases.find = MagicMock(return_value=_chain([
        {"id": "case-A", "reference": "GA-100"},
    ]))

    def _boom(*_a, **_kw):
        raise RuntimeError("aggregate failed")

    fdb.svc_engineer_photos.aggregate = MagicMock(side_effect=_boom)

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await get_equipment_service_history(
                "eq-1", user=_user(), limit=50,
            )
    out = _run(go())
    # Rollup still returned cleanly with photos_count defaulted to 0.
    assert len(out["visits"]) == 1
    assert out["visits"][0]["photos_count"] == 0


def test_service_history_respects_limit():
    from routes.svc.engineer_equipment import get_equipment_service_history
    fdb = _fake_db()
    fdb.equipment.find_one = AsyncMock(return_value={"id": "eq-1", "name": "X"})
    rows = [
        {"id": f"m-{i}", "case_id": f"c-{i}",
         "created_at": f"2026-01-{(i + 1):02d}T00:00:00Z"}
        for i in range(10)
    ]
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain(rows))
    fdb.svc_cases.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await get_equipment_service_history(
                "eq-1", user=_user(), limit=5,
            )
    out = _run(go())
    assert len(out["visits"]) == 5
    # Totals reflect ALL rows, not just the clipped page.
    assert out["totals"]["visit_count"] == 10


# ── 4 · Router registration ───────────────────────────────────────────


def test_service_history_route_registered():
    from routes.svc.engineer_equipment import router
    paths = {r.path for r in router.routes}
    assert "/svc/engineer/equipment/{equipment_id}/service-history" in paths


# ── 5 · Frontend wiring pins ──────────────────────────────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_equipment_row_is_expandable_with_service_history():
    src = _read("pages/ServiceOps/Engineer/EngineerEquipment.js")
    # Toggle button + history pane test IDs.
    assert "equipment-row-toggle-" in src
    assert "equipment-history-" in src
    # Fetches the new endpoint.
    assert "/service-history" in src
    # Renders the ServiceHistory component (totals + timeline).
    assert "function ServiceHistory" in src
    assert "equipment-history-timeline" in src
    assert "equipment-history-visits" in src
    assert "equipment-history-serviced" in src
    assert "equipment-history-last" in src
    # Empty-state copy testid.
    assert "equipment-history-empty-" in src


def test_history_panel_uses_lazy_loading():
    """The panel must be lazy-loaded — calling it on mount for every
    equipment row in a 200-row org would hammer the API."""
    src = _read("pages/ServiceOps/Engineer/EngineerEquipment.js")
    # The fetch lives behind the toggle handler, not in a useEffect
    # that fires on initial render.
    assert "next && history === null" in src
