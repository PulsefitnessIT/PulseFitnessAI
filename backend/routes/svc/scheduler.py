"""
Pulse Fitness Service Operations — Scheduling & Allocation.

Iter 215dq (Phase 3).

Two flavours of allocation:

    1. **Manual** drag-and-drop diary endpoint:
         POST /api/svc/scheduler/assign
         body: {case_id, engineer_id, scheduled_at}

    2. **Heuristic auto-assign** (no LLM required):
         POST /api/svc/scheduler/auto-assign?case_id=X
         scoring formula from §7 of SERVICE_OPS_ARCHITECTURE.md:

           score(engineer, case) =
              100
              - (drive_minutes_from_prev_job × 1.0)
              - (skill_mismatch          × 50)
              + (van_stock_match         × 20)
              - (sla_breach_risk         × 30)
              - (overtime_minutes        × 0.5)

       Picks the highest-scoring engineer, returns top-3 with
       breakdown so the operator can override.

LLM tie-break (Phase 5) layers on top of this without touching the
core scoring code.
"""
__integration_fields__ = {
    # Diary endpoint — read-only aggregate of svc_engineers + svc_cases
    # (already mapped in engineer.py / cases.py manifests). No writes,
    # no new collections.
    "diary.engineers":             "sicon: AppointmentResource[] (read-through from svc_engineers)",
    "diary.cases":                 "sicon: ServiceCall[] (read-through from svc_cases)",
    "diary.unassigned":            "sicon: ServiceCall[] (read-through; unassigned filter)",
    # Manual + auto assign — write-path on svc_cases (mirrored to Sicon)
    "assign.case_id":              "sicon: ServiceCallID · Pulse Fitness → Sicon",
    "assign.engineer_id":          "sicon: AppointmentResourceID · sage: Employee.Reference · Pulse Fitness → both",
    "assign.engineer_name":        "sicon: AppointmentResourceName · Pulse Fitness → Sicon",
    "assign.scheduled_at":         "sicon: AppointmentStartDate · Pulse Fitness → Sicon",
    "assign.estimated_minutes":    "sicon: AppointmentDurationMinutes · Pulse Fitness → Sicon",
    # Auto-assign scoring breakdown — operator UX only (informs Sicon push)
    "score.engineer_id":           "sicon: AppointmentResourceID (winning candidate) · Pulse Fitness → Sicon (when commit=true)",
    "score.value":                 "gymaxis_only: heuristic score (0-100)",
    "score.breakdown.drive_minutes":   "gymaxis_only: scheduler heuristic input",
    "score.breakdown.skill_mismatch":  "gymaxis_only: scheduler heuristic input",
    "score.breakdown.van_match":       "gymaxis_only: scheduler heuristic input",
    "score.breakdown.sla_breach_risk": "gymaxis_only: scheduler heuristic input",
    "score.breakdown.overtime_minutes": "gymaxis_only: scheduler heuristic input",
    # AI tie-break attribution — operator UX
    "ai_tiebreak.chosen_engineer_id": "sicon: AppointmentResourceID (chosen) · Pulse Fitness → Sicon (when commit=true)",
    "ai_tiebreak.reasoning":          "gymaxis_only: operator UX",
    "ai_tiebreak.latency_ms":         "gymaxis_only: AI observability",
}

from datetime import datetime, timezone, timedelta
from typing import Any
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.svc_state import (
    transition as state_transition,
    append_event,
    OPEN_STATES, ASSIGNED, NEW, TRIAGED,
)
from routes.svc.integrations import sicon_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/scheduler", tags=["Service Ops · Scheduler"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Diary view — engineers × time-slots
# ─────────────────────────────────────────────────────────────────

@router.get("/diary")
async def get_diary(
    start: str = Query(..., description="ISO datetime (inclusive) — start of window"),
    days: int = Query(7, ge=1, le=14),
    user=Depends(get_current_user),
):
    """Return engineers + their scheduled cases inside the window.

    The frontend lays them out on a 30-min grid; this endpoint just
    returns the raw rows so we can render any zoom level.
    """
    of = _of(user)
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError as e:
        raise HTTPException(400, "start must be ISO datetime") from e
    end_dt = start_dt + timedelta(days=days)
    engineers = await db.svc_engineers.find(of, {"_id": 0}).sort("full_name", 1).to_list(500)
    cases = await db.svc_cases.find(
        {
            **of,
            "status": {"$in": list(OPEN_STATES)},
            "scheduled_at": {"$ne": None, "$gte": start_dt.isoformat(), "$lt": end_dt.isoformat()},
        },
        {
            "_id": 0,
            "id": 1, "reference": 1, "title": 1, "priority": 1, "status": 1,
            "site_name": 1, "asset_name": 1, "scheduled_at": 1, "estimated_minutes": 1,
            "sla_resolve_at": 1, "assigned_engineer_id": 1, "assigned_engineer_name": 1,
        },
    ).sort("scheduled_at", 1).to_list(2000)
    # Unassigned but open queue too, so the operator can drag them in.
    unassigned = await db.svc_cases.find(
        {
            **of,
            "status": {"$in": list(OPEN_STATES)},
            "$or": [{"assigned_engineer_id": ""}, {"assigned_engineer_id": None}],
        },
        {
            "_id": 0,
            "id": 1, "reference": 1, "title": 1, "priority": 1, "status": 1,
            "site_name": 1, "asset_name": 1, "estimated_minutes": 1,
            "sla_resolve_at": 1,
        },
    ).sort("sla_resolve_at", 1).limit(50).to_list(50)
    return {
        "start": start_dt.isoformat(),
        "days": days,
        "engineers": engineers,
        "cases": cases,
        "unassigned": unassigned,
    }


# ─────────────────────────────────────────────────────────────────
# Manual assign — used by drag-and-drop UI
# ─────────────────────────────────────────────────────────────────

@router.post("/assign")
async def assign_case(data: dict, user=Depends(get_current_user)):
    """Manually assign an engineer + scheduled_at to a case.

    Body: {case_id, engineer_id, scheduled_at?, estimated_minutes?}
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    engineer_id = (data or {}).get("engineer_id")
    if not case_id or not engineer_id:
        raise HTTPException(400, "case_id and engineer_id required")
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    eng = await db.svc_engineers.find_one({"id": engineer_id, **of}, {"_id": 0})
    if not eng:
        raise HTTPException(404, "Engineer not found")
    updates: dict[str, Any] = {
        "assigned_engineer_id": engineer_id,
        "assigned_engineer_name": eng.get("full_name") or "",
        "updated_at": _now(),
    }
    if data.get("scheduled_at"):
        updates["scheduled_at"] = data["scheduled_at"]
    if data.get("estimated_minutes"):
        updates["estimated_minutes"] = int(data["estimated_minutes"])
    await db.svc_cases.update_one({"id": case_id}, {"$set": updates})
    # Move case to `assigned` if it was new/triaged; respect state-machine rules.
    if case.get("status") in (NEW, TRIAGED):
        try:
            await state_transition(
                case_id=case_id, organization_id=of["organization_id"],
                target_state=ASSIGNED, actor=user,
                reason=f"Scheduled with {eng.get('full_name')}",
            )
        except ValueError:
            pass
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Assigned to {eng.get('full_name')} at {data.get('scheduled_at') or 'no time set'}",
        extra={"engineer_id": engineer_id, "scheduled_at": data.get("scheduled_at"), "kind": "assignment"},
    )
    # Re-fetch case to get updated status after state transition
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    await sicon_sync.push_case(case)
    return case


# ─────────────────────────────────────────────────────────────────
# Heuristic auto-assign — top-3 with score breakdown
# ─────────────────────────────────────────────────────────────────

def _drive_minutes_estimate(prev_pc: str, next_pc: str) -> int:
    """Naive postcode-area drive estimate.

    Real geo lookups land in Phase 5 (geo.py); for now we compare the
    UK outward postcode (first half) — same outward = 15min, same
    region letter = 45min, otherwise 90min.
    """
    if not prev_pc or not next_pc:
        return 30  # unknown → assume an average drive
    a, b = prev_pc.upper().split(" ")[0], next_pc.upper().split(" ")[0]
    if a == b:
        return 15
    if a and b and a[0] == b[0]:
        return 45
    return 90


def _score(engineer: dict, case: dict, *, engineer_open_jobs: int, van_skus: set[str]) -> dict:
    """Compute the engineer-vs-case score per the formula in the architecture spec."""
    required_skills = set(case.get("required_skills") or [])
    eng_skills = set(engineer.get("skills") or [])
    skill_mismatch = len(required_skills - eng_skills)
    likely_parts = set(p.get("part_sku", "") for p in (case.get("allocated_parts") or []) if p.get("part_sku"))
    van_match = len(likely_parts & van_skus)
    drive_minutes = _drive_minutes_estimate(
        engineer.get("home_address", {}).get("postcode") or "",
        case.get("site_postcode") or "",
    )
    # SLA risk proxy — fewer hours to resolve target = higher risk.
    sla_breach_risk = 0
    if case.get("sla_resolve_at"):
        try:
            mins_left = (datetime.fromisoformat(case["sla_resolve_at"]) - datetime.now(timezone.utc)).total_seconds() / 60
            if mins_left <= 60:
                sla_breach_risk = 3
            elif mins_left <= 240:
                sla_breach_risk = 2
            elif mins_left <= 480:
                sla_breach_risk = 1
        except Exception:
            pass
    overtime_minutes = max(0, (engineer_open_jobs - 4) * 60)  # >4 jobs starts costing OT

    score = 100.0
    score -= drive_minutes * 1.0
    score -= skill_mismatch * 50.0
    score += van_match * 20.0
    score -= sla_breach_risk * 30.0
    score -= overtime_minutes * 0.5

    return {
        "engineer_id": engineer.get("id"),
        "engineer_name": engineer.get("full_name") or "",
        "score": round(score, 1),
        "breakdown": {
            "drive_minutes": drive_minutes,
            "skill_mismatch": skill_mismatch,
            "van_match": van_match,
            "sla_breach_risk": sla_breach_risk,
            "overtime_minutes": overtime_minutes,
        },
    }


async def _score_engineers_for_case(case: dict, organization_id: str, limit: int = 5) -> list[dict]:
    """Reusable helper — used by ``/auto-assign`` and by the intake hot-path
    to stamp ``recommended_engineer_*`` on every new case.

    Returns the top ``limit`` engineer rankings; each dict adds a tiny
    human-readable ``reason`` so the UI can render it inline (e.g.
    "On-site postcode match · 2 likely parts on van").
    """
    of = {"organization_id": organization_id}
    engineers = await db.svc_engineers.find(
        {**of, "active": {"$ne": False}}, {"_id": 0},
    ).to_list(500)
    if not engineers:
        return []

    pipeline = [
        {"$match": {**of, "status": {"$in": list(OPEN_STATES)}, "assigned_engineer_id": {"$ne": ""}}},
        {"$group": {"_id": "$assigned_engineer_id", "n": {"$sum": 1}}},
    ]
    load: dict[str, int] = {}
    async for d in db.svc_cases.aggregate(pipeline):
        load[d["_id"]] = d["n"]

    van_skus: dict[str, set] = {}
    async for v in db.svc_van_stock.find({**of, "qty": {"$gt": 0}}, {"_id": 0}):
        van_skus.setdefault(v["engineer_id"], set()).add(v["part_sku"])

    rankings = sorted(
        (
            _score(
                e, case,
                engineer_open_jobs=load.get(e.get("id"), 0),
                van_skus=van_skus.get(e.get("id"), set()),
            )
            for e in engineers
        ),
        key=lambda r: r["score"],
        reverse=True,
    )
    for r in rankings:
        b = r.get("breakdown", {})
        bits: list[str] = []
        if b.get("drive_minutes", 999) <= 15:
            bits.append("local postcode")
        elif b.get("drive_minutes", 0) <= 45:
            bits.append("nearby region")
        if b.get("van_match", 0) >= 1:
            bits.append(f"{b['van_match']} likely part(s) on van")
        if b.get("skill_mismatch", 0) == 0:
            bits.append("skill match")
        if b.get("sla_breach_risk", 0) >= 2:
            bits.append("SLA risk pickup")
        r["reason"] = " · ".join(bits) or "best available"
    return rankings[:limit]


@router.post("/auto-assign")
async def auto_assign(
    case_id: str = Query(..., description="Case to auto-assign"),
    commit: bool = Query(False, description="If true, actually assign the top engineer"),
    user=Depends(get_current_user),
):
    """Score every active engineer for the given case and return a ranking."""
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    engineers = await db.svc_engineers.find(
        {**of, "active": {"$ne": False}}, {"_id": 0},
    ).to_list(500)
    if not engineers:
        raise HTTPException(409, "No active engineers — add one before auto-assigning")

    # Use the shared helper that adds the human-readable 'reason' field
    rankings = await _score_engineers_for_case(case, organization_id=of["organization_id"], limit=500)

    response = {"case_id": case_id, "rankings": rankings[:5]}

    # Phase 5 — AI tie-break when the top two are within 10 points.
    # This is best-effort: if the AI service is down we still return the
    # heuristic ranking unchanged.
    if len(rankings) >= 2 and (rankings[0]["score"] - rankings[1]["score"]) <= 10.0:
        try:
            from routes.svc.ai import scheduler_tiebreak  # local import = no circular
            close = [r for r in rankings if r["score"] >= rankings[0]["score"] - 10.0][:3]
            tb = await scheduler_tiebreak(
                {"case_id": case_id, "candidate_engineer_ids": [r["engineer_id"] for r in close]},
                user=user,
            )
            if tb.get("ok") and tb.get("chosen_engineer_id"):
                # Move chosen to the top of the rankings without changing scores —
                # the operator sees the AI nudge but the math is preserved.
                chosen_id = tb["chosen_engineer_id"]
                rankings.sort(key=lambda r: (0 if r["engineer_id"] == chosen_id else 1, -r["score"]))
                response["rankings"] = rankings[:5]
                response["ai_tiebreak"] = {
                    "chosen_engineer_id": chosen_id,
                    "reasoning": tb.get("reasoning") or "",
                    "latency_ms": tb.get("latency_ms"),
                }
        except Exception as e:
            logger.warning("auto-assign tiebreak skipped: %s", e)

    if commit and rankings:
        top = rankings[0]
        eng = next((e for e in engineers if e.get("id") == top["engineer_id"]), None)
        if eng:
            await db.svc_cases.update_one(
                {"id": case_id, **of},
                {"$set": {
                    "assigned_engineer_id": eng["id"],
                    "assigned_engineer_name": eng.get("full_name") or "",
                    "updated_at": _now(),
                }},
            )
            if case.get("status") in (NEW, TRIAGED):
                try:
                    await state_transition(
                        case_id=case_id, organization_id=of["organization_id"],
                        target_state=ASSIGNED, actor=user,
                        reason=f"Auto-assigned (score {top['score']})",
                    )
                except ValueError:
                    pass
            await append_event(
                case_id=case_id, organization_id=of["organization_id"],
                event_type="note", actor=user,
                body=f"Auto-assigned to {eng.get('full_name')} (score {top['score']})",
                extra={"engineer_id": eng["id"], "auto": True, "rankings": rankings[:3]},
            )
            response["assigned_engineer_id"] = eng["id"]
            response["assigned_engineer_name"] = eng.get("full_name")
            response["score"] = top["score"]
            updated = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
            await sicon_sync.push_case(updated)

    return response
