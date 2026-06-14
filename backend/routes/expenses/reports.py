"""Expenses — dashboards, reports, accounting export & job linking (iter 278)."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response

from utils.auth import get_current_user
from utils.database import db

from .common import (
    router, org_of, can_review, scope_filter, now_iso, audit,
    DRAFT, SUBMITTED, NEEDS_DETAILS, APPROVED, REJECTED, REIMBURSED, EXPORTED,
)


@router.get("/dashboard")
async def expenses_dashboard(user=Depends(get_current_user)):
    org_id = org_of(user)
    reviewer = can_review(user)
    mine = {"organization_id": org_id, "user_id": user.get("id")}

    async def _sum(q):
        rows = await db.expenses.find(q, {"_id": 0, "gross_amount": 1}).to_list(2000)
        return round(sum(r.get("gross_amount") or 0 for r in rows), 2), len(rows)

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_total, _ = await _sum({**mine, "created_at": {"$gte": month_start},
                                 "status": {"$nin": ["cancelled"]}})
    mileage_total, _ = await _sum({**mine, "expense_type": "mileage",
                                   "created_at": {"$gte": month_start}})

    me = {
        "drafts": await db.expenses.count_documents({**mine, "status": DRAFT}),
        "submitted": await db.expenses.count_documents({**mine, "status": SUBMITTED}),
        "needs_details": await db.expenses.count_documents({**mine, "status": NEEDS_DETAILS}),
        "approved": await db.expenses.count_documents({**mine, "status": APPROVED}),
        "reimbursed": await db.expenses.count_documents({**mine, "status": REIMBURSED}),
        "month_total": month_total,
        "mileage_total": mileage_total,
    }

    out = {"me": me, "can_review": reviewer}
    if reviewer:
        org = {"organization_id": org_id}
        awaiting_reimb, _ = await _sum({**org, "status": APPROVED})
        vat_rows = await db.expenses.find(
            {**org, "status": {"$in": [APPROVED, EXPORTED, REIMBURSED]}},
            {"_id": 0, "tax_amount": 1}).to_list(5000)
        out["team"] = {
            "awaiting_approval": await db.expenses.count_documents({**org, "status": SUBMITTED}),
            "needs_details": await db.expenses.count_documents({**org, "status": NEEDS_DETAILS}),
            "approved_awaiting_reimbursement": await db.expenses.count_documents({**org, "status": APPROVED}),
            "awaiting_reimbursement_total": awaiting_reimb,
            "vat_total": round(sum(r.get("tax_amount") or 0 for r in vat_rows), 2),
            "missing_receipts": await db.expenses.count_documents(
                {**org, "expense_type": {"$in": ["receipt", "out_of_pocket"]},
                 "receipt_paths": {"$in": [None, []]},
                 "status": {"$in": [SUBMITTED, NEEDS_DETAILS]}}),
        }
    return out


@router.get("/reports")
async def expenses_reports(
    group_by: str = Query("category"),  # category|country|user|customer|job|status
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    user=Depends(get_current_user),
):
    q = scope_filter(user)
    if status and status != "all":
        q["status"] = {"$in": status.split(",")}
    else:
        q["status"] = {"$ne": "cancelled"}
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["transaction_date"] = rng

    key_map = {
        "category": ("category_name", "Uncategorised"),
        "country": ("country_code", "—"),
        "user": ("user_name", "—"),
        "customer": ("customer_name", "No customer"),
        "job": ("job_reference", "No job"),
        "status": ("status", "—"),
        "currency": ("currency", "—"),
    }
    field, fallback = key_map.get(group_by, key_map["category"])
    rows = await db.expenses.find(
        q, {"_id": 0, field: 1, "gross_amount": 1, "tax_amount": 1, "currency": 1}
    ).to_list(5000)

    groups: dict = defaultdict(lambda: {"label": "", "count": 0, "gross": 0.0, "tax": 0.0})
    total_gross = total_tax = 0.0
    for r in rows:
        label = r.get(field) or fallback
        g = groups[label]
        g["label"] = label
        g["count"] += 1
        g["gross"] += r.get("gross_amount") or 0
        g["tax"] += r.get("tax_amount") or 0
        total_gross += r.get("gross_amount") or 0
        total_tax += r.get("tax_amount") or 0
    result = sorted(
        [{"label": v["label"], "count": v["count"],
          "gross": round(v["gross"], 2), "tax": round(v["tax"], 2)} for v in groups.values()],
        key=lambda x: x["gross"], reverse=True)
    return {
        "group_by": group_by, "rows": result,
        "totals": {"count": len(rows), "gross": round(total_gross, 2), "tax": round(total_tax, 2)},
    }


@router.get("/job/{job_id}")
async def job_expenses(job_id: str, user=Depends(get_current_user)):
    """Expenses linked to a job (job-profitability integration)."""
    q = {"organization_id": org_of(user), "job_id": job_id}
    if not can_review(user):
        q["user_id"] = user.get("id")
    rows = await db.expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    active = [r for r in rows if r.get("status") != "cancelled"]
    return {
        "expenses": rows,
        "summary": {
            "total": round(sum(r.get("gross_amount") or 0 for r in active), 2),
            "approved": round(sum(r.get("gross_amount") or 0 for r in active if r.get("status") in (APPROVED, EXPORTED, REIMBURSED)), 2),
            "unapproved": round(sum(r.get("gross_amount") or 0 for r in active if r.get("status") in (DRAFT, SUBMITTED, NEEDS_DETAILS)), 2),
            "billable": round(sum(r.get("gross_amount") or 0 for r in active if r.get("billable_to_customer")), 2),
            "count": len(active),
        },
    }


_EXPORT_COLUMNS = [
    ("reference", "Expense ID"), ("user_name", "Employee"), ("user_id", "Employee Code"),
    ("country_code", "Country"), ("currency", "Currency"), ("category_name", "Category"),
    ("accounting_code", "Accounting Code"), ("payroll_code", "Payroll Code"),
    ("merchant", "Merchant"), ("merchant_country", "Merchant Country"),
    ("transaction_date", "Transaction Date"), ("submitted_date", "Submitted Date"),
    ("gross_amount", "Gross"), ("net_amount", "Net"), ("tax_amount", "Tax"),
    ("tax_rate", "Tax Rate"), ("status", "Status"), ("reviewer_name", "Reviewer"),
    ("review_note", "Review Note"), ("reimbursed_at", "Reimbursed Date"),
    ("job_reference", "Job"), ("customer_name", "Customer"), ("site_name", "Site"),
    ("description", "Description"),
]


@router.get("/export.csv")
async def export_expenses_csv(
    status: str = Query("approved"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    mark_exported: bool = Query(True),
    user=Depends(get_current_user),
):
    if not can_review(user):
        raise HTTPException(403, "Finance access required")
    org_id = org_of(user)
    q = {"organization_id": org_id}
    if status and status != "all":
        q["status"] = {"$in": status.split(",")}
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["transaction_date"] = rng
    rows = await db.expenses.find(q, {"_id": 0}).sort("transaction_date", 1).to_list(10000)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([h for _, h in _EXPORT_COLUMNS])
    for r in rows:
        w.writerow([r.get(k, "") if r.get(k) is not None else "" for k, _ in _EXPORT_COLUMNS])

    if mark_exported and rows:
        ids = [r["id"] for r in rows if r.get("status") == APPROVED]
        if ids:
            await db.expenses.update_many(
                {"id": {"$in": ids}, "organization_id": org_id},
                {"$set": {"status": EXPORTED, "export_status": "exported",
                          "exported_at": now_iso(), "locked": True, "updated_at": now_iso()}})
            for rid in ids:
                await audit({"id": rid, "organization_id": org_id}, user, "exported", new="exported")

    fname = f"expenses-export-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
