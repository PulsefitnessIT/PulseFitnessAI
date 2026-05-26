"""Iter 220l — Engineer self-service ratings view.

The Public Engineer Card already exposes ratings to potential
customers. Engineers themselves had no view of their reputation
INSIDE the Engineer App — making it impossible to spot a bad-review
trend before it becomes a churn cliff.

This endpoint aggregates customer ratings on `svc_cases` the
authenticated engineer has been assigned to, returning:

  * `summary.avg` — overall average (rounded to 2 dp)
  * `summary.count` — total ratings
  * `summary.distribution` — `{1: n, 2: n, …, 5: n}`
  * `summary.last_30d_avg` — rolling avg for the last 30 days (so
     trends are obvious)
  * `ratings` — most-recent-first list of `{case_id, reference,
     rating, comment, customer_name, rated_at, closed_at, site_name}`
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer ratings (iter 220l)"],
)


@router.get("/me/ratings")
async def my_ratings(
    user: dict = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
):
    eng_id = user["id"]
    match = {
        "assigned_engineer_id": eng_id,
        "customer_rating": {"$gte": 1},
    }
    # Distribution + average
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$customer_rating",
            "n": {"$sum": 1},
        }},
    ]
    rows = await db.svc_cases.aggregate(pipeline).to_list(20)
    distribution = {str(i): 0 for i in range(1, 6)}
    total = 0
    weighted = 0.0
    for r in rows:
        k = int(r["_id"])
        distribution[str(k)] = int(r["n"])
        total += int(r["n"])
        weighted += k * int(r["n"])
    avg = round(weighted / total, 2) if total else None

    # 30-day rolling
    thirty_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    last_30d_avg_rows = await db.svc_cases.aggregate([
        {"$match": {**match, "customer_feedback_at": {"$gte": thirty_ago}}},
        {"$group": {"_id": None, "avg": {"$avg": "$customer_rating"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    last_30d_avg = (
        round(float(last_30d_avg_rows[0]["avg"]), 2)
        if last_30d_avg_rows and last_30d_avg_rows[0].get("avg") is not None
        else None
    )
    last_30d_count = int(last_30d_avg_rows[0]["n"]) if last_30d_avg_rows else 0

    # The list itself — most recent first by feedback time then closed_at.
    docs = await db.svc_cases.find(
        match,
        {
            "_id": 0,
            "id": 1, "reference": 1, "title": 1,
            "customer_rating": 1, "customer_rating_comment": 1,
            "customer_name": 1, "site_name": 1,
            "customer_feedback_at": 1, "closed_at": 1,
        },
    ).sort([("customer_feedback_at", -1), ("closed_at", -1)]).limit(limit).to_list(limit)

    ratings = [
        {
            "case_id": d["id"],
            "reference": d.get("reference"),
            "title": d.get("title"),
            "rating": int(d.get("customer_rating") or 0),
            "comment": d.get("customer_rating_comment") or "",
            "customer_name": d.get("customer_name") or "",
            "site_name": d.get("site_name") or "",
            "rated_at": d.get("customer_feedback_at"),
            "closed_at": d.get("closed_at"),
        }
        for d in docs
    ]

    return {
        "summary": {
            "avg": avg,
            "count": total,
            "distribution": distribution,
            "last_30d_avg": last_30d_avg,
            "last_30d_count": last_30d_count,
        },
        "ratings": ratings,
    }


__all__ = ["router"]
