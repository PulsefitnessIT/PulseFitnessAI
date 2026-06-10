"""
Master Admin · CRM analytics sub-router.

Iter 216h181 — Extracted from `routes/master_admin.py` as phase 5b of
the 4,283 LoC → focused-routers decomposition.

Owns the Master-Admin CRM analytics surface:
    GET /master-admin/crm-analytics

The single route stitches together 14 private analytic helpers that
each query a slice of `crm2_*` collections:
    _crm_pipeline_analytics       — opps by stage + win-rate
    _crm_entity_counts            — contacts / companies / activities / cases / assets
    _crm_quote_analytics          — quote pipeline (draft/sent/accepted)
    _crm_workflow_stats           — workflow + tender activity
    _crm_user_and_activity_stats  — role distribution + activity type breakdown
    _crm_top_deals_at_risk        — top at-risk deals (probability / stale / past-due)
    _crm_renewals_due             — upcoming close dates in a window
    _crm_ai_usage_block           — AI assistant usage roll-up

Legacy v1 helpers (preserved verbatim for backwards-compat with any future
caller that may consume them — currently dead code in the v2 endpoint):
    _aggregate_cursor_values, _count_by_field_cursor, _get_pipeline_stages,
    _get_lead_score_distribution, _get_crm_overview, _get_crm_growth,
    _get_sage_status

Shared helper (`require_master_admin`) is imported from
`routes.master_admin` because it's used by ~12 other modules.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import require_master_admin


router = APIRouter()


# ───────────── legacy v1 helpers (preserved verbatim) ─────────────

async def _aggregate_cursor_values(cursor, field: str) -> int:
    """Sum a numeric field across all documents in an async cursor."""
    total = 0
    async for doc in cursor:
        total += doc.get(field, 0)
    return total


async def _count_by_field_cursor(cursor, field: str) -> dict[str, int]:
    """Group-count documents by a field from an async cursor."""
    counts: dict[str, int] = {}
    async for doc in cursor:
        key = doc.get(field, "unknown") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


async def _get_pipeline_stages() -> list[dict]:
    """Platform-wide pipeline stage rollup with deal counts and values.

    Pipelines are now org-scoped (SEC-008) so there is no single global
    pipeline doc; this master view uses the canonical stage template and
    counts deals across all tenants by stage id.
    """
    from utils.crm_pipeline import DEFAULT_PIPELINE_STAGES
    stages = []
    for stage in DEFAULT_PIPELINE_STAGES:
        count = await db.crm_deals.count_documents({"stage": stage["id"]})
        total_value = await _aggregate_cursor_values(
            db.crm_deals.find({"stage": stage["id"]}, {"_id": 0, "value": 1}), "value",
        )
        stages.append({
            "id": stage["id"], "name": stage["name"],
            "color": stage.get("color", "#007AFF"), "count": count, "value": total_value,
        })
    return stages


async def _get_lead_score_distribution() -> dict[str, int]:
    """Classify contacts into hot/warm/cold/unscored buckets."""
    ranges: dict[str, int] = {"hot": 0, "warm": 0, "cold": 0, "unscored": 0}
    async for c in db.crm_contacts.find({}, {"_id": 0, "lead_score": 1}):
        score = c.get("lead_score")
        if score is None:
            ranges["unscored"] += 1
        elif score >= 70:
            ranges["hot"] += 1
        elif score >= 40:
            ranges["warm"] += 1
        else:
            ranges["cold"] += 1
    return ranges


async def _get_crm_overview() -> dict:
    """Core CRM entity counts."""
    return {
        "total_contacts": await db.crm_contacts.count_documents({}),
        "total_companies": await db.crm_companies.count_documents({}),
        "total_deals": await db.crm_deals.count_documents({}),
        "total_users": await db.crm_users.count_documents({}),
        "total_conversations": await db.crm_conversations.count_documents({}),
        "total_workflows": await db.crm_workflows.count_documents({}),
        "active_workflows": await db.crm_workflows.count_documents({"active": True}),
        "total_quotes": await db.crm_quotes.count_documents({}),
        "total_meetings": await db.crm_meetings.count_documents({}),
        "total_activities": await db.crm_activities.count_documents({}),
    }


async def _get_crm_growth() -> dict:
    """CRM growth metrics for 7d and 30d windows."""
    thirty = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    seven = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return {
        "new_contacts_30d": await db.crm_contacts.count_documents({"created_at": {"$gte": thirty}}),
        "new_deals_30d": await db.crm_deals.count_documents({"created_at": {"$gte": thirty}}),
        "new_contacts_7d": await db.crm_contacts.count_documents({"created_at": {"$gte": seven}}),
        "recent_activities_30d": await db.crm_activities.count_documents({"created_at": {"$gte": thirty}}),
    }


async def _get_sage_status() -> dict:
    """Check Sage 200 integration status."""
    sage_config = await db.crm_integrations.find_one({"type": "sage200"}, {"_id": 0})
    if not sage_config:
        return {"status": "not_configured", "last_sync": None}
    status = "connected" if sage_config.get("access_token") else "configured"
    return {"status": status, "last_sync": sage_config.get("last_sync")}


# ───────────── v2 (active) helpers ─────────────

async def _crm_pipeline_analytics() -> dict:
    """Fetch pipeline metrics for master admin analytics."""
    active_opps = await db.crm2_opportunities.find(
        {"stage": {"$nin": ["closed_won", "closed_lost"]}}, {"_id": 0, "value": 1, "weighted_value": 1, "stage": 1}
    ).to_list(500)
    won_opps = await db.crm2_opportunities.find({"stage": "closed_won"}, {"_id": 0, "value": 1}).to_list(500)
    lost_count = await db.crm2_opportunities.count_documents({"stage": "closed_lost"})
    won_count = len(won_opps)
    total_closed = won_count + lost_count
    stage_counts = {}
    for o in active_opps:
        s = o.get("stage", "lead")
        stage_counts[s] = stage_counts.get(s, 0) + 1
    return {
        "stages": [{"stage": k, "count": v} for k, v in stage_counts.items()],
        "won_deals": won_count, "lost_deals": lost_count,
        "total_won_value": sum(o.get("value", 0) for o in won_opps),
        "win_rate": round((won_count / max(total_closed, 1)) * 100, 1),
        "_active_opps": active_opps,
    }


async def _crm_entity_counts() -> dict:
    """Fetch entity counts for master admin analytics."""
    return {
        "total_contacts": await db.crm2_contacts.count_documents({}),
        "total_companies": await db.crm2_companies.count_documents({}),
        "total_activities": await db.crm2_activities.count_documents({}),
        "open_cases": await db.crm2_cases.count_documents({"status": {"$nin": ["closed", "resolved"]}}),
        "total_assets": await db.crm2_assets.count_documents({}),
        "tasks_due": await db.crm2_activities.count_documents({"type": "task", "completed_at": None}),
    }


async def _crm_quote_analytics() -> dict:
    """Fetch quote metrics for master admin analytics."""
    accepted_q = await db.crm2_quotes.find({"status": "accepted"}, {"_id": 0, "total": 1}).to_list(500)
    return {
        "draft": await db.crm2_quotes.count_documents({"status": "draft"}),
        "sent": await db.crm2_quotes.count_documents({"status": "sent"}),
        "accepted": len(accepted_q),
        "total_value": sum(q.get("total", 0) for q in accepted_q),
    }


async def _crm_workflow_stats() -> dict:
    """Get workflow and tender statistics."""
    return {
        "wf_total": await db.crm2_workflows.count_documents({}),
        "wf_active": await db.crm2_workflows.count_documents({"active": True}),
        "wf_runs": await db.crm2_workflow_runs.count_documents({}),
        "total_tenders": await db.crm2_tenders.count_documents({}),
        "active_tenders": await db.crm2_tenders.count_documents({"status": {"$in": ["draft", "in_progress", "review"]}}),
    }


async def _crm_user_and_activity_stats() -> dict:
    """Get CRM user role distribution and activity type breakdown."""
    crm_users = await db.crm_users.find({}, {"_id": 0, "role": 1}).to_list(200)
    users_by_role = {}
    for u in crm_users:
        r = u.get("role", "user")
        users_by_role[r] = users_by_role.get(r, 0) + 1

    activity_types = {}
    for a in await db.crm2_activities.find({}, {"_id": 0, "type": 1}).to_list(1000):
        t = a.get("type", "other")
        activity_types[t] = activity_types.get(t, 0) + 1

    return {"users_by_role": users_by_role, "user_count": len(crm_users), "activity_types": activity_types}


async def _crm_top_deals_at_risk(limit: int = 5) -> list[dict]:
    """Iter 215br — Top deals at risk for Master Admin CRM tab.

    A deal is "at risk" when any of:
      • probability < 50 AND value > 0 (low-confidence pipeline)
      • close_date is in the past but stage is still open
      • last updated >14 days ago and stage is open
    Sorted by value desc and capped at `limit`.
    """
    today_iso = datetime.now(timezone.utc).date().isoformat()
    stale_threshold = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    open_filter = {"stage": {"$nin": ["closed_won", "closed_lost"]}}

    rows = await db.crm2_opportunities.find(
        {**open_filter, "$or": [
            {"probability": {"$lt": 50}, "value": {"$gt": 0}},
            {"close_date": {"$lt": today_iso, "$ne": ""}},
            {"updated_at": {"$lt": stale_threshold}},
        ]},
        {"_id": 0, "id": 1, "title": 1, "value": 1, "stage": 1, "probability": 1,
         "company_name": 1, "close_date": 1, "updated_at": 1, "owner_name": 1},
    ).sort("value", -1).limit(limit).to_list(limit)

    out = []
    for r in rows:
        reasons = []
        if (r.get("probability") or 0) < 50 and (r.get("value") or 0) > 0:
            reasons.append("low_probability")
        cd = r.get("close_date") or ""
        if cd and cd < today_iso:
            reasons.append("close_date_past")
        if (r.get("updated_at") or "") < stale_threshold:
            reasons.append("stale_14d")
        r["risk_reasons"] = reasons
        out.append(r)
    return out


async def _crm_renewals_due(window_days: int = 30) -> dict:
    """Iter 215br — Upcoming renewals/closes inside `window_days`. Returns
    a list of the closest ones plus a count and total weighted value."""
    today = datetime.now(timezone.utc).date()
    cutoff = (today + timedelta(days=window_days)).isoformat()
    rows = await db.crm2_opportunities.find(
        {
            "stage": {"$nin": ["closed_won", "closed_lost"]},
            "close_date": {"$gte": today.isoformat(), "$lte": cutoff, "$ne": ""},
        },
        {"_id": 0, "id": 1, "title": 1, "value": 1, "weighted_value": 1, "stage": 1,
         "probability": 1, "company_name": 1, "close_date": 1, "owner_name": 1},
    ).sort("close_date", 1).to_list(50)
    return {
        "window_days": window_days,
        "count": len(rows),
        "total_value": sum(r.get("value") or 0 for r in rows),
        "weighted_value": sum(r.get("weighted_value") or 0 for r in rows),
        "items": rows[:8],
    }


async def _crm_ai_usage_block() -> dict:
    """Iter 215br — Lightweight CRM AI usage panel for Master Admin.

    Counts data we actually persist today: tender questions auto-drafted
    by the AI assistant, opportunities with AI-coached next-best-action,
    and copilot/help sessions logged through `help_sessions` (if present).
    Anything not yet wired returns 0 — purposely no fake numbers.
    """
    autopilot_drafts = await db.crm2_tender_questions.count_documents({
        "ai_draft": {"$exists": True, "$nin": ["", None]},
    })
    win_intel_hits = await db.crm2_activities.count_documents({
        "type": {"$in": ["ai_insight", "win_intel", "ai_summary"]},
    })
    # Copilot sessions — opportunistic; collection may not exist yet.
    copilot_sessions = 0
    try:
        copilot_sessions = await db.crm_copilot_sessions.count_documents({})
    except Exception:
        copilot_sessions = 0
    if not copilot_sessions:
        # Fall back to help-centre AI sessions which the in-app copilot uses.
        try:
            copilot_sessions = await db.help_sessions.count_documents({"source": {"$in": ["copilot", "crm_copilot"]}})
        except Exception:
            copilot_sessions = 0
    return {
        "autopilot_drafts": autopilot_drafts,
        "win_intel_hits": win_intel_hits,
        "copilot_sessions": copilot_sessions,
        "total": autopilot_drafts + win_intel_hits + copilot_sessions,
    }


# ───────────── route ─────────────

@router.get("/master-admin/crm-analytics")
async def get_crm_analytics(user: dict = Depends(get_current_user)) -> dict:
    """Comprehensive CRM analytics for master admin — uses v2 collections."""
    require_master_admin(user)

    pipeline = await _crm_pipeline_analytics()
    counts = await _crm_entity_counts()
    quotes = await _crm_quote_analytics()
    wf = await _crm_workflow_stats()
    ua = await _crm_user_and_activity_stats()

    active_opps = pipeline.pop("_active_opps")
    pipeline_value = sum(o.get("value", 0) for o in active_opps)
    weighted_forecast = sum(o.get("weighted_value", 0) for o in active_opps)

    recent_deals = await db.crm2_opportunities.find(
        {}, {"_id": 0, "title": 1, "value": 1, "stage": 1, "company_name": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)
    recent_activities = await db.crm2_activities.find(
        {}, {"_id": 0, "type": 1, "subject": 1, "owner_name": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)

    # Iter 215br — v2 growth windows for the KPI sub-labels.
    thirty = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    growth = {
        "new_contacts_30d": await db.crm2_contacts.count_documents({"created_at": {"$gte": thirty}}),
        "new_deals_30d": await db.crm2_opportunities.count_documents({"created_at": {"$gte": thirty}}),
        "recent_activities_30d": await db.crm2_activities.count_documents({"created_at": {"$gte": thirty}}),
    }

    # Iter 215br — enriched panels for the Master Admin CRM tab.
    deals_at_risk = await _crm_top_deals_at_risk(5)
    renewals_due = await _crm_renewals_due(30)
    ai_usage = await _crm_ai_usage_block()

    return {
        "overview": {
            **counts, "active_opportunities": len(active_opps),
            # Iter 233 — the KPI card reads `total_deals`; keep both names
            # so neither the card nor older consumers render blank.
            "total_deals": len(active_opps),
            "pipeline_value": pipeline_value, "weighted_forecast": weighted_forecast,
            "total_tenders": wf["total_tenders"], "active_tenders": wf["active_tenders"],
        },
        "growth": growth,
        "pipeline": pipeline,
        "quotes": quotes,
        "contacts": {"source_breakdown": {}, "lead_scores": {}},
        "inbox": {"open_conversations": 0, "high_priority": 0},
        "users": {"by_role": ua["users_by_role"], "total": ua["user_count"]},
        "workflows": {"total": wf["wf_total"], "active": wf["wf_active"], "total_executions": wf["wf_runs"]},
        "integrations": {"sage200": {"status": "not_configured"}},
        "activity_types": ua["activity_types"],
        "recent_deals": recent_deals,
        "recent_activities": recent_activities,
        # New panels (iter 215br)
        "deals_at_risk": deals_at_risk,
        "renewals_due": renewals_due,
        "ai_usage": ai_usage,
    }
