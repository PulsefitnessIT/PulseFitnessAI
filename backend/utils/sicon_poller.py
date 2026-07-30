"""
Sicon background poller.
Loops every POLL_INTERVAL_SECONDS (default 300s = 5 min) polling Sicon for
inbound updates (case statuses, appointments, tracking notes) and retrying
failed outbound queue operations.

Gated by sicon_config.enabled on a per-organization basis.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from utils.database import db
from utils.sicon_sync import poll_sicon_updates_for_org, retry_queue_for_org

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("SICON_POLL_INTERVAL_SECONDS", "300"))
KPI_RECALC_INTERVAL_SECONDS = int(os.environ.get("SICON_KPI_RECALC_INTERVAL_SECONDS", "900"))

_poller_task: asyncio.Task | None = None


async def _run_org_poll_cycle(org_id: str) -> None:
    """Poll + retry for a single org, logging interesting non-zero counts."""
    try:
        counts = await poll_sicon_updates_for_org(org_id)
        if any(counts.get(k, 0) for k in ("cases_updated", "appointments_updated", "notes_added")):
            logger.info(f"[Sicon poll] org={org_id} counts={counts}")
    except Exception as e:
        logger.warning(f"[Sicon poll] org={org_id} failed: {e}")
    try:
        retry = await retry_queue_for_org(org_id)
        if retry.get("retried"):
            logger.info(f"[Sicon retry] org={org_id} counts={retry}")
    except Exception as e:
        logger.warning(f"[Sicon retry] org={org_id} failed: {e}")


async def _run_trial_lifecycle() -> None:
    try:
        from utils.trial_lifecycle import run_trial_lifecycle_once
        frontend_url = os.environ.get("FRONTEND_URL", "")
        trial_counts = await run_trial_lifecycle_once(frontend_url)
        if any(trial_counts.get(k, 0) for k in ("reminders_sent", "expired", "suspended")):
            logger.info(f"[Trial lifecycle] counts={trial_counts}")
    except Exception as e:
        logger.warning(f"[Trial lifecycle] failed: {e}")


async def _run_archive_lifecycle() -> None:
    try:
        from utils.archive_lifecycle import run_archive_lifecycle_once
        archive_counts = await run_archive_lifecycle_once()
        if any(archive_counts.get(k, 0) for k in ("warnings_sent", "deleted")):
            logger.info(f"[Archive lifecycle] counts={archive_counts}")
    except Exception as e:
        logger.warning(f"[Archive lifecycle] failed: {e}")


async def _run_trust_collectors() -> None:
    """Scan platform health signals and publish trust_events.

    Part of the Trust Backbone (Layer 1). Fires alongside the Sicon poller so
    we benefit from the existing 5-min cadence without a new scheduler.
    """
    try:
        from utils.trust_events import record_trust_event, auto_resolve_trust_event
        from datetime import datetime, timedelta, timezone

        queued = await db.sicon_sync_queue.count_documents({"status": {"$in": ["pending", "retrying"]}})
        failed = await db.sicon_sync_queue.count_documents({"status": "failed"})
        if queued >= 25 or failed >= 5:
            sev = "high" if (queued >= 50 or failed >= 20) else "med"
            await record_trust_event(
                type="sicon.queue.backlog", severity=sev,
                summary=f"Sicon sync queue: {queued} pending, {failed} failed",
                payload={"queued": queued, "failed": failed},
                dedupe_key="sicon.queue.backlog",
            )
        else:
            await auto_resolve_trust_event("sicon.queue.backlog", note="Queue back to healthy levels")

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        storm = await db.trust_events.count_documents({
            "severity": {"$in": ["high", "critical"]},
            "created_at": {"$gte": cutoff},
        })
        if storm >= 20:
            await record_trust_event(
                type="trust.event_storm", severity="critical",
                summary=f"Trust event storm: {storm} high/critical events in 10 min",
                payload={"count_10m": storm},
                dedupe_key="trust.event_storm",
            )
    except Exception as e:
        logger.warning(f"[Trust collectors] failed: {e}")


async def _run_support_analytics_rollup() -> None:
    """Snapshot today's Ask/escalation/CSAT numbers so we can chart trends."""
    try:
        from routes.support_escalate import rollup_daily_support_analytics
        snap = await rollup_daily_support_analytics()
        if snap and (snap.get("asks") or snap.get("escalated")):
            logger.info(f"[Support analytics] snap={snap}")
    except Exception as e:
        logger.warning(f"[Support analytics] failed: {e}")


async def _run_engineer_directory_refresh() -> None:
    """Phase C — refresh the Sicon engineer directory cache."""
    try:
        from utils.sicon_sync import refresh_all_sicon_engineers
        totals = await refresh_all_sicon_engineers()
        if totals["fetched"]:
            logger.info(f"[Sicon engineers] {totals}")
    except Exception as e:
        logger.warning(f"[Sicon engineers] refresh failed: {e}")


_LAST_NUDGE_RUN: dict = {"date": None}


async def _run_proactive_nudges_daily() -> None:
    """Run the proactive-nudge scanners once per UTC day. Idempotent."""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        if _LAST_NUDGE_RUN.get("date") == today:
            return
        from utils.proactive_nudges import run_proactive_nudges
        totals = await run_proactive_nudges()
        _LAST_NUDGE_RUN["date"] = today
        logger.info(f"[Nudges] daily run {totals}")
    except Exception as e:
        logger.warning(f"[Nudges] daily run failed: {e}")


_LAST_PII_PURGE: dict = {"date": None}


async def _run_pii_retention_daily() -> None:
    """Purge archived orgs older than PII_RETENTION_DAYS. Runs once per UTC day."""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        if _LAST_PII_PURGE.get("date") == today:
            return
        from utils.hardening import purge_archived_orgs
        totals = await purge_archived_orgs()
        _LAST_PII_PURGE["date"] = today
        if totals.get("orgs_purged"):
            logger.info(f"[PII retention] purged {totals}")
    except Exception as e:
        logger.warning(f"[PII retention] daily run failed: {e}")


_LAST_DIGEST_HOUR: dict = {"stamp": None}


async def _run_digest_dispatcher_hourly() -> None:
    """Dispatch due digests once per wall-clock hour."""
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        if _LAST_DIGEST_HOUR.get("stamp") == stamp:
            return
        from utils.digest import dispatch_due_digests
        totals = await dispatch_due_digests()
        _LAST_DIGEST_HOUR["stamp"] = stamp
        if totals.get("sent"):
            logger.info(f"[digest] hourly dispatch {totals}")
    except Exception as e:
        logger.warning(f"[digest] hourly dispatch failed: {e}")


_LAST_MOD_ROTATION_RUN: dict = {"date": None}


async def _run_mod_password_rotation_daily() -> None:
    """Scan MOD site-code passwords once per UTC day. Idempotent."""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        if _LAST_MOD_ROTATION_RUN.get("date") == today:
            return
        from utils.mod_password_rotation import scan_mod_password_rotation
        totals = await scan_mod_password_rotation()
        _LAST_MOD_ROTATION_RUN["date"] = today
        if totals.get("reminders_sent"):
            logger.info(f"[MOD rotation] daily scan {totals}")
    except Exception as e:
        logger.warning(f"[MOD rotation] daily scan failed: {e}")


async def _poll_once() -> None:
    """Run one poll cycle across all Sicon-enabled organizations + lifecycle sweeps."""
    cursor = db.sicon_config.find({"enabled": True}, {"_id": 0, "organization_id": 1})
    async for cfg in cursor:
        org_id = cfg.get("organization_id")
        if org_id:
            await _run_org_poll_cycle(org_id)

    await _run_trial_lifecycle()
    await _run_archive_lifecycle()
    await _run_trust_collectors()
    await _run_support_analytics_rollup()
    await _run_engineer_directory_refresh()
    await _run_proactive_nudges_daily()
    await _run_pii_retention_daily()
    await _run_digest_dispatcher_hourly()
    await _run_mod_password_rotation_daily()
    await _run_mod_readiness_weekly()
    await _run_booking_reminders()
    await _run_abandoned_checkout_sweep()
    await _run_memberships_weekly_digest()
    await _run_memberships_winback()
    await _run_lifecycle_emails()
    await _run_equipment_image_backfill_weekly()
    await _run_marketing_autopilot()
    await _run_memberships_crm_loop()
    await _run_family_autopay()
    await _run_ppm_autogen()
    await _run_svc_digest_dispatcher()


async def _run_svc_digest_dispatcher() -> None:
    """Phase 6+: send daily/weekly Service Ops digest emails when due."""
    try:
        from utils.svc_digest import run_svc_digest_dispatcher
        await run_svc_digest_dispatcher()
    except Exception:
        logger.exception("[svc-digest] cycle failed")


async def _run_family_autopay() -> None:
    """Iter 215aa — monthly Family Auto-Bill sweep. The helper
    short-circuits outside the 1st-3rd of the month and dedupes via
    ``system_jobs`` locks so this is safe to invoke every cron tick."""
    try:
        from routes.memberships.family_autopay import run_family_autopay_cycle
        stats = await run_family_autopay_cycle()
        if stats.get("attempted"):
            logger.info("[family-autopay] %s", stats)
    except Exception:
        logger.exception("[family-autopay] cycle failed")

    # Iter 215ad — daily dunning retry ladder. Runs every cron tick
    # but only actually does work for invoices whose
    # ``auto_pay_next_retry_at`` has come due.
    try:
        from routes.memberships.family_autopay import run_autopay_retry_ladder
        stats = await run_autopay_retry_ladder()
        if stats.get("retried"):
            logger.info("[autopay-retry-ladder] %s", stats)
    except Exception:
        logger.exception("[autopay-retry-ladder] cycle failed")


async def _run_memberships_crm_loop() -> None:
    """Phase 6: detect member signals + auto-fire CRM/marketing emails."""
    try:
        from routes.memberships_phase6 import run_crm_loop_cycle
        await run_crm_loop_cycle()
    except Exception:
        logger.exception("[memberships-crm-loop] cycle failed")


async def _run_ppm_autogen() -> None:
    """Phase 2: spawn service-desk cases from PPM tasks coming due."""
    try:
        from utils.ppm_autogen import run_ppm_autogen_cycle
        await run_ppm_autogen_cycle()
    except Exception:
        logger.exception("[ppm-autogen] cycle failed")


async def _run_marketing_autopilot() -> None:
    """Marketing Autopilot: send-when-due + auto post-mortem sweeps."""
    try:
        from utils.marketing_autopilot import run_autopilot_cycle
        await run_autopilot_cycle()
    except Exception:
        logger.exception("[marketing-autopilot] cycle failed")


async def _run_equipment_image_backfill_weekly() -> None:
    """Monday 03:00 UTC — auto-find manufacturer images for equipment that
    has none. Idempotent per day + per-weekday gated."""
    try:
        from utils.equipment_image_cron import run_equipment_image_backfill
        await run_equipment_image_backfill()
    except Exception:
        logger.exception("[equipment-image-backfill] cycle failed")


async def _run_memberships_winback() -> None:
    """Fire 'we've missed you' emails to lapsed members (>=7 days off after a 5+ day streak)."""
    try:
        from utils.memberships_winback import run_winback_dispatcher
        await run_winback_dispatcher()
    except Exception:
        logger.exception("[memberships-winback] cycle failed")


async def _run_lifecycle_emails() -> None:
    """Iter 215c2 — trial nurture + winback emails for the operator side
    of the platform. Idempotent (dedupe per org+template)."""
    try:
        from utils.lifecycle_emails import send_lifecycle_emails
        await send_lifecycle_emails()
    except Exception:
        logger.exception("[lifecycle-emails] cycle failed")


async def _run_memberships_weekly_digest() -> None:
    """Fire weekly digest on UTC-Monday. The dispatcher itself gates on
    weekday + per-org idempotency so we can safely call it every cycle."""
    try:
        from utils.memberships_digest import run_weekly_digest_dispatcher
        await run_weekly_digest_dispatcher()
    except Exception:
        logger.exception("[memberships-digest] cycle failed")


async def _run_abandoned_checkout_sweep() -> None:
    try:
        from routes.memberships_payments import sweep_abandoned_checkouts
        await sweep_abandoned_checkouts()
    except Exception:
        logger.exception("[abandoned-checkout-sweep] cycle failed")


async def _run_mod_readiness_weekly() -> None:
    """Monday 09:00 UTC — email HQ the whole-of-MOD go-live readiness Excel.
    Self-gated to Monday morning + idempotent per week via system_jobs."""
    try:
        from utils.mod_readiness_digest import run_mod_readiness_weekly
        res = await run_mod_readiness_weekly()
        if res.get("sent"):
            logger.info(f"[mod-readiness] weekly email {res}")
    except Exception:
        logger.exception("[mod-readiness] cycle failed")


async def _run_booking_reminders() -> None:
    try:
        from utils.booking_reminders import run_booking_reminders
        await run_booking_reminders()
    except Exception:
        logger.exception("[bookings-reminders] cycle failed")


async def poller_loop() -> None:
    """Long-running loop. Runs once immediately, then every POLL_INTERVAL_SECONDS."""
    logger.info(f"Sicon poller started (interval={POLL_INTERVAL_SECONDS}s)")
    while True:
        try:
            await _poll_once()
        except asyncio.CancelledError:
            logger.info("Sicon poller cancelled")
            raise
        except Exception as e:
            logger.error(f"Sicon poller iteration error: {e}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_poller() -> None:
    """Start the background poller task if not already running."""
    global _poller_task
    if _poller_task and not _poller_task.done():
        return
    loop = asyncio.get_event_loop()
    _poller_task = loop.create_task(poller_loop())


def stop_poller() -> None:
    global _poller_task
    if _poller_task and not _poller_task.done():
        _poller_task.cancel()
    _poller_task = None
