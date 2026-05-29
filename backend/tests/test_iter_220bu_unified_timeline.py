"""Iter 220bu — Cross-module unified timeline.

Pins the new `GET /crm/v2/timeline` endpoint that merges activities,
quotes, cases, and synthesised tender events into a single
chronological feed scoped to one of company / opportunity / tender.

Test slices:

  1. Scope validation — exactly one of company_id / opportunity_id /
     tender_id must be passed; cross-tenant scopes 404.
  2. Merging — events from all 4 sources appear in the response with
     a stable normalised shape (`id`, `type`, `occurred_at`, ...).
  3. Ordering — newest first, deterministic.
  4. Org isolation — sibling-org data never bleeds in.
  5. Tender scope — synthesises both ``tender:created`` and (when
     updated_at differs) ``tender:status_changed`` events.
  6. Pagination — limit + skip behave correctly.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.skip = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _fake_db():
    fdb = MagicMock()
    for coll in ("crm2_companies", "crm2_opportunities", "crm2_tenders",
                 "crm2_activities", "crm2_cases", "crm_quotes"):
        c = getattr(fdb, coll)
        c.find_one = AsyncMock(return_value=None)
        c.find = MagicMock(return_value=_cursor([]))
    return fdb


_USER = {"id": "u-1", "organization_id": "org-A"}


def _t(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


# ══════════════════ 1 · Scope validation ════════════════════════════


def test_timeline_requires_exactly_one_scope():
    from routes import crm_v2 as m
    fdb = _fake_db()

    async def go(company_id="", opportunity_id="", tender_id=""):
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(
                company_id=company_id, opportunity_id=opportunity_id,
                tender_id=tender_id, user=_USER,
            )

    # Zero scopes → 400.
    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 400
    # Two scopes → 400.
    with pytest.raises(HTTPException) as exc:
        _run(go(company_id="c-1", opportunity_id="o-1"))
    assert exc.value.status_code == 400


def test_timeline_404s_when_scope_not_in_org():
    from routes import crm_v2 as m
    fdb = _fake_db()
    fdb.crm2_companies.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(
                company_id="from-other-org", user=_USER,
            )
    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 404


def test_timeline_400s_when_limit_out_of_range():
    from routes import crm_v2 as m
    fdb = _fake_db()
    async def go(limit):
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(
                company_id="c-1", limit=limit, user=_USER,
            )
    for bad in (0, -5, 501, 10000):
        with pytest.raises(HTTPException) as exc:
            _run(go(bad))
        assert exc.value.status_code == 400


# ══════════════════ 2 · Merging across all 4 sources ════════════════


def test_company_scope_merges_activities_quotes_cases_tenders():
    from routes import crm_v2 as m
    fdb = _fake_db()
    fdb.crm2_companies.find_one = AsyncMock(return_value={
        "id": "co-1", "name": "Acme Gyms Ltd",
    })
    fdb.crm2_activities.find = MagicMock(return_value=_cursor([
        {"id": "a-1", "type": "call", "subject": "Discovery call",
         "body": "Walked the spec", "company_id": "co-1",
         "owner_name": "Sam", "created_at": _t(10)},
        {"id": "a-2", "type": "note", "subject": "Follow-up reminder",
         "body": "", "company_id": "co-1", "owner_name": "Sam",
         "created_at": _t(60)},
    ]))
    fdb.crm_quotes.find = MagicMock(return_value=_cursor([
        {"id": "q-1", "quote_number": "QT-001", "title": "Equipment refresh",
         "status": "sent", "total": 45000, "currency": "GBP",
         "company_id": "co-1", "created_by_name": "Alex",
         "created_at": _t(30)},
    ]))
    fdb.crm2_cases.find = MagicMock(return_value=_cursor([
        {"id": "c-1", "case_number": "CS-A1B2", "subject": "Treadmill fault",
         "status": "open", "description": "Belt slips at 12 km/h",
         "owner_name": "Sam", "company_id": "co-1", "created_at": _t(5)},
    ]))
    fdb.crm2_tenders.find = MagicMock(return_value=_cursor([
        {"id": "t-1", "title": "Council frame", "status": "submitted",
         "company_id": "co-1", "bid_owner": "Sam",
         "created_at": _t(120), "updated_at": _t(15)},  # touched → emits 2 events
    ]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(company_id="co-1", user=_USER)
    out = _run(go())

    assert out["scope"]["type"] == "company"
    assert out["scope"]["label"] == "Acme Gyms Ltd"
    # 2 activities + 1 quote + 1 case + 2 tender events = 6 rows.
    assert out["total"] == 6
    types = [e["type"] for e in out["events"]]
    assert "activity:call" in types
    assert "activity:note" in types
    assert "quote:sent" in types
    assert "case:open" in types
    assert "tender:created" in types
    assert "tender:status_changed" in types


# ══════════════════ 3 · Newest-first ordering ═══════════════════════


def test_timeline_sorts_newest_first():
    from routes import crm_v2 as m
    fdb = _fake_db()
    fdb.crm2_companies.find_one = AsyncMock(return_value={"id": "co-1", "name": "X"})
    # Activities ordered backwards so we can verify the sort happens
    # at our layer (not relying on Mongo ordering alone).
    fdb.crm2_activities.find = MagicMock(return_value=_cursor([
        {"id": "old", "type": "note", "subject": "Old", "body": "",
         "company_id": "co-1", "owner_name": "X", "created_at": _t(60)},
        {"id": "newest", "type": "note", "subject": "Newest", "body": "",
         "company_id": "co-1", "owner_name": "X", "created_at": _t(1)},
        {"id": "mid", "type": "note", "subject": "Middle", "body": "",
         "company_id": "co-1", "owner_name": "X", "created_at": _t(30)},
    ]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(company_id="co-1", user=_USER)
    out = _run(go())
    subjects = [e["subject"] for e in out["events"]]
    assert subjects == ["Newest", "Middle", "Old"]


# ══════════════════ 4 · Org isolation — scope validation enforces it ═


def test_timeline_uses_org_scoped_queries_only():
    """Verify the queries we issue all carry organization_id (or the
    org-scoped foreign key) so a crafted scope id from another org
    can't pull data."""
    from routes import crm_v2 as m
    fdb = _fake_db()
    fdb.crm2_companies.find_one = AsyncMock(return_value={
        "id": "co-1", "name": "Acme",
    })

    # Capture the queries each collection sees.
    captured: dict[str, dict] = {}
    def _capture(name):
        def _find(q, _proj):
            captured[name] = q
            return _cursor([])
        return _find

    fdb.crm2_activities.find = MagicMock(side_effect=_capture("activities"))
    fdb.crm_quotes.find = MagicMock(side_effect=_capture("quotes"))
    fdb.crm2_cases.find = MagicMock(side_effect=_capture("cases"))
    fdb.crm2_tenders.find = MagicMock(side_effect=_capture("tenders"))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(company_id="co-1", user=_USER)
    _run(go())

    # Every source's query carries the org filter (either via
    # ``organization_id`` for quotes — which lacks crm v2 of() — or
    # via the spread of _of(user)).
    assert captured["activities"]["organization_id"] == "org-A"
    assert captured["quotes"]["organization_id"] == "org-A"
    assert captured["cases"]["organization_id"] == "org-A"
    assert captured["tenders"]["organization_id"] == "org-A"


# ══════════════════ 5 · Tender scope synthesises events ═════════════


def test_tender_scope_emits_created_and_status_changed_events():
    from routes import crm_v2 as m
    fdb = _fake_db()
    fdb.crm2_tenders.find_one = AsyncMock(return_value={
        "id": "t-1", "title": "Council bid",
        "company_id": "co-1", "opportunity_id": None,
    })
    # The find() for tender events returns the tender itself.
    fdb.crm2_tenders.find = MagicMock(return_value=_cursor([
        {"id": "t-1", "title": "Council bid", "status": "submitted",
         "company_id": "co-1", "created_at": _t(180), "updated_at": _t(20),
         "bid_owner": "Sam"},
    ]))
    # And quotes linked to the tender (tender_id).
    fdb.crm_quotes.find = MagicMock(return_value=_cursor([
        {"id": "q-1", "quote_number": "QT-100", "title": "Pricing v1",
         "status": "sent", "total": 50000, "currency": "GBP",
         "tender_id": "t-1", "created_by_name": "Alex",
         "created_at": _t(60)},
    ]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(tender_id="t-1", user=_USER)
    out = _run(go())

    types = [e["type"] for e in out["events"]]
    # Tender-scope doesn't pull activities or cases (they don't link).
    assert "tender:created" in types
    assert "tender:status_changed" in types
    assert "quote:sent" in types
    # Untouched tender (created_at == updated_at) should emit only
    # the ``created`` event.


def test_tender_scope_untouched_tender_only_emits_created_event():
    from routes import crm_v2 as m
    fdb = _fake_db()
    same_ts = _t(100)
    fdb.crm2_tenders.find_one = AsyncMock(return_value={
        "id": "t-2", "title": "Untouched bid",
        "company_id": None, "opportunity_id": None,
    })
    fdb.crm2_tenders.find = MagicMock(return_value=_cursor([
        {"id": "t-2", "title": "Untouched bid", "status": "draft",
         "created_at": same_ts, "updated_at": same_ts},
    ]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(tender_id="t-2", user=_USER)
    out = _run(go())
    types = [e["type"] for e in out["events"]]
    assert "tender:created" in types
    assert "tender:status_changed" not in types


# ══════════════════ 6 · Pagination ══════════════════════════════════


def test_timeline_pagination_returns_correct_slice():
    from routes import crm_v2 as m
    fdb = _fake_db()
    fdb.crm2_companies.find_one = AsyncMock(return_value={"id": "co-1", "name": "X"})
    # 10 activities, newest first.
    acts = [
        {"id": f"a-{i:02d}", "type": "note", "subject": f"Activity {i}",
         "body": "", "company_id": "co-1", "owner_name": "X",
         "created_at": _t(i)}
        for i in range(10)
    ]
    fdb.crm2_activities.find = MagicMock(return_value=_cursor(acts))

    async def go(limit, skip):
        with patch.object(m, "db", fdb):
            return await m.unified_timeline(
                company_id="co-1", limit=limit, skip=skip, user=_USER,
            )
    page1 = _run(go(limit=3, skip=0))
    page2 = _run(go(limit=3, skip=3))
    assert len(page1["events"]) == 3
    assert len(page2["events"]) == 3
    # Disjoint sets.
    p1_ids = {e["id"] for e in page1["events"]}
    p2_ids = {e["id"] for e in page2["events"]}
    assert p1_ids.isdisjoint(p2_ids)
    # Total count is consistent across pages.
    assert page1["total"] == page2["total"] == 10
    # Page 2 is older than page 1 (newest-first ordering).
    assert page1["events"][0]["occurred_at"] > page2["events"][0]["occurred_at"]


# ══════════════════ 7 · Normalised shape stability ══════════════════


def test_event_shape_is_stable_across_sources():
    """Every event must carry the same set of top-level keys so the
    React renderer doesn't need a per-source branch."""
    from routes import crm_v2 as m
    expected_keys = {
        "id", "source_collection", "source_id", "type", "occurred_at",
        "subject", "body", "actor", "icon_hint", "status_hint",
        "deep_link",
    }

    # Build one of each.
    act = m._norm_activity({
        "id": "a", "type": "call", "subject": "X", "body": "y",
        "owner_name": "Sam", "created_at": _t(10),
    })
    qt = m._norm_quote({
        "id": "q", "quote_number": "QT-1", "title": "T", "status": "sent",
        "total": 100, "currency": "GBP", "created_by_name": "Alex",
        "created_at": _t(10),
    })
    cs = m._norm_case({
        "id": "c", "case_number": "CS-1", "subject": "X", "status": "open",
        "description": "y", "owner_name": "Sam", "created_at": _t(10),
    })
    tn = m._norm_tender_event({
        "id": "t", "title": "X", "status": "submitted", "bid_owner": "Sam",
        "created_at": _t(10), "updated_at": _t(5),
    }, event="status_changed")
    for ev in (act, qt, cs, tn):
        assert set(ev.keys()) == expected_keys, (
            f"event {ev.get('id')} missing keys: {expected_keys - set(ev.keys())}"
        )
        # Deep-link is always a CRM-internal route (not a raw API URL).
        assert ev["deep_link"].startswith("/crm/")
