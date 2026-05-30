"""
GymAxis Service Operations — Engineer Diary & Dispatch.

Iter 216h140 (Phase 4).

Unifies an engineer's calendar view over three sources:
  • svc_cases           — scheduled service jobs (existing)
  • ppm_tasks           — recurring PPM visits (existing)
  • svc_diary_blocks    — non-job blocks (NEW: holiday, training, lunch)

Endpoints:
  Engineer self-service:
    GET   /api/svc/engineer/diary?from=&to=         — own slots in range
    POST  /api/svc/engineer/diary/case/{id}/reschedule    — own job only
    POST  /api/svc/engineer/diary/blocks            — create own block
    DELETE /api/svc/engineer/diary/blocks/{id}      — delete own block

  Admin dispatcher:
    GET   /api/svc/admin/diary?engineer_id=&from=&to=   — any engineer
    GET   /api/svc/admin/diary/unassigned           — open cases needing dispatch
    POST  /api/svc/admin/diary/case/{id}/assign     — engineer_id + scheduled_at
    POST  /api/svc/admin/diary/ppm-task/{id}/assign — assign PPM task to engineer

The "slot" envelope returned from the diary endpoint is uniform across
all three sources so the React grid only deals with one shape.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db
from utils.svc_state import ASSIGNED, NEW, TRIAGED, append_event
from routes.partners import require_engineer_app_access
from routes.svc.integrations import sicon_sync

logger = logging.getLogger(__name__)

# Two routers so we can mount engineer routes behind the Engineer-App
# access guard, and admin routes behind the normal admin role check.
engineer_router = APIRouter(
    prefix="/svc/engineer/diary",
    tags=["Service Ops · Engineer Diary"],
    dependencies=[Depends(require_engineer_app_access)],
)
admin_router = APIRouter(
    prefix="/svc/admin/diary",
    tags=["Service Ops · Admin Diary"],
)


# ── helpers ──────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _require_dispatcher(user: dict) -> None:
    """Admin / manager / master_admin may dispatch. Plain engineers
    use the engineer-side endpoints."""
    role = (user.get("role") or "").lower()
    if role in ("owner", "manager") or user.get("is_master_admin"):
        return
    raise HTTPException(403, "Dispatcher role required")


def _parse_range(from_: str, to_: str) -> tuple[str, str]:
    """Validate ISO date strings, default to current week if missing."""
    try:
        start = datetime.fromisoformat(from_) if from_ else (
            datetime.now(timezone.utc) - timedelta(days=7)
        )
        end = datetime.fromisoformat(to_) if to_ else (
            datetime.now(timezone.utc) + timedelta(days=14)
        )
    except ValueError:
        raise HTTPException(400, "from/to must be ISO datetime strings")
    if end < start:
        raise HTTPException(400, "to must be >= from")
    return start.isoformat(), end.isoformat()


def _case_slot(case: dict) -> dict:
    """Normalise a svc_case into a diary slot."""
    sched = case.get("scheduled_at")
    minutes = case.get("estimated_minutes") or 60
    end = None
    if sched:
        try:
            end = (datetime.fromisoformat(sched.replace("Z", "+00:00"))
                   + timedelta(minutes=int(minutes))).isoformat()
        except (ValueError, TypeError):
            end = None
    return {
        "id": f"case::{case['id']}",
        "source": "case",
        "source_id": case["id"],
        "kind": "job",
        "title": case.get("title") or case.get("reference") or "Service job",
        "subtitle": case.get("site_name") or case.get("customer_name") or "",
        "reference": case.get("reference"),
        "priority": case.get("priority"),
        "status": case.get("status"),
        "engineer_id": case.get("assigned_engineer_id"),
        "site_id": case.get("site_id"),
        "site_name": case.get("site_name"),
        "start_at": sched,
        "end_at": end,
        "duration_minutes": minutes,
        "deeplink": f"/svc/engineer/jobs/{case['id']}",
    }


def _ppm_slot(task: dict) -> dict:
    """Normalise a ppm_task into a diary slot."""
    sched_date = task.get("scheduled_date")
    start = None
    end = None
    if sched_date:
        # ppm_tasks store a date string like "2026-02-20". Anchor to 09:00 UTC.
        try:
            anchor = datetime.fromisoformat(sched_date + "T09:00:00+00:00")
            start = anchor.isoformat()
            end = (anchor + timedelta(minutes=int(task.get("estimated_minutes") or 90))).isoformat()
        except ValueError:
            pass
    return {
        "id": f"ppm::{task['id']}",
        "source": "ppm",
        "source_id": task["id"],
        "kind": "ppm",
        "title": task.get("title") or "PPM visit",
        "subtitle": task.get("site_name") or "",
        "reference": task.get("reference") or task.get("schedule_id", "")[:8],
        "priority": "ppm",
        "status": task.get("status") or "scheduled",
        "engineer_id": task.get("assigned_to") or task.get("assigned_engineer_id"),
        "site_id": task.get("site_id"),
        "site_name": task.get("site_name"),
        "start_at": start,
        "end_at": end,
        "duration_minutes": task.get("estimated_minutes") or 90,
        "deeplink": "/ppm",
    }


def _block_slot(block: dict) -> dict:
    return {
        "id": f"block::{block['id']}",
        "source": "block",
        "source_id": block["id"],
        "kind": block.get("kind") or "block",
        "title": block.get("title") or "Block",
        "subtitle": block.get("note") or "",
        "reference": None,
        "priority": None,
        "status": "blocked",
        "engineer_id": block.get("engineer_id"),
        "site_id": None,
        "site_name": None,
        "start_at": block.get("start_at"),
        "end_at": block.get("end_at"),
        "duration_minutes": block.get("duration_minutes"),
        "deeplink": None,
    }


async def _collect_slots(
    org_id: str, engineer_id: str, start_iso: str, end_iso: str,
) -> list[dict]:
    of = {"organization_id": org_id}
    # 1) Scheduled jobs
    cases = await db.svc_cases.find(
        {**of, "assigned_engineer_id": engineer_id,
         "scheduled_at": {"$gte": start_iso, "$lte": end_iso}},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
         "status": 1, "site_name": 1, "site_id": 1, "scheduled_at": 1,
         "estimated_minutes": 1, "customer_name": 1, "assigned_engineer_id": 1},
    ).sort("scheduled_at", 1).to_list(500)
    # 2) PPM tasks (date-only field, compare on the date prefix)
    start_date = start_iso[:10]
    end_date = end_iso[:10]
    ppm_tasks = await db.ppm_tasks.find(
        {**of, "assigned_to": engineer_id,
         "scheduled_date": {"$gte": start_date, "$lte": end_date}},
        {"_id": 0},
    ).sort("scheduled_date", 1).to_list(500)
    # 3) Blocks
    blocks = await db.svc_diary_blocks.find(
        {**of, "engineer_id": engineer_id,
         "start_at": {"$gte": start_iso, "$lte": end_iso}},
        {"_id": 0},
    ).sort("start_at", 1).to_list(500)

    slots = ([_case_slot(c) for c in cases]
             + [_ppm_slot(t) for t in ppm_tasks]
             + [_block_slot(b) for b in blocks])
    slots = [s for s in slots if s["start_at"]]
    slots.sort(key=lambda s: s["start_at"])
    return slots


# ── Engineer-facing diary ────────────────────────────────────────

@engineer_router.get("")
async def my_diary(
    from_: Optional[str] = Query(None, alias="from"),
    to_:   Optional[str] = Query(None, alias="to"),
    user=Depends(get_current_user),
):
    start_iso, end_iso = _parse_range(from_, to_)
    of = _of(user)
    slots = await _collect_slots(of["organization_id"], user["id"], start_iso, end_iso)
    return {"slots": slots, "from": start_iso, "to": end_iso,
            "engineer_id": user["id"], "count": len(slots)}


class RescheduleIn(BaseModel):
    scheduled_at: str = Field(..., description="ISO datetime")


@engineer_router.post("/case/{case_id}/reschedule")
async def my_reschedule(
    case_id: str, body: RescheduleIn, user=Depends(get_current_user),
):
    of = _of(user)
    try:
        datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "scheduled_at must be ISO datetime")
    case = await db.svc_cases.find_one(
        {"id": case_id, **of}, {"_id": 0, "assigned_engineer_id": 1},
    )
    if not case:
        raise HTTPException(404, "Job not found")
    if case.get("assigned_engineer_id") != user["id"] and not user.get("is_master_admin"):
        # Iter 220az · F-29 / F-33 — 404 (not 403) on cross-engineer.
        raise HTTPException(404, "Job not found")
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$set": {"scheduled_at": body.scheduled_at, "updated_at": _now()}},
    )
    return {"ok": True, "case_id": case_id, "scheduled_at": body.scheduled_at}


class BlockIn(BaseModel):
    title: str = Field(..., max_length=120)
    start_at: str
    end_at: str
    kind: str = Field("block", description="block | holiday | training | lunch")
    note: Optional[str] = Field(None, max_length=400)


@engineer_router.post("/blocks")
async def my_block_create(body: BlockIn, user=Depends(get_current_user)):
    of = _of(user)
    try:
        s = datetime.fromisoformat(body.start_at.replace("Z", "+00:00"))
        e = datetime.fromisoformat(body.end_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "start_at and end_at must be ISO datetimes")
    if e <= s:
        raise HTTPException(400, "end_at must be after start_at")
    doc = {
        "id": str(uuid.uuid4()),
        **of,
        "engineer_id": user["id"],
        "kind": body.kind or "block",
        "title": body.title,
        "note": body.note,
        "start_at": body.start_at,
        "end_at": body.end_at,
        "duration_minutes": int((e - s).total_seconds() / 60),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_diary_blocks.insert_one(doc)
    doc.pop("_id", None)
    return {"block": _block_slot(doc)}


@engineer_router.delete("/blocks/{block_id}")
async def my_block_delete(block_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_diary_blocks.delete_one(
        {"id": block_id, **of, "engineer_id": user["id"]},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Block not found")
    return {"ok": True}


# ── Admin dispatcher ─────────────────────────────────────────────

@admin_router.get("")
async def admin_diary(
    engineer_id: str = Query(..., description="Engineer to view"),
    from_: Optional[str] = Query(None, alias="from"),
    to_:   Optional[str] = Query(None, alias="to"),
    user=Depends(get_current_user),
):
    _require_dispatcher(user)
    of = _of(user)
    start_iso, end_iso = _parse_range(from_, to_)
    slots = await _collect_slots(of["organization_id"], engineer_id, start_iso, end_iso)
    return {"slots": slots, "from": start_iso, "to": end_iso,
            "engineer_id": engineer_id, "count": len(slots)}


@admin_router.get("/unassigned")
async def admin_unassigned(
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
):
    """Open service jobs that need a dispatcher's attention:
       no engineer assigned OR no scheduled_at."""
    _require_dispatcher(user)
    of = _of(user)
    rows = await db.svc_cases.find(
        {**of,
         "status": {"$nin": ["closed", "invoiced", "cancelled", "void"]},
         "$or": [
             {"assigned_engineer_id": {"$in": [None, ""]}},
             {"scheduled_at": {"$in": [None, ""]}},
         ]},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
         "status": 1, "site_name": 1, "customer_name": 1,
         "scheduled_at": 1, "assigned_engineer_id": 1, "sla_resolve_at": 1,
         "estimated_minutes": 1},
    ).sort([("priority", 1), ("sla_resolve_at", 1)]).limit(limit).to_list(limit)
    return {"jobs": rows, "count": len(rows)}


class AssignIn(BaseModel):
    engineer_id: str
    scheduled_at: str
    estimated_minutes: Optional[int] = Field(None, ge=15, le=600)


@admin_router.post("/case/{case_id}/assign")
async def admin_assign_case(
    case_id: str, body: AssignIn, user=Depends(get_current_user),
):
    _require_dispatcher(user)
    of = _of(user)
    try:
        datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "scheduled_at must be ISO datetime")
    eng = await db.svc_engineers.find_one(
        {"id": body.engineer_id, **of}, {"_id": 0, "id": 1, "full_name": 1},
    )
    if not eng:
        raise HTTPException(404, "Engineer not found")
    case = await db.svc_cases.find_one(
        {"id": case_id, **of},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "site_name": 1,
         "assigned_engineer_id": 1, "scheduled_at": 1, "status": 1},
    )
    if not case:
        raise HTTPException(404, "Job not found")
    prev_engineer = case.get("assigned_engineer_id")
    prev_scheduled = case.get("scheduled_at")
    prev_status = case.get("status")
    upd = {
        "assigned_engineer_id": body.engineer_id,
        "assigned_engineer_name": eng.get("full_name"),
        "scheduled_at": body.scheduled_at,
        "updated_at": _now(),
    }
    if body.estimated_minutes:
        upd["estimated_minutes"] = body.estimated_minutes
    # Iter 216h151 — if the case is still in an "intake" state (NEW or
    # TRIAGED), scheduling it to an engineer is the canonical
    # transition to ASSIGNED. We do this inline rather than via
    # `transition()` to avoid two writes — the state machine permits
    # NEW→ASSIGNED and TRIAGED→ASSIGNED.
    promoted_status = None
    if prev_status in (NEW, TRIAGED):
        upd["status"] = ASSIGNED
        promoted_status = ASSIGNED
    await db.svc_cases.update_one({"id": case_id, **of}, {"$set": upd})

    # Timeline event so the audit trail and case view reflect the
    # dispatch. Best-effort — never blocks the response.
    try:
        if promoted_status:
            await append_event(
                case_id=case_id,
                organization_id=of["organization_id"],
                event_type="state_change",
                actor=user,
                body=f"Scheduled to {eng.get('full_name') or body.engineer_id}",
                extra={"from_state": prev_status, "to_state": promoted_status,
                       "via": "dispatch_schedule",
                       "scheduled_at": body.scheduled_at,
                       "prev_engineer": prev_engineer},
            )
        else:
            await append_event(
                case_id=case_id,
                organization_id=of["organization_id"],
                event_type="dispatch",
                actor=user,
                body=("Rescheduled" if prev_engineer == body.engineer_id else
                      f"Reassigned to {eng.get('full_name') or body.engineer_id}"),
                extra={"scheduled_at": body.scheduled_at,
                       "prev_engineer": prev_engineer,
                       "prev_scheduled_at": prev_scheduled},
            )
    except Exception:
        pass

    # Iter 216h142 — fire a notification on assign / reassign / reschedule.
    # Iter 220dm — switched from bare `pass` to logging so a regression
    # that breaks notification creation can be seen in the logs instead
    # of being silently swallowed.
    try:
        from routes.svc.notifications import create_notification
        when_str = datetime.fromisoformat(
            body.scheduled_at.replace("Z", "+00:00"),
        ).strftime("%a %d %b · %H:%M")
        ref = case.get("reference") or case_id[:8]
        title = case.get("title") or "Service job"
        site = case.get("site_name") or "Site"
        if prev_engineer == body.engineer_id:
            # Reschedule (same engineer, new time)
            await create_notification(
                user_id=body.engineer_id,
                organization_id=of["organization_id"],
                kind="job_rescheduled",
                title=f"Rescheduled: {ref} · {title}",
                body=f"{site} — new time {when_str}",
                link=f"/svc/engineer/jobs/{case_id}",
                source_type="case",
                source_id=case_id,
            )
        else:
            # New assignment
            await create_notification(
                user_id=body.engineer_id,
                organization_id=of["organization_id"],
                kind="job_assigned",
                title=f"New job: {ref} · {title}",
                body=f"{site} — scheduled {when_str}",
                link=f"/svc/engineer/jobs/{case_id}",
                source_type="case",
                source_id=case_id,
            )
            # If we replaced a previous engineer, let them know it's gone.
            if prev_engineer:
                await create_notification(
                    user_id=prev_engineer,
                    organization_id=of["organization_id"],
                    kind="job_unassigned",
                    title=f"Reassigned: {ref}",
                    body=f"{site} was passed to {eng.get('full_name') or 'another engineer'}.",
                    link=f"/svc/engineer/jobs/{case_id}",
                    source_type="case",
                    source_id=case_id,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dispatch notification failed for case=%s: %s", case_id, exc)

    # Iter 216h153 — Sicon outbox: dispatch updates the upstream call
    # with the new engineer/time and (when promoted) records the
    # state change as a tracking note.
    try:
        full_case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
        if full_case:
            await sicon_sync.push_case(full_case)
            if promoted_status:
                last_evt = await db.svc_case_events.find_one(
                    {"case_id": case_id, "type": "state_change"},
                    sort=[("at", -1)], projection={"_id": 0},
                )
                if last_evt:
                    await sicon_sync.push_event(
                        last_evt, case_reference=full_case.get("reference"),
                    )
    except Exception as e:
        logger.warning("[svc→sicon] diary schedule push failed: %s", e)

    # Iter 216h155 — audit dispatch decisions for compliance.
    try:
        await audit_log(
            action="svc.case.dispatch",
            user_id=user.get("id", ""),
            user_email=user.get("email", ""),
            resource_type="svc_case",
            resource_id=case_id,
            details=f"{case.get('reference', '')} → eng={body.engineer_id}"
                    + (f" @ {body.scheduled_at}" if body.scheduled_at else "")
                    + (f" (status {prev_status}→{promoted_status})"
                       if promoted_status else ""),
        )
    except Exception as e:
        logger.warning("[audit] diary schedule failed: %s", e)

    return {"ok": True, "case_id": case_id, **upd}


class PPMAssignIn(BaseModel):
    engineer_id: str
    scheduled_date: Optional[str] = Field(
        None, description="YYYY-MM-DD, defaults to existing"
    )


@admin_router.post("/ppm-task/{task_id}/assign")
async def admin_assign_ppm(
    task_id: str, body: PPMAssignIn, user=Depends(get_current_user),
):
    _require_dispatcher(user)
    of = _of(user)
    task = await db.ppm_tasks.find_one({"id": task_id, **of}, {"_id": 0, "id": 1})
    if not task:
        raise HTTPException(404, "PPM task not found")
    upd: dict = {"assigned_to": body.engineer_id, "updated_at": _now()}
    if body.scheduled_date:
        try:
            datetime.fromisoformat(body.scheduled_date + "T09:00:00+00:00")
        except ValueError:
            raise HTTPException(400, "scheduled_date must be YYYY-MM-DD")
        upd["scheduled_date"] = body.scheduled_date
    await db.ppm_tasks.update_one({"id": task_id, **of}, {"$set": upd})
    return {"ok": True, "task_id": task_id, **upd}


# ── Index setup ──────────────────────────────────────────────────

async def ensure_diary_indexes():
    """Called on app boot from route_registry."""
    try:
        await db.svc_diary_blocks.create_index(
            [("organization_id", 1), ("engineer_id", 1), ("start_at", 1)],
        )
        await db.svc_diary_blocks.create_index([("id", 1)], unique=True)
    except Exception as e:
        logger.warning("svc_diary_blocks index warning: %s", e)


__all__ = ["engineer_router", "admin_router", "ensure_diary_indexes"]
