"""Iter 216h128 — Pulse Sales CAPEX-sourced opportunity engine.

Generates internal Pulse Fitness sales opportunities whenever a
Pulse customer's equipment hits a CAPEX 'monitor' / 'at_risk' /
'replace_soon' / 'replace_now' band. These opportunities are
*strictly invisible* to the customer and only readable by:

  • Pulse Fitness Master Admin (admin@pulsefitness.ai)
  • Pulse Master Admin (delegated via `is_pulse_admin=true`)

Customers (Third Space, MOD HQ, MOD sub-orgs) never see this view.
The data feeds Pulse Fitness's internal sales pipeline so the team
can proactively pitch replacements before a customer needs to ask.

Scope: tenants with account_type in PULSE_SALES_TARGET_TYPES.

Auto-dismiss: opportunities older than 60 days with no activity are
moved to status='dismissed' by the daily sweeper.

Persisted shape (`db.pulse_sales_opportunities`):
{
  id, organization_id, organization_name, equipment_id, equipment_name,
  equipment_type, location, capex_status, capex_score, replacement_cost,
  severity_signal, status, assigned_to, notes[], created_at,
  updated_at, last_activity_at, auto_dismiss_at, dismissed_at,
  source: "capex.scan"
}
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()

PULSE_SALES_TARGET_TYPES = ("pulse_pro", "mod_site", "mod_branch", "mod_org")
ACTIVE_STATUSES = ("new", "contacted", "qualified")
TERMINAL_STATUSES = ("won", "lost", "dismissed")
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES
AUTO_DISMISS_DAYS = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signal_for(capex_status: str, capex_score: float | int) -> str:
    if capex_status == "replace_now":
        return "urgent"
    if capex_status == "replace_soon":
        return "high"
    if capex_status == "at_risk":
        return "medium"
    return "low"


async def _list_target_orgs() -> list[dict]:
    return await db.organizations.find(
        {"account_type": {"$in": list(PULSE_SALES_TARGET_TYPES)}},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    ).to_list(2000)


async def _scan_org_for_opportunities(org: dict, now_iso: str) -> dict:
    """Walk one org's CAPEX state and upsert opportunities.

    Idempotent — keyed by (organization_id, equipment_id, source).
    Existing rows in TERMINAL_STATUSES are left alone (won't be
    re-opened by the sweeper).
    """
    from routes.capex import (
        _get_thresholds,
        _build_severity_lookup,
        _aggregate_capex_results,
    )
    from utils.helpers import get_bulk_equipment_stats

    org_id = org["id"]
    org_filter = {"organization_id": org_id}
    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(5000)
    if not equipment_list:
        return {"org_id": org_id, "scanned": 0, "created": 0, "updated": 0}

    bulk_stats = await get_bulk_equipment_stats(equipment_list, org_filter)
    all_issues = await db.issues.find(
        org_filter,
        {"_id": 0, "id": 1, "serial_number": 1, "severity": 1,
         "resolution_type": 1, "resolved_by": 1, "equipment_id": 1,
         "issue_description": 1, "status": 1, "created_at": 1,
         "resolved_at": 1, "updated_at": 1},
    ).to_list(20000)
    severity_lookup, selffix_lookup = _build_severity_lookup(all_issues)
    thresholds = await _get_thresholds(org_id)
    faults_by_eq: dict[str, list] = {}
    for iss in all_issues:
        eid = iss.get("equipment_id")
        if eid:
            faults_by_eq.setdefault(eid, []).append(iss)
    results, _, _, _, _, _, _ = _aggregate_capex_results(
        equipment_list, bulk_stats, severity_lookup, selffix_lookup,
        thresholds, faults_by_eq,
    )
    flagged = [
        r for r in results
        if (r.get("capex") or {}).get("status") in
           ("monitor", "at_risk", "replace_soon", "replace_now")
    ]
    created = 0
    updated = 0
    for r in flagged:
        capex = r.get("capex") or {}
        equipment_id = r.get("id")
        existing = await db.pulse_sales_opportunities.find_one(
            {"organization_id": org_id, "equipment_id": equipment_id,
             "source": "capex.scan"},
            {"_id": 0},
        )
        signal = _signal_for(capex.get("status", "monitor"), capex.get("score", 0))
        payload: dict[str, Any] = {
            "organization_id": org_id,
            "organization_name": org.get("name") or "Unknown",
            "account_type": org.get("account_type"),
            "equipment_id": equipment_id,
            "equipment_name": r.get("name"),
            "equipment_type": r.get("equipment_type"),
            "location": r.get("location"),
            "capex_status": capex.get("status"),
            "capex_score": capex.get("score"),
            "replacement_cost": capex.get("replacement_cost"),
            "severity_signal": signal,
            "source": "capex.scan",
            "updated_at": now_iso,
            "last_capex_observed_at": now_iso,
        }
        if not existing:
            payload.update({
                "id": str(uuid.uuid4()),
                "status": "new",
                "assigned_to": None,
                "notes": [],
                "created_at": now_iso,
                "last_activity_at": now_iso,
                "auto_dismiss_at": (
                    datetime.now(timezone.utc) + timedelta(days=AUTO_DISMISS_DAYS)
                ).isoformat(),
            })
            await db.pulse_sales_opportunities.insert_one({**payload})
            created += 1
        else:
            # Don't re-open closed rows
            if existing.get("status") in TERMINAL_STATUSES:
                continue
            await db.pulse_sales_opportunities.update_one(
                {"id": existing["id"]},
                {"$set": payload},
            )
            updated += 1
    return {"org_id": org_id, "scanned": len(flagged),
            "created": created, "updated": updated}


async def sweep_capex_opportunities() -> dict:
    """Scan every Pulse-target org and refresh opportunities.

    Also performs the auto-dismiss pass on stale rows.
    Idempotent — safe to run hourly or daily.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    targets = await _list_target_orgs()
    totals = {"orgs_scanned": 0, "created": 0, "updated": 0,
              "auto_dismissed": 0, "errors": 0}
    for org in targets:
        try:
            r = await _scan_org_for_opportunities(org, now_iso)
            totals["orgs_scanned"] += 1
            totals["created"] += r["created"]
            totals["updated"] += r["updated"]
        except Exception as exc:  # pragma: no cover
            totals["errors"] += 1
            logger.warning("[pulse-sales] scan failed for %s: %s",
                           org.get("id"), exc)
    # Auto-dismiss stale rows
    cutoff = (now - timedelta(days=AUTO_DISMISS_DAYS)).isoformat()
    auto_res = await db.pulse_sales_opportunities.update_many(
        {"status": {"$in": list(ACTIVE_STATUSES)},
         "last_activity_at": {"$lt": cutoff}},
        {"$set": {"status": "dismissed",
                  "dismissed_at": now_iso,
                  "dismissed_reason": "auto_dismiss_60d_inactive",
                  "updated_at": now_iso}},
    )
    totals["auto_dismissed"] = auto_res.modified_count
    logger.info("[pulse-sales] sweep complete %s", totals)
    return totals


# ───────────────────────── HTTP API ───────────────────────────────


def _require_pulse_sales_reader(user: dict) -> None:
    """Allow Pulse Fitness MA + Pulse MA only."""
    require_master_admin(user)


class OpportunityUpdate(BaseModel):
    status: str | None = Field(default=None)
    assigned_to: str | None = None
    note: str | None = Field(default=None, max_length=1000)


@router.get("/pulse-sales/opportunities")
async def list_opportunities(
    user: dict = Depends(get_current_user),
    status: str | None = None,
    organization_id: str | None = None,
    severity: str | None = None,
    include_dismissed: bool = False,
    limit: int = 200,
):
    """List Pulse-internal CAPEX opportunities. Master-admin gated."""
    _require_pulse_sales_reader(user)
    # Iter 220as — clamp client-supplied limit to MAX_LIMIT.
    from utils.pagination import safe_limit
    limit = safe_limit(limit, default=200, hard_max=500)
    q: dict[str, Any] = {}
    if status:
        if status not in ALL_STATUSES:
            raise HTTPException(status_code=400, detail="invalid status")
        q["status"] = status
    elif not include_dismissed:
        q["status"] = {"$nin": ["dismissed"]}
    if organization_id:
        q["organization_id"] = organization_id
    if severity:
        q["severity_signal"] = severity
    rows = await db.pulse_sales_opportunities.find(
        q, {"_id": 0},
    ).sort([("severity_signal", -1), ("updated_at", -1)]).to_list(max(1, min(500, limit)))
    # Build a tiny summary header
    summary = {s: 0 for s in ALL_STATUSES}
    counts = await db.pulse_sales_opportunities.aggregate(
        [{"$group": {"_id": "$status", "n": {"$sum": 1}}}],
    ).to_list(20)
    for c in counts:
        if c["_id"] in summary:
            summary[c["_id"]] = c["n"]
    return {"opportunities": rows, "summary": summary, "total": len(rows)}


@router.get("/pulse-sales/summary")
async def summary(user: dict = Depends(get_current_user)):
    _require_pulse_sales_reader(user)
    counts_by_status = {s: 0 for s in ALL_STATUSES}
    counts_by_severity = {"urgent": 0, "high": 0, "medium": 0, "low": 0}
    pipeline_value = 0
    rows = await db.pulse_sales_opportunities.aggregate(
        [{"$group": {"_id": {"status": "$status", "severity": "$severity_signal"},
                     "n": {"$sum": 1},
                     "value": {"$sum": {"$ifNull": ["$replacement_cost", 0]}}}}],
    ).to_list(100)
    for r in rows:
        st = r["_id"]["status"]
        sv = r["_id"]["severity"]
        if st in counts_by_status:
            counts_by_status[st] += r["n"]
        if sv in counts_by_severity:
            counts_by_severity[sv] += r["n"]
        if st in ACTIVE_STATUSES:
            pipeline_value += r["value"] or 0
    by_org = await db.pulse_sales_opportunities.aggregate([
        {"$match": {"status": {"$in": list(ACTIVE_STATUSES)}}},
        {"$group": {
            "_id": {"id": "$organization_id", "name": "$organization_name",
                    "account_type": "$account_type"},
            "n": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$replacement_cost", 0]}},
        }},
        {"$sort": {"value": -1}},
        {"$limit": 25},
    ]).to_list(50)
    top_orgs = [{
        "organization_id": r["_id"]["id"],
        "organization_name": r["_id"].get("name") or "Unknown",
        "account_type": r["_id"].get("account_type"),
        "active_opportunities": r["n"],
        "pipeline_value": r["value"] or 0,
    } for r in by_org]
    return {
        "by_status": counts_by_status,
        "by_severity": counts_by_severity,
        "active_pipeline_value": pipeline_value,
        "top_orgs": top_orgs,
    }


@router.patch("/pulse-sales/opportunities/{opportunity_id}")
async def update_opportunity(
    opportunity_id: str,
    body: OpportunityUpdate,
    user: dict = Depends(get_current_user),
):
    _require_pulse_sales_reader(user)
    row = await db.pulse_sales_opportunities.find_one(
        {"id": opportunity_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    set_payload: dict[str, Any] = {"updated_at": _now_iso(),
                                   "last_activity_at": _now_iso()}
    push_payload: dict[str, Any] = {}
    if body.status is not None:
        if body.status not in ALL_STATUSES:
            raise HTTPException(status_code=400, detail="invalid status")
        set_payload["status"] = body.status
        if body.status in TERMINAL_STATUSES:
            set_payload["closed_at"] = _now_iso()
            set_payload["closed_by"] = user.get("email")
    if body.assigned_to is not None:
        set_payload["assigned_to"] = body.assigned_to.strip() or None
    if body.note:
        push_payload["notes"] = {
            "id": str(uuid.uuid4()),
            "author_email": user.get("email"),
            "author_name": user.get("full_name") or user.get("email"),
            "text": body.note.strip(),
            "created_at": _now_iso(),
        }
    update: dict[str, Any] = {"$set": set_payload}
    if push_payload:
        update["$push"] = push_payload
    await db.pulse_sales_opportunities.update_one({"id": opportunity_id}, update)
    fresh = await db.pulse_sales_opportunities.find_one(
        {"id": opportunity_id}, {"_id": 0},
    )
    return {"opportunity": fresh}


@router.post("/pulse-sales/sweep-capex")
async def trigger_sweep(user: dict = Depends(get_current_user)):
    """Manual trigger of the CAPEX scan (master-admin only)."""
    _require_pulse_sales_reader(user)
    result = await sweep_capex_opportunities()
    return {"success": True, "result": result}
