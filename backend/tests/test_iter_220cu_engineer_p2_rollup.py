"""Iter 220cu — Engineer "My day" briefing, today rollup, quote PDF
machines table.

Three new capabilities:

1. ``GET /api/svc/engineer/me/briefing`` — single-fetch "your day"
   summary used by the EngineerHomeV2 strip.
2. ``GET /api/svc/engineer/me/today-rollup`` — single-fetch
   timesheet rollup for the EngineerEndOfDay screen.
3. ``utils/engineer_quote_pdf.build_engineer_quote_pdf`` — renders a
   "MACHINES THIS QUOTE COVERS" table when ``quote.machines`` is
   non-empty.
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


# ──────────────────────────────────────────────────────────────────
# /me/briefing
# ──────────────────────────────────────────────────────────────────


def test_briefing_returns_next_stop_with_counts():
    """Engineer has 3 jobs scheduled today, 1 still open, 2 pending
    parts requests, 1 pending quote, 4 unread inbox items."""
    next_stop = {
        "id": "case-1", "reference": "GA-001", "title": "Treadmill belt",
        "site_name": "Acme HQ", "site_address": "1 High St",
        "scheduled_at": "2026-05-30T09:30:00Z",
    }
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=next_stop)
    fdb.svc_cases.count_documents = AsyncMock(side_effect=[3, 1])
    fdb.svc_parts_requests.count_documents = AsyncMock(return_value=2)
    fdb.svc_engineer_notifications.count_documents = AsyncMock(return_value=4)
    fdb.svc_engineer_quotes.count_documents = AsyncMock(return_value=1)

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_my_day_briefing
            return await engineer_my_day_briefing(user=_user())

    out = _run(run())
    assert out["jobs_today_total"] == 3
    assert out["jobs_today_remaining"] == 1
    assert out["next_stop"]["id"] == "case-1"
    assert out["pending_parts_count"] == 2
    assert out["pending_quotes_count"] == 1
    assert out["unread_inbox_count"] == 4


def test_briefing_handles_missing_next_stop_gracefully():
    """No scheduled jobs today → next_stop is None, counts all zero."""
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=None)
    fdb.svc_cases.count_documents = AsyncMock(return_value=0)
    fdb.svc_parts_requests.count_documents = AsyncMock(return_value=0)
    fdb.svc_engineer_notifications.count_documents = AsyncMock(return_value=0)
    fdb.svc_engineer_quotes.count_documents = AsyncMock(return_value=0)

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_my_day_briefing
            return await engineer_my_day_briefing(user=_user())

    out = _run(run())
    assert out["next_stop"] is None
    assert out["jobs_today_total"] == 0
    assert out["unread_inbox_count"] == 0


# ──────────────────────────────────────────────────────────────────
# /me/today-rollup
# ──────────────────────────────────────────────────────────────────


def test_today_rollup_aggregates_hours_miles_jobs_revenue():
    """One 90 min on_site + 30 min travel entry on the same case, two
    mileage entries (5 + 7 mi), one job closed today, two invoices
    totalling £350 → assembled correctly into the rollup payload."""
    time_entries = [
        {"category": "on_site", "duration_minutes": 90, "case_id": "case-1"},
        {"category": "travel",  "duration_minutes": 30, "case_id": "case-1"},
    ]
    mileage = [{"miles": 5.0}, {"miles": 7.0}]
    invoices = [{"total": 150.0}, {"total": 200.0}]

    fdb = MagicMock()
    fdb.svc_time_entries.find = MagicMock(return_value=_async_iter(time_entries))
    fdb.svc_mileage_entries.find = MagicMock(return_value=_async_iter(mileage))
    fdb.svc_engineer_invoices.find = MagicMock(return_value=_async_iter(invoices))
    fdb.svc_cases.count_documents = AsyncMock(return_value=1)

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_today_rollup
            return await engineer_today_rollup(user=_user())

    out = _run(run())
    assert out["minutes_by_category"]["on_site"] == 90
    assert out["minutes_by_category"]["travel"] == 30
    assert out["hours_on_site"] == 1.5
    assert out["hours_travel"] == 0.5
    assert out["hours_total"] == 2.0
    assert out["miles"] == 12.0
    assert out["jobs_touched"] == 1
    assert out["jobs_closed"] == 1
    assert out["invoices_today"] == 2
    assert out["revenue_today_gbp"] == 350.0
    assert out["date"] == datetime.now(timezone.utc).date().isoformat()


def test_today_rollup_empty_day_returns_zeros():
    fdb = MagicMock()
    fdb.svc_time_entries.find = MagicMock(return_value=_async_iter([]))
    fdb.svc_mileage_entries.find = MagicMock(return_value=_async_iter([]))
    fdb.svc_engineer_invoices.find = MagicMock(return_value=_async_iter([]))
    fdb.svc_cases.count_documents = AsyncMock(return_value=0)

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_today_rollup
            return await engineer_today_rollup(user=_user())

    out = _run(run())
    assert out["hours_total"] == 0
    assert out["miles"] == 0
    assert out["jobs_touched"] == 0
    assert out["invoices_today"] == 0


# ──────────────────────────────────────────────────────────────────
# Quote PDF — machines table
# ──────────────────────────────────────────────────────────────────


def test_quote_pdf_renders_machines_table_when_present():
    """A quote with 2 machines must produce a PDF that, when extracted
    via pypdf, contains the table header phrase and each machine's
    serial number."""
    from utils.engineer_quote_pdf import build_engineer_quote_pdf
    import io
    import pypdf
    quote = {
        "id": "q1", "quote_number": "EQ-20260530-AAAA",
        "issued_at": "2026-05-30T09:00:00Z",
        "valid_until": "2026-06-29T09:00:00Z",
        "customer_name": "Acme Gym", "customer_email": "ops@acme.com",
        "engineer_name": "E", "case_reference": "GA-001",
        "machines": [
            {"name": "Treadmill #4", "serial": "TM-44", "notes": "Belt"},
            {"name": "Rower #1",     "serial": "RW-12", "notes": ""},
        ],
        "description_of_work": "Service two machines.",
        "lines": [{
            "kind": "labour", "description": "Labour",
            "quantity": 2, "unit_price": 80, "line_total": 160,
        }],
        "vat_rate": 20, "discount_pct": 0,
        "subtotal": 160, "vat_amount": 32, "total": 192,
    }
    pdf = build_engineer_quote_pdf(quote)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000  # non-trivial document
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    text = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "MACHINES THIS QUOTE COVERS" in text
    assert "TM-44" in text
    assert "RW-12" in text


def test_quote_pdf_skips_machines_table_when_list_empty():
    from utils.engineer_quote_pdf import build_engineer_quote_pdf
    import io
    import pypdf
    quote = {
        "id": "q2", "quote_number": "EQ-20260530-BBBB",
        "customer_name": "Acme Gym",
        "engineer_name": "E", "case_reference": "GA-002",
        "machines": [],
        "lines": [{
            "kind": "labour", "description": "Labour",
            "quantity": 1, "unit_price": 80, "line_total": 80,
        }],
        "vat_rate": 20, "subtotal": 80, "vat_amount": 16, "total": 96,
    }
    pdf = build_engineer_quote_pdf(quote)
    assert isinstance(pdf, bytes)
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    text = "\n".join(p.extract_text() or "" for p in reader.pages)
    # Heading must be absent when there are no machines.
    assert "MACHINES THIS QUOTE COVERS" not in text
