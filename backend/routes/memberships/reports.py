"""Front-desk sales reconciliation — iter 216h204.

Closes the cash-handling audit loop opened by iter 216h203. Operators
need to be able to:

  * See every pack sold at the desk (cash / card terminal / bank
    transfer / comp / other) for a given date range.
  * Filter by operator (who took the money) and method.
  * Get a summary by method so the Z-report on the cash drawer ties
    out to the system.
  * Export to CSV for handing to the bookkeeper or Sage.

Endpoints
---------
* ``GET  /api/memberships/reports/desk-sales``         JSON
* ``GET  /api/memberships/reports/desk-sales/export.csv``  CSV download

Filters: ``from`` (ISO date YYYY-MM-DD, inclusive), ``to`` (inclusive),
``operator_id`` (optional), ``method`` (optional).
Default range when neither ``from`` nor ``to`` is supplied = today
(operator's local date — we use UTC and let the frontend translate).
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from routes.memberships.helpers import _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-reports"])


def _parse_iso_date(s: str, *, end_of_day: bool = False) -> datetime:
    """Tolerant parser: 'YYYY-MM-DD' or full ISO. UTC."""
    try:
        if "T" in s:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_of_day:
            d += timedelta(days=1, microseconds=-1)
        return d
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"Invalid date format: {s!r}. Use YYYY-MM-DD.") from exc


async def _build_query(
    org_id: str,
    *,
    from_: Optional[str],
    to: Optional[str],
    operator_id: Optional[str],
    method: Optional[str],
) -> dict:
    """Shared filter builder for the JSON + CSV endpoints."""
    today = datetime.now(timezone.utc)
    start = _parse_iso_date(from_) if from_ else today.replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    end = _parse_iso_date(to, end_of_day=True) if to else today.replace(
        hour=23, minute=59, second=59, microsecond=999999,
    )
    if start > end:
        raise HTTPException(400, "`from` must be ≤ `to`.")
    q: dict = {
        "organization_id": org_id,
        "kind": "credit_pack_desk",
        "created_at": {"$gte": start.isoformat(), "$lte": end.isoformat()},
    }
    if operator_id:
        q["recorded_by"] = operator_id
    if method:
        ALLOWED = {"cash", "card_terminal", "bank_transfer", "comp", "other"}
        if method not in ALLOWED:
            raise HTTPException(400, f"method must be one of {sorted(ALLOWED)}")
        q["method"] = method
    return q


async def _hydrate_rows(rows: list[dict], org_id: str) -> list[dict]:
    """Attach member name + operator name + plan name to each row."""
    if not rows:
        return rows
    member_ids = list({r.get("member_id") for r in rows if r.get("member_id")})
    operator_ids = list({r.get("recorded_by") for r in rows if r.get("recorded_by")})
    plan_ids = list({r.get("plan_id") for r in rows if r.get("plan_id")})

    members = await db.members.find(
        {"id": {"$in": member_ids}, "organization_id": org_id},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    ).to_list(len(member_ids)) if member_ids else []
    operators = await db.users.find(
        {"id": {"$in": operator_ids}},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    ).to_list(len(operator_ids)) if operator_ids else []
    plans = await db.membership_plans.find(
        {"id": {"$in": plan_ids}, "organization_id": org_id},
        {"_id": 0, "id": 1, "name": 1, "credits_count": 1},
    ).to_list(len(plan_ids)) if plan_ids else []

    m_by_id = {m["id"]: m for m in members}
    o_by_id = {o["id"]: o for o in operators}
    p_by_id = {p["id"]: p for p in plans}

    def _fullname(u: dict) -> str:
        if not u:
            return ""
        fn = (u.get("first_name") or "").strip()
        ln = (u.get("last_name") or "").strip()
        return (f"{fn} {ln}".strip()) or u.get("email") or ""

    for r in rows:
        m = m_by_id.get(r.get("member_id")) or {}
        o = o_by_id.get(r.get("recorded_by")) or {}
        p = p_by_id.get(r.get("plan_id")) or {}
        r["member_name"] = _fullname(m)
        r["member_email"] = m.get("email") or ""
        r["operator_name"] = _fullname(o)
        r["plan_name"] = p.get("name") or ""
        r["credits_added"] = int(p.get("credits_count") or 0)
    return rows


# ═══════════════════════ JSON endpoint ═══════════════════════


@router.get(
    "/memberships/reports/desk-sales",
    dependencies=[Depends(require_module("memberships"))],
)
async def desk_sales_report(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    operator_id: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    user: dict = Depends(get_current_user),
) -> dict:
    org_id = await _require_operator_org(user)
    q = await _build_query(
        org_id, from_=from_, to=to, operator_id=operator_id, method=method,
    )
    rows = await db.payment_transactions.find(q, {"_id": 0}).sort(
        "created_at", -1,
    ).to_list(limit)
    rows = await _hydrate_rows(rows, org_id)

    # Summary: total £, count, by method.
    total_pence = sum(int(r.get("amount_pence") or 0) for r in rows)
    by_method: dict[str, dict] = {}
    for r in rows:
        m = r.get("method") or "other"
        bucket = by_method.setdefault(m, {"count": 0, "total_pence": 0})
        bucket["count"] += 1
        bucket["total_pence"] += int(r.get("amount_pence") or 0)

    # Operator leaderboard (top 5 by £).
    by_operator: dict[str, dict] = {}
    for r in rows:
        op = r.get("recorded_by") or "unknown"
        bucket = by_operator.setdefault(
            op, {"operator_id": op, "operator_name": r.get("operator_name") or "—",
                  "count": 0, "total_pence": 0},
        )
        bucket["count"] += 1
        bucket["total_pence"] += int(r.get("amount_pence") or 0)
    top_operators = sorted(
        by_operator.values(), key=lambda b: b["total_pence"], reverse=True,
    )[:5]

    return {
        "rows": rows,
        "summary": {
            "count": len(rows),
            "total_pence": total_pence,
            "by_method": by_method,
            "top_operators": top_operators,
        },
        "filters": {
            "from": from_, "to": to,
            "operator_id": operator_id, "method": method,
        },
    }


# ═══════════════════════ CSV export ═══════════════════════


@router.get(
    "/memberships/reports/desk-sales/export.csv",
    dependencies=[Depends(require_module("memberships"))],
)
async def desk_sales_export_csv(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    operator_id: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Stream the same data as the JSON endpoint but as a CSV for the
    bookkeeper / Sage import. No limit clamp — bookkeepers want the
    full month."""
    org_id = await _require_operator_org(user)
    q = await _build_query(
        org_id, from_=from_, to=to, operator_id=operator_id, method=method,
    )
    rows = await db.payment_transactions.find(q, {"_id": 0}).sort(
        "created_at", -1,
    ).to_list(50_000)  # 50k rows = ~5 years of daily desk sales
    rows = await _hydrate_rows(rows, org_id)

    def _generate():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "Date", "Time (UTC)", "Member", "Member email", "Plan",
            "Credits added", "Method", "Amount (GBP)", "Reference",
            "Note", "Operator", "Transaction ID",
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for r in rows:
            created_iso = r.get("created_at") or ""
            try:
                d = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
                date_str = d.strftime("%Y-%m-%d")
                time_str = d.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                date_str = created_iso[:10]
                time_str = created_iso[11:19]
            w.writerow([
                date_str, time_str,
                r.get("member_name") or "",
                r.get("member_email") or "",
                r.get("plan_name") or "",
                r.get("credits_added") or 0,
                r.get("method") or "",
                f"{int(r.get('amount_pence') or 0) / 100:.2f}",
                r.get("reference") or "",
                r.get("note") or "",
                r.get("operator_name") or "",
                r.get("id") or "",
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"desk-sales-{from_ or 'today'}-{to or 'today'}.csv"
    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
