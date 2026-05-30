"""Iter 220ct — Engineer-app P1 polish tests.

Three new capabilities:

1. ``GET /api/svc/engineer/customers/open-cases`` — duplicate-prevention
   probe used by the New Job form.
2. ``GET /api/svc/engineer/jobs/{case_id}/invoice-prefill`` — quote →
   invoice continuity. Returns labour / mileage / parts pre-populated
   so the engineer doesn't re-key at close-out.
3. The InvoiceBuilder reads ``?case_id=`` and consumes the prefill.
   That's a pure-frontend wire-up — we only pin the backend contract
   here.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="eng-1", org="org-1"):
    return {"id": uid, "organization_id": org, "email": "e@x"}


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
# /customers/open-cases
# ──────────────────────────────────────────────────────────────────


def _customers_fake_db(cases):
    fdb = MagicMock()

    class _Cursor:
        def __init__(self, xs):
            self.xs = list(xs)

        def sort(self, *_, **__):
            return self

        def limit(self, _n):
            return self

        async def to_list(self, *args, **kwargs):
            return self.xs

    fdb.svc_cases.find = MagicMock(return_value=_Cursor(cases))
    return fdb


def test_open_cases_returns_count_and_rows_for_matching_email():
    cases = [
        {"id": "c1", "reference": "GA-001", "title": "Treadmill belt",
         "status": "in_progress", "priority": "P2"},
        {"id": "c2", "reference": "GA-002", "title": "Rower display",
         "status": "scheduled", "priority": "P3"},
    ]
    fdb = _customers_fake_db(cases)

    async def run():
        with patch("routes.svc.engineer_customers.db", fdb):
            from routes.svc.engineer_customers import open_cases_for_customer
            out = await open_cases_for_customer(
                user=_user(),
                email="op@acme.com", phone=None, name=None, site_name=None,
            )
        assert out["count"] == 2
        assert {r["id"] for r in out["cases"]} == {"c1", "c2"}
        # The Mongo query must $match on email + a status in the open set.
        q = fdb.svc_cases.find.call_args.args[0]
        assert q["status"]["$in"]  # status filter present
        assert any("customer_email" in o for o in q["$or"])

    _run(run())


def test_open_cases_empty_payload_returns_zero_without_querying_db():
    fdb = _customers_fake_db([])

    async def run():
        with patch("routes.svc.engineer_customers.db", fdb):
            from routes.svc.engineer_customers import open_cases_for_customer
            out = await open_cases_for_customer(
                user=_user(),
                email=None, phone=None, name=None, site_name=None,
            )
        # No identifying field → no DB call, just a zero shape.
        assert out == {"count": 0, "cases": []}
        fdb.svc_cases.find.assert_not_called()

    _run(run())


def test_open_cases_name_match_is_case_insensitive():
    fdb = _customers_fake_db([{"id": "c1", "reference": "GA-001"}])

    async def run():
        with patch("routes.svc.engineer_customers.db", fdb):
            from routes.svc.engineer_customers import open_cases_for_customer
            await open_cases_for_customer(
                user=_user(),
                email=None, phone=None, name="Acme Gym", site_name=None,
            )
        q = fdb.svc_cases.find.call_args.args[0]
        name_clauses = [
            c for c in q["$or"]
            if "customer_name" in c and isinstance(c["customer_name"], dict)
        ]
        assert name_clauses
        regex = name_clauses[0]["customer_name"]
        assert regex["$options"] == "i"
        assert "Acme" in regex["$regex"]
        assert "Gym" in regex["$regex"]

    _run(run())


# ──────────────────────────────────────────────────────────────────
# /invoices/jobs/{case_id}/invoice-prefill
# ──────────────────────────────────────────────────────────────────


def _invoice_fake_db(*, case, time_entries=None, mileage=None):
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=case)
    fdb.svc_time_entries.find = MagicMock(
        return_value=_async_iter(time_entries or []),
    )
    fdb.svc_mileage_entries.find = MagicMock(
        return_value=_async_iter(mileage or []),
    )
    return fdb


def test_invoice_prefill_pulls_labour_mileage_and_parts():
    """A finished case with 90 min on-site + 12 miles + one allocated
    part → invoice payload has 4 lines (callout + labour + travel + part)
    when the engineer has a non-zero callout fee in their rates."""
    case = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "assigned_engineer_id": "eng-1",
        "customer_name": "Acme Gym", "customer_email": "op@acme.com",
        "site_name": "Acme HQ", "asset_name": "Treadmill #4",
        "resolution_notes": "Replaced drive belt and lubricated deck.",
        "allocated_parts": [{
            "sku": "ABC-12", "name": "Drive belt",
            "qty": 1, "unit_price": 45.0,
            "machine_name": "Treadmill #4",
        }],
    }
    time_entries = [
        {"category": "on_site", "duration_minutes": 60},
        {"category": "on_site", "duration_minutes": 30},
    ]
    mileage = [{"miles": 12.0}]
    fdb = _invoice_fake_db(case=case, time_entries=time_entries, mileage=mileage)

    partner = {
        "id": "p-1",
        "rates": {
            "callout_fee": 50.0,
            "labour_rate_per_hour": 80.0,
            "mileage_rate": 0.45,
        },
    }

    async def run():
        with patch("routes.svc.engineer_invoices.db", fdb), \
             patch("routes.partners._get_partner_by_user",
                   AsyncMock(return_value=partner)):
            from routes.svc.engineer_invoices import invoice_prefill_from_case
            out = await invoice_prefill_from_case("case-1", user=_user())
        # Headline fields mirrored.
        assert out["customer_name"] == "Acme Gym"
        assert out["asset_name"] == "Treadmill #4"
        assert out["description_of_work"].startswith("Replaced drive belt")
        # Meta totals.
        meta = out["totals_meta"]
        assert meta["on_site_minutes"] == 90
        assert meta["on_site_hours"] == 1.5
        assert meta["miles"] == 12.0
        assert meta["parts_count"] == 1
        # Lines: callout + labour + travel + part.
        kinds = [ln["kind"] for ln in out["lines"]]
        assert kinds == ["callout", "labour", "travel", "part"]
        labour = next(ln for ln in out["lines"] if ln["kind"] == "labour")
        assert labour["quantity"] == 1.5
        assert labour["unit_price"] == 80.0
        travel = next(ln for ln in out["lines"] if ln["kind"] == "travel")
        assert travel["quantity"] == 12.0
        assert travel["unit_price"] == 0.45
        part = next(ln for ln in out["lines"] if ln["kind"] == "part")
        assert part["quantity"] == 1
        assert part["unit_price"] == 45.0
        assert "SKU ABC-12" in part["notes"]

    _run(run())


def test_invoice_prefill_falls_back_to_single_labour_line_when_empty():
    """No time, no mileage, no parts → return one labour line at the
    engineer's hourly rate so the form isn't empty."""
    case = {"id": "case-9", "organization_id": "org-1",
            "assigned_engineer_id": "eng-1", "customer_name": "Acme"}
    fdb = _invoice_fake_db(case=case, time_entries=[], mileage=[])

    async def run():
        with patch("routes.svc.engineer_invoices.db", fdb), \
             patch("routes.partners._get_partner_by_user",
                   AsyncMock(return_value={"rates": {"labour_rate_per_hour": 75.0}})):
            from routes.svc.engineer_invoices import invoice_prefill_from_case
            out = await invoice_prefill_from_case("case-9", user=_user())
        assert len(out["lines"]) == 1
        assert out["lines"][0]["kind"] == "labour"
        assert out["lines"][0]["unit_price"] == 75.0

    _run(run())


def test_invoice_prefill_404s_when_case_missing():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=None)

    async def run():
        with patch("routes.svc.engineer_invoices.db", fdb):
            from routes.svc.engineer_invoices import invoice_prefill_from_case
            try:
                await invoice_prefill_from_case("nope", user=_user())
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 404

    _run(run())


def test_invoice_prefill_404s_when_case_belongs_to_other_engineer():
    """Defensive — engineers must not see jobs assigned to peers."""
    case = {
        "id": "case-5", "organization_id": "org-1",
        "assigned_engineer_id": "someone-else",
    }
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=case)

    async def run():
        with patch("routes.svc.engineer_invoices.db", fdb):
            from routes.svc.engineer_invoices import invoice_prefill_from_case
            try:
                await invoice_prefill_from_case("case-5", user=_user())
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 404

    _run(run())
