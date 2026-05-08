"""Master Admin → Collections dashboard.

Single-pane CFO-shaped view of where money is sitting. Reuses the
existing ``org_billing_invoices`` + ``org_billing_payments`` +
``invoice_share_links`` collections — no new schema.

The dashboard handler is intentionally thin orchestration:

  ``collections_dashboard``
   ├── ``_fetch_outstanding_invoices``   – Mongo I/O
   ├── ``_compute_aging_and_rollups``    – pure CPU
   ├── ``_hydrate_top_overdue``          – Mongo I/O (org names)
   └── ``_fetch_reminders_mtd``          – Mongo I/O

Pure-function pieces are trivially unit-testable; I/O pieces are
straightforward to mock.

Returned shape (stable contract — exercised by
``tests/test_collections_dashboard_iter214.py``)::

    {
        "as_of":             iso,
        "currency":          "GBP",
        "total_outstanding": int,
        "buckets":           [4 entries: current / 1_30 / 31_60 / 61_plus],
        "top_overdue":       [up to 10 orgs sorted by balance desc],
        "reminders_mtd":     {total, by_stage{7,14,28}, delivered, skipped}
    }
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────


_BUCKET_META = [
    {"key": "current", "label": "Current",  "min_days": -9999, "max_days": 0},
    {"key": "1_30",    "label": "1 - 30",   "min_days": 1,     "max_days": 30},
    {"key": "31_60",   "label": "31 - 60",  "min_days": 31,    "max_days": 60},
    {"key": "61_plus", "label": "61+",      "min_days": 61,    "max_days": 99999},
]
_DUNNING_STAGES = ("7", "14", "28")


# ── Tiny helpers ────────────────────────────────────────────────────


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _bucket_for(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    return "61_plus"


def _empty_org_rollup(org_id: str, ccy: str) -> dict:
    return {
        "organization_id": org_id,
        "balance": 0,
        "currency": ccy,
        "max_days_overdue": -9999,
        "invoice_count": 0,
        "last_reminded_at": None,
        "reminder_count": 0,
    }


# ── Data fetchers ───────────────────────────────────────────────────


async def _fetch_outstanding_invoices(ccy: str) -> tuple[list[dict], dict[str, int]]:
    """Pull every issued invoice in *ccy* + a per-invoice paid total."""
    invoices = await db.org_billing_invoices.find(
        {"status": "issued", "currency": ccy},
        {"_id": 0},
    ).to_list(length=10000)

    paid_rows = await db.org_billing_payments.aggregate([
        {"$match": {"currency": ccy, "invoice_id": {"$ne": None}}},
        {"$group": {"_id": "$invoice_id", "paid": {"$sum": "$amount"}}},
    ]).to_list(length=10000)
    paid_by_invoice = {r["_id"]: int(r["paid"] or 0) for r in paid_rows}
    return invoices, paid_by_invoice


async def _hydrate_top_overdue(org_rollup: dict[str, dict]) -> list[dict]:
    """Sort by balance desc, take top 10, hydrate org names."""
    top = sorted(
        org_rollup.values(),
        key=lambda r: (r["balance"], r["max_days_overdue"]),
        reverse=True,
    )[:10]
    org_ids = [t["organization_id"] for t in top if t["organization_id"]]
    name_by_id: dict[str, str] = {}
    if org_ids:
        org_docs = await db.organizations.find(
            {"id": {"$in": org_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(length=len(org_ids))
        name_by_id = {o["id"]: o.get("name", "") for o in org_docs}
    for t in top:
        t["organization_name"] = name_by_id.get(t["organization_id"], "—")
        if t["max_days_overdue"] < 0:
            t["max_days_overdue"] = 0  # never surface negative on the UI
    return top


async def _fetch_reminders_mtd(now: datetime) -> dict:
    """Month-to-date dunning telemetry from share-links + audit rows."""
    month_start_iso = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    by_stage = {s: 0 for s in _DUNNING_STAGES}
    share_rows = await db.invoice_share_links.find(
        {"kind": "dunning", "created_at": {"$gte": month_start_iso}},
        {"_id": 0, "stage": 1},
    ).to_list(length=10000)
    for r in share_rows:
        s = str(r.get("stage") or "")
        if s in by_stage:
            by_stage[s] += 1

    delivered, skipped = 0, 0
    audit_cur = db.org_billing_invoices.aggregate([
        {"$unwind": {"path": "$reminders", "preserveNullAndEmptyArrays": False}},
        {"$match": {"reminders.sent_at": {"$gte": month_start_iso}}},
        {"$group": {"_id": "$reminders.delivered", "n": {"$sum": 1}}},
    ])
    async for row in audit_cur:
        n = int(row.get("n") or 0)
        if row.get("_id"):
            delivered += n
        else:
            skipped += n
    return {
        "total": delivered + skipped,
        "by_stage": by_stage,
        "delivered": delivered,
        "skipped": skipped,
    }


# ── Pure computation ────────────────────────────────────────────────


def _apply_invoice_to_rollup(roll: dict, inv: dict, balance: int, days_overdue: int) -> None:
    """Mutate *roll* in place with one invoice's contribution."""
    roll["balance"] += balance
    roll["invoice_count"] += 1
    if days_overdue > roll["max_days_overdue"]:
        roll["max_days_overdue"] = days_overdue
    reminders = inv.get("reminders") or []
    if not reminders:
        return
    roll["reminder_count"] += len(reminders)
    last = reminders[-1].get("sent_at")
    if last and (roll["last_reminded_at"] is None or last > roll["last_reminded_at"]):
        roll["last_reminded_at"] = last


def _compute_aging_and_rollups(
    invoices: list[dict],
    paid_by_invoice: dict[str, int],
    ccy: str,
    now: datetime,
) -> tuple[dict[str, dict], dict[str, dict], int]:
    """Pure: walk invoices once, return (buckets, org_rollup, total)."""
    buckets = {b["key"]: {**b, "count": 0, "amount": 0} for b in _BUCKET_META}
    org_rollup: dict[str, dict] = {}
    total_outstanding = 0

    for inv in invoices:
        total = int(inv.get("total") or 0)
        balance = max(total - paid_by_invoice.get(inv.get("id"), 0), 0)
        if balance == 0:
            continue
        due = _parse_iso(inv.get("due_at"))
        days_overdue = (now - due).days if due else 0

        bkey = _bucket_for(days_overdue)
        buckets[bkey]["count"] += 1
        buckets[bkey]["amount"] += balance
        total_outstanding += balance

        org_id = inv.get("organization_id") or ""
        roll = org_rollup.setdefault(org_id, _empty_org_rollup(org_id, ccy))
        _apply_invoice_to_rollup(roll, inv, balance, days_overdue)

    return buckets, org_rollup, total_outstanding


# ── Public endpoint ─────────────────────────────────────────────────


@router.get("/master-admin/collections/dashboard")
async def collections_dashboard(
    currency: str = "GBP",
    user: dict = Depends(get_current_user),
) -> dict:
    """Aging buckets + top overdue accounts + MTD dunning telemetry."""
    _require_master(user)
    ccy = (currency or "GBP").upper()
    now = _now()

    invoices, paid_by_invoice = await _fetch_outstanding_invoices(ccy)
    buckets, org_rollup, total_outstanding = _compute_aging_and_rollups(
        invoices, paid_by_invoice, ccy, now,
    )
    top_overdue = await _hydrate_top_overdue(org_rollup)
    reminders_mtd = await _fetch_reminders_mtd(now)

    return {
        "as_of": now.isoformat(),
        "currency": ccy,
        "total_outstanding": total_outstanding,
        "buckets": list(buckets.values()),
        "top_overdue": top_overdue,
        "reminders_mtd": reminders_mtd,
    }
