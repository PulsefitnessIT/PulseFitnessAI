"""Master Admin · GymAxis Growth Hub — Iter 220ag.

Single aggregation endpoint that powers the new
**Master Admin → Growth → Marketing Studio** landing page (renamed from
the operator-MarketingSuite embed which was inappropriate for self-
promotion: "fill empty classes", "re-engage inactive members" etc.).

This module **does not duplicate** any existing tooling. It reads from
the live collections owned by:

  * ``master_admin_trials``           → trial accounts + conversion rate
  * ``master_admin_sales_insights``   → public-site chat sessions
  * ``routes/marketing/seo_autopilot``→ SEO articles + dashboard
  * ``utils/email``                   → outbound ``email_send_events``
  * ``routes/crm_*``                  → deal pipeline + companies

and surfaces a single ``GET /api/master-admin/growth/overview`` JSON
payload purpose-built for "How is GymAxis self-marketing performing
this month?"

The Hub UI deep-links into the existing modules for any drill-down —
we never re-implement the underlying CRUD.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import require_master_admin

router = APIRouter(tags=["master-admin-growth-hub"])


async def _safe_count(coll, query: dict) -> int:
    try:
        return int(await coll.count_documents(query))
    except Exception:  # pragma: no cover — diagnostics, not a feature
        return 0


async def _sum_value_field(coll, query: dict, field: str = "value") -> float:
    total = 0.0
    try:
        cursor = coll.find(query, {"_id": 0, field: 1})
        async for doc in cursor:
            v = doc.get(field) or 0
            try:
                total += float(v)
            except (TypeError, ValueError):
                continue
    except Exception:  # pragma: no cover
        return 0.0
    return total


@router.get("/master-admin/growth/overview")
async def growth_overview(user: dict = Depends(get_current_user)) -> dict:
    """One JSON payload powering the GymAxis Growth Hub landing tiles.

    Returns five module groups, each with its KPIs *and* the deep-link
    section ID the UI should jump to so the master admin can drill in
    without us re-implementing that module's UI here.
    """
    require_master_admin(user)

    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    cutoff_30d_iso = cutoff_30d.isoformat()

    # ── Trials (read-only roll-up from existing trial logic) ──────────
    trial_orgs = await db.organizations.find(
        {"$or": [{"is_trial": True}, {"trial_status": "converted"}]},
        {"_id": 0, "is_trial": 1, "trial_status": 1,
         "converted_at": 1, "created_at": 1, "trial_ends_at": 1},
    ).to_list(2000)
    trial_active = sum(
        1 for o in trial_orgs
        if o.get("is_trial") and o.get("trial_status") not in ("converted", "expired")
    )
    trial_converted_30d = 0
    for o in trial_orgs:
        ts = o.get("converted_at")
        if not ts or o.get("trial_status") != "converted":
            continue
        try:
            if (isinstance(ts, str) and ts >= cutoff_30d_iso) or (
                isinstance(ts, datetime) and ts >= cutoff_30d
            ):
                trial_converted_30d += 1
        except Exception:  # pragma: no cover
            continue

    # ── SEO Autopilot ─────────────────────────────────────────────────
    seo_total = await _safe_count(db.seo_articles, {"status": {"$ne": "archived"}})
    seo_published = await _safe_count(db.seo_articles, {"status": "published"})
    seo_drafts = await _safe_count(db.seo_articles, {"status": "draft"})
    seo_kw_queued = await _safe_count(db.seo_keywords, {"status": "queued"})
    last_autopilot_run = await db.seo_autopilot_runs.find_one(
        {}, {"_id": 0}, sort=[("date", -1)],
    )
    seo_views_total = 0
    try:
        cursor = db.seo_articles.find(
            {"status": "published"}, {"_id": 0, "metrics": 1},
        )
        async for doc in cursor:
            seo_views_total += int((doc.get("metrics") or {}).get("views") or 0)
    except Exception:  # pragma: no cover
        pass

    # ── Outbound emails (30d) ────────────────────────────────────────
    emails_sent_30d = await _safe_count(
        db.email_send_events, {"status": "sent", "created_at": {"$gte": cutoff_30d}},
    )
    emails_failed_30d = await _safe_count(
        db.email_send_events,
        {"status": {"$ne": "sent"}, "created_at": {"$gte": cutoff_30d}},
    )

    # ── CRM pipeline ─────────────────────────────────────────────────
    deals_open = await _safe_count(db.crm_deals, {"stage": {"$nin": ["won", "lost"]}})
    deals_won_30d = await _safe_count(
        db.crm_deals, {"stage": "won", "updated_at": {"$gte": cutoff_30d_iso}},
    )
    deals_lost_30d = await _safe_count(
        db.crm_deals, {"stage": "lost", "updated_at": {"$gte": cutoff_30d_iso}},
    )
    pipeline_value = await _sum_value_field(
        db.crm_deals, {"stage": {"$nin": ["won", "lost"]}},
    )
    companies_total = await _safe_count(db.crm_companies, {})

    # ── Sales insights (public-chat sessions, 30d) ──────────────────
    chat_sessions_30d = await _safe_count(
        db.mkt_chat_sessions, {"created_at": {"$gte": cutoff_30d}},
    )
    chat_messages_30d = await _safe_count(
        db.mkt_chat_messages, {"created_at": {"$gte": cutoff_30d}},
    )

    return {
        "as_of": now.isoformat(),
        "trials": {
            "active": trial_active,
            "converted_30d": trial_converted_30d,
            "deep_link": "trials",
        },
        "seo": {
            "articles_total": seo_total,
            "articles_published": seo_published,
            "articles_draft": seo_drafts,
            "keywords_queued": seo_kw_queued,
            "blog_views_total": seo_views_total,
            "last_autopilot_run": last_autopilot_run or None,
            "deep_link": "seo-autopilot",
        },
        "outbound": {
            "sent_30d": emails_sent_30d,
            "failed_30d": emails_failed_30d,
            "deep_link": "emails",
        },
        "pipeline": {
            "deals_open": deals_open,
            "deals_won_30d": deals_won_30d,
            "deals_lost_30d": deals_lost_30d,
            "pipeline_value_gbp": round(pipeline_value, 2),
            "companies_total": companies_total,
            "deep_link": "crm-deals",
        },
        "sales_insights": {
            "chat_sessions_30d": chat_sessions_30d,
            "chat_messages_30d": chat_messages_30d,
            "deep_link": "sales-insights",
        },
    }


__all__ = ["router"]
