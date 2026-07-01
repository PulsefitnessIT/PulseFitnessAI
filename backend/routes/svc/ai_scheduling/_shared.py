"""
Pulse Fitness Service Desk — AI Scheduling Agent (Phase 1 MVP).

The AI recommends. The planner decides.

This is a *re-planning & approval layer* on top of the existing Service
Desk primitives — it does NOT duplicate jobs, engineers, sites, SLAs or
the diary. It:

  * reads today's engineer schedule from `svc_cases` + `svc_engineers`
  * classifies each job movable / protected (in-progress or planner-locked)
  * generates a reviewable proposal (current vs proposed) for two modes:
        - remaining_day   : re-sequence/re-time the day's safe-to-move jobs
                            by SLA urgency, defer what can't fit
        - add_priority_job: insert an urgent job into the best engineer's
                            remaining day and cascade the safe moves
  * lets the planner approve all / selected, reject, or lock jobs
  * applies approved changes via the EXISTING diary writer
    (`routes.svc.diary.admin_assign_case`) so notifications, Sicon push
    and audit stay single-source.

New collections (the layer only):
  scheduling_proposals, scheduling_proposal_items, job_locks,
  schedule_audit_events.

Reused as-is: svc_cases, svc_engineers, svc_state, scheduler scoring,
postcode drive estimate, diary writers, notifications.
"""
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/scheduling", tags=["Service Ops · AI Scheduling"])

# Display work window (London office default). Settings UI lands in Phase 4.
DAY_START_HOUR = 8
DAY_END_HOUR = 18
PROPOSAL_TTL_HOURS = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


_SETTINGS_DEFAULTS = {
    "enabled": True,
    "require_approval": True,
    "auto_apply_low_risk": False,
    "proactive_p1": True,
    "work_start_hour": DAY_START_HOUR,
    "work_end_hour": DAY_END_HOUR,
    "timezone": "UTC",
    "weights": {"sla": 5, "travel": 3, "skill": 4, "stock": 2, "priority": 5},
    "confidence_threshold": 0.5,
    "customer_notifications": {"enabled": False, "on_reschedule": True, "on_delay": True},
    "engineer_notifications": {"enabled": True},
}


async def _get_settings(org_id: str) -> dict:
    doc = await db.scheduling_settings.find_one({"organization_id": org_id}, {"_id": 0})
    merged = {**_SETTINGS_DEFAULTS}
    if doc:
        for k, v in doc.items():
            if k in ("organization_id", "updated_at", "updated_by"):
                continue
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
    return merged


# ── Protect-in-progress classification ───────────────────────────


_PROTECTED_REASONS = {
    EN_ROUTE: "Engineer already travelling",
    ON_SITE: "Engineer on site / job in progress",
    PAUSED_PARTS: "Work underway — waiting for parts",
    PAUSED_CUSTOMER: "Work underway — waiting for customer",
    REPAIRED: "Work completed — awaiting sign-off",
    AWAITING_SIGN_OFF: "Work completed — awaiting sign-off",
}


def _protect_reason(case: dict, lock_ids: set[str]) -> Optional[str]:
    """Return a human reason if the job must NOT be moved, else None."""
    if case.get("id") in lock_ids:
        return "Locked by planner"
    status = case.get("status")
    if status in TERMINAL_STATES:
        return "Job is closed"
    if status in _PROTECTED_REASONS:
        return _PROTECTED_REASONS[status]
    return None


def _eng_postcode(eng: dict) -> str:
    return (eng.get("home_address") or {}).get("postcode") or ""


def _sla_state(finish_dt: Optional[datetime], sla_resolve_at: Optional[str]) -> str:
    """on_track | at_risk | breached | none (no SLA target)."""
    sla = _parse_iso(sla_resolve_at)
    if not sla:
        return "none"
    if not finish_dt:
        return "at_risk"
    if finish_dt > sla:
        return "breached"
    # within 2h of the deadline = at risk
    if (sla - finish_dt) <= timedelta(hours=2):
        return "at_risk"
    return "on_track"


def _sla_label(old_state: str, new_state: str) -> str:
    if old_state == "breached" and new_state in ("on_track", "at_risk"):
        return "saved"
    if old_state in ("on_track",) and new_state in ("breached", "at_risk"):
        return "worsened"
    return new_state


def _day_bounds(date_str: str, start_h: int = DAY_START_HOUR, end_h: int = DAY_END_HOUR) -> tuple[datetime, datetime]:
    d = datetime.fromisoformat(date_str + "T00:00:00+00:00")
    return (d.replace(hour=start_h), d.replace(hour=end_h))


def _next_working_morning(date_str: str, hour: int = 9) -> str:
    d = datetime.fromisoformat(date_str + "T00:00:00+00:00") + timedelta(days=1)
    if d.weekday() == 5:   # Sat → Mon
        d += timedelta(days=2)
    elif d.weekday() == 6:  # Sun → Mon
        d += timedelta(days=1)
    return d.replace(hour=hour).isoformat()


# ── Core planner — one engineer's remaining day ──────────────────


def _nn_order(jobs: list[dict], start_pc: str) -> list[dict]:
    """Greedy nearest-neighbour ordering by postcode-area drive estimate."""
    remaining = list(jobs)
    ordered: list[dict] = []
    prev = start_pc
    while remaining:
        nxt = min(remaining, key=lambda j: _drive_minutes_estimate(prev, j.get("site_postcode") or ""))
        ordered.append(nxt)
        prev = nxt.get("site_postcode") or prev
        remaining.remove(nxt)
    return ordered


def _total_travel(start_pc: str, ordered_pcs: list[str]) -> int:
    """Total drive minutes for a sequence starting from the engineer base."""
    total = 0
    prev = start_pc
    for pc in ordered_pcs:
        total += _drive_minutes_estimate(prev, pc or "")
        prev = pc or prev
    return total


def _travel_saved(items: list[dict], eng_pc_by_id: dict[str, str]) -> int:
    """Per-engineer (old order travel) − (proposed order travel), summed."""
    saved = 0
    by_eng: dict[str, list[dict]] = {}
    for i in items:
        by_eng.setdefault(i["engineer_id"], []).append(i)
    for eng_id, group in by_eng.items():
        base = eng_pc_by_id.get(eng_id, "")
        old_seq = [g["site_postcode"] for g in sorted(
            group, key=lambda g: g.get("old_scheduled_at") or "~") if g.get("old_scheduled_at")]
        new_seq = [g["site_postcode"] for g in sorted(
            group, key=lambda g: g.get("new_order") if g.get("new_order") is not None else 999)]
        saved += _total_travel(base, old_seq) - _total_travel(base, new_seq)
    return saved


def _plan_engineer_day(
    eng: dict,
    day_jobs: list[dict],
    lock_ids: set[str],
    *,
    date_str: str,
    cutoff: datetime,
    extra_job: Optional[dict] = None,
    extra_jobs: Optional[list[dict]] = None,
    strategy: str = "sla",
    dur_map: Optional[dict[str, int]] = None,
    day_start_hour: int = DAY_START_HOUR,
    day_end_hour: int = DAY_END_HOUR,
) -> list[dict]:
    """Return proposal items for one engineer.

    Protected jobs (in-progress / locked) keep their slot. Safe-to-move
    jobs are re-ordered and re-timed sequentially from `cutoff`, skipping
    over protected time-blocks. Jobs that don't fit before the end of the
    working day are deferred to the next morning.

    strategy:
      - 'sla'        : order by SLA urgency (soonest deadline first).
      - 'travel'     : nearest-neighbour order to minimise drive time.
      - 'sla_rescue' : only re-plan jobs at risk / breached; on-track jobs
                       stay put (treated as soft anchors).
    """
    _, day_end = _day_bounds(date_str, day_start_hour, day_end_hour)
    eng_pc = _eng_postcode(eng)

    # Original order (by current scheduled_at) for the "old_order" field.
    original_sorted = sorted(day_jobs, key=lambda j: j.get("scheduled_at") or "")
    old_order = {j["id"]: i for i, j in enumerate(original_sorted)}

    protected: list[dict] = []
    movable: list[dict] = []
    for j in day_jobs:
        reason = _protect_reason(j, lock_ids)
        if reason:
            j["_protect_reason"] = reason
            protected.append(j)
        else:
            movable.append(j)

    if extra_job is not None:
        movable.append(extra_job)
    for ej in (extra_jobs or []):
        movable.append(ej)
    extra_ids = {e["id"] for e in ([extra_job] if extra_job else []) + (extra_jobs or [])}
    dur_map = dur_map or {}

    def _est_for(j: dict) -> int:
        return int(j.get("estimated_minutes") or dur_map.get(j.get("fault_code") or "", 0) or 60)

    if not movable:
        return []

    # SLA-rescue: keep on-track jobs where they are; only pull the at-risk ones.
    soft_anchor: list[dict] = []
    if strategy == "sla_rescue":
        rescue, keep = [], []
        for j in movable:
            old_dt = _parse_iso(j.get("scheduled_at"))
            est = _est_for(j)
            st = _sla_state((old_dt + timedelta(minutes=est)) if old_dt else None, j.get("sla_resolve_at"))
            if st in ("at_risk", "breached") or (j["id"] in extra_ids):
                rescue.append(j)
            else:
                keep.append(j)
        soft_anchor = keep
        movable = rescue
        if not movable:
            return []  # nothing at risk → no rescue needed

    # Protected (+ soft-anchor) time-blocks the cursor must skip over.
    blocks: list[tuple[datetime, datetime]] = []
    for p in protected + soft_anchor:
        st = _parse_iso(p.get("scheduled_at"))
        if st:
            blocks.append((st, st + timedelta(minutes=int(p.get("estimated_minutes") or 60))))
    blocks.sort(key=lambda b: b[0])

    def _sla_key(j: dict):
        sla = _parse_iso(j.get("sla_resolve_at"))
        return (sla is None, sla or datetime.max.replace(tzinfo=timezone.utc),
                old_order.get(j["id"], 999))

    if strategy == "travel":
        movable = _nn_order(movable, eng_pc)
    else:
        movable.sort(key=_sla_key)

    items: list[dict] = []
    cursor = cutoff
    prev_pc = eng_pc

    def _fit_after(candidate: datetime, dur_min: int) -> datetime:
        """Earliest start >= candidate where [start, start+dur] clears every
        protected block (so we never double-book the engineer)."""
        c = candidate
        moved = True
        while moved:
            moved = False
            end = c + timedelta(minutes=dur_min)
            for bs, be in blocks:
                if c < be and end > bs:  # interval overlaps the block
                    c = be
                    moved = True
                    break
        return c

    for j in movable:
        est = _est_for(j)
        drive = _drive_minutes_estimate(prev_pc, j.get("site_postcode") or "")
        start = _fit_after(cursor + timedelta(minutes=drive), est)
        finish = start + timedelta(minutes=est)

        old_dt = _parse_iso(j.get("scheduled_at"))
        old_sla = _sla_state(
            (old_dt + timedelta(minutes=est)) if old_dt else None,
            j.get("sla_resolve_at"),
        )

        is_extra = j["id"] in extra_ids
        orig_eng = j.get("assigned_engineer_id")
        is_reassign = is_extra and bool(orig_eng) and orig_eng != eng["id"]
        is_insert = is_extra and not is_reassign
        learned = bool(not j.get("estimated_minutes") and dur_map.get(j.get("fault_code") or ""))

        if finish > day_end and not is_extra:
            # Doesn't fit today → defer to next working morning.
            new_iso = _next_working_morning(date_str, day_start_hour + 1)
            new_finish = _parse_iso(new_iso) + timedelta(minutes=est)
            new_sla = _sla_state(new_finish, j.get("sla_resolve_at"))
            change = "defer"
            reason = "No safe slot left today — deferred to next working morning to protect jobs already underway."
        else:
            new_iso = start.isoformat()
            new_sla = _sla_state(finish, j.get("sla_resolve_at"))
            change = (
                "reassign" if is_reassign else
                "insert" if is_insert else
                ("unchanged" if old_dt and abs((old_dt - start).total_seconds()) < 300 else "move")
            )
            cursor = finish
            prev_pc = j.get("site_postcode") or prev_pc
            reason = _item_reason(change, j, drive, old_sla, new_sla)
        if learned:
            reason += f" (Duration estimated from {est} min of similar past jobs.)"

        cur_eng_id = orig_eng if is_reassign else eng["id"]
        cur_eng_name = (j.get("assigned_engineer_name") or "") if is_reassign else (eng.get("full_name") or "")
        items.append({
            "case_id": j["id"],
            "reference": j.get("reference"),
            "title": j.get("title") or "Service job",
            "site_name": j.get("site_name") or j.get("customer_name") or "",
            "site_postcode": j.get("site_postcode") or "",
            "engineer_id": cur_eng_id,
            "engineer_name": cur_eng_name,
            "new_engineer_id": eng["id"],
            "new_engineer_name": eng.get("full_name") or "",
            "old_scheduled_at": j.get("scheduled_at"),
            "new_scheduled_at": new_iso,
            "old_order": old_order.get(j["id"]),
            "estimated_minutes": est,
            "learned_duration": learned,
            "change_type": change,
            "movable": True,
            "protected_reason": None,
            "travel_impact_minutes": drive,
            "sla_old": old_sla,
            "sla_new": new_sla,
            "sla_label": _sla_label(old_sla, new_sla),
            "risk_level": _risk_level(change, j, old_sla, new_sla),
            "confidence": _confidence(j, drive),
            "reason": reason,
        })

    # Soft-anchored (SLA-rescue) on-track jobs — shown unchanged.
    for p in soft_anchor:
        old_dt = _parse_iso(p.get("scheduled_at"))
        est = int(p.get("estimated_minutes") or 60)
        old_sla = _sla_state((old_dt + timedelta(minutes=est)) if old_dt else None,
                             p.get("sla_resolve_at"))
        items.append({
            "case_id": p["id"], "reference": p.get("reference"),
            "title": p.get("title") or "Service job",
            "site_name": p.get("site_name") or p.get("customer_name") or "",
            "site_postcode": p.get("site_postcode") or "",
            "engineer_id": eng["id"], "engineer_name": eng.get("full_name") or "",
            "new_engineer_id": eng["id"], "new_engineer_name": eng.get("full_name") or "",
            "old_scheduled_at": p.get("scheduled_at"), "new_scheduled_at": p.get("scheduled_at"),
            "old_order": old_order.get(p["id"]), "estimated_minutes": est,
            "change_type": "unchanged", "movable": True, "protected_reason": None,
            "travel_impact_minutes": 0, "sla_old": old_sla, "sla_new": old_sla,
            "sla_label": old_sla, "risk_level": "low", "confidence": 1.0,
            "reason": "On track — left in place by the SLA rescue.",
        })

    # Protected jobs appear in the proposal too (read-only, "protected").
    for p in protected:
        old_dt = _parse_iso(p.get("scheduled_at"))
        est = int(p.get("estimated_minutes") or 60)
        old_sla = _sla_state((old_dt + timedelta(minutes=est)) if old_dt else None,
                             p.get("sla_resolve_at"))
        items.append({
            "case_id": p["id"],
            "reference": p.get("reference"),
            "title": p.get("title") or "Service job",
            "site_name": p.get("site_name") or p.get("customer_name") or "",
            "site_postcode": p.get("site_postcode") or "",
            "engineer_id": eng["id"],
            "engineer_name": eng.get("full_name") or "",
            "new_engineer_id": eng["id"],
            "new_engineer_name": eng.get("full_name") or "",
            "old_scheduled_at": p.get("scheduled_at"),
            "new_scheduled_at": p.get("scheduled_at"),
            "old_order": old_order.get(p["id"]),
            "estimated_minutes": est,
            "change_type": "protected",
            "movable": False,
            "protected_reason": p.get("_protect_reason"),
            "travel_impact_minutes": 0,
            "sla_old": old_sla,
            "sla_new": old_sla,
            "sla_label": old_sla,
            "risk_level": "low",
            "confidence": 1.0,
            "reason": p.get("_protect_reason") or "Protected — left unchanged.",
        })

    # Assign new_order from the final proposed timeline (movable + protected).
    sortable = [i for i in items if i["new_scheduled_at"]]
    sortable.sort(key=lambda i: i["new_scheduled_at"])
    for idx, i in enumerate(sortable):
        i["new_order"] = idx
    return items


def _item_reason(change: str, job: dict, drive: int, old_sla: str, new_sla: str) -> str:
    if change == "reassign":
        return (f"Reassigned to the best-fit available engineer (~{drive} min travel) because the "
                f"original engineer is unavailable.")
    if change == "insert":
        return (f"Urgent job inserted into this engineer's remaining day — "
                f"closest qualified engineer (~{drive} min travel).")
    if change == "unchanged":
        return "Already in the best position — left unchanged."
    bits = []
    if new_sla in ("breached", "at_risk") or old_sla in ("breached", "at_risk"):
        if _sla_label(old_sla, new_sla) == "saved":
            bits.append("re-ordered earlier to protect its SLA")
        elif new_sla == "at_risk":
            bits.append("kept as early as safely possible (SLA tight)")
    bits.append(f"~{drive} min travel from the previous stop")
    return "Moved: " + ", ".join(bits) + "."


def _risk_level(change: str, job: dict, old_sla: str, new_sla: str) -> str:
    if _sla_label(old_sla, new_sla) == "worsened":
        return "high"
    pr = (job.get("priority") or "").lower()
    if change == "defer" and pr in ("p1", "p2"):
        return "high"
    if change in ("move", "insert") and pr in ("p1",):
        return "medium"
    return "low"


def _confidence(job: dict, drive: int) -> float:
    c = 0.9
    if not job.get("site_postcode"):
        c -= 0.15  # travel estimate is a guess without a postcode
    if not job.get("estimated_minutes"):
        c -= 0.1
    return round(max(0.4, c), 2)


async def _lock_ids(org_id: str) -> set[str]:
    rows = await db.job_locks.find({"organization_id": org_id}, {"_id": 0, "case_id": 1}).to_list(2000)
    return {r["case_id"] for r in rows}


def _summarise(items: list[dict]) -> dict:
    moved = sum(1 for i in items if i["change_type"] in ("move", "reassign"))
    inserted = sum(1 for i in items if i["change_type"] == "insert")
    deferred = sum(1 for i in items if i["change_type"] == "defer")
    protectedn = sum(1 for i in items if i["change_type"] == "protected")
    sla_saved = sum(1 for i in items if i["sla_label"] == "saved")
    sla_worsened = sum(1 for i in items if i["sla_label"] == "worsened")
    engineers = len({i["engineer_id"] for i in items} | {i["new_engineer_id"] for i in items})
    travel = sum(i.get("travel_impact_minutes") or 0 for i in items if i["change_type"] in ("move", "insert", "reassign"))
    reassigned = sum(1 for i in items if i["change_type"] == "reassign")
    return {
        "jobs_moved": moved, "jobs_inserted": inserted, "jobs_deferred": deferred,
        "jobs_reassigned": reassigned,
        "jobs_protected": protectedn, "sla_saved": sla_saved, "sla_worsened": sla_worsened,
        "engineers_affected": engineers, "total_travel_minutes": travel,
        "actionable": moved + inserted + deferred,
    }


# ── Models ────────────────────────────────────────────────────────


class ReplanIn(BaseModel):
    mode: str = Field("remaining_day",
                      description="remaining_day | add_priority_job | reduce_travel | sla_rescue | engineer_delayed | engineer_unavailable")
    date: Optional[str] = Field(None, description="YYYY-MM-DD, defaults to today")
    engineer_ids: Optional[list[str]] = None
    engineer_id: Optional[str] = Field(None, description="Target engineer for delayed/unavailable modes")
    delay_minutes: Optional[int] = Field(None, description="Delay for engineer_delayed mode")
    priority_case_id: Optional[str] = Field(None, description="Required for add_priority_job")
    trigger: str = Field("manual", description="What triggered this re-plan")


class SimulateIn(BaseModel):
    scenario: str = Field(..., description="engineer_sick | engineer_delayed | job_longer | add_emergency")
    date: Optional[str] = None
    engineer_id: Optional[str] = None
    delay_minutes: Optional[int] = None
    case_id: Optional[str] = None
    extra_minutes: Optional[int] = None
    priority_case_id: Optional[str] = None


class DecisionIn(BaseModel):
    item_ids: Optional[list[str]] = None
    approve_all: bool = False
    reject_all: bool = False
    override_reason: Optional[str] = None


class LockIn(BaseModel):
    case_id: str
    reason: Optional[str] = None


# ── Board: today's schedule + classification (left side of review) ─


_MODE_STRATEGY = {
    "remaining_day": "sla",
    "add_priority_job": "sla",
    "reduce_travel": "travel",
    "sla_rescue": "sla_rescue",
    "engineer_delayed": "sla",
    "engineer_unavailable": "sla",
    "full_day": "sla",
    "tomorrow": "sla",
    "weekly": "sla",
}


_JOB_PROJ = {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
             "status": 1, "site_name": 1, "site_postcode": 1, "customer_name": 1,
             "scheduled_at": 1, "estimated_minutes": 1, "sla_resolve_at": 1,
             "assigned_engineer_id": 1, "assigned_engineer_name": 1, "fault_code": 1}


async def _duration_stats(org_id: str) -> dict[str, dict]:
    """Learn typical job duration per fault_code from on-site time entries on
    completed jobs. Returns {fault_code: {avg, n}}."""
    # actual on-site minutes per case
    actual_by_case: dict[str, int] = {}
    try:
        pipe = [
            {"$match": {"organization_id": org_id, "category": "on_site"}},
            {"$group": {"_id": "$case_id", "mins": {"$sum": "$duration_minutes"}}},
        ]
        async for r in db.svc_time_entries.aggregate(pipe):
            if r.get("_id") and (r.get("mins") or 0) > 0:
                actual_by_case[r["_id"]] = int(r["mins"])
    except Exception as e:  # noqa: BLE001
        logger.info("duration stats aggregate skipped: %s", e)
        return {}
    if not actual_by_case:
        return {}
    cases = await db.svc_cases.find(
        {"organization_id": org_id, "id": {"$in": list(actual_by_case.keys())}},
        {"_id": 0, "id": 1, "fault_code": 1, "estimated_minutes": 1},
    ).to_list(5000)
    agg: dict[str, dict] = {}
    for c in cases:
        fc = c.get("fault_code") or "_unknown"
        a = agg.setdefault(fc, {"actual_total": 0, "est_total": 0, "n": 0})
        a["actual_total"] += actual_by_case.get(c["id"], 0)
        a["est_total"] += int(c.get("estimated_minutes") or 0)
        a["n"] += 1
    out = {}
    for fc, a in agg.items():
        if a["n"]:
            out[fc] = {
                "avg": round(a["actual_total"] / a["n"]),
                "avg_estimated": round(a["est_total"] / a["n"]) if a["est_total"] else None,
                "n": a["n"],
            }
    return out


async def _ai_narrative(mode: str, summary: dict, items: list[dict]) -> Optional[str]:
    """Best-effort one-paragraph plain-English summary of the proposal.
    Degrades silently (returns None) if the LLM is unavailable."""
    actionable = [i for i in items if i["change_type"] in ("move", "insert", "defer", "reassign")]
    if not actionable:
        return None
    try:
        from routes.svc.ai import _chat
        lines = [
            f"- {i['reference']} ({i['change_type']}): {i['reason']} SLA {i['sla_label']}."
            for i in actionable[:12]
        ]
        text = (
            f"Mode: {mode}. Summary: {summary}. Changes:\n" + "\n".join(lines) +
            "\n\nWrite ONE short paragraph (max 3 sentences) a service planner can read at a glance: "
            "what the re-plan does, what it protects, and the SLA/travel benefit. Plain UK English, no markdown."
        )
        out = await _chat(
            system="You summarise field-service schedule re-plans for a planner. Be concise, factual, reassuring.",
            user_text=text,
        )
        return (out or "").strip()[:600] or None
    except Exception as e:  # noqa: BLE001
        logger.info("ai narrative skipped: %s", e)
        return None


async def _generate_proposal(
    *, user: dict, org_id: str, mode: str, date: Optional[str],
    engineer_ids: Optional[list[str]], priority_case_id: Optional[str],
    trigger: str, with_narrative: bool = True,
    engineer_id: Optional[str] = None, delay_minutes: Optional[int] = None,
    extra_minutes: Optional[int] = None, longer_case_id: Optional[str] = None,
    persist: bool = True,
) -> dict:
    of = {"organization_id": org_id}
    settings = await _get_settings(org_id)
    sh = int(settings.get("work_start_hour") or DAY_START_HOUR)
    eh = int(settings.get("work_end_hour") or DAY_END_HOUR)

    # Mode → date/cutoff shaping for full-day / tomorrow.
    if mode == "tomorrow":
        date = date or _next_working_morning(_now_dt().date().isoformat(), 0)[:10]
    date_str = date or _now_dt().date().isoformat()
    cutoff = _now_dt()
    day_start, _ = _day_bounds(date_str, sh, eh)
    if mode in ("full_day", "tomorrow") or date_str > _now_dt().date().isoformat():
        cutoff = day_start
    elif cutoff < day_start:
        cutoff = day_start

    strategy = _MODE_STRATEGY.get(mode, "sla")
    lock_ids = await _lock_ids(org_id)
    dur_map = {fc: s["avg"] for fc, s in (await _duration_stats(org_id)).items()}
    engineers = await db.svc_engineers.find(
        {**of, "active": {"$ne": False}}, {"_id": 0},
    ).to_list(500)
    if engineer_ids:
        engineers = [e for e in engineers if e["id"] in set(engineer_ids)]
    eng_pc_by_id = {e["id"]: _eng_postcode(e) for e in engineers}

    async def _day_jobs_for(eid: str, dstr: str = None) -> list[dict]:
        ds = dstr or date_str
        jobs = await db.svc_cases.find(
            {**of, "assigned_engineer_id": eid,
             "status": {"$in": list(OPEN_STATES)},
             "scheduled_at": {"$gte": ds, "$lt": ds + "T23:59:59Z"}},
            _JOB_PROJ,
        ).sort("scheduled_at", 1).to_list(200)
        if longer_case_id and extra_minutes:
            for j in jobs:
                if j["id"] == longer_case_id:
                    j["estimated_minutes"] = int(j.get("estimated_minutes") or 60) + int(extra_minutes)
        return jobs

    all_items: list[dict] = []

    if mode == "add_priority_job":
        if not priority_case_id:
            raise HTTPException(400, "priority_case_id required for add_priority_job")
        case = await db.svc_cases.find_one({"id": priority_case_id, **of}, _JOB_PROJ)
        if not case:
            raise HTTPException(404, "Priority job not found")
        rankings = await _score_engineers_for_case(case, organization_id=org_id, limit=5)
        if not rankings:
            raise HTTPException(409, "No active engineers to assign this job to")
        best_id = rankings[0]["engineer_id"]
        best_eng = next((e for e in engineers if e["id"] == best_id), None)
        if not best_eng:
            best_eng = await db.svc_engineers.find_one({"id": best_id, **of}, {"_id": 0})
        if not best_eng:
            raise HTTPException(409, "Recommended engineer unavailable")
        eng_pc_by_id[best_id] = _eng_postcode(best_eng)
        all_items = _plan_engineer_day(
            best_eng, await _day_jobs_for(best_id), lock_ids, date_str=date_str, cutoff=cutoff,
            extra_job=case, strategy=strategy, dur_map=dur_map, day_start_hour=sh, day_end_hour=eh,
        )

    elif mode == "engineer_delayed":
        if not engineer_id:
            raise HTTPException(400, "engineer_id required for engineer_delayed")
        eng = next((e for e in engineers if e["id"] == engineer_id), None)
        if not eng:
            raise HTTPException(404, "Engineer not found / inactive")
        delayed_cutoff = cutoff + timedelta(minutes=int(delay_minutes or 0))
        all_items = _plan_engineer_day(
            eng, await _day_jobs_for(engineer_id), lock_ids, date_str=date_str,
            cutoff=delayed_cutoff, strategy=strategy, dur_map=dur_map, day_start_hour=sh, day_end_hour=eh,
        )

    elif mode == "engineer_unavailable":
        if not engineer_id:
            raise HTTPException(400, "engineer_id required for engineer_unavailable")
        orphan = await db.svc_cases.find(
            {**of, "assigned_engineer_id": engineer_id,
             "status": {"$in": list(OPEN_STATES)},
             "scheduled_at": {"$gte": date_str, "$lt": date_str + "T23:59:59Z"}},
            _JOB_PROJ,
        ).sort("scheduled_at", 1).to_list(200)
        orphan_movable = [j for j in orphan if not _protect_reason(j, lock_ids)]
        other_ids = {e["id"] for e in engineers if e["id"] != engineer_id}
        assign_map: dict[str, list[dict]] = {}
        no_cover: list[dict] = []
        for j in orphan_movable:
            rankings = await _score_engineers_for_case(j, organization_id=org_id, limit=10)
            pick = next((r["engineer_id"] for r in rankings if r["engineer_id"] in other_ids), None)
            if pick:
                assign_map.setdefault(pick, []).append(j)
            else:
                no_cover.append(j)
        for rid, jobs in assign_map.items():
            receiving = next((e for e in engineers if e["id"] == rid), None)
            if not receiving:
                continue
            eng_pc_by_id[rid] = _eng_postcode(receiving)
            items = _plan_engineer_day(
                receiving, await _day_jobs_for(rid), lock_ids, date_str=date_str,
                cutoff=cutoff, extra_jobs=jobs, strategy=strategy, dur_map=dur_map,
                day_start_hour=sh, day_end_hour=eh,
            )
            all_items.extend(items)
        for j in no_cover:  # nobody to cover → defer to next morning
            est = int(j.get("estimated_minutes") or dur_map.get(j.get("fault_code") or "", 0) or 60)
            new_iso = _next_working_morning(date_str, sh + 1)
            old_dt = _parse_iso(j.get("scheduled_at"))
            old_sla = _sla_state((old_dt + timedelta(minutes=est)) if old_dt else None, j.get("sla_resolve_at"))
            new_sla = _sla_state(_parse_iso(new_iso) + timedelta(minutes=est), j.get("sla_resolve_at"))
            all_items.append({
                "case_id": j["id"], "reference": j.get("reference"),
                "title": j.get("title") or "Service job",
                "site_name": j.get("site_name") or j.get("customer_name") or "",
                "site_postcode": j.get("site_postcode") or "",
                "engineer_id": engineer_id, "engineer_name": j.get("assigned_engineer_name") or "",
                "new_engineer_id": engineer_id, "new_engineer_name": j.get("assigned_engineer_name") or "",
                "old_scheduled_at": j.get("scheduled_at"), "new_scheduled_at": new_iso,
                "old_order": None, "estimated_minutes": est, "learned_duration": False,
                "change_type": "defer", "movable": True, "protected_reason": None,
                "travel_impact_minutes": 0, "sla_old": old_sla, "sla_new": new_sla,
                "sla_label": _sla_label(old_sla, new_sla),
                "risk_level": "high" if (j.get("priority") or "").lower() in ("p1", "p2") else "medium",
                "confidence": 0.6,
                "reason": "No qualified engineer available to cover — deferred to the next working morning.",
            })

    elif mode == "weekly":
        # Plan the next 5 working days from date_str.
        d0 = datetime.fromisoformat(date_str + "T00:00:00+00:00")
        days: list[str] = []
        probe = d0
        while len(days) < 5:
            if probe.weekday() < 5:  # Mon–Fri
                days.append(probe.date().isoformat())
            probe += timedelta(days=1)
        for ds in days:
            d_start, _ = _day_bounds(ds, sh, eh)
            d_cut = d_start if ds > _now_dt().date().isoformat() else max(_now_dt(), d_start)
            for eng in engineers:
                dj = await _day_jobs_for(eng["id"], ds)
                if not dj:
                    continue
                all_items.extend(_plan_engineer_day(
                    eng, dj, lock_ids, date_str=ds, cutoff=d_cut,
                    strategy=strategy, dur_map=dur_map, day_start_hour=sh, day_end_hour=eh,
                ))

    else:  # remaining_day | reduce_travel | sla_rescue | full_day | tomorrow
        for eng in engineers:
            day_jobs = await _day_jobs_for(eng["id"])
            if not day_jobs:
                continue
            items = _plan_engineer_day(
                eng, day_jobs, lock_ids, date_str=date_str, cutoff=cutoff,
                strategy=strategy, dur_map=dur_map, day_start_hour=sh, day_end_hour=eh,
            )
            all_items.extend(items)

    summary = _summarise(all_items)
    summary["travel_saved_minutes"] = _travel_saved(all_items, eng_pc_by_id)
    confidence = round(
        sum(i["confidence"] for i in all_items) / len(all_items), 2,
    ) if all_items else 0.0

    narrative = None
    if with_narrative and summary["actionable"]:
        narrative = await _ai_narrative(mode, summary, all_items)

    proposal_id = str(uuid.uuid4())
    now = _now()
    proposal = {
        "id": proposal_id, "organization_id": org_id,
        "site_id": user.get("active_site_id") or None,
        "mode": mode, "trigger": trigger,
        "status": "awaiting_approval" if summary["actionable"] else "draft",
        "date": date_str,
        "created_by": user.get("id"), "created_by_name": user.get("full_name") or user.get("email"),
        "created_at": now, "updated_at": now,
        "expires_at": (_now_dt() + timedelta(hours=PROPOSAL_TTL_HOURS)).isoformat(),
        "summary": summary, "confidence": confidence, "narrative": narrative,
        "item_count": len(all_items),
    }

    item_docs = []
    for it in all_items:
        item_docs.append({
            "id": str(uuid.uuid4()), "proposal_id": proposal_id, "organization_id": org_id,
            "decision": "pending", **it,
        })

    if persist:
        await db.scheduling_proposals.insert_one(dict(proposal))
        proposal.pop("_id", None)
        if item_docs:
            await db.scheduling_proposal_items.insert_many([dict(d) for d in item_docs])
        for d in item_docs:
            d.pop("_id", None)
        await _audit(org_id, proposal_id, "proposal_generated", user,
                     f"{mode} ({trigger}) · {summary['actionable']} actionable change(s)")

    return {"proposal": proposal, "items": item_docs}


_APPLY_CHANGES = {"move", "insert", "reassign", "defer"}


async def _audit(org_id: str, proposal_id: Optional[str], action: str, user: dict, detail: str) -> None:
    try:
        await db.schedule_audit_events.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org_id,
            "proposal_id": proposal_id, "action": action,
            "actor_id": user.get("id"), "actor_email": user.get("email"),
            "detail": detail, "at": _now(),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("schedule audit failed: %s", e)
    try:
        await audit_log(
            action=f"svc.scheduling.{action}",
            user_id=user.get("id", ""), user_email=user.get("email", ""),
            resource_type="scheduling_proposal", resource_id=proposal_id or "",
            details=detail,
        )
    except Exception:
        pass


# ── Proactive trigger: a P1 / emergency job was just logged ──────


async def suggest_replan_for_new_case(case: dict, user: dict) -> Optional[str]:
    """Best-effort: when a high-priority (P1) job is logged, auto-generate an
    `add_priority_job` proposal (a SUGGESTION — nothing is applied) and notify
    the org's dispatchers so they can review & approve. Returns the proposal id
    or None. Never raises (wrapped by the caller too)."""
    try:
        priority = (case.get("priority") or "").lower()
        if priority not in ("p1",):
            return None
        org_id = case.get("organization_id")
        if not org_id or not case.get("id"):
            return None
        settings = await _get_settings(org_id)
        if not settings.get("enabled", True) or not settings.get("proactive_p1", True):
            return None
        # Need at least one active engineer to suggest against.
        eng = await db.svc_engineers.find_one(
            {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0, "id": 1},
        )
        if not eng:
            return None
        result = await _generate_proposal(
            user=user, org_id=org_id, mode="add_priority_job", date=None,
            engineer_ids=None, priority_case_id=case["id"],
            trigger="priority_job_logged", with_narrative=False,
        )
        proposal = result["proposal"]
        # Notify dispatchers (owners / managers) with a deep link.
        try:
            from routes.svc.notifications import create_notification
            dispatchers = await db.users.find(
                {"organization_id": org_id, "role": {"$in": ["owner", "manager"]}},
                {"_id": 0, "id": 1},
            ).to_list(50)
            ref = case.get("reference") or case["id"][:8]
            for d in dispatchers:
                if not d.get("id"):
                    continue
                await create_notification(
                    user_id=d["id"], organization_id=org_id,
                    kind="scheduling_suggestion",
                    title=f"Priority job logged — re-plan suggested ({ref})",
                    body="The AI has prepared a schedule suggestion. Review & approve in AI Scheduling.",
                    link="/service-desk?tab=scheduler",
                    source_type="scheduling_proposal", source_id=proposal["id"],
                    fire_push=False,
                )
        except Exception as e:  # noqa: BLE001
            logger.info("scheduling suggestion notify skipped: %s", e)
        return proposal["id"]
    except Exception as e:  # noqa: BLE001
        logger.info("suggest_replan_for_new_case skipped: %s", e)
        return None


# ── Engineer App: schedule-change banner + acknowledge ───────────


engineer_router = APIRouter(
    prefix="/svc/engineer/schedule-changes",
    tags=["Service Ops · Engineer · Schedule Changes"],
    dependencies=[Depends(require_engineer_app_access)],
)


async def _notify_customer_reschedule(item: dict, org_id: str, user: dict) -> None:
    case = await db.svc_cases.find_one(
        {"id": item["case_id"], "organization_id": org_id},
        {"_id": 0, "id": 1, "reference": 1, "customer_email": 1, "customer_name": 1,
         "site_name": 1, "comms_auto_notify": 1},
    )
    if not case:
        return
    to = (case.get("customer_email") or "").strip()
    of = {"organization_id": org_id}
    when = item.get("new_scheduled_at")
    when_label = _parse_iso(when).strftime("%a %d %b, %H:%M") if _parse_iso(when) else "shortly"
    subject = f"Your service appointment has been updated — {case.get('reference') or ''}".strip()
    if not to or "@" not in to or case.get("comms_auto_notify") is False:
        # Log as skipped so the desk can see it was intentionally not sent.
        from routes.svc.comms import _log_send
        await _log_send(of=of, kind="schedule_rescheduled", to=to or "(no email)",
                        subject=subject, template_key="schedule_rescheduled",
                        ok=False, error="no customer email / opted out",
                        case_id=case["id"], actor=user)
        return
    html = (
        f"<p>Hello {case.get('customer_name') or 'there'},</p>"
        f"<p>The appointment for <strong>{case.get('reference') or 'your service job'}</strong> "
        f"at {case.get('site_name') or 'your site'} has been rescheduled to "
        f"<strong>{when_label}</strong>.</p>"
        f"<p>We'll be in touch if anything changes. Thank you.</p>"
    )
    ok = False
    try:
        from utils.email import send_email
        ok = await send_email(to=to, subject=subject, html=html,
                              organization_id=org_id, kind="schedule_rescheduled",
                              category="service")
    except Exception as e:  # noqa: BLE001
        logger.info("customer reschedule email failed: %s", e)
    try:
        from routes.svc.comms import _log_send
        await _log_send(of=of, kind="schedule_rescheduled", to=to, subject=subject,
                        template_key="schedule_rescheduled", ok=bool(ok), error=None,
                        case_id=case["id"], actor=user)
    except Exception:  # noqa: BLE001
        pass


# ── Reports ───────────────────────────────────────────────────────


async def ensure_scheduling_indexes() -> None:
    try:
        await db.scheduling_proposals.create_index([("organization_id", 1), ("created_at", -1)])
        await db.scheduling_proposals.create_index([("id", 1)], unique=True)
        await db.scheduling_proposal_items.create_index([("proposal_id", 1)])
        await db.job_locks.create_index([("organization_id", 1), ("case_id", 1)], unique=True)
        await db.schedule_audit_events.create_index([("organization_id", 1), ("at", -1)])
        await db.scheduling_changes.create_index([("organization_id", 1), ("engineer_id", 1), ("acknowledged", 1)])
    except Exception as e:  # noqa: BLE001
        logger.warning("scheduling index warning: %s", e)


__all__ = ["router", "engineer_router", "ensure_scheduling_indexes", "suggest_replan_for_new_case"]

__all__ = ['DAY_END_HOUR', 'DAY_START_HOUR', 'DecisionIn', 'LockIn', 'PROPOSAL_TTL_HOURS', 'ReplanIn', 'SimulateIn', '_APPLY_CHANGES', '_JOB_PROJ', '_MODE_STRATEGY', '_PROTECTED_REASONS', '_SETTINGS_DEFAULTS', '_ai_narrative', '_audit', '_confidence', '_day_bounds', '_duration_stats', '_eng_postcode', '_generate_proposal', '_get_settings', '_item_reason', '_lock_ids', '_next_working_morning', '_nn_order', '_notify_customer_reschedule', '_now', '_now_dt', '_of', '_parse_iso', '_plan_engineer_day', '_protect_reason', '_risk_level', '_sla_label', '_sla_state', '_summarise', '_total_travel', '_travel_saved', 'engineer_router', 'ensure_scheduling_indexes', 'logger', 'router', 'suggest_replan_for_new_case']
