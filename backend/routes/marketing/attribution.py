"""Conversion tracking + dashboard v2 (attribution-aware).

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _now_iso,
    _org_id,
)

router = APIRouter()


# ───────────────────────── Conversion Attribution ─────────────────────

@router.post("/marketing/track/conversion")
async def track_conversion(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Called by the bookings/payments services when a member action happens.
    Looks back ATTRIBUTION_WINDOW_DAYS days for the most recent click/open by
    that contact, attributes the conversion + revenue to that message and its
    parent campaign.

    Body: ``{contact_id, kind: 'booking'|'payment', revenue_gbp?, ref_id?}``.
    Internal endpoint — gated to staff but tenant-scoped automatically.
    """
    org_id = await _org_id(user)
    contact_id = body.get("contact_id")
    revenue = float(body.get("revenue_gbp") or 0)
    kind = body.get("kind") or "booking"
    ref_id = body.get("ref_id")
    if not contact_id:
        raise HTTPException(400, "contact_id required")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    msg = await db.marketing_messages.find_one(
        {"organization_id": org_id, "contact_id": contact_id,
         "$or": [{"opened_at": {"$gte": cutoff}}, {"clicked_at": {"$gte": cutoff}}]},
        {"_id": 0, "id": 1, "campaign_id": 1, "attribution": 1},
        sort=[("opened_at", -1)],
    )
    if not msg:
        return {"attributed": False, "reason": "no recent message engagement"}

    await db.marketing_messages.update_one(
        {"id": msg["id"]},
        {"$inc": {"attribution.revenue_gbp": revenue},
         "$push": {"attribution.bookings": {"kind": kind, "ref_id": ref_id, "at": _now_iso(), "revenue_gbp": revenue}}},
    )
    await db.marketing_campaigns.update_one(
        {"id": msg["campaign_id"]},
        {"$inc": {"metrics.converted": 1, "metrics.revenue_gbp": revenue}},
    )
    return {"attributed": True, "campaign_id": msg["campaign_id"], "revenue_gbp": revenue}


# Update the dashboard endpoint to surface attributed revenue from the
# campaigns metrics doc (single aggregation pass).
@router.get("/marketing/dashboard/v2", dependencies=[Depends(require_module("marketing"))])
async def dashboard_v2(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    pipeline = [
        {"$match": {"organization_id": org_id, "sent_at": {"$gte": month_ago}}},
        {"$group": {"_id": None,
                    "campaigns": {"$sum": 1},
                    "sent": {"$sum": "$metrics.sent"},
                    "opened": {"$sum": "$metrics.opened"},
                    "clicked": {"$sum": "$metrics.clicked"},
                    "converted": {"$sum": "$metrics.converted"},
                    "revenue_gbp": {"$sum": "$metrics.revenue_gbp"}}},
    ]
    rollup = {"campaigns": 0, "sent": 0, "opened": 0, "clicked": 0, "converted": 0, "revenue_gbp": 0}
    async for r in db.marketing_campaigns.aggregate(pipeline):
        rollup.update({k: r.get(k, 0) for k in rollup})
    return {
        "campaigns_30d": rollup["campaigns"],
        "messages_sent_30d": rollup["sent"],
        "opens_30d": rollup["opened"],
        "clicks_30d": rollup["clicked"],
        "conversions_30d": rollup["converted"],
        "revenue_attributed_gbp": rollup["revenue_gbp"],
        "open_rate_pct": round((rollup["opened"] / rollup["sent"] * 100) if rollup["sent"] else 0, 1),
        "click_rate_pct": round((rollup["clicked"] / rollup["sent"] * 100) if rollup["sent"] else 0, 1),
        "audiences_total": await db.marketing_audiences.count_documents({"organization_id": org_id}),
        "journeys_active": await db.marketing_journeys.count_documents({"organization_id": org_id, "status": "active"}),
    }
