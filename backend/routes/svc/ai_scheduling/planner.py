from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from utils.auth import get_current_user
from utils.audit import audit_log
from utils.database import db
from utils.svc_state import (
    OPEN_STATES, TERMINAL_STATES,
    ASSIGNED, NEW, TRIAGED, EN_ROUTE, ON_SITE,
    PAUSED_PARTS, PAUSED_CUSTOMER, REPAIRED, AWAITING_SIGN_OFF,
)
from routes.svc.scheduler import _score_engineers_for_case, _drive_minutes_estimate
from routes.svc.diary import admin_assign_case, AssignIn, _require_dispatcher
from routes.partners import require_engineer_app_access
from ._shared import *  # noqa: F401,F403


@router.get("/board")
async def scheduling_board(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    user=Depends(get_current_user),
):
    of = _of(user)
    _require_dispatcher(user)
    date_str = date or _now_dt().date().isoformat()
    lock_ids = await _lock_ids(of["organization_id"])
    engineers = await db.svc_engineers.find(
        {**of, "active": {"$ne": False}}, {"_id": 0},
    ).sort("full_name", 1).to_list(500)

    rows = []
    risk_count = 0
    movable_count = 0
    locked_count = len(lock_ids)
    for eng in engineers:
        jobs = await db.svc_cases.find(
            {**of, "assigned_engineer_id": eng["id"],
             "status": {"$in": list(OPEN_STATES)},
             "scheduled_at": {"$gte": date_str, "$lt": date_str + "T23:59:59Z"}},
            {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
             "status": 1, "site_name": 1, "site_postcode": 1, "customer_name": 1,
             "scheduled_at": 1, "estimated_minutes": 1, "sla_resolve_at": 1},
        ).sort("scheduled_at", 1).to_list(200)
        job_rows = []
        for j in jobs:
            pr = _protect_reason(j, lock_ids)
            old_dt = _parse_iso(j.get("scheduled_at"))
            est = int(j.get("estimated_minutes") or 60)
            sla = _sla_state((old_dt + timedelta(minutes=est)) if old_dt else None, j.get("sla_resolve_at"))
            if sla in ("at_risk", "breached"):
                risk_count += 1
            if not pr:
                movable_count += 1
            job_rows.append({**j, "protected": bool(pr), "protected_reason": pr, "sla_state": sla})
        rows.append({"engineer_id": eng["id"], "engineer_name": eng.get("full_name"),
                     "jobs": job_rows, "job_count": len(job_rows)})

    # Unassigned / priority jobs waiting for a slot
    unassigned = await db.svc_cases.count_documents(
        {**of, "status": {"$in": list(OPEN_STATES)},
         "$or": [{"assigned_engineer_id": {"$in": [None, ""]}},
                 {"assigned_engineer_id": {"$exists": False}}]},
    )
    return {
        "date": date_str,
        "engineers": rows,
        "stats": {
            "engineers_working": sum(1 for r in rows if r["job_count"] > 0),
            "jobs_at_risk": risk_count,
            "jobs_movable": movable_count,
            "jobs_locked": locked_count,
            "jobs_unassigned": unassigned,
        },
    }


# ── Generate a proposal ───────────────────────────────────────────


@router.post("/replan")
async def replan(body: ReplanIn, user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    if body.mode not in _MODE_STRATEGY and body.mode != "add_priority_job":
        raise HTTPException(400, f"Unknown mode '{body.mode}'")
    return await _generate_proposal(
        user=user, org_id=of["organization_id"], mode=body.mode, date=body.date,
        engineer_ids=body.engineer_ids, priority_case_id=body.priority_case_id,
        engineer_id=body.engineer_id, delay_minutes=body.delay_minutes,
        trigger=body.trigger,
    )


@router.post("/simulate")
async def simulate(body: SimulateIn, user=Depends(get_current_user)):
    """What-if: returns the scheduling impact WITHOUT persisting an
    approvable proposal. Stored as a lightweight simulation record."""
    of = _of(user)
    _require_dispatcher(user)
    org_id = of["organization_id"]
    scenario = body.scenario
    mode_map = {
        "engineer_sick": "engineer_unavailable",
        "engineer_delayed": "engineer_delayed",
        "job_longer": "remaining_day",
        "add_emergency": "add_priority_job",
    }
    if scenario not in mode_map:
        raise HTTPException(400, f"Unknown scenario '{scenario}'")
    result = await _generate_proposal(
        user=user, org_id=org_id, mode=mode_map[scenario], date=body.date,
        engineer_ids=None, priority_case_id=body.priority_case_id,
        engineer_id=body.engineer_id, delay_minutes=body.delay_minutes,
        extra_minutes=body.extra_minutes, longer_case_id=body.case_id,
        trigger=f"simulation:{scenario}", with_narrative=False, persist=False,
    )
    sim_id = str(uuid.uuid4())
    await db.scheduling_simulations.insert_one({
        "id": sim_id, "organization_id": org_id, "scenario": scenario,
        "params": body.model_dump(exclude_none=True),
        "summary": result["proposal"]["summary"],
        "created_by": user.get("id"), "created_at": _now(),
    })
    result["simulation_id"] = sim_id
    return result


@router.get("/duration-insights")
async def duration_insights(user=Depends(get_current_user)):
    """Learned job-duration stats per fault code (estimated vs actual)."""
    of = _of(user)
    _require_dispatcher(user)
    stats = await _duration_stats(of["organization_id"])
    rows = []
    for fc, s in sorted(stats.items(), key=lambda kv: -kv[1]["n"]):
        est = s.get("avg_estimated")
        variance = None
        if est:
            variance = round((s["avg"] - est) / est * 100)
        rows.append({"fault_code": fc, "sample_count": s["n"],
                     "avg_actual_minutes": s["avg"], "avg_estimated_minutes": est,
                     "variance_pct": variance})
    return {"insights": rows, "count": len(rows)}


# ── List / fetch proposals ────────────────────────────────────────


@router.get("/proposals")
async def list_proposals(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
):
    of = _of(user)
    _require_dispatcher(user)
    # Auto-expire stale awaiting_approval proposals so the inbox self-cleans.
    await db.scheduling_proposals.update_many(
        {**of, "status": "awaiting_approval", "expires_at": {"$lt": _now()}},
        {"$set": {"status": "expired", "updated_at": _now()}},
    )
    q = dict(of)
    if status:
        q["status"] = status
    rows = await db.scheduling_proposals.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"proposals": rows, "count": len(rows)}


@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    proposal = await db.scheduling_proposals.find_one({"id": proposal_id, **of}, {"_id": 0})
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    items = await db.scheduling_proposal_items.find(
        {"proposal_id": proposal_id, **of}, {"_id": 0},
    ).to_list(1000)
    items.sort(key=lambda i: (i.get("new_engineer_name") or "", i.get("new_order") if i.get("new_order") is not None else 999))
    return {"proposal": proposal, "items": items}


# ── Approve / reject ──────────────────────────────────────────────


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, body: DecisionIn, user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    proposal = await db.scheduling_proposals.find_one({"id": proposal_id, **of}, {"_id": 0})
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if proposal["status"] in ("applied", "cancelled", "rejected", "expired"):
        raise HTTPException(409, f"Proposal already {proposal['status']}")

    items = await db.scheduling_proposal_items.find(
        {"proposal_id": proposal_id, **of}, {"_id": 0},
    ).to_list(1000)
    target_ids = set(body.item_ids or [])
    applied, skipped, errors = 0, 0, []
    settings = await _get_settings(of["organization_id"])
    cust_notify = bool((settings.get("customer_notifications") or {}).get("enabled"))

    for it in items:
        if it["change_type"] not in _APPLY_CHANGES:
            continue  # protected / unchanged — nothing to apply
        if not body.approve_all and it["id"] not in target_ids:
            continue
        try:
            assign = AssignIn(
                engineer_id=it.get("new_engineer_id") or it["engineer_id"],
                scheduled_at=it["new_scheduled_at"],
                estimated_minutes=it.get("estimated_minutes"),
            )
            await admin_assign_case(it["case_id"], assign, user)
            await db.scheduling_proposal_items.update_one(
                {"id": it["id"], **of},
                {"$set": {"decision": "applied", "decided_by": user.get("id"),
                          "decided_at": _now(),
                          "override_reason": body.override_reason}},
            )
            # Record an engineer-facing schedule change to acknowledge.
            try:
                eng_target = it.get("new_engineer_id") or it["engineer_id"]
                await db.scheduling_changes.insert_one({
                    "id": str(uuid.uuid4()), "organization_id": of["organization_id"],
                    "engineer_id": eng_target, "case_id": it["case_id"],
                    "reference": it.get("reference"), "title": it.get("title"),
                    "change_type": it["change_type"],
                    "old_scheduled_at": it.get("old_scheduled_at"),
                    "new_scheduled_at": it.get("new_scheduled_at"),
                    "reason": it.get("reason"), "proposal_id": proposal_id,
                    "acknowledged": False, "created_at": _now(),
                })
            except Exception:  # noqa: BLE001
                pass
            # Customer comms on reschedule (gated by org settings; default off).
            if cust_notify and it["change_type"] in ("move", "reassign", "defer"):
                try:
                    await _notify_customer_reschedule(it, of["organization_id"], user)
                except Exception:  # noqa: BLE001
                    pass
            applied += 1
        except HTTPException as e:
            errors.append({"case_id": it["case_id"], "detail": str(e.detail)})
        except Exception as e:  # noqa: BLE001
            logger.warning("apply scheduling item failed case=%s: %s", it["case_id"], e)
            errors.append({"case_id": it["case_id"], "detail": "apply failed"})

    actionable = [i for i in items if i["change_type"] in _APPLY_CHANGES]
    applied_now = await db.scheduling_proposal_items.count_documents(
        {"proposal_id": proposal_id, **of, "decision": "applied"},
    )
    new_status = "applied" if applied_now >= len(actionable) and not errors else "partially_approved"
    if applied == 0 and not errors:
        skipped = len(actionable)
    await db.scheduling_proposals.update_one(
        {"id": proposal_id, **of},
        {"$set": {"status": new_status, "updated_at": _now(),
                  "applied_count": applied_now}},
    )
    await _audit(of["organization_id"], proposal_id, "proposal_approved", user,
                 f"applied={applied} status={new_status}"
                 + (f" override={body.override_reason}" if body.override_reason else ""))
    proposal = await db.scheduling_proposals.find_one({"id": proposal_id, **of}, {"_id": 0})
    return {"ok": True, "applied": applied, "skipped": skipped, "errors": errors,
            "proposal": proposal}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, body: DecisionIn, user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    proposal = await db.scheduling_proposals.find_one({"id": proposal_id, **of}, {"_id": 0})
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    target_ids = set(body.item_ids or [])
    item_filter = {"proposal_id": proposal_id, **of}
    if not body.reject_all:
        if not target_ids:
            raise HTTPException(400, "item_ids required unless reject_all=true")
        item_filter["id"] = {"$in": list(target_ids)}
    res = await db.scheduling_proposal_items.update_many(
        {**item_filter, "decision": "pending"},
        {"$set": {"decision": "rejected", "decided_by": user.get("id"), "decided_at": _now()}},
    )
    pending = await db.scheduling_proposal_items.count_documents(
        {"proposal_id": proposal_id, **of, "decision": "pending",
         "change_type": {"$in": list(_APPLY_CHANGES)}},
    )
    applied = await db.scheduling_proposal_items.count_documents(
        {"proposal_id": proposal_id, **of, "decision": "applied"},
    )
    new_status = "rejected" if (body.reject_all or pending == 0) and applied == 0 else proposal["status"]
    await db.scheduling_proposals.update_one(
        {"id": proposal_id, **of}, {"$set": {"status": new_status, "updated_at": _now()}},
    )
    await _audit(of["organization_id"], proposal_id, "proposal_rejected", user,
                 f"rejected={res.modified_count}")
    proposal = await db.scheduling_proposals.find_one({"id": proposal_id, **of}, {"_id": 0})
    return {"ok": True, "rejected": res.modified_count, "proposal": proposal}


# ── Planner job locks ─────────────────────────────────────────────


@router.get("/locks")
async def list_locks(user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    rows = await db.job_locks.find(of, {"_id": 0}).to_list(2000)
    return {"locks": rows, "count": len(rows)}


@router.post("/locks")
async def lock_job(body: LockIn, user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    case = await db.svc_cases.find_one({"id": body.case_id, **of}, {"_id": 0, "id": 1, "reference": 1})
    if not case:
        raise HTTPException(404, "Job not found")
    doc = {
        "id": str(uuid.uuid4()), **of, "case_id": body.case_id,
        "reason": body.reason or "Planner-locked",
        "locked_by": user.get("id"), "locked_by_name": user.get("full_name") or user.get("email"),
        "created_at": _now(),
    }
    await db.job_locks.update_one(
        {"organization_id": of["organization_id"], "case_id": body.case_id},
        {"$set": doc}, upsert=True,
    )
    await _audit(of["organization_id"], None, "job_locked", user, f"case={body.case_id}")
    doc.pop("_id", None)
    return {"ok": True, "lock": doc}


@router.delete("/locks/{case_id}")
async def unlock_job(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    _require_dispatcher(user)
    res = await db.job_locks.delete_one({**of, "case_id": case_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Lock not found")
    await _audit(of["organization_id"], None, "job_unlocked", user, f"case={case_id}")
    return {"ok": True}


# ── Audit helper ──────────────────────────────────────────────────


@router.get("/reports")
async def scheduling_reports(
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
):
    of = _of(user)
    _require_dispatcher(user)
    since = (_now_dt() - timedelta(days=days)).isoformat()
    proposals = await db.scheduling_proposals.find(
        {**of, "created_at": {"$gte": since}}, {"_id": 0},
    ).to_list(2000)
    prop_ids = [p["id"] for p in proposals]
    items = []
    if prop_ids:
        items = await db.scheduling_proposal_items.find(
            {**of, "proposal_id": {"$in": prop_ids}}, {"_id": 0},
        ).to_list(20000)

    actionable = [i for i in items if i["change_type"] in _APPLY_CHANGES]
    applied = [i for i in actionable if i.get("decision") == "applied"]
    rejected = [i for i in actionable if i.get("decision") == "rejected"]
    overrides = [i for i in applied if i.get("override_reason")]
    travel_saved = sum((p.get("summary") or {}).get("travel_saved_minutes", 0) or 0 for p in proposals)

    by_status: dict[str, int] = {}
    for p in proposals:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1

    # Per-engineer utilisation from applied items.
    eng_util: dict[str, dict] = {}
    for i in applied:
        e = eng_util.setdefault(i.get("new_engineer_name") or "Unassigned",
                                {"jobs": 0, "minutes": 0})
        e["jobs"] += 1
        e["minutes"] += int(i.get("estimated_minutes") or 0)

    acceptance = round(len(applied) / len(actionable) * 100) if actionable else None
    return {
        "window_days": days,
        "proposals_generated": len(proposals),
        "proposals_by_status": by_status,
        "jobs_moved": sum(1 for i in applied if i["change_type"] == "move"),
        "jobs_reassigned": sum(1 for i in applied if i["change_type"] == "reassign"),
        "jobs_deferred": sum(1 for i in applied if i["change_type"] == "defer"),
        "jobs_inserted": sum(1 for i in applied if i["change_type"] == "insert"),
        "jobs_protected": sum(1 for i in items if i["change_type"] == "protected"),
        "sla_saved": sum(1 for i in applied if i.get("sla_label") == "saved"),
        "sla_worsened": sum(1 for i in applied if i.get("sla_label") == "worsened"),
        "travel_saved_minutes": travel_saved,
        "ai_acceptance_rate_pct": acceptance,
        "changes_applied": len(applied),
        "changes_rejected": len(rejected),
        "manual_overrides": len(overrides),
        "engineer_utilisation": [
            {"engineer": k, **v} for k, v in sorted(eng_util.items(), key=lambda kv: -kv[1]["jobs"])
        ],
    }
