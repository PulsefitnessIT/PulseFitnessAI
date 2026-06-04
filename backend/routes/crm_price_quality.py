"""CRM · Master Price List — data-quality dashboard + reporting (Iter 220 P1).

A single health view over the catalogue: missing Sage codes / prices /
categories, low-margin items, cost > sell, duplicate codes, obsolete,
never-quoted, unmapped data, recently re-priced — with drill-down lists,
per-issue CSV reports and a by-category margin breakdown.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response

from utils.database import db
from routes.crm_auth import get_crm_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/price-list", tags=["CRM Price List · Quality"])

OBSOLETE_STATUSES = ["obsolete", "discontinued"]

ISSUES = {
    "missing_sage": "Missing Sage code",
    "missing_sell": "Missing sell price",
    "missing_cost": "Missing cost price",
    "no_category": "Missing category",
    "low_margin": "Low margin",
    "cost_gt_sell": "Cost above sell",
    "duplicate_sku": "Duplicate product code",
    "obsolete": "Obsolete / discontinued",
    "never_quoted": "Never quoted",
    "with_unmapped": "Has imported data",
    "recently_changed": "Recently re-priced",
}


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


async def _threshold(user: dict) -> float:
    s = await db.crm_price_list_settings.find_one(_of(user), {"_id": 0, "margin_threshold_pct": 1})
    try:
        return float((s or {}).get("margin_threshold_pct", 10))
    except (TypeError, ValueError):
        return 10.0


async def _quoted_ids(user: dict) -> list[str]:
    pipe = [
        {"$match": _of(user)},
        {"$unwind": "$lines"},
        {"$group": {"_id": "$lines.product_id"}},
    ]
    ids = [d["_id"] async for d in db.crm2_quotes.aggregate(pipe) if d.get("_id")]
    return ids


async def _duplicate_skus(user: dict) -> list[str]:
    pipe = [
        {"$match": {**_of(user), "active": True, "sku": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$sku", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    return [d["_id"] async for d in db.crm_products.aggregate(pipe)]


def _issue_query(issue: str, threshold: float, dup_skus: list[str], quoted_ids: list[str]) -> dict:
    base = {"active": True}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    if issue == "missing_sage":
        return {**base, "$or": [{"sage_code": {"$exists": False}}, {"sage_code": ""}]}
    if issue == "missing_sell":
        return {**base, "sell_price": {"$lte": 0}}
    if issue == "missing_cost":
        return {**base, "cost_price": {"$lte": 0}}
    if issue == "no_category":
        return {**base, "$or": [{"category": {"$exists": False}}, {"category": ""}]}
    if issue == "low_margin":
        safe_sell = {"$cond": [{"$gt": ["$sell_price", 0]}, "$sell_price", 1]}
        return {**base, "sell_price": {"$gt": 0},
                "$expr": {"$lt": [{"$multiply": [{"$divide": [{"$subtract": ["$sell_price", "$cost_price"]}, safe_sell]}, 100]}, threshold]}}
    if issue == "cost_gt_sell":
        return {**base, "sell_price": {"$gt": 0}, "$expr": {"$gt": ["$cost_price", "$sell_price"]}}
    if issue == "duplicate_sku":
        return {**base, "sku": {"$in": dup_skus}} if dup_skus else {**base, "sku": "\x00__none__"}
    if issue == "obsolete":
        return {**base, "status": {"$in": OBSOLETE_STATUSES}}
    if issue == "never_quoted":
        return {**base, "id": {"$nin": quoted_ids}}
    if issue == "with_unmapped":
        return {**base, "unmapped_fields.0": {"$exists": True}}
    if issue == "recently_changed":
        return {**base, "price_history": {"$elemMatch": {"at": {"$gte": cutoff}}}}
    raise HTTPException(422, "Unknown issue")


@router.get("/quality")
async def quality_dashboard(user=Depends(get_crm_user)) -> dict:
    of = _of(user)
    threshold = await _threshold(user)
    dup_skus = await _duplicate_skus(user)
    quoted_ids = await _quoted_ids(user)

    total = await db.crm_products.count_documents({**of, "active": True})
    archived = await db.crm_products.count_documents({**of, "active": False})

    counts = {}
    for key in ISSUES:
        q = _issue_query(key, threshold, dup_skus, quoted_ids)
        counts[key] = await db.crm_products.count_documents({**of, **q})

    # by-category breakdown (count + avg margin)
    by_cat_pipe = [
        {"$match": {**of, "active": True}},
        {"$group": {
            "_id": {"$ifNull": ["$category", "Uncategorised"]},
            "count": {"$sum": 1},
            "avg_margin": {"$avg": {"$cond": [{"$gt": ["$sell_price", 0]},
                          {"$multiply": [{"$divide": [{"$subtract": ["$sell_price", "$cost_price"]}, "$sell_price"]}, 100]}, None]}},
            "total_sell": {"$sum": "$sell_price"},
        }},
        {"$sort": {"count": -1}},
    ]
    by_category = []
    async for d in db.crm_products.aggregate(by_cat_pipe):
        by_category.append({
            "category": d["_id"], "count": d["count"],
            "avg_margin": round(d["avg_margin"], 1) if d.get("avg_margin") is not None else None,
            "total_sell": round(d.get("total_sell", 0) or 0, 2),
        })

    # health score: % of products with NO blocking issue (distinct count,
    # so a product with several issues isn't penalised multiple times).
    blocker_or = [
        {"$or": [{"sage_code": {"$exists": False}}, {"sage_code": ""}]},
        {"sell_price": {"$lte": 0}},
        {"$or": [{"category": {"$exists": False}}, {"category": ""}]},
        {"sell_price": {"$gt": 0}, "$expr": {"$gt": ["$cost_price", "$sell_price"]}},
    ]
    blocked = await db.crm_products.count_documents({**of, "active": True, "$or": blocker_or})
    health = 100 if total == 0 else max(0, round((1 - blocked / total) * 100))
    return {
        "total": total, "archived": archived,
        "margin_threshold": threshold,
        "counts": counts, "labels": ISSUES,
        "by_category": by_category,
        "health_score": health, "blocked_count": blocked,
    }


@router.get("/quality/list")
async def quality_list(issue: str, skip: int = 0, limit: int = 50, user=Depends(get_crm_user)) -> dict:
    of = _of(user)
    threshold = await _threshold(user)
    dup_skus = await _duplicate_skus(user) if issue == "duplicate_sku" else []
    quoted_ids = await _quoted_ids(user) if issue == "never_quoted" else []
    q = {**of, **_issue_query(issue, threshold, dup_skus, quoted_ids)}
    total = await db.crm_products.count_documents(q)
    cur = db.crm_products.find(q, {"_id": 0, "id": 1, "sku": 1, "name": 1, "category": 1,
                                   "sage_code": 1, "cost_price": 1, "sell_price": 1, "status": 1}).sort([("category", 1), ("sku", 1)]).skip(skip).limit(limit)
    items = []
    async for p in cur:
        sell = float(p.get("sell_price") or 0)
        cost = float(p.get("cost_price") or 0)
        p["margin_percent"] = round((sell - cost) / sell * 100, 1) if sell > 0 else 0
        items.append(p)
    return {"issue": issue, "label": ISSUES.get(issue, issue), "total": total, "items": items, "skip": skip, "limit": limit}


@router.get("/quality/report.csv")
async def quality_report_csv(issue: str, user=Depends(get_crm_user)):
    of = _of(user)
    threshold = await _threshold(user)
    dup_skus = await _duplicate_skus(user) if issue == "duplicate_sku" else []
    quoted_ids = await _quoted_ids(user) if issue == "never_quoted" else []
    q = {**of, **_issue_query(issue, threshold, dup_skus, quoted_ids)}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Product Code", "Name", "Category", "Sage Code", "Cost Price", "Sell Price", "Margin %", "Status"])
    cur = db.crm_products.find(q, {"_id": 0}).sort([("category", 1), ("sku", 1)])
    async for p in cur:
        sell = float(p.get("sell_price") or 0)
        cost = float(p.get("cost_price") or 0)
        margin = round((sell - cost) / sell * 100, 1) if sell > 0 else 0
        w.writerow([p.get("sku", ""), p.get("name", ""), p.get("category", ""), p.get("sage_code", ""),
                    cost, sell, margin, p.get("status", "")])
    fname = f"quality_{issue}_{datetime.now(timezone.utc):%Y%m%d}.csv"
    return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
