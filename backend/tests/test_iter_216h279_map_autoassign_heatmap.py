"""Iter 216h279 — Map auto-assign + Coverage Heatmap + Tender panel.

Follow-up to 216h278's Interactive UK Territory Map. Adds three P2
enhancements that complete the feature:

1. `POST /map-auto-assign` — one-click apply: pushes every region's
   coverage onto unassigned companies, opportunities and tenders.
2. `GET  /coverage-heatmap` — flat `{counties:{}, postcode_areas:{}}`
   payload of MAX(open tender £, pipeline £) per region.
3. Frontend Tender Coverage panel that reads `/coverage-report`
   (already shipped in h278) — covered by the React JSX rendering,
   not unit-tested here.

These tests pin the backend contracts so a future refactor can't
silently break the map UI.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.crm_territories import coverage_heatmap, map_auto_assign


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _async_iter(items):
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
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=_Cur(items))
    return cur


def _admin():
    return {"id": "u-admin", "organization_id": "org-1", "role": "admin"}


# ── Heatmap ────────────────────────────────────────────────────────


def test_coverage_heatmap_returns_max_of_tender_or_pipeline():
    fake_db = MagicMock()
    fake_db.crm_territories.find = MagicMock(return_value=_make_cursor([
        {"id": "t-london", "region_type": "county", "region_code": "Greater London"},
        {"id": "t-sw",     "region_type": "postcode_area", "region_code": "SW"},
    ]))
    # t-london: tenders £10k, opps £100k → max = 100k
    # t-sw:     tenders £50k, opps £20k  → max = 50k
    calls = {"tenders": 0, "opps": 0}

    def find_factory(coll_name):
        def find(query, _proj):
            calls[coll_name] += 1
            tid = query.get("territory_id")
            if coll_name == "tenders":
                v = 10_000 if tid == "t-london" else 50_000
            else:
                v = 100_000 if tid == "t-london" else 20_000
            return _make_cursor([{"value": v}])
        return find

    fake_db.crm_v2_tenders.find = MagicMock(side_effect=find_factory("tenders"))
    fake_db.crm2_opportunities.find = MagicMock(side_effect=find_factory("opps"))

    with patch("routes.crm_territories.db", fake_db):
        out = _run(coverage_heatmap(user=_admin()))
    assert out["counties"]["Greater London"] == 100_000.0
    assert out["postcode_areas"]["SW"] == 50_000.0
    # Confirmed both streams were sampled.
    assert calls["tenders"] == 2
    assert calls["opps"] == 2


def test_coverage_heatmap_empty_when_no_territories():
    fake_db = MagicMock()
    fake_db.crm_territories.find = MagicMock(return_value=_make_cursor([]))
    with patch("routes.crm_territories.db", fake_db):
        out = _run(coverage_heatmap(user=_admin()))
    assert out == {"counties": {}, "postcode_areas": {}}


# ── Auto-assign ────────────────────────────────────────────────────


def test_map_auto_assign_writes_to_all_three_entities():
    fake_db = MagicMock()
    # Each entity has 1 unassigned record.
    fake_db.crm2_companies.find = MagicMock(return_value=_async_iter([
        {"id": "c1", "postcode": "SW1A 1AA"},
    ]))
    fake_db.crm2_opportunities.find = MagicMock(return_value=_async_iter([
        {"id": "o1", "postcode": "SW1A 1AA"},
    ]))
    fake_db.crm_v2_tenders.find = MagicMock(return_value=_async_iter([
        {"id": "t1", "postcode": "SW1A 1AA"},
    ]))
    fake_db.crm2_companies.update_one = AsyncMock()
    fake_db.crm2_opportunities.update_one = AsyncMock()
    fake_db.crm_v2_tenders.update_one = AsyncMock()

    async def fake_assign_from_territory(rec, _org):
        return {"territory_id": "t-sw", "owner_id": "u-rep", "owner_name": "Jane"}

    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.assign_from_territory", side_effect=fake_assign_from_territory), \
         patch("routes.crm_territories.log_audit", AsyncMock()):
        out = _run(map_auto_assign(data={}, user=_admin()))

    assert out["dry_run"] is False
    assert out["totals"] == {"company": 1, "opportunity": 1, "tender": 1}
    assert out["total"] == 3
    # Verify the territory_id + owner were applied to each entity.
    for upd in (
        fake_db.crm2_companies.update_one,
        fake_db.crm2_opportunities.update_one,
        fake_db.crm_v2_tenders.update_one,
    ):
        patch_doc = upd.call_args[0][1]["$set"]
        assert patch_doc["territory_id"] == "t-sw"
        assert patch_doc["owner_id"] == "u-rep"


def test_map_auto_assign_dry_run_does_not_write():
    fake_db = MagicMock()
    fake_db.crm2_companies.find = MagicMock(return_value=_async_iter([{"id": "c1"}]))
    fake_db.crm2_opportunities.find = MagicMock(return_value=_async_iter([]))
    fake_db.crm_v2_tenders.find = MagicMock(return_value=_async_iter([]))
    fake_db.crm2_companies.update_one = AsyncMock()

    async def fake_assign(_rec, _org):
        return {"territory_id": "t-sw"}

    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.assign_from_territory", side_effect=fake_assign), \
         patch("routes.crm_territories.log_audit", AsyncMock()) as audit:
        out = _run(map_auto_assign(data={"dry_run": True}, user=_admin()))
    assert out["dry_run"] is True
    assert out["totals"]["company"] == 1
    # No writes, no audit.
    fake_db.crm2_companies.update_one.assert_not_called()
    audit.assert_not_called()


def test_map_auto_assign_skips_records_without_matching_territory():
    fake_db = MagicMock()
    fake_db.crm2_companies.find = MagicMock(return_value=_async_iter([{"id": "c1"}]))
    fake_db.crm2_opportunities.find = MagicMock(return_value=_async_iter([]))
    fake_db.crm_v2_tenders.find = MagicMock(return_value=_async_iter([]))
    fake_db.crm2_companies.update_one = AsyncMock()

    async def fake_assign(_rec, _org):
        return {}  # no territory match

    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.assign_from_territory", side_effect=fake_assign), \
         patch("routes.crm_territories.log_audit", AsyncMock()):
        out = _run(map_auto_assign(data={}, user=_admin()))
    assert out["total"] == 0
    fake_db.crm2_companies.update_one.assert_not_called()


def test_map_auto_assign_requires_admin_role():
    rep = {"id": "u-rep", "organization_id": "org-1", "role": "rep"}
    with pytest.raises(Exception) as exc:
        _run(map_auto_assign(data={}, user=rep))
    assert "Insufficient" in str(exc.value.detail) or "permission" in str(exc.value).lower()
