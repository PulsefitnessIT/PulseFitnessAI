"""Pulse Fitness platform vitals — Iter 216h93.

Master-admin-only `/api/health/full` complements the public `/health/deep`:
that one is for uptime probes; this one is for the human in a hurry
debugging a customer report. Returns:

  • Everything `/health/deep` covers (mongo, integrations, JWT, sender),
  • Row counts on the collections that matter to the business,
  • Partner network specifics (active subs, recent commissions),
  • Service-desk recent throughput,
  • Stripe partner price ID configuration check,
  • Most recent scheduled-job heartbeats.

Master admin only. Never echoes secret values — only presence flags.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


async def _safe_count(coll, query: dict | None = None) -> int:
    try:
        return await db[coll].count_documents(query or {})
    except Exception as e:
        logger.warning(f"health-full: count failed on {coll}: {e!r}")
        return -1


@router.get("/health/full")
async def health_full(user=Depends(get_current_user)) -> dict:
    """Comprehensive platform vitals — Master Admin only."""
    if not user.get("is_master_admin"):
        raise HTTPException(403, "Master admin only")

    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    out: dict = {
        "overall": "ok",
        "version": os.environ.get("SENTRY_RELEASE") or "dev",
        "generated_at": now.isoformat(),
    }

    # ── Mongo ping ───────────────────────────────────────────────
    mongo_status = "ok"
    try:
        await db.command("ping")
    except Exception as e:
        mongo_status = "down"
        out["overall"] = "degraded"
        logger.warning(f"health-full: mongo ping failed: {e!r}")
    out["mongo"] = {"status": mongo_status}

    # ── Integration / secret presence (booleans only) ────────────
    out["integrations"] = {
        "stripe":           bool(os.environ.get("STRIPE_API_KEY", "").strip()),
        "stripe_webhook":   bool(os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()),
        "resend":           bool(os.environ.get("RESEND_API_KEY", "").strip()),
        "emergent_llm":     bool(os.environ.get("EMERGENT_LLM_KEY", "").strip()),
        "sentry":           bool(os.environ.get("SENTRY_DSN", "").strip()),
        "twilio":           bool(os.environ.get("TWILIO_ACCOUNT_SID", "").strip()),
        "sicon":            bool(os.environ.get("SICON_BASE_URL", "").strip()),
    }
    out["partner_plan_prices"] = {
        "p30": bool(os.environ.get("STRIPE_PRICE_PARTNER_PLAN_30", "").strip()),
        "p15": bool(os.environ.get("STRIPE_PRICE_PARTNER_PLAN_15", "").strip()),
    }

    # ── Business row counts ──────────────────────────────────────
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    out["business"] = {
        "organizations":          await _safe_count("organizations"),
        "active_orgs_30d":        await _safe_count("organizations", {"updated_at": {"$gte": thirty_days_ago}}),
        "users":                  await _safe_count("users"),
        "users_active_7d":        await _safe_count("users", {"last_login_at": {"$gte": seven_days_ago}}),
        "members":                await _safe_count("members"),
    }

    out["service_desk"] = {
        "cases_total":            await _safe_count("svc_cases"),
        "cases_open":             await _safe_count("svc_cases", {"status": {"$nin": ["closed", "invoiced", "cancelled", "void"]}}),
        "cases_closed_7d":        await _safe_count("svc_cases", {"status": "closed", "closed_at": {"$gte": seven_days_ago}}),
        "cases_awaiting_signoff": await _safe_count("svc_cases", {"status": "awaiting_sign_off"}),
        "engineers":              await _safe_count("svc_engineers", {"active": {"$ne": False}}),
        "safety_signoffs_7d":     await _safe_count("svc_case_safety_signoffs", {"signed_at": {"$gte": seven_days_ago}}),
        "ratings_captured_7d":    await _safe_count("svc_cases", {"customer_rating": {"$gte": 1}, "customer_feedback_at": {"$gte": seven_days_ago}}),
    }

    out["partner_network"] = {
        "partners_total":         await _safe_count("partner_engineers"),
        "partners_approved":      await _safe_count("partner_engineers", {"status": "approved"}),
        "partners_subscribed":    await _safe_count("partner_engineers", {"subscription.status": "active"}),
        "partners_pending":       await _safe_count("partner_engineers", {"status": "pending"}),
        "referrals_active":       await _safe_count("partner_referrals", {"status": "active"}),
        "commissions_30d":        await _safe_count("partner_commission_ledger", {"created_at": {"$gte": thirty_days_ago}}),
    }

    # Last heartbeats from key scheduled jobs (recorded on the
    # respective in-memory schedulers writing to a 'job_runs' coll).
    try:
        recent_jobs = await db.job_runs.find(
            {}, {"_id": 0, "name": 1, "finished_at": 1, "status": 1},
        ).sort("finished_at", -1).limit(10).to_list(10)
    except Exception:
        recent_jobs = []
    out["recent_jobs"] = recent_jobs

    # ── Sender / JWT health (mirrored from /health/deep) ─────────
    sender = os.environ.get("SENDER_EMAIL", "").strip().lower()
    weak_sender = (
        not sender
        or sender.endswith("@resend.dev")
        or sender.endswith("@example.com")
        or sender.startswith("onboarding@")
    )
    out["sender_email"] = {
        "status": "configured" if not weak_sender else "weak",
        "value": sender or None,
    }
    if weak_sender:
        out["overall"] = "degraded"

    jwt_secret = os.environ.get("JWT_SECRET", "")
    weak_jwt = (
        not jwt_secret or len(jwt_secret) < 32
        or "gymaxis-ai-secret" in jwt_secret.lower()
        or "change-me" in jwt_secret.lower()
    )
    out["jwt"] = {"status": "ok" if not weak_jwt else "weak"}
    if weak_jwt:
        out["overall"] = "degraded"

    # ── Email pacer / rate limiter (Iter 216h100) ───────────────────
    try:
        from utils.email_rate_limiter import stats as _rl_stats
        rl = _rl_stats()
        # 24h delivery success snapshot piggybacks the existing
        # email_send_events index used by /master-admin/email-health.
        cutoff = now - timedelta(hours=24)
        sent_24h = await _safe_count("email_send_events", {"status": "sent", "created_at": {"$gte": cutoff}})
        failed_24h = await _safe_count("email_send_events", {"status": {"$ne": "sent"}, "created_at": {"$gte": cutoff}})
        out["email"] = {
            "max_rps": rl["max_rps"],
            "in_window": rl["in_window"],
            "queue_depth": rl["queue_depth"],
            "sent_24h": sent_24h,
            "failed_24h": failed_24h,
            "status": (
                "backed_up" if rl["queue_depth"] >= 20
                else ("amber" if failed_24h > sent_24h else "ok")
            ),
        }
        if out["email"]["status"] == "backed_up":
            out["overall"] = "degraded"
    except Exception as e:  # pragma: no cover — never break health-full on stats
        logger.warning(f"health-full: email stats failed: {e!r}")
        out["email"] = {"status": "unknown"}

    out["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return out


__all__ = ["router"]
