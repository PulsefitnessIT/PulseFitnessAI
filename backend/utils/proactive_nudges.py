"""
Proactive Nudges (P2, Feb 2026).

Nightly scanners that scan each organization's data for looming issues and
emit ``trust_events`` scoped to the org. The frontend reads
``/api/nudges`` and surfaces a gentle "3 items need attention" banner.

Three initial scanners:

1. ``warranty_expiring`` — equipment whose ``warranty_expiry`` falls within
   the next 30 days.
2. ``ppm_overdue`` — PPM tasks in ``scheduled`` state whose ``scheduled_date``
   is in the past.
3. ``supplier_sla_drift`` — suppliers whose closed-case CSAT in the last
   90 days is averaging below 3.0 stars.

All scanners are idempotent (``dedupe_key`` per condition per org) so running
the poll cycle every 5 minutes does not spam events.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.database import db
from utils.trust_events import record_trust_event, auto_resolve_trust_event

logger = logging.getLogger(__name__)

WARRANTY_WINDOW_DAYS = 30
SLA_DRIFT_WINDOW_DAYS = 90
SLA_DRIFT_MIN_RATINGS = 3
SLA_DRIFT_THRESHOLD = 3.0

NUDGE_VISIBILITY = ["org_owner", "org_manager"]


def _iso(d: datetime) -> str:
    return d.isoformat()


async def _iter_active_orgs() -> list[dict]:
    """Return every non-archived org the scanner should evaluate."""
    return await db.organizations.find(
        {"archived_at": {"$in": [None, "", False]}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(2000)


# ─── Scanner 1 · Warranty expiring ────────────────────────────────

async def scan_warranty_expiring(org: dict) -> None:
    org_id = org["id"]
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=WARRANTY_WINDOW_DAYS)
    today_s, horizon_s = today.isoformat(), horizon.isoformat()

    cursor = db.equipment.find(
        {"organization_id": org_id,
         "warranty_expiry": {"$gte": today_s, "$lte": horizon_s}},
        {"_id": 0, "id": 1, "name": 1, "warranty_expiry": 1, "serial_number": 1},
    )
    items = await cursor.to_list(500)
    dedupe = f"nudge.warranty_expiring:{org_id}"
    if not items:
        await auto_resolve_trust_event(dedupe, note="No equipment inside warranty window")
        return

    soonest = min(e["warranty_expiry"] for e in items if e.get("warranty_expiry"))
    plural = len(items) != 1
    msg = (
        f"{len(items)} piece{'s' if plural else ''} of equipment "
        f"{'go' if plural else 'goes'} out of warranty by {soonest}. "
        f"Consider renewing cover or raising any outstanding claims."
    )
    await record_trust_event(
        type="nudge.warranty_expiring",
        severity="med" if len(items) >= 5 else "low",
        org_id=org_id,
        summary=f"{len(items)} item(s) have warranty expiring in the next {WARRANTY_WINDOW_DAYS} days",
        customer_safe_message=msg,
        payload={"count": len(items), "soonest": soonest,
                 "items": [{"id": e["id"], "name": e.get("name"),
                            "expires": e.get("warranty_expiry")} for e in items[:10]]},
        visible_to=NUDGE_VISIBILITY,
        dedupe_key=dedupe,
    )


# ─── Scanner 2 · PPM overdue ──────────────────────────────────────

async def scan_ppm_overdue(org: dict) -> None:
    org_id = org["id"]
    today_s = datetime.now(timezone.utc).date().isoformat()

    cursor = db.ppm_tasks.find(
        {"organization_id": org_id,
         "status": "scheduled",
         "scheduled_date": {"$lt": today_s}},
        {"_id": 0, "id": 1, "title": 1, "scheduled_date": 1, "schedule_id": 1},
    )
    overdue = await cursor.to_list(500)
    dedupe = f"nudge.ppm_overdue:{org_id}"
    if not overdue:
        await auto_resolve_trust_event(dedupe, note="No overdue PPM tasks")
        return

    oldest = min(t["scheduled_date"] for t in overdue if t.get("scheduled_date"))
    await record_trust_event(
        type="nudge.ppm_overdue",
        severity="high" if len(overdue) >= 10 else "med",
        org_id=org_id,
        summary=f"{len(overdue)} PPM task(s) are overdue (oldest {oldest})",
        customer_safe_message=(
            f"{len(overdue)} planned-maintenance task"
            f"{'s are' if len(overdue) != 1 else ' is'} overdue. "
            f"The oldest has been waiting since {oldest}."
        ),
        payload={"count": len(overdue), "oldest": oldest,
                 "tasks": [{"id": t["id"], "title": t.get("title"),
                            "scheduled": t.get("scheduled_date")} for t in overdue[:10]]},
        visible_to=NUDGE_VISIBILITY,
        dedupe_key=dedupe,
    )


# ─── Scanner 3 · Supplier SLA drift ───────────────────────────────

async def _compute_supplier_drift(org_id: str, since_iso: str) -> list[dict]:
    """Aggregate closed-case ratings per supplier over the last 90 days."""
    pipeline: list[dict] = [
        {"$match": {
            "organization_id": org_id,
            "current_status": {"$in": ["resolved", "closed"]},
            "rating": {"$gte": 1, "$lte": 5},
            "updated_at": {"$gte": since_iso},
        }},
        {"$group": {
            "_id": "$supplier_name",
            "avg": {"$avg": "$rating"},
            "count": {"$sum": 1},
        }},
        {"$match": {
            "count": {"$gte": SLA_DRIFT_MIN_RATINGS},
            "avg": {"$lt": SLA_DRIFT_THRESHOLD},
        }},
    ]
    return await db.supplier_cases.aggregate(pipeline).to_list(50)


async def scan_supplier_sla_drift(org: dict) -> None:
    org_id = org["id"]
    since = datetime.now(timezone.utc) - timedelta(days=SLA_DRIFT_WINDOW_DAYS)
    drifting = await _compute_supplier_drift(org_id, _iso(since))
    dedupe = f"nudge.supplier_sla_drift:{org_id}"
    if not drifting:
        await auto_resolve_trust_event(dedupe, note="All suppliers above threshold")
        return

    worst = min(drifting, key=lambda r: r.get("avg", 5))
    await record_trust_event(
        type="nudge.supplier_sla_drift",
        severity="med",
        org_id=org_id,
        summary=f"{len(drifting)} supplier(s) averaging below {SLA_DRIFT_THRESHOLD}/5 over the last {SLA_DRIFT_WINDOW_DAYS} days",
        customer_safe_message=(
            f"{worst['_id']} is averaging {worst['avg']:.1f}/5 across "
            f"{int(worst['count'])} recent jobs. It may be worth a quarterly review."
        ),
        payload={"suppliers": [{"name": r["_id"], "avg": round(r["avg"], 2),
                                "count": int(r["count"])} for r in drifting]},
        visible_to=NUDGE_VISIBILITY,
        dedupe_key=dedupe,
    )


# ─── Public entry point ───────────────────────────────────────────

_SCANNERS: tuple[Any, ...] = (scan_warranty_expiring, scan_ppm_overdue, scan_supplier_sla_drift)


async def run_proactive_nudges() -> dict:
    """Run every scanner for every org. Returns summary counts. Never raises."""
    totals = {"orgs": 0, "scanners": 0, "errors": 0}
    orgs = await _iter_active_orgs()
    totals["orgs"] = len(orgs)
    for org in orgs:
        for scanner in _SCANNERS:
            try:
                await scanner(org)
                totals["scanners"] += 1
            except Exception as exc:  # never break the poller
                totals["errors"] += 1
                logger.warning(f"[nudges] {scanner.__name__} failed for {org.get('id')}: {exc}")
    # Iter 216h115 — sweep MOD fault acceptance timeouts (org-agnostic).
    try:
        from utils.mod_acceptance import sweep_pending_acceptances
        sweep_result = await sweep_pending_acceptances()
        totals["mod_acceptance"] = sweep_result
    except Exception as exc:  # pragma: no cover
        totals["errors"] += 1
        logger.warning(f"[nudges] mod_acceptance sweep failed: {exc}")
    # Iter 216h116 — sweep posting-out deactivations + compliance reminders.
    try:
        from utils.mod_postings import sweep_posting_outs
        totals["mod_postings"] = await sweep_posting_outs()
    except Exception as exc:  # pragma: no cover
        totals["errors"] += 1
        logger.warning(f"[nudges] mod_postings sweep failed: {exc}")
    try:
        from routes.mod_compliance import sweep_compliance_reminders
        totals["mod_compliance"] = await sweep_compliance_reminders()
    except Exception as exc:  # pragma: no cover
        totals["errors"] += 1
        logger.warning(f"[nudges] mod_compliance sweep failed: {exc}")
    # Iter 216h117 — RIDDOR 7-day follow-up reminders.
    try:
        from routes.mod_incidents import sweep_riddor_followups
        totals["mod_riddor"] = await sweep_riddor_followups()
    except Exception as exc:  # pragma: no cover
        totals["errors"] += 1
        logger.warning(f"[nudges] mod_riddor sweep failed: {exc}")
    logger.info(f"[nudges] cycle complete {totals}")
    return totals
