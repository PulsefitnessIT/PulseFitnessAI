"""Iter 216h204 — Desk-sales reconciliation report.

Backend coverage for /api/memberships/reports/desk-sales (JSON + CSV).

Run: pytest backend/tests/test_iter_216h204_desk_sales_report.py -q
"""
from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_db(rows, *, members=None, operators=None, plans=None):
    fake = MagicMock()

    def _cursor(data):
        cur = MagicMock()
        cur.sort = lambda *_a, **_k: cur
        cur.to_list = AsyncMock(return_value=list(data))
        return cur

    fake.payment_transactions = MagicMock()
    fake.payment_transactions.find = MagicMock(return_value=_cursor(rows))
    fake.members = MagicMock()
    fake.members.find = MagicMock(return_value=_cursor(members or []))
    fake.users = MagicMock()
    fake.users.find = MagicMock(return_value=_cursor(operators or []))
    fake.membership_plans = MagicMock()
    fake.membership_plans.find = MagicMock(return_value=_cursor(plans or []))
    return fake


def _today_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── _parse_iso_date ───────────────────────────────────────────────────


def test_parse_iso_date_accepts_yyyy_mm_dd() -> None:
    from routes.memberships.reports import _parse_iso_date

    d = _parse_iso_date("2026-05-18")
    assert d.year == 2026 and d.month == 5 and d.day == 18
    assert d.tzinfo is not None


def test_parse_iso_date_end_of_day_flag() -> None:
    from routes.memberships.reports import _parse_iso_date

    d = _parse_iso_date("2026-05-18", end_of_day=True)
    assert d.hour == 23 and d.minute == 59 and d.second == 59


def test_parse_iso_date_rejects_bad_input() -> None:
    from routes.memberships.reports import _parse_iso_date

    with pytest.raises(HTTPException) as exc:
        _parse_iso_date("not-a-date")
    assert exc.value.status_code == 400


# ── Filter validation ────────────────────────────────────────────────


def test_report_rejects_from_after_to() -> None:
    from routes.memberships import reports as r

    fake = _build_db([])
    async def _stub_org(u): return "org-1"

    with patch.object(r, "db", fake), \
         patch.object(r, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_org)):
        with pytest.raises(HTTPException) as exc:
            _run(r.desk_sales_report(
                from_="2026-06-01", to="2026-01-01",
                operator_id=None, method=None, limit=100,
                user={"id": "u1", "organization_id": "org-1"},
            ))
        assert exc.value.status_code == 400


def test_report_rejects_invalid_method() -> None:
    from routes.memberships import reports as r

    fake = _build_db([])
    async def _stub_org(u): return "org-1"

    with patch.object(r, "db", fake), \
         patch.object(r, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_org)):
        with pytest.raises(HTTPException) as exc:
            _run(r.desk_sales_report(
                from_=None, to=None, operator_id=None, method="bitcoin",
                limit=100, user={"id": "u1", "organization_id": "org-1"},
            ))
        assert exc.value.status_code == 400


# ── Happy paths ──────────────────────────────────────────────────────


def test_report_returns_empty_summary_when_no_rows() -> None:
    from routes.memberships import reports as r

    fake = _build_db([])
    async def _stub_org(u): return "org-1"

    with patch.object(r, "db", fake), \
         patch.object(r, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_org)):
        result = _run(r.desk_sales_report(
            from_=None, to=None, operator_id=None, method=None,
            limit=100, user={"id": "u1", "organization_id": "org-1"},
        ))

    assert result["rows"] == []
    assert result["summary"]["count"] == 0
    assert result["summary"]["total_pence"] == 0
    assert result["summary"]["by_method"] == {}
    assert result["summary"]["top_operators"] == []


def test_report_summarises_by_method_and_top_operators() -> None:
    from routes.memberships import reports as r

    iso_now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"id": "t1", "member_id": "m1", "plan_id": "p1", "method": "cash",
         "amount_pence": 5000, "recorded_by": "u-alice", "created_at": iso_now},
        {"id": "t2", "member_id": "m2", "plan_id": "p1", "method": "cash",
         "amount_pence": 5000, "recorded_by": "u-alice", "created_at": iso_now},
        {"id": "t3", "member_id": "m3", "plan_id": "p2", "method": "card_terminal",
         "amount_pence": 9000, "recorded_by": "u-bob", "created_at": iso_now},
        {"id": "t4", "member_id": "m4", "plan_id": "p1", "method": "comp",
         "amount_pence": 0, "recorded_by": "u-alice", "created_at": iso_now},
    ]
    members = [
        {"id": "m1", "first_name": "Keir", "last_name": "Burnham", "email": "k@x"},
        {"id": "m2", "first_name": "Jen", "last_name": "Pae", "email": "j@x"},
        {"id": "m3", "first_name": "Tom", "last_name": "Lee", "email": "t@x"},
        {"id": "m4", "first_name": "Anna", "last_name": "Quin", "email": "a@x"},
    ]
    operators = [
        {"id": "u-alice", "first_name": "Alice", "last_name": "B", "email": "a@x"},
        {"id": "u-bob", "first_name": "Bob", "last_name": "C", "email": "b@x"},
    ]
    plans = [
        {"id": "p1", "name": "5 pack", "credits_count": 5},
        {"id": "p2", "name": "10 pack", "credits_count": 10},
    ]
    fake = _build_db(rows, members=members, operators=operators, plans=plans)

    async def _stub_org(u): return "org-1"

    with patch.object(r, "db", fake), \
         patch.object(r, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_org)):
        result = _run(r.desk_sales_report(
            from_=_today_iso(), to=_today_iso(),
            operator_id=None, method=None, limit=100,
            user={"id": "u1", "organization_id": "org-1"},
        ))

    s = result["summary"]
    assert s["count"] == 4
    assert s["total_pence"] == 19000  # 5000 + 5000 + 9000 + 0
    assert s["by_method"]["cash"] == {"count": 2, "total_pence": 10000}
    assert s["by_method"]["card_terminal"] == {"count": 1, "total_pence": 9000}
    assert s["by_method"]["comp"] == {"count": 1, "total_pence": 0}
    # Alice took £100, Bob took £90 — Alice first.
    assert s["top_operators"][0]["operator_id"] == "u-alice"
    assert s["top_operators"][0]["total_pence"] == 10000  # 5000+5000+0
    assert s["top_operators"][1]["operator_id"] == "u-bob"

    # Hydration: member + operator + plan name attached.
    first = result["rows"][0]
    assert first["member_name"] == "Keir Burnham"
    assert first["plan_name"] == "5 pack"
    assert first["operator_name"] == "Alice B"
    assert first["credits_added"] == 5


def test_report_hydrates_unknown_ids_as_blank_not_crash() -> None:
    """A txn whose member/operator/plan has been deleted must not 500."""
    from routes.memberships import reports as r

    rows = [{
        "id": "t1", "member_id": "m-ghost", "plan_id": "p-ghost",
        "method": "cash", "amount_pence": 5000,
        "recorded_by": "u-ghost",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }]
    fake = _build_db(rows)  # no members/operators/plans

    async def _stub_org(u): return "org-1"

    with patch.object(r, "db", fake), \
         patch.object(r, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_org)):
        result = _run(r.desk_sales_report(
            from_=None, to=None, operator_id=None, method=None,
            limit=10, user={"id": "u1", "organization_id": "org-1"},
        ))

    assert result["rows"][0]["member_name"] == ""
    assert result["rows"][0]["plan_name"] == ""
    assert result["rows"][0]["operator_name"] == ""


def test_report_filter_passes_method_to_mongo_query() -> None:
    from routes.memberships import reports as r

    fake = _build_db([])

    async def _stub_org(u): return "org-1"

    with patch.object(r, "db", fake), \
         patch.object(r, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_org)):
        _run(r.desk_sales_report(
            from_=None, to=None, operator_id="u-alice", method="cash",
            limit=10, user={"id": "u1", "organization_id": "org-1"},
        ))

    call_filter = fake.payment_transactions.find.call_args[0][0]
    assert call_filter["organization_id"] == "org-1"
    assert call_filter["kind"] == "credit_pack_desk"
    assert call_filter["method"] == "cash"
    assert call_filter["recorded_by"] == "u-alice"


# ── CSV export ───────────────────────────────────────────────────────


def test_csv_export_writes_header_and_one_row_per_txn() -> None:
    from routes.memberships import reports as r

    rows = [{
        "id": "t1", "member_id": "m1", "plan_id": "p1",
        "method": "cash", "amount_pence": 5000,
        "recorded_by": "u-alice",
        "created_at": "2026-05-18T14:30:00+00:00",
        "reference": "rcpt#1", "note": "happy customer",
    }]
    members = [{"id": "m1", "first_name": "Keir", "last_name": "B", "email": "k@x"}]
    operators = [{"id": "u-alice", "first_name": "Alice", "last_name": "B", "email": "a@x"}]
    plans = [{"id": "p1", "name": "5 pack", "credits_count": 5}]
    fake = _build_db(rows, members=members, operators=operators, plans=plans)

    async def _stub_org(u): return "org-1"

    with patch.object(r, "db", fake), \
         patch.object(r, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_org)):
        resp = _run(r.desk_sales_export_csv(
            from_="2026-05-18", to="2026-05-18",
            operator_id=None, method=None,
            user={"id": "u1", "organization_id": "org-1"},
        ))

    # Drain the streaming generator into a string.
    body_chunks = []
    async def _drain():
        async for chunk in resp.body_iterator:
            body_chunks.append(chunk)
    _run(_drain())
    body = "".join(body_chunks)

    reader = csv.reader(io.StringIO(body))
    header = next(reader)
    assert header[0] == "Date"
    assert "Amount (GBP)" in header
    row = next(reader)
    assert row[0] == "2026-05-18"  # Date
    assert row[2] == "Keir B"        # Member
    assert row[4] == "5 pack"        # Plan
    assert row[6] == "cash"          # Method
    assert row[7] == "50.00"         # Amount (5000 pence)
    assert row[8] == "rcpt#1"
    # Only one data row.
    assert next(reader, None) is None
    # Content-Disposition is set to attachment.
    assert "attachment" in resp.headers.get("content-disposition", "").lower()
