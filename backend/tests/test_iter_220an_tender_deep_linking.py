"""Iter 220an — Tenders module · deep linking to companies + opportunities.

Pins:

  * ``GET /crm/v2/tenders`` hydrates each row with ``company_name`` +
    ``opportunity_title`` / ``opportunity_stage`` so the list grid can
    render clickable badges without N+1 fetches.
  * ``GET /crm/v2/tenders/{id}`` enriches with ``company`` and
    ``opportunity`` stubs (id + name/title + key fields).
  * ``GET /crm/v2/companies/{id}`` now includes a ``tenders`` array
    of every tender raised against that company.
  * ``GET /crm/v2/opportunities/{id}`` now includes a ``tenders``
    array of every tender raised under that deal.
  * ``POST /crm/v2/tenders`` rejects cross-tenant ``company_id`` /
    ``opportunity_id`` and auto-links company when only the opp is
    supplied.
  * ``PUT  /crm/v2/tenders/{id}`` enforces same-org ownership and
    company↔opportunity consistency when re-pointing links.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _async_iter(items):
    class _Cur:
        def __init__(self, items): self._items = list(items)
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)
    return _Cur(items)


def _cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.skip = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "crm2_tenders", "crm2_tender_questions", "crm2_tender_docs",
        "crm2_companies", "crm2_opportunities", "crm2_quotes",
        "crm2_contacts", "crm2_cases", "crm2_assets", "crm2_contracts",
        "crm2_activities",
    ):
        c = getattr(fdb, coll)
        c.insert_one = AsyncMock()
        c.update_one = AsyncMock()
        c.delete_one = AsyncMock()
        c.delete_many = AsyncMock()
        c.find_one = AsyncMock(return_value=None)
        c.count_documents = AsyncMock(return_value=0)
        c.find = MagicMock(return_value=_cursor([]))
    return fdb


_USER = {"id": "u-1", "organization_id": "org-1"}


# ── /tenders list — hydrates with company_name + opp title ─────────

def test_list_tenders_hydrates_company_and_opportunity_names():
    from routes import crm_v2 as m

    fdb = _fake_db()
    tenders = [
        {"id": "t-1", "title": "Frame agreement", "company_id": "co-1",
         "opportunity_id": "op-1", "status": "draft", "type": "ITT"},
        {"id": "t-2", "title": "DPS lot 4", "company_id": "co-1",
         "opportunity_id": None, "status": "submitted", "type": "DPS"},
        {"id": "t-3", "title": "RFP one-off", "company_id": None,
         "opportunity_id": None, "status": "draft", "type": "RFP"},
    ]
    fdb.crm2_tenders.count_documents = AsyncMock(return_value=3)
    fdb.crm2_tenders.find = MagicMock(return_value=_cursor(tenders))

    # The find calls for companies + opps return async iterators.
    fdb.crm2_companies.find = MagicMock(
        return_value=_async_iter([{"id": "co-1", "name": "Anytime Fitness UK"}])
    )
    fdb.crm2_opportunities.find = MagicMock(
        return_value=_async_iter([
            {"id": "op-1", "title": "Anytime national rollout", "stage": "proposal"},
        ])
    )

    async def go():
        with patch.object(m, "db", fdb):
            return await m.list_tenders(skip=0, limit=50, user=_USER)
    out = _run(go())
    assert out["total"] == 3
    rows = {t["id"]: t for t in out["tenders"]}
    assert rows["t-1"]["company_name"] == "Anytime Fitness UK"
    assert rows["t-1"]["opportunity_title"] == "Anytime national rollout"
    assert rows["t-1"]["opportunity_stage"] == "proposal"
    # Tender with no opp shouldn't get an opportunity_title key.
    assert "opportunity_title" not in rows["t-2"]
    assert rows["t-2"]["company_name"] == "Anytime Fitness UK"
    # Tender with neither link should have neither field.
    assert "company_name" not in rows["t-3"]
    assert "opportunity_title" not in rows["t-3"]


# ── /tenders/{id} — enriches with company + opportunity ──────────

def test_get_tender_enriches_with_company_and_opportunity():
    from routes import crm_v2 as m

    fdb = _fake_db()
    tender = {"id": "t-1", "title": "Frame agreement", "company_id": "co-1",
              "opportunity_id": "op-1", "organization_id": "org-1"}
    fdb.crm2_tenders.find_one = AsyncMock(return_value=tender)
    fdb.crm2_tender_questions.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_tender_docs.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_companies.find_one = AsyncMock(return_value={
        "id": "co-1", "name": "Anytime Fitness UK", "sector": "Fitness"
    })
    fdb.crm2_opportunities.find_one = AsyncMock(return_value={
        "id": "op-1", "title": "Anytime national rollout",
        "stage": "proposal", "value": 500_000, "company_id": "co-1",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.get_tender(tender_id="t-1", user=_USER)
    out = _run(go())
    assert out["company"]["name"] == "Anytime Fitness UK"
    assert out["opportunity"]["title"] == "Anytime national rollout"
    assert out["opportunity"]["stage"] == "proposal"
    assert out["opportunity"]["value"] == 500_000


def test_get_tender_omits_links_when_none_set():
    from routes import crm_v2 as m

    fdb = _fake_db()
    fdb.crm2_tenders.find_one = AsyncMock(return_value={
        "id": "t-1", "title": "Standalone tender",
        "company_id": None, "opportunity_id": None,
    })
    fdb.crm2_tender_questions.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_tender_docs.find = MagicMock(return_value=_cursor([]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.get_tender(tender_id="t-1", user=_USER)
    out = _run(go())
    assert "company" not in out
    assert "opportunity" not in out


# ── /companies/{id} — adds tenders ─────────────────────────────────

def test_get_company_returns_linked_tenders():
    from routes import crm_v2 as m

    fdb = _fake_db()
    fdb.crm2_companies.find_one = AsyncMock(return_value={
        "id": "co-1", "name": "Anytime Fitness UK",
    })
    # Default empty cursors for unrelated collections — we only care about
    # the tenders branch here.
    fdb.crm2_contacts.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_opportunities.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_quotes.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_cases.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_assets.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_contracts.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_activities.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_tenders.find = MagicMock(return_value=_cursor([
        {"id": "t-1", "title": "Frame agreement", "status": "draft", "type": "ITT"},
        {"id": "t-2", "title": "DPS lot 4", "status": "submitted", "type": "DPS"},
    ]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.get_company(company_id="co-1", user=_USER)
    out = _run(go())
    assert [t["id"] for t in out["tenders"]] == ["t-1", "t-2"]


# ── /opportunities/{id} — adds tenders ─────────────────────────────

def test_get_opportunity_returns_linked_tenders():
    from routes import crm_v2 as m

    fdb = _fake_db()
    fdb.crm2_opportunities.find_one = AsyncMock(return_value={
        "id": "op-1", "title": "Anytime national rollout", "company_id": None,
        "contact_id": None,
    })
    fdb.crm2_activities.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_quotes.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_tenders.find = MagicMock(return_value=_cursor([
        {"id": "t-1", "title": "Frame agreement", "status": "in_progress"},
    ]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.get_opportunity(opp_id="op-1", user=_USER)
    out = _run(go())
    assert [t["id"] for t in out["tenders"]] == ["t-1"]


# ── POST /tenders — cross-tenant rejection ─────────────────────────

def test_create_tender_rejects_unknown_company():
    from fastapi import HTTPException
    from routes import crm_v2 as m

    fdb = _fake_db()
    # company_id supplied but find_one returns None → 400.
    fdb.crm2_companies.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.create_tender(
                    {"title": "rogue", "company_id": "co-other"},
                    user=_USER,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400
    fdb.crm2_tenders.insert_one.assert_not_called()


def test_create_tender_rejects_company_opportunity_mismatch():
    from fastapi import HTTPException
    from routes import crm_v2 as m

    fdb = _fake_db()
    fdb.crm2_companies.find_one = AsyncMock(return_value={"id": "co-1"})
    fdb.crm2_opportunities.find_one = AsyncMock(return_value={
        "id": "op-1", "company_id": "co-different",
    })

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.create_tender(
                    {"title": "mismatched", "company_id": "co-1",
                     "opportunity_id": "op-1"},
                    user=_USER,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400
    fdb.crm2_tenders.insert_one.assert_not_called()


def test_create_tender_auto_links_company_from_opportunity():
    from routes import crm_v2 as m

    fdb = _fake_db()
    # No company supplied, but opportunity belongs to co-7.
    fdb.crm2_opportunities.find_one = AsyncMock(return_value={
        "id": "op-1", "company_id": "co-7",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.create_tender(
                {"title": "auto-linked", "opportunity_id": "op-1"},
                user=_USER,
            )
    out = _run(go())
    assert out["company_id"] == "co-7"
    assert out["opportunity_id"] == "op-1"
    fdb.crm2_tenders.insert_one.assert_awaited_once()


# ── PUT /tenders/{id} — same-org ownership + consistency ─────────

def test_update_tender_rejects_cross_org_company():
    from fastapi import HTTPException
    from routes import crm_v2 as m

    fdb = _fake_db()
    fdb.crm2_tenders.find_one = AsyncMock(return_value={
        "id": "t-1", "organization_id": "org-1", "company_id": None,
    })
    fdb.crm2_companies.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.update_tender(
                    tender_id="t-1",
                    data={"company_id": "co-other-tenant"},
                    user=_USER,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400
    fdb.crm2_tenders.update_one.assert_not_called()


def test_update_tender_accepts_consistent_links_and_persists():
    from routes import crm_v2 as m

    fdb = _fake_db()
    fdb.crm2_tenders.find_one = AsyncMock(return_value={
        "id": "t-1", "organization_id": "org-1", "company_id": "co-1",
        "opportunity_id": None,
    })
    fdb.crm2_companies.find_one = AsyncMock(return_value={"id": "co-1"})
    fdb.crm2_opportunities.find_one = AsyncMock(return_value={
        "id": "op-2", "company_id": "co-1",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.update_tender(
                tender_id="t-1",
                data={"opportunity_id": "op-2"},
                user=_USER,
            )
    out = _run(go())
    assert out == {"success": True}
    fdb.crm2_tenders.update_one.assert_awaited_once()
    call = fdb.crm2_tenders.update_one.await_args
    assert call.args[1]["$set"]["opportunity_id"] == "op-2"
