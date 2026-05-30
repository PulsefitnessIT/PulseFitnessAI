"""Iter 220co — Parts cost per machine rollup.

Pins the new ``parts_cost`` block added to
``GET /api/svc/engineer/equipment/{id}/service-history``:

  * ``totals.parts_cost.approved_gbp`` — sum of qty × list_price for
    requests in ``approved``/``fulfilled`` that match any of this
    asset's machine_row ids.
  * ``totals.parts_cost.pending_gbp`` — same, for pending requests.
  * Each ``visits[i].parts_cost`` carries the same per-case breakdown.
"""
from __future__ import annotations

import asyncio
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


def _fake_db(*, equipment, machines, cases, photos_agg, parts_agg):
    fdb = MagicMock()
    for coll in (
        "equipment", "svc_work_visit_machines", "svc_cases",
        "svc_engineer_photos", "svc_parts_requests",
    ):
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
        getattr(fdb, coll).find = MagicMock(return_value=_chain([]))
        getattr(fdb, coll).aggregate = MagicMock(return_value=_async_iter([]))

    fdb.equipment.find_one = AsyncMock(return_value=equipment)
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain(machines))
    fdb.svc_cases.find = MagicMock(return_value=_chain(cases))
    fdb.svc_engineer_photos.aggregate = MagicMock(
        return_value=_async_iter(photos_agg),
    )
    fdb.svc_parts_requests.aggregate = MagicMock(
        return_value=_async_iter(parts_agg),
    )
    return fdb


def test_parts_cost_rollup_splits_approved_vs_pending():
    """One approved + one pending parts request, both tagged to a
    machine row that belongs to this equipment. The endpoint must:

      * sum approved/pending separately (qty × list_price_gbp);
      * surface the per-case bucket on each visit;
      * round £ values to 2dp.
    """
    equipment = {
        "id": "eq-1", "organization_id": "org-1",
        "name": "Treadmill A",
    }
    machines = [
        {
            "id": "mr-1", "case_id": "case-1", "asset_id": "eq-1",
            "asset_name": "Treadmill A", "serviced": True, "cleaned": False,
            "notes": None, "created_at": "2026-05-30T09:00:00Z",
            "updated_at": "2026-05-30T10:00:00Z", "source": "manual",
        },
        {
            "id": "mr-2", "case_id": "case-2", "asset_id": "eq-1",
            "asset_name": "Treadmill A", "serviced": False, "cleaned": True,
            "notes": "second visit", "created_at": "2026-04-15T09:00:00Z",
            "updated_at": "2026-04-15T10:00:00Z", "source": "manual",
        },
    ]
    cases = [
        {"id": "case-1", "reference": "GA-001", "status": "closed",
         "completed_at": "2026-05-30T11:00:00Z"},
        {"id": "case-2", "reference": "GA-002", "status": "in_progress",
         "completed_at": None, "updated_at": "2026-04-15T12:00:00Z"},
    ]
    # 2 approved on case-1 (£40 × 1 + £10 × 1 → £50)
    # 1 pending  on case-2 (£15 × 2 → £30)
    parts_agg = [
        {"_id": {"case_id": "case-1", "status": "approved"},
         "qty": 1, "spend": 40.0, "n": 1},
        {"_id": {"case_id": "case-1", "status": "fulfilled"},
         "qty": 1, "spend": 10.0, "n": 1},
        {"_id": {"case_id": "case-2", "status": "pending"},
         "qty": 2, "spend": 30.0, "n": 1},
    ]
    fdb = _fake_db(
        equipment=equipment, machines=machines, cases=cases,
        photos_agg=[], parts_agg=parts_agg,
    )

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import (
                get_equipment_service_history,
            )
            out = await get_equipment_service_history(
                "eq-1", user=_user(), limit=50,
            )
        pc = out["totals"]["parts_cost"]
        assert pc["approved_gbp"] == 50.0
        assert pc["pending_gbp"] == 30.0
        assert pc["total_gbp"] == 80.0
        assert pc["approved_qty"] == 2
        assert pc["pending_qty"] == 2
        assert pc["request_count"] == 3
        # Per-visit buckets — newest first (case-1 completed 2026-05-30).
        v1 = out["visits"][0]
        assert v1["case_id"] == "case-1"
        assert v1["parts_cost"]["approved_gbp"] == 50.0
        assert v1["parts_cost"]["pending_gbp"] == 0.0
        v2 = out["visits"][1]
        assert v2["case_id"] == "case-2"
        assert v2["parts_cost"]["pending_gbp"] == 30.0
        assert v2["parts_cost"]["approved_gbp"] == 0.0
    _run(run())


def test_parts_cost_zero_when_no_machine_rows():
    """Empty machine-row list → totals.parts_cost is present and zero;
    the rollup must not crash on missing data."""
    fdb = _fake_db(
        equipment={"id": "eq-9", "organization_id": "org-1", "name": "Bike"},
        machines=[], cases=[], photos_agg=[], parts_agg=[],
    )

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import (
                get_equipment_service_history,
            )
            out = await get_equipment_service_history(
                "eq-9", user=_user(), limit=50,
            )
        pc = out["totals"]["parts_cost"]
        assert pc["approved_gbp"] == 0.0
        assert pc["pending_gbp"] == 0.0
        assert pc["total_gbp"] == 0.0
        assert pc["request_count"] == 0
        assert out["visits"] == []
    _run(run())


def test_parts_cost_ignores_cancelled_or_rejected():
    """Aggregation only matches pending/approved/fulfilled — cancelled
    or rejected requests must NOT inflate the spend. We simulate this
    by sending an agg result with only the three valid statuses and
    asserting the Mongo ``$match`` stage filters by them."""
    machines = [
        {"id": "mr-1", "case_id": "case-1", "asset_id": "eq-1",
         "asset_name": "Treadmill A", "serviced": False, "cleaned": False,
         "notes": None, "created_at": "2026-05-30T09:00:00Z",
         "updated_at": "2026-05-30T10:00:00Z", "source": "manual"},
    ]
    fdb = _fake_db(
        equipment={"id": "eq-1", "organization_id": "org-1", "name": "T"},
        machines=machines, cases=[], photos_agg=[], parts_agg=[],
    )

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import (
                get_equipment_service_history,
            )
            out = await get_equipment_service_history(
                "eq-1", user=_user(), limit=50,
            )
        # Inspect the pipeline that was sent to svc_parts_requests.aggregate
        call = fdb.svc_parts_requests.aggregate.call_args
        pipeline = call.args[0]
        match_stage = pipeline[0]["$match"]
        assert match_stage["status"] == {
            "$in": ["pending", "approved", "fulfilled"],
        }
        assert match_stage["machine_id"] == {"$in": ["mr-1"]}
        # And the totals block exists with zeros.
        assert out["totals"]["parts_cost"]["approved_gbp"] == 0.0
    _run(run())
