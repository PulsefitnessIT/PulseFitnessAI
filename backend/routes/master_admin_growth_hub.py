"""Master Admin · Pulse Fitness Growth Hub — Iter 220ag / 220ah.

Single aggregation endpoint that powers the new
**Master Admin → Growth → Marketing Studio** landing page (renamed from
the operator-MarketingSuite embed which was inappropriate for self-
promotion: "fill empty classes", "re-engage inactive members" etc.).

Iter 220ah adds the **B2B Journey Templates launcher**:
``POST /api/master-admin/growth/journey-templates/{template_id}/launch``
materialises a pre-canned multi-step email journey directly in
``marketing_journeys`` scoped to the master-admin org, then returns
the new ``journey_id`` so the UI can deep-link into the Marketing →
Journeys runner.

This module **does not duplicate** any existing tooling. It reads from
the live collections owned by:

  * ``master_admin_trials``           → trial accounts + conversion rate
  * ``master_admin_sales_insights``   → public-site chat sessions
  * ``routes/marketing/seo_autopilot``→ SEO articles + dashboard
  * ``utils/email``                   → outbound ``email_send_events``
  * ``routes/crm_*``                  → deal pipeline + companies

and surfaces a single ``GET /api/master-admin/growth/overview`` JSON
payload purpose-built for "How is Pulse Fitness self-marketing performing
this month?"

The Hub UI deep-links into the existing modules for any drill-down —
we never re-implement the underlying CRUD.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

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
    """One JSON payload powering the Pulse Fitness Growth Hub landing tiles.

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
    # Iter 220aq — Scope pipeline to the master-admin org only, and
    # union both legacy ``crm_deals`` and the live ``crm2_opportunities``
    # collection (the v2 CRM portal writes to crm2_opportunities, the
    # public /demo-request landing page still creates a ``crm_deals``
    # row). Before this fix, the tile aggregated ALL tenants' deals
    # globally — a £50k deal in any customer's CRM bled into the
    # Pulse Fitness self-promo Growth Hub.
    ma_org = await _master_admin_org_id()
    of = {"organization_id": ma_org}
    deals_open = (
        await _safe_count(db.crm_deals, {**of, "stage": {"$nin": ["won", "lost"]}})
        + await _safe_count(
            db.crm2_opportunities, {**of, "stage": {"$nin": ["closed_won", "closed_lost"]}},
        )
    )
    deals_won_30d = (
        await _safe_count(
            db.crm_deals, {**of, "stage": "won", "updated_at": {"$gte": cutoff_30d_iso}},
        )
        + await _safe_count(
            db.crm2_opportunities,
            {**of, "stage": "closed_won", "updated_at": {"$gte": cutoff_30d_iso}},
        )
    )
    deals_lost_30d = (
        await _safe_count(
            db.crm_deals, {**of, "stage": "lost", "updated_at": {"$gte": cutoff_30d_iso}},
        )
        + await _safe_count(
            db.crm2_opportunities,
            {**of, "stage": "closed_lost", "updated_at": {"$gte": cutoff_30d_iso}},
        )
    )
    pipeline_value = (
        await _sum_value_field(
            db.crm_deals, {**of, "stage": {"$nin": ["won", "lost"]}},
        )
        + await _sum_value_field(
            db.crm2_opportunities,
            {**of, "stage": {"$nin": ["closed_won", "closed_lost"]}},
        )
    )
    companies_total = await _safe_count(
        db.crm_companies, of,
    ) + await _safe_count(db.crm2_companies, of)

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


__all__ = ["router", "JOURNEY_TEMPLATES"]


# ── Iter 220ak — Growth Hub alerts feed ──────────────────────────
#
# Backed by the ``growth_alerts`` collection that the public demo-
# request endpoint writes into on every inbound. Surfaced at the top
# of the Growth Hub so the master admin sees new prospects without
# leaving the dashboard.


@router.get("/master-admin/growth/alerts")
async def list_growth_alerts(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    org_id = await _master_admin_org_id()
    rows = await db.growth_alerts.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).limit(25).to_list(25)
    unread = await db.growth_alerts.count_documents(
        {"organization_id": org_id, "read": False},
    )
    return {"alerts": rows, "unread": unread}


@router.post("/master-admin/growth/alerts/mark-read")
async def mark_growth_alerts_read(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    org_id = await _master_admin_org_id()
    result = await db.growth_alerts.update_many(
        {"organization_id": org_id, "read": False},
        {"$set": {"read": True, "read_at": _now_iso()}},
    )
    return {"ok": True, "marked": int(getattr(result, "modified_count", 0) or 0)}


# ── Iter 220aj — 30-day sparklines for Growth Hub KPI tiles ──────
#
# Each metric returns a list of 30 ``{date, value}`` points (chrono
# order, oldest first). Where we have a row-level created_at column,
# the bucket is exact; for blog views (a running counter today) we
# snapshot the total daily into ``seo_view_snapshots`` so the trend
# accumulates from "now". The Hub tile renders an inline SVG sparkline
# under the headline number.


_SPARK_DAYS = 30


def _bucket_dates(now: datetime) -> list[str]:
    """Return the last 30 ISO ``YYYY-MM-DD`` date strings, oldest
    first. Stable across timezones — we use UTC for grouping."""
    today = now.date()
    return [(today - timedelta(days=29 - i)).isoformat() for i in range(_SPARK_DAYS)]


async def _bucket_count_by_day(
    coll, *, date_field: str, query: dict | None = None,
    is_iso_string: bool = False,
) -> dict[str, int]:
    """Return ``{YYYY-MM-DD: count}`` for the last 30 days. Works on
    BSON ``Date`` fields or ISO-string fields (the platform mixes
    both — historical inserts used ISO strings, newer code uses
    timezone-aware datetimes)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=_SPARK_DAYS)
    buckets: dict[str, int] = {}
    q = dict(query or {})
    if is_iso_string:
        q[date_field] = {"$gte": cutoff.isoformat()}
    else:
        q[date_field] = {"$gte": cutoff}
    try:
        async for doc in coll.find(q, {"_id": 0, date_field: 1}):
            v = doc.get(date_field)
            if not v:
                continue
            if isinstance(v, datetime):
                key = v.date().isoformat()
            else:
                # ISO string — slice off the date portion.
                try:
                    key = str(v)[:10]
                except Exception:  # pragma: no cover
                    continue
            buckets[key] = buckets.get(key, 0) + 1
    except Exception:  # pragma: no cover — diagnostics, not feature
        pass
    return buckets


async def _snapshot_blog_views_today(total_views: int) -> None:
    """Persist today's running blog-view total so we can build a real
    trend over time. Idempotent ``upsert`` on the date key."""
    today = datetime.now(timezone.utc).date().isoformat()
    await db.seo_view_snapshots.update_one(
        {"date": today},
        {"$set": {"date": today, "total_views": int(total_views),
                  "captured_at": _now_iso()}},
        upsert=True,
    )


async def _blog_views_series() -> list[dict]:
    """Return the 30-day blog-views series. Reads from
    ``seo_view_snapshots`` (filled by the overview endpoint on each
    fetch). Days without a snapshot inherit the previous day's value
    so the line stays continuous."""
    now = datetime.now(timezone.utc)
    dates = _bucket_dates(now)
    rows = await db.seo_view_snapshots.find(
        {"date": {"$in": dates}}, {"_id": 0, "date": 1, "total_views": 1},
    ).to_list(_SPARK_DAYS)
    by_date = {r["date"]: int(r.get("total_views") or 0) for r in rows}
    last = 0
    out: list[dict] = []
    for d in dates:
        if d in by_date:
            last = by_date[d]
        out.append({"date": d, "value": last})
    return out


def _series_from_buckets(buckets: dict[str, int], now: datetime) -> list[dict]:
    return [
        {"date": d, "value": int(buckets.get(d, 0))}
        for d in _bucket_dates(now)
    ]


@router.get("/master-admin/growth/sparklines")
async def growth_sparklines(user: dict = Depends(get_current_user)) -> dict:
    """Return per-metric 30-day daily series for the Hub KPI tiles.

    Resolved fields per metric:
      * ``trials_started`` — ``organizations.created_at`` where ``is_trial``.
      * ``blog_views`` — daily snapshot from ``seo_view_snapshots`` (also
        upserts today's value so the trend accumulates).
      * ``emails_sent`` — ``email_send_events.created_at`` where ``status=sent``.
      * ``deals_created`` — ``crm_deals.created_at`` (ISO string or datetime).
      * ``chat_sessions`` — ``mkt_chat_sessions.created_at``.
    """
    require_master_admin(user)
    now = datetime.now(timezone.utc)

    # Trials — organizations.created_at, filter on is_trial.
    trials_b = await _bucket_count_by_day(
        db.organizations, date_field="created_at",
        query={"is_trial": True},
    )

    # Snapshot today's running blog-view total so the series fills
    # over time. Sum across all published articles.
    total_views = 0
    try:
        async for doc in db.seo_articles.find(
            {"status": "published"}, {"_id": 0, "metrics": 1},
        ):
            total_views += int((doc.get("metrics") or {}).get("views") or 0)
    except Exception:  # pragma: no cover
        pass
    await _snapshot_blog_views_today(total_views)
    blog_views_series = await _blog_views_series()

    emails_b = await _bucket_count_by_day(
        db.email_send_events, date_field="created_at",
        query={"status": "sent"},
    )
    # Iter 220aq — scope deal-creation sparkline to the master-admin
    # org. Same fix as the overview endpoint above. Note we also union
    # crm2_opportunities so deals filed via the v2 CRM portal count.
    ma_org = await _master_admin_org_id()
    deals_v1 = await _bucket_count_by_day(
        db.crm_deals, date_field="created_at", is_iso_string=True,
        query={"organization_id": ma_org},
    )
    deals_v2 = await _bucket_count_by_day(
        db.crm2_opportunities, date_field="created_at", is_iso_string=True,
        query={"organization_id": ma_org},
    )
    deals_b = {d: deals_v1.get(d, 0) + deals_v2.get(d, 0)
               for d in set(deals_v1) | set(deals_v2)}
    chats_b = await _bucket_count_by_day(
        db.mkt_chat_sessions, date_field="created_at",
    )

    return {
        "as_of": now.isoformat(),
        "days": _SPARK_DAYS,
        "series": {
            "trials_started": _series_from_buckets(trials_b, now),
            "blog_views":     blog_views_series,
            "emails_sent":    _series_from_buckets(emails_b, now),
            "deals_created":  _series_from_buckets(deals_b, now),
            "chat_sessions":  _series_from_buckets(chats_b, now),
        },
    }


# ── B2B Journey Templates — Iter 220ah ───────────────────────────
#
# Pre-canned multi-step email journeys for Pulse Fitness self-promotion.
# Each template materialises into a real ``marketing_journeys`` row
# scoped to the master-admin organisation, with ``send_email`` nodes
# the omni-channel dispatcher already knows how to fire. The operator
# then either presses **Test send** in the Marketing → Journeys runner
# (preview to themselves) or **Enrol contact** to start the live run
# for a specific CRM contact.
#
# We **don't** call the LLM at launch time — every email is hand-
# written here so the launch is instant. Operators can edit any node
# in the Marketing → Journeys canvas afterwards.

_BRAND_SIG_HTML = (
    "<br><br>—<br>"
    "Pulse Fitness · operations + CRM for fitness operators<br>"
    "<a href=\"https://www.pulsefitness.ai/demo\">Book a 20-min demo</a>"
)


def _email_node(*, subject: str, html: str, day: int) -> dict:
    """Build a `send_email` leaf node. ``day`` is informational only —
    the runtime dispatcher fires every leaf when enrolled (waits land
    in the upcoming scheduler iteration); operators can re-order /
    edit subjects + bodies in the visual canvas after launch."""
    return {
        "id": str(uuid.uuid4()),
        "type": "send_email",
        "title": f"Day {day} · {subject}",
        "subject": subject,
        "body": html + _BRAND_SIG_HTML,
        "day": day,
    }


JOURNEY_TEMPLATES: dict[str, dict] = {
    "cold-to-demo": {
        "name": "Cold prospect → demo",
        "description": (
            "7 emails over 14 days. Hook → value → social proof → CTA. "
            "For new CRM contacts in the target ICP (gym chains, 3+ sites)."
        ),
        "trigger": {"event": "manual_enrol"},
        "nodes": [
            _email_node(
                day=1,
                subject="A quick question about how you run service jobs",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Curious — when a treadmill goes down at peak hours, who's the "
                    "first person on your team that hears about it, and how long until "
                    "the service company picks up the phone?</p>"
                    "<p>Most operators we speak to say the answer is &quot;3–6 hours and "
                    "an angry WhatsApp thread&quot;. We built Pulse Fitness specifically for "
                    "that gap.</p>"
                    "<p>If you're open to a 20-min look, I'll share a 1-page benchmark of "
                    "how multi-site chains are running this in 2026.</p>"
                ),
            ),
            _email_node(
                day=3,
                subject="The hidden cost of equipment downtime (a 2-min read)",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Quick number: a single treadmill out of service at a busy site "
                    "costs the average chain ~£42/day in cancelled PT sessions and "
                    "member-experience hits. Across 8 sites and 6 weeks of slow "
                    "supplier response, that's £14,000+ in a single quarter.</p>"
                    "<p>We wrote a 5-min playbook on cutting that. Want me to send it "
                    "over?</p>"
                ),
            ),
            _email_node(
                day=6,
                subject="How {Anytime Fitness / Fitness4Less / etc.} runs service ops",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>One pattern we keep seeing in 5+ site chains: the on-site team "
                    "logs faults via QR-code → Pulse Fitness auto-routes to the cheapest "
                    "available partner engineer → 24h SLA → invoice posts back to Sage.</p>"
                    "<p>Total time gym manager spends on each fault: ~45 seconds.</p>"
                    "<p>Want a 20-min walkthrough? I can show you the exact dashboard "
                    "your area manager would see.</p>"
                ),
            ),
            _email_node(
                day=9,
                subject="3 things to look for in a service-ops platform",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>If you're already evaluating tools, three non-negotiables:</p>"
                    "<ol>"
                    "<li><strong>Real partner-engineer network</strong> — not a job board.</li>"
                    "<li><strong>CAPEX visibility</strong> — replacement costs forecasted from "
                    "asset age + downtime trend.</li>"
                    "<li><strong>Accounting integration</strong> — Sage 200 / Xero, not CSV.</li>"
                    "</ol>"
                    "<p>Happy to share how we score on each. 20 min?</p>"
                ),
            ),
            _email_node(
                day=12,
                subject="Last note — and a free benchmark",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>I'll stop emailing after this one. If service-ops isn't on the "
                    "priority list this quarter, no problem at all — happy to circle "
                    "back next quarter.</p>"
                    "<p>Either way, here's our 2026 multi-site downtime benchmark "
                    "(no email gate, just a link): "
                    "<a href=\"https://www.pulsefitness.ai/benchmark\">www.pulsefitness.ai/benchmark</a>.</p>"
                ),
            ),
        ],
    },
    "demo-booked": {
        "name": "Demo booked → close",
        "description": (
            "Recap email + 2 follow-ups (T+1d, T+5d) with mutual action plan. "
            "Fires for CRM deals in the 'Demo Booked' stage."
        ),
        "trigger": {"event": "demo_booked"},
        "nodes": [
            _email_node(
                day=0,
                subject="Demo recap — {{first_name}} + {{your_site_count}} sites",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Great chat earlier. Quick recap of what we agreed:</p>"
                    "<ul>"
                    "<li><strong>Goals:</strong> cut equipment downtime, get CAPEX "
                    "visibility, kill the WhatsApp service thread.</li>"
                    "<li><strong>Scope:</strong> 30-day pilot at your flagship site, "
                    "with shadow data for the other locations.</li>"
                    "<li><strong>Next step:</strong> mutual-action plan attached — "
                    "5 milestones, ~3 weeks to value.</li>"
                    "</ul>"
                    "<p>Anything I've mis-heard, just hit reply.</p>"
                ),
            ),
            _email_node(
                day=1,
                subject="One small thing — the partner-engineer onboarding video",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Forgot to send this in the recap. 4-min walkthrough showing "
                    "what your area manager sees when a fault comes in:</p>"
                    "<p><a href=\"https://www.pulsefitness.ai/demo-video/partner-flow\">"
                    "Watch the partner-flow demo (4 min)</a></p>"
                    "<p>Worth showing to whoever runs ops day-to-day.</p>"
                ),
            ),
            _email_node(
                day=5,
                subject="Quick check — anything blocking us?",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Just checking in. From the call, the bottleneck was the "
                    "Sage 200 integration sign-off. Is that still where things stand?</p>"
                    "<p>Happy to jump on a 10-min call with whoever owns the finance "
                    "stack — I can walk them through exactly what we post and when.</p>"
                ),
            ),
        ],
    },
    "trial-conversion": {
        "name": "Trial day 1 / 7 / 13 → paid",
        "description": (
            "Activation nudge, value reminder, conversion push. "
            "Fires automatically when an org flips ``is_trial = true``."
        ),
        "trigger": {"event": "trial_started"},
        "nodes": [
            _email_node(
                day=1,
                subject="Welcome to Pulse Fitness — the 1 thing to do today",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Your trial is live. Most of our converting trials hit value "
                    "in the first 24 hours by doing one thing:</p>"
                    "<p><strong>Add 5 pieces of equipment and log 1 fault.</strong> "
                    "Takes 6 minutes total.</p>"
                    "<p>Quick guide: "
                    "<a href=\"https://www.pulsefitness.ai/docs/quickstart\">5-min quickstart</a></p>"
                    "<p>Stuck? Hit reply — I read these myself.</p>"
                ),
            ),
            _email_node(
                day=7,
                subject="How your trial compares to others (good news)",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Mid-trial check. By day 7, the orgs that go on to subscribe "
                    "have logged an average of 12 faults and connected at least one "
                    "partner engineer. You're in the right ballpark.</p>"
                    "<p>If you want a 15-min review of your specific setup before "
                    "the trial ends, grab a slot here: "
                    "<a href=\"https://www.pulsefitness.ai/trial-review\">trial-review</a>.</p>"
                ),
            ),
            _email_node(
                day=13,
                subject="Trial ends tomorrow — quick decision needed",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Your trial ends tomorrow. No pressure — but if you want to "
                    "keep the data and partner-engineer connections you've built, "
                    "easiest path is to subscribe before midnight.</p>"
                    "<p>If you're not ready, just reply and we can pause / extend "
                    "rather than lose the work.</p>"
                    "<p>Either way: 3 short clicks here to convert → "
                    "<a href=\"https://www.pulsefitness.ai/subscribe\">subscribe</a>.</p>"
                ),
            ),
        ],
    },
    "lost-revival": {
        "name": "Lost deal → 90-day re-engagement",
        "description": (
            "Quarterly 'what's new' digest + a relevant case study. "
            "Fires for CRM deals stage=lost in the last 12 months."
        ),
        "trigger": {"event": "deal_lost_90d"},
        "nodes": [
            _email_node(
                day=0,
                subject="A 60-second update from Pulse Fitness (no pitch)",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>We chatted ~90 days ago. Quick update — three things shipped "
                    "since then that might change your view:</p>"
                    "<ul>"
                    "<li><strong>Partner-engineer marketplace</strong> — 200+ vetted "
                    "field engineers, average 8h response.</li>"
                    "<li><strong>Sicon Service + Sage 200 ledger posting</strong> — "
                    "kills double-entry for AP teams.</li>"
                    "<li><strong>RIDDOR + accident reporting</strong> — built in, no "
                    "extra HSE software needed.</li>"
                    "</ul>"
                    "<p>No need to reply — just figured I'd close the loop.</p>"
                ),
            ),
            _email_node(
                day=14,
                subject="Case study you might find interesting",
                html=(
                    "<p>Hi {{first_name}},</p>"
                    "<p>Quick one — we just published how a 12-site UK chain cut "
                    "equipment downtime by 38% in 90 days using Pulse Fitness.</p>"
                    "<p><a href=\"https://www.pulsefitness.ai/case-studies/12-site-chain\">"
                    "Read the case study (5 min)</a></p>"
                    "<p>If the numbers look relevant, happy to share what they "
                    "specifically configured. No pitch attached.</p>"
                ),
            ),
        ],
    },
}


async def _master_admin_org_id() -> str:
    """Return the Pulse Fitness master-admin organisation_id used as the
    canonical home for self-promo journeys. Falls back to the first
    master admin's ``organization_id`` if a dedicated master-admin org
    isn't found — this matches how the rest of the master-admin tools
    resolve their org context."""
    user = await db.users.find_one(
        {"is_master_admin": True},
        {"_id": 0, "organization_id": 1},
        sort=[("created_at", 1)],
    )
    if user and user.get("organization_id"):
        return str(user["organization_id"])
    org = await db.organizations.find_one(
        {"$or": [{"is_master_admin": True}, {"slug": "gymaxis"}, {"name": "Pulse Fitness"}]},
        {"_id": 0, "id": 1},
    )
    if org and org.get("id"):
        return str(org["id"])
    raise HTTPException(500, "No master-admin organisation found")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/master-admin/growth/journey-templates")
async def list_journey_templates(user: dict = Depends(get_current_user)) -> dict:
    """Return the static template catalogue + whether each has already
    been materialised into a live journey on this org (so the UI can
    show "Re-create" vs "Launch")."""
    require_master_admin(user)
    org_id = await _master_admin_org_id()
    out = []
    for tid, t in JOURNEY_TEMPLATES.items():
        existing = await db.marketing_journeys.find_one(
            {"organization_id": org_id, "template_id": tid},
            {"_id": 0, "id": 1, "status": 1, "created_at": 1, "metrics": 1},
        )
        out.append({
            "id": tid,
            "name": t["name"],
            "description": t["description"],
            "node_count": len(t.get("nodes") or []),
            "existing_journey": existing,
        })
    return {"templates": out}


@router.post("/master-admin/growth/journey-templates/{template_id}/launch")
async def launch_journey_template(
    template_id: str, user: dict = Depends(get_current_user),
) -> dict:
    """Materialise a B2B template into ``marketing_journeys`` for the
    master-admin org. Idempotent: re-launching returns the existing
    journey (UI calls "Re-create" to deliberately spawn a new one)."""
    require_master_admin(user)
    tpl = JOURNEY_TEMPLATES.get(template_id)
    if not tpl:
        raise HTTPException(404, "Unknown template id")
    org_id = await _master_admin_org_id()

    existing = await db.marketing_journeys.find_one(
        {"organization_id": org_id, "template_id": template_id},
        {"_id": 0},
    )
    if existing:
        return {"journey": existing, "created": False}

    journey_id = str(uuid.uuid4())
    now = _now_iso()
    doc = {
        "id": journey_id,
        "organization_id": org_id,
        "template_id": template_id,
        "name": tpl["name"],
        "description": tpl["description"],
        "status": "draft",
        "trigger": tpl.get("trigger") or {"event": "manual_enrol"},
        "nodes": [dict(n) for n in (tpl.get("nodes") or [])],
        "edges": [],
        "ai_optimisation": {},
        "metrics": {"entered": 0, "completed": 0, "converted": 0, "revenue_gbp": 0},
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("id"),
        "scope": "gymaxis_self_promo",
    }
    await db.marketing_journeys.insert_one(doc)
    doc.pop("_id", None)
    return {"journey": doc, "created": True}


@router.post("/master-admin/growth/journey-templates/{template_id}/recreate")
async def recreate_journey_template(
    template_id: str, user: dict = Depends(get_current_user),
) -> dict:
    """Force-recreate the journey from the template (archives the
    previous version). Used when the master admin has edited the
    template or wants a fresh copy."""
    require_master_admin(user)
    tpl = JOURNEY_TEMPLATES.get(template_id)
    if not tpl:
        raise HTTPException(404, "Unknown template id")
    org_id = await _master_admin_org_id()

    # Archive any existing rows so the new one is canonical.
    await db.marketing_journeys.update_many(
        {"organization_id": org_id, "template_id": template_id,
         "status": {"$ne": "archived"}},
        {"$set": {"status": "archived", "updated_at": _now_iso()}},
    )

    journey_id = str(uuid.uuid4())
    now = _now_iso()
    doc = {
        "id": journey_id,
        "organization_id": org_id,
        "template_id": template_id,
        "name": tpl["name"],
        "description": tpl["description"],
        "status": "draft",
        "trigger": tpl.get("trigger") or {"event": "manual_enrol"},
        "nodes": [dict(n) for n in (tpl.get("nodes") or [])],
        "edges": [],
        "ai_optimisation": {},
        "metrics": {"entered": 0, "completed": 0, "converted": 0, "revenue_gbp": 0},
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("id"),
        "scope": "gymaxis_self_promo",
    }
    await db.marketing_journeys.insert_one(doc)
    doc.pop("_id", None)
    return {"journey": doc, "created": True}
