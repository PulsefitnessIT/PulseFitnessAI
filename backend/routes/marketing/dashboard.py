"""Marketing dashboard headline counts.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _org_id,
)

router = APIRouter()


# ───────────────────────── Dashboard / Performance ─────────────────────

@router.get("/marketing/dashboard", dependencies=[Depends(require_module("marketing"))])
async def dashboard(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    campaigns_30d = await db.marketing_campaigns.count_documents(
        {"organization_id": org_id, "sent_at": {"$gte": month_ago}},
    )
    sent_30d = 0
    opened_30d = 0
    cursor = db.marketing_campaigns.find(
        {"organization_id": org_id, "sent_at": {"$gte": month_ago}},
        {"_id": 0, "metrics": 1},
    )
    async for c in cursor:
        m = c.get("metrics") or {}
        sent_30d += m.get("sent", 0)
        opened_30d += m.get("opened", 0)
    open_rate = (opened_30d / sent_30d) if sent_30d else 0
    audiences_total = await db.marketing_audiences.count_documents({"organization_id": org_id})
    journeys_active = await db.marketing_journeys.count_documents({"organization_id": org_id, "status": "active"})
    return {
        "campaigns_30d": campaigns_30d,
        "messages_sent_30d": sent_30d,
        "opens_30d": opened_30d,
        "open_rate_pct": round(open_rate * 100, 1),
        "audiences_total": audiences_total,
        "journeys_active": journeys_active,
        "revenue_attributed_gbp": 0,  # Phase 2: real attribution
    }
