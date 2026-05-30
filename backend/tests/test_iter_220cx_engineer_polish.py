"""Iter 220cx — Engineer review polish: closed-but-not-invoiced
recovery + voice confidence + global mic FAB.

This file covers the BACKEND additions only — the FAB mount and
the in-progress badge are pure frontend wire-ups verified by the
ESLint pass on the project.

Pinned behaviour:

* ``GET /api/svc/engineer/me/briefing`` returns ``not_invoiced``
  + ``not_invoiced_count`` for jobs closed in the last 7 days that
  have no linked invoice.
* When *every* closed case has an invoice, the array stays empty
  and the count is 0.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="eng-1", org="org-1"):
    return {"id": uid, "organization_id": org, "email": "e@x", "full_name": "E"}


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


def _briefing_db(*, not_invoiced_cases=None, invoice_lookup=None):
    """Build a minimal Mongo stub that the briefing endpoint can use."""
    fdb = MagicMock()
    # Counts return 0 by default — happy-path coverage for those is
    # already pinned in test_iter_220cu.
    fdb.svc_cases.find_one = AsyncMock(return_value=None)
    fdb.svc_cases.count_documents = AsyncMock(return_value=0)
    fdb.svc_parts_requests.count_documents = AsyncMock(return_value=0)
    fdb.svc_engineer_notifications.count_documents = AsyncMock(return_value=0)
    fdb.svc_engineer_quotes.count_documents = AsyncMock(return_value=0)
    # The closed-cases scan is a find() — return whatever we were
    # handed. The endpoint also calls svc_engineer_invoices.find_one
    # per case to decide whether it's "not invoiced".
    fdb.svc_cases.find = MagicMock(return_value=_async_iter(not_invoiced_cases or []))
    invoice_lookup = invoice_lookup or {}

    async def _find_invoice(query, *_a, **_k):
        return invoice_lookup.get(query.get("case_id"))

    fdb.svc_engineer_invoices.find_one = AsyncMock(side_effect=_find_invoice)
    return fdb


def test_briefing_surfaces_closed_jobs_with_no_invoice():
    """Two closed-this-week jobs; only one has an invoice → the
    briefing reports the other as ``not_invoiced``."""
    closed_now = datetime.now(timezone.utc).isoformat()
    cases = [
        {"id": "case-a", "reference": "GA-100", "title": "Belt swap",
         "customer_name": "Acme", "closed_at": closed_now, "status": "closed"},
        {"id": "case-b", "reference": "GA-101", "title": "Display reset",
         "customer_name": "Beta", "closed_at": closed_now, "status": "closed"},
    ]
    # case-a is already invoiced; case-b is the one we need to chase.
    invoice_lookup = {"case-a": {"id": "inv-a"}}
    fdb = _briefing_db(
        not_invoiced_cases=cases, invoice_lookup=invoice_lookup,
    )

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_my_day_briefing
            return await engineer_my_day_briefing(user=_user())

    out = _run(run())
    assert out["not_invoiced_count"] == 1
    assert len(out["not_invoiced"]) == 1
    assert out["not_invoiced"][0]["id"] == "case-b"
    assert out["not_invoiced"][0]["reference"] == "GA-101"


def test_briefing_returns_empty_when_all_closed_jobs_invoiced():
    closed_now = datetime.now(timezone.utc).isoformat()
    cases = [
        {"id": "case-a", "reference": "GA-100", "title": "x",
         "closed_at": closed_now, "status": "closed"},
    ]
    fdb = _briefing_db(
        not_invoiced_cases=cases,
        invoice_lookup={"case-a": {"id": "inv-a"}},
    )

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_my_day_briefing
            return await engineer_my_day_briefing(user=_user())

    out = _run(run())
    assert out["not_invoiced_count"] == 0
    assert out["not_invoiced"] == []


def test_briefing_handles_no_closed_jobs_gracefully():
    """No closed jobs at all → not_invoiced fields still present
    so the frontend can rely on the contract."""
    fdb = _briefing_db()

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_my_day_briefing
            return await engineer_my_day_briefing(user=_user())

    out = _run(run())
    assert "not_invoiced" in out
    assert "not_invoiced_count" in out
    assert out["not_invoiced_count"] == 0


def test_briefing_caps_not_invoiced_list_at_five():
    """20 closed-uninvoiced jobs → only first 5 returned (UI cap)."""
    closed_now = datetime.now(timezone.utc).isoformat()
    cases = [
        {"id": f"case-{i}", "reference": f"GA-{i}",
         "title": "x", "closed_at": closed_now, "status": "closed"}
        for i in range(20)
    ]
    fdb = _briefing_db(not_invoiced_cases=cases, invoice_lookup={})

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_my_day_briefing
            return await engineer_my_day_briefing(user=_user())

    out = _run(run())
    assert out["not_invoiced_count"] == 5
    assert len(out["not_invoiced"]) == 5
