"""Payment risk scoring — Phase B (iter 216aa).

Heuristic risk model that ranks members by likelihood of failing their
next charge. Inputs come straight from the existing autopay / dunning
collections (`member_invoices`, `members.autopay_*`).

Score (0-100) is the sum of weighted signals; the band is derived from
the score:
  • ≥ 60 → high
  • ≥ 30 → medium
  • <  30 → low

Signals & weights:
  • Open invoices with balance_pence > 0 (× 30, capped)
  • Days past due on the oldest open invoice (× 0.8)
  • Failed/declined autopay attempts last 90d (× 12 each, capped 36)
  • Autopay disabled when there *is* an active recurring plan (+15)
  • Recent successful payment in last 30d (-10, can go below 0)

Endpoints:
  GET /api/memberships/billing/payment-risk?band=&limit=
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import _require_operator_org

router = APIRouter(tags=["memberships-payment-risk"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _band_for(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


async def _score_member(org_id: str, member: dict, now: datetime) -> dict:
    member_id = member["id"]
    of = {"organization_id": org_id, "member_id": member_id}

    # Open invoices.
    open_inv = await db.member_invoices.find(
        {**of, "status": {"$in": ["open", "overdue", "past_due"]}},
        {"_id": 0, "id": 1, "balance_pence": 1, "amount_pence": 1,
         "due_at": 1, "created_at": 1},
    ).to_list(50)
    open_balance = sum(int(i.get("balance_pence") or i.get("amount_pence") or 0) for i in open_inv)
    open_count = len(open_inv)
    days_past_due = 0
    for i in open_inv:
        due = i.get("due_at") or i.get("created_at")
        if not due:
            continue
        try:
            d = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            delta = (now - d).days
            if delta > days_past_due:
                days_past_due = delta
        except Exception:
            continue

    # Recent failed autopay attempts (last 90d).
    horizon_iso = (now - timedelta(days=90)).isoformat()
    failed = await db.autopay_attempts.count_documents({
        **of, "ok": False, "at": {"$gte": horizon_iso},
    })
    succeeded_30 = await db.autopay_attempts.count_documents({
        **of, "ok": True, "at": {"$gte": (now - timedelta(days=30)).isoformat()},
    })

    autopay_enabled = bool(member.get("autopay_enabled"))
    has_active_plan = await db.member_memberships.find_one(
        {**of, "status": "active", "kind": {"$in": ["recurring", "monthly"]}},
        {"_id": 0, "id": 1},
    )

    score = 0.0
    reasons: list[str] = []
    if open_balance > 0:
        bump = min(30, 8 + open_count * 8)
        score += bump
        reasons.append(
            f"£{open_balance / 100:,.2f} outstanding "
            f"({open_count} open invoice{'s' if open_count != 1 else ''})"
        )
    if days_past_due > 0:
        score += min(40, days_past_due * 0.8)
        reasons.append(f"{days_past_due} day{'s' if days_past_due != 1 else ''} past due")
    if failed > 0:
        score += min(36, failed * 12)
        reasons.append(f"{failed} failed autopay attempt{'s' if failed != 1 else ''} (90d)")
    if not autopay_enabled and has_active_plan:
        score += 15
        reasons.append("Autopay disabled but member has an active recurring plan")
    if succeeded_30 > 0:
        score -= 10
        reasons.append("Successful payment in last 30 days (lowers risk)")

    score_int = max(0, min(100, int(round(score))))
    return {
        "member_id": member_id,
        "member_name": (
            f"{member.get('first_name') or ''} {member.get('last_name') or ''}".strip()
            or member.get("email") or "(unknown)"
        ),
        "member_email": member.get("email"),
        "score": score_int,
        "band": _band_for(score_int),
        "reasons": reasons,
        "open_balance_pence": open_balance,
        "open_invoice_count": open_count,
        "days_past_due": days_past_due,
        "failed_autopay_90d": failed,
        "autopay_enabled": autopay_enabled,
    }


@router.get(
    "/memberships/billing/payment-risk",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_payment_risk(
    band: Optional[str] = Query(None, pattern="^(low|medium|high)$"),
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    now = _now()
    members = await db.members.find(
        {"organization_id": org_id, "status": {"$ne": "cancelled"}},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1,
         "autopay_enabled": 1},
    ).to_list(2000)

    rows: list[dict] = []
    for m in members:
        row = await _score_member(org_id, m, now)
        if band and row["band"] != band:
            continue
        if row["score"] <= 0 and row["open_balance_pence"] == 0 and row["failed_autopay_90d"] == 0:
            # Skip "obviously fine" members to keep the table actionable.
            continue
        rows.append(row)

    rows.sort(key=lambda r: (-r["score"], -r["open_balance_pence"]))
    rows = rows[:limit]
    summary = {
        "high": sum(1 for r in rows if r["band"] == "high"),
        "medium": sum(1 for r in rows if r["band"] == "medium"),
        "low": sum(1 for r in rows if r["band"] == "low"),
        "total_open_balance_pence": sum(r["open_balance_pence"] for r in rows),
    }
    return {"rows": rows, "count": len(rows), "summary": summary,
            "scored_at": now.isoformat()}


__all__ = ["router"]
