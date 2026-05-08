"""Proactive insights for the operator dashboard.

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
    _now_iso,
    _org_id,
)

router = APIRouter()


# ───────────────────────── Insights (proactive) ─────────────────────────

@router.get("/marketing/insights", dependencies=[Depends(require_module("marketing"))])
async def list_insights(user: dict = Depends(get_current_user)):
    """Synthesise proactive opportunity tiles. Real implementation pulls from
    a nightly aggregator; Phase 1 computes lightweight queries on demand so
    the surface is alive from day 1."""
    org_id = await _org_id(user)
    insights: list[dict] = []

    # 1. Capacity opportunity — under-booked classes (uses memberships data
    #    when present; falls back to a static suggestion otherwise).
    under_booked = await db.class_sessions.find(
        {"organization_id": org_id, "starts_at": {"$gte": _now_iso()},
         "$expr": {"$lt": [{"$size": {"$ifNull": ["$attendees", []]}}, {"$multiply": ["$capacity", 0.5]}]}},
        {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "capacity": 1, "attendees": 1},
    ).limit(3).to_list(length=3)
    for cls in under_booked:
        insights.append({
            "id": f"capacity-{cls['id']}",
            "kind": "capacity",
            "icon": "calendar",
            "title": f"{cls.get('name', 'Class')} is under capacity",
            "body": f"Only {len(cls.get('attendees') or [])} of {cls.get('capacity', 0)} spots booked. Run a free-class promo?",
            "cta": {"label": "Draft a campaign", "action": "draft_campaign", "audience_hint": "inactive_members"},
            "predicted_revenue_uplift_gbp": 280,
        })

    # 2. Churn risk — high-risk contacts not contacted in 14 d.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    risk_count = await db.crm_contacts.count_documents({
        "organization_id": org_id,
        "churn_risk_score": {"$gte": 60},
        "$or": [{"last_marketing_contact_at": {"$lte": cutoff}}, {"last_marketing_contact_at": None}],
    })
    if risk_count > 0:
        insights.append({
            "id": "churn-risk-cohort",
            "kind": "churn_risk",
            "icon": "trending-down",
            "title": f"{risk_count} members at risk of churning",
            "body": "These members haven't been contacted in 14 days and have a churn-risk score over 60.",
            "cta": {"label": "Run win-back journey", "action": "start_journey", "template": "winback"},
            "predicted_revenue_uplift_gbp": min(risk_count * 49, 5_000),
        })

    # 3. Trend — last campaign performance vs 90d average.
    last = await db.marketing_campaigns.find_one(
        {"organization_id": org_id, "status": "sent"},
        {"_id": 0, "id": 1, "name": 1, "metrics": 1, "sent_at": 1},
        sort=[("sent_at", -1)],
    )
    if last:
        opened = (last.get("metrics") or {}).get("opened", 0)
        sent = (last.get("metrics") or {}).get("sent", 0) or 1
        rate = opened / sent
        if rate < 0.10 and sent >= 25:
            insights.append({
                "id": f"perf-{last['id']}",
                "kind": "performance",
                "icon": "alert-triangle",
                "title": f"'{last['name']}' under-performed",
                "body": f"Open rate {round(rate * 100, 1)}% vs your benchmark. Try our AI subject-line optimiser on the next one.",
                "cta": {"label": "Optimise next campaign", "action": "ai_optimise"},
                "predicted_revenue_uplift_gbp": 120,
            })

    # 4. Always-on starter tile if nothing else — keeps the surface useful
    #    on a fresh org.
    if not insights:
        insights.append({
            "id": "welcome-tile",
            "kind": "welcome",
            "icon": "sparkles",
            "title": "Send your first campaign",
            "body": "Start with a welcome email to your most engaged members — we'll AI-draft the copy for you.",
            "cta": {"label": "Quick start", "action": "quickstart"},
            "predicted_revenue_uplift_gbp": 0,
        })

    insights.sort(key=lambda x: x.get("predicted_revenue_uplift_gbp", 0), reverse=True)
    return {"insights": insights}
