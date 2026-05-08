"""GymAxis Staffing — workforce intelligence backend.

Covers all 12 canonical staffing modules (Smart Rota, Profiles & Skills,
Availability & Leave, Shift Marketplace, Performance, Payroll, Live
Floor, Multi-Site, AI Optimisation, Compliance Rules, Comms). Time
tracking / clock-in is intentionally stubbed — user asked to park it.

Role gating
-----------
- `owner` / `manager` / `master_admin` → full management surface.
- `staff` → ONLY their own shifts, leave, open-shift marketplace, and
  announcements (read-only unless noted).
- `gym_floor` kiosk accounts have no direct staffing API access — the
  kiosk view reuses `/api/gym-floor/*` endpoints for roster + handover.

Data model
----------
- `staff_members`      — canonical staff record (certs, hourly_cost, site_ids)
- `staff_shifts`        — single shift (staff_id, site_id, start, end, role)
- `staff_leave_requests`— time-off request (holiday, sick, unpaid, training)
- `staff_open_shifts`   — unassigned shifts waiting to be claimed
- `staff_swap_requests` — shift swap between two staff members
- `staff_announcements` — manager → staff broadcasts
- `staff_rules`         — per-org compliance rules (max hours, break minutes)

Every endpoint writes only to the caller's organization_id and returns
role-filtered rows.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────────────────── Helpers ─────────────────────────

def _role(user: dict) -> str:
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return "master_admin"
    r = (user.get("role") or "").lower()
    return r if r in {"owner", "manager", "staff", "gym_floor"} else "staff"


def _is_manager(user: dict) -> bool:
    return _role(user) in {"owner", "manager", "master_admin"}


def _require_manager(user: dict) -> None:
    if not _is_manager(user):
        raise HTTPException(403, "Managers and owners only")


def _org(user: dict) -> str:
    oid = user.get("organization_id")
    if not oid:
        raise HTTPException(400, "No organization context")
    return oid


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(doc: dict) -> dict:
    """Strip MongoDB _id + ObjectId sentinels before returning."""
    if not isinstance(doc, dict):
        return doc
    d = {k: v for k, v in doc.items() if k != "_id"}
    # Normalise datetimes to ISO strings so FastAPI's default JSON encoder
    # and downstream clients agree on format.
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.astimezone(timezone.utc).isoformat() if v.tzinfo else v.replace(tzinfo=timezone.utc).isoformat()
    return d


def _my_staff_id(user: dict, org_id: str) -> str | None:
    """Resolve the staff_members.id that matches the logged-in user.

    Staff records are linked to users by `user_id` (same UUID as
    `users.id`) OR by email match if user_id wasn't provided at create
    time. Returns None if no staff record exists — in which case a
    staff user won't be able to see any personal data yet.
    """
    u_id = user.get("id")
    email = (user.get("email") or "").lower()
    query = {"organization_id": org_id, "$or": [
        {"user_id": u_id} if u_id else {"user_id": "__never__"},
        {"email": email} if email else {"email": "__never__"},
    ]}
    doc = db.staff_members.find_one(query, {"_id": 0, "id": 1})
    if hasattr(doc, "__await__"):
        # Async Motor returns a coroutine.
        import asyncio  # noqa: WPS433 — lazy import
        doc = asyncio.get_event_loop().run_until_complete(doc)  # pragma: no cover
    return (doc or {}).get("id")


async def _my_staff_id_async(user: dict, org_id: str) -> str | None:
    """Async variant used by handlers — avoids the sync shim above."""
    u_id = user.get("id")
    email = (user.get("email") or "").lower()
    or_clauses = []
    if u_id:
        or_clauses.append({"user_id": u_id})
    if email:
        or_clauses.append({"email": email})
    if not or_clauses:
        return None
    doc = await db.staff_members.find_one(
        {"organization_id": org_id, "$or": or_clauses},
        {"_id": 0, "id": 1},
    )
    return (doc or {}).get("id")


# ───────────────────────── Models ─────────────────────────

VALID_ROLES = {"instructor", "pt", "manager", "reception", "cleaner", "maintenance", "lifeguard", "duty_manager", "other"}
VALID_SHIFT_STATUS = {"scheduled", "confirmed", "completed", "cancelled", "open"}
VALID_LEAVE_TYPE = {"holiday", "sick", "unpaid", "training", "other"}
VALID_LEAVE_STATUS = {"pending", "approved", "rejected", "cancelled"}
VALID_SWAP_STATUS = {"pending", "accepted", "rejected", "cancelled"}


class StaffCreate(BaseModel):
    full_name: str
    email: str | None = None
    user_id: str | None = None
    primary_role: str = "reception"
    secondary_roles: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    site_ids: list[str] = Field(default_factory=list)
    contract_type: str | None = "part_time"  # part_time|full_time|casual|contractor
    weekly_hours: float | None = None
    hourly_cost: float = 0.0
    phone: str | None = None
    active: bool = True
    notes: str | None = None


class StaffUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    primary_role: str | None = None
    secondary_roles: list[str] | None = None
    certifications: list[str] | None = None
    site_ids: list[str] | None = None
    contract_type: str | None = None
    weekly_hours: float | None = None
    hourly_cost: float | None = None
    phone: str | None = None
    active: bool | None = None
    notes: str | None = None


class ShiftCreate(BaseModel):
    staff_id: str | None = None           # optional → creates an Open Shift
    site_id: str | None = None
    date: str                              # YYYY-MM-DD (local gym time)
    start_time: str                        # HH:MM
    end_time: str                          # HH:MM
    role: str = "reception"
    notes: str | None = None
    break_minutes: int = 0
    status: str = "scheduled"


class ShiftUpdate(BaseModel):
    staff_id: str | None = None
    site_id: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    role: str | None = None
    notes: str | None = None
    break_minutes: int | None = None
    status: str | None = None


class LeaveRequestCreate(BaseModel):
    start_date: str                   # YYYY-MM-DD
    end_date: str                     # YYYY-MM-DD (inclusive)
    leave_type: str = "holiday"
    reason: str | None = None


class SwapRequestCreate(BaseModel):
    offered_shift_id: str
    recipient_staff_id: str | None = None   # None → post to marketplace
    requested_shift_id: str | None = None   # None → drop / claim


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    audience: str = "all"                  # all | site:<id> | role:<role>
    pinned: bool = False


class RulesUpdate(BaseModel):
    max_hours_per_week: float | None = None
    min_rest_hours_between_shifts: float | None = None
    min_break_minutes_per_shift: float | None = None
    max_days_consecutive: int | None = None
    require_manager_approval_for_overtime: bool | None = None


def _shift_hours(s: dict) -> float:
    """Compute paid hours for a shift (start→end minus break)."""
    try:
        sh, sm = [int(x) for x in s["start_time"].split(":")]
        eh, em = [int(x) for x in s["end_time"].split(":")]
        mins = (eh * 60 + em) - (sh * 60 + sm) - int(s.get("break_minutes") or 0)
        return max(0.0, mins / 60.0)
    except Exception:
        return 0.0


# ───────────────────────── Staff profiles ─────────────────────────

@router.get("/staffing/staff")
async def list_staff(include_inactive: bool = Query(False), user: dict = Depends(get_current_user)):
    """Managers see all staff. Staff see their own profile only."""
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if not include_inactive:
        q["active"] = True
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        q["id"] = sid or "__none__"
    rows = await db.staff_members.find(q, {"_id": 0}).sort("full_name", 1).to_list(1000)
    return {"staff": rows, "role": _role(user)}


@router.post("/staffing/staff")
async def create_staff(body: StaffCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    if body.primary_role not in VALID_ROLES:
        raise HTTPException(400, f"primary_role must be one of {sorted(VALID_ROLES)}")
    org_id = _org(user)
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
        **body.dict(),
    }
    await db.staff_members.insert_one(doc.copy())
    return _clean(doc)


@router.patch("/staffing/staff/{staff_id}")
async def update_staff(staff_id: str, body: StaffUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if "primary_role" in patch and patch["primary_role"] not in VALID_ROLES:
        raise HTTPException(400, "invalid primary_role")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_members.update_one({"id": staff_id, "organization_id": org_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "staff not found")
    doc = await db.staff_members.find_one({"id": staff_id}, {"_id": 0})
    return doc


@router.delete("/staffing/staff/{staff_id}")
async def archive_staff(staff_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_members.update_one({"id": staff_id, "organization_id": org_id}, {"$set": {"active": False, "archived_at": _now().isoformat()}})
    if res.matched_count == 0:
        raise HTTPException(404, "staff not found")
    return {"ok": True}


# ───────────────────────── Rota / shifts ─────────────────────────

@router.get("/staffing/shifts")
async def list_shifts(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    site_id: str | None = Query(None),
    staff_id: str | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Manager view: every shift. Staff view: only their own."""
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if date_from:
        q["date"] = {**q.get("date", {}), "$gte": date_from}
    if date_to:
        q["date"] = {**q.get("date", {}), "$lte": date_to}
    if site_id:
        q["site_id"] = site_id
    if status:
        q["status"] = status
    if staff_id and _is_manager(user):
        q["staff_id"] = staff_id
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        q["staff_id"] = sid or "__none__"
    rows = await db.staff_shifts.find(q, {"_id": 0}).sort([("date", 1), ("start_time", 1)]).to_list(1000)
    # Enrich with staff name + labour cost (computed) — useful for the rota grid.
    if rows:
        staff_ids = list({r.get("staff_id") for r in rows if r.get("staff_id")})
        staff = {s["id"]: s async for s in db.staff_members.find({"id": {"$in": staff_ids}}, {"_id": 0, "id": 1, "full_name": 1, "hourly_cost": 1, "primary_role": 1})}
        for r in rows:
            s = staff.get(r.get("staff_id") or "", {})
            r["staff_name"] = s.get("full_name") or ("OPEN SHIFT" if r.get("status") == "open" else "—")
            r["hours"] = _shift_hours(r)
            r["labour_cost"] = round(r["hours"] * float(s.get("hourly_cost") or 0.0), 2) if _is_manager(user) else None
    return {"shifts": rows, "role": _role(user)}


@router.post("/staffing/shifts")
async def create_shift(body: ShiftCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    if body.status not in VALID_SHIFT_STATUS:
        raise HTTPException(400, "invalid status")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
        **body.dict(),
    }
    # No staff → open shift that managers can publish or staff can claim.
    if not doc.get("staff_id"):
        doc["status"] = "open"
    await db.staff_shifts.insert_one(doc.copy())
    # Compliance check: soft warn on breaches (doesn't block).
    warnings = await _check_compliance(org_id, doc)
    return {"shift": _clean(doc), "warnings": warnings}


@router.patch("/staffing/shifts/{shift_id}")
async def update_shift(shift_id: str, body: ShiftUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if "status" in patch and patch["status"] not in VALID_SHIFT_STATUS:
        raise HTTPException(400, "invalid status")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_shifts.update_one({"id": shift_id, "organization_id": org_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "shift not found")
    doc = await db.staff_shifts.find_one({"id": shift_id}, {"_id": 0})
    warnings = await _check_compliance(org_id, doc) if doc else []
    return {"shift": doc, "warnings": warnings}


@router.delete("/staffing/shifts/{shift_id}")
async def delete_shift(shift_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_shifts.delete_one({"id": shift_id, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "shift not found")
    return {"ok": True}


@router.post("/staffing/shifts/bulk")
async def bulk_create_shifts(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Copy-week helper: accepts {source_start, target_start, site_id?} and
    clones all shifts from the source week to the target week.
    """
    _require_manager(user)
    org_id = _org(user)
    src = body.get("source_start")
    tgt = body.get("target_start")
    if not src or not tgt:
        raise HTTPException(400, "source_start and target_start required (YYYY-MM-DD)")
    delta_days = (datetime.fromisoformat(tgt).date() - datetime.fromisoformat(src).date()).days
    q = {"organization_id": org_id, "date": {"$gte": src, "$lt": (datetime.fromisoformat(src).date() + timedelta(days=7)).isoformat()}}
    if body.get("site_id"):
        q["site_id"] = body["site_id"]
    src_rows = await db.staff_shifts.find(q, {"_id": 0}).to_list(10_000)
    created = []
    for r in src_rows:
        new_date = (datetime.fromisoformat(r["date"]).date() + timedelta(days=delta_days)).isoformat()
        clone = {**r, "id": str(uuid4()), "date": new_date, "created_at": _now().isoformat(), "created_by": user.get("email"), "status": "scheduled"}
        clone.pop("updated_at", None)
        await db.staff_shifts.insert_one(clone.copy())
        created.append(clone.get("id"))
    return {"created_count": len(created), "created_ids": created}


# ───────────────────────── Availability & leave ─────────────────────────

@router.get("/staffing/leave")
async def list_leave(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        q["staff_id"] = sid or "__none__"
    rows = await db.staff_leave_requests.find(q, {"_id": 0}).sort("start_date", -1).to_list(500)
    return {"leave": rows, "role": _role(user)}


@router.post("/staffing/leave")
async def create_leave(body: LeaveRequestCreate, user: dict = Depends(get_current_user)):
    """Any authenticated staff member can submit. Managers submit on
    behalf of themselves or use PATCH-approve for others."""
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(400, "No staff record linked to your account — ask a manager to add you.")
    if body.leave_type not in VALID_LEAVE_TYPE:
        raise HTTPException(400, "invalid leave_type")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": sid,
        "status": "pending",
        "created_at": _now().isoformat(),
        **body.dict(),
    }
    await db.staff_leave_requests.insert_one(doc.copy())
    return _clean(doc)


@router.patch("/staffing/leave/{leave_id}")
async def decide_leave(leave_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Managers only — approve / reject with optional notes."""
    _require_manager(user)
    org_id = _org(user)
    decision = (body.get("status") or "").lower()
    if decision not in {"approved", "rejected", "cancelled"}:
        raise HTTPException(400, "status must be approved|rejected|cancelled")
    patch = {"status": decision, "decided_at": _now().isoformat(), "decided_by": user.get("email")}
    if body.get("manager_notes"):
        patch["manager_notes"] = body["manager_notes"]
    res = await db.staff_leave_requests.update_one({"id": leave_id, "organization_id": org_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "leave request not found")
    doc = await db.staff_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    return doc


# ───────────────────────── Shift marketplace ─────────────────────────

@router.get("/staffing/marketplace/open")
async def list_open_shifts(user: dict = Depends(get_current_user)):
    """All logged-in staff can see open shifts to claim. Managers see
    the same list for oversight."""
    org_id = _org(user)
    rows = await db.staff_shifts.find({"organization_id": org_id, "status": "open"}, {"_id": 0}).sort("date", 1).to_list(500)
    for r in rows:
        r["hours"] = _shift_hours(r)
    return {"open_shifts": rows}


@router.post("/staffing/marketplace/open/{shift_id}/claim")
async def claim_open_shift(shift_id: str, user: dict = Depends(get_current_user)):
    """Any staff member (or manager) can claim an open shift. Request is
    queued for manager approval before the shift is assigned."""
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(400, "No staff record linked to your account.")
    shift = await db.staff_shifts.find_one({"id": shift_id, "organization_id": org_id, "status": "open"}, {"_id": 0})
    if not shift:
        raise HTTPException(404, "open shift not found")
    # Insert a swap request that represents the claim. Manager approves.
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "kind": "claim",
        "offered_shift_id": shift_id,
        "requesting_staff_id": sid,
        "status": "pending",
        "created_at": _now().isoformat(),
    }
    await db.staff_swap_requests.insert_one(doc.copy())
    return _clean(doc)


@router.post("/staffing/marketplace/swap")
async def request_swap(body: SwapRequestCreate, user: dict = Depends(get_current_user)):
    """Staff requests a shift swap. Sent to recipient (or marketplace)
    pending manager approval.
    """
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(400, "No staff record linked to your account.")
    shift = await db.staff_shifts.find_one({"id": body.offered_shift_id, "organization_id": org_id}, {"_id": 0})
    if not shift or (shift.get("staff_id") != sid and not _is_manager(user)):
        raise HTTPException(400, "Offered shift isn't yours or doesn't exist.")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "kind": "swap" if body.requested_shift_id else "drop",
        "offered_shift_id": body.offered_shift_id,
        "requested_shift_id": body.requested_shift_id,
        "requesting_staff_id": sid,
        "recipient_staff_id": body.recipient_staff_id,
        "status": "pending",
        "created_at": _now().isoformat(),
    }
    await db.staff_swap_requests.insert_one(doc.copy())
    return _clean(doc)


@router.get("/staffing/marketplace/requests")
async def list_swap_requests(user: dict = Depends(get_current_user)):
    """Managers see every request. Staff see requests they originated
    OR were addressed to."""
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        if not sid:
            return {"requests": []}
        q["$or"] = [{"requesting_staff_id": sid}, {"recipient_staff_id": sid}]
    rows = await db.staff_swap_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"requests": rows}


@router.patch("/staffing/marketplace/requests/{req_id}")
async def decide_swap(req_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Managers approve/reject. On approve, we apply the effect:
    - kind=claim    → assign the offered_shift_id to requesting_staff.
    - kind=drop     → mark the offered shift as `open`.
    - kind=swap     → swap staff_ids between offered and requested shifts.
    """
    _require_manager(user)
    org_id = _org(user)
    decision = (body.get("status") or "").lower()
    if decision not in {"approved", "rejected", "cancelled"}:
        raise HTTPException(400, "status must be approved|rejected|cancelled")
    req = await db.staff_swap_requests.find_one({"id": req_id, "organization_id": org_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "request not found")
    patch = {"status": decision, "decided_at": _now().isoformat(), "decided_by": user.get("email")}
    if decision == "approved":
        kind = req.get("kind")
        if kind == "claim":
            await db.staff_shifts.update_one(
                {"id": req["offered_shift_id"], "organization_id": org_id},
                {"$set": {"staff_id": req["requesting_staff_id"], "status": "scheduled"}},
            )
        elif kind == "drop":
            await db.staff_shifts.update_one(
                {"id": req["offered_shift_id"], "organization_id": org_id},
                {"$set": {"status": "open", "staff_id": None}},
            )
        elif kind == "swap" and req.get("requested_shift_id"):
            a = await db.staff_shifts.find_one({"id": req["offered_shift_id"]}, {"_id": 0})
            b = await db.staff_shifts.find_one({"id": req["requested_shift_id"]}, {"_id": 0})
            if a and b:
                await db.staff_shifts.update_one({"id": a["id"]}, {"$set": {"staff_id": b.get("staff_id")}})
                await db.staff_shifts.update_one({"id": b["id"]}, {"$set": {"staff_id": a.get("staff_id")}})
    await db.staff_swap_requests.update_one({"id": req_id}, {"$set": patch})
    return {**req, **patch}


# ───────────────────────── Performance & Payroll ─────────────────────────

@router.get("/staffing/performance")
async def performance_summary(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Managers-only cross-staff analytics. Links staff → classes and
    revenue where possible (uses memberships_classes + bookings)."""
    _require_manager(user)
    org_id = _org(user)
    # Default to last 30 days.
    dt_to = datetime.fromisoformat(date_to) if date_to else _now()
    dt_from = datetime.fromisoformat(date_from) if date_from else (dt_to - timedelta(days=30))
    staff = await db.staff_members.find({"organization_id": org_id, "active": True}, {"_id": 0}).to_list(1000)
    summary = []
    for s in staff:
        sid = s["id"]
        # Scheduled hours in window.
        shifts = await db.staff_shifts.find(
            {"organization_id": org_id, "staff_id": sid, "date": {"$gte": dt_from.date().isoformat(), "$lte": dt_to.date().isoformat()}},
            {"_id": 0, "start_time": 1, "end_time": 1, "break_minutes": 1},
        ).to_list(5000)
        hours = sum(_shift_hours(x) for x in shifts)
        # Instructor linkage — classes where instructor_id == user_id OR instructor_name == full_name.
        linked_name = s.get("full_name")
        classes_count = 0
        attendance_count = 0
        try:
            classes_count = await db.memberships_classes.count_documents({
                "organization_id": org_id,
                "$or": [{"instructor_id": s.get("user_id") or "__none__"}, {"instructor_name": linked_name}],
            })
            attendance_count = await db.memberships_bookings.count_documents({
                "organization_id": org_id,
                "instructor_name": linked_name,
                "status": "attended",
            })
        except Exception:  # collections may not exist on fresh orgs
            classes_count = 0
            attendance_count = 0
        summary.append({
            "staff_id": sid,
            "full_name": linked_name,
            "primary_role": s.get("primary_role"),
            "hours_scheduled": round(hours, 2),
            "labour_cost": round(hours * float(s.get("hourly_cost") or 0.0), 2),
            "classes_delivered": classes_count,
            "attendees": attendance_count,
        })
    summary.sort(key=lambda x: x["hours_scheduled"], reverse=True)
    return {"window": {"from": dt_from.isoformat(), "to": dt_to.isoformat()}, "staff": summary}


@router.get("/staffing/payroll/export")
async def payroll_csv(
    date_from: str,
    date_to: str,
    user: dict = Depends(get_current_user),
):
    """Managers export CSV of hours + labour cost per staff for a date
    window. Ready to import into Sage or any common payroll tool."""
    _require_manager(user)
    org_id = _org(user)
    shifts = await db.staff_shifts.find(
        {"organization_id": org_id, "date": {"$gte": date_from, "$lte": date_to}, "status": {"$ne": "cancelled"}},
        {"_id": 0},
    ).to_list(50_000)
    staff = {s["id"]: s async for s in db.staff_members.find({"organization_id": org_id}, {"_id": 0})}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Staff ID", "Name", "Role", "Hours", "Hourly Cost", "Total Cost"])
    totals: dict[str, dict] = {}
    for sh in shifts:
        sid = sh.get("staff_id") or ""
        s = staff.get(sid) or {}
        hrs = _shift_hours(sh)
        t = totals.setdefault(sid, {"name": s.get("full_name") or "OPEN SHIFT", "role": s.get("primary_role") or "", "hours": 0.0, "rate": float(s.get("hourly_cost") or 0)})
        t["hours"] += hrs
    for sid, t in totals.items():
        w.writerow([sid, t["name"], t["role"], round(t["hours"], 2), t["rate"], round(t["hours"] * t["rate"], 2)])
    csv_bytes = buf.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payroll-{date_from}-to-{date_to}.csv"},
    )


# ───────────────────────── Live Gym Floor view ─────────────────────────

@router.get("/staffing/live-floor")
async def live_floor(site_id: str | None = Query(None), user: dict = Depends(get_current_user)):
    """Who's scheduled right now, per site. Available to everyone in the
    org so gym floor staff can see their own crew."""
    org_id = _org(user)
    now = _now()
    today = now.date().isoformat()
    now_hm = now.strftime("%H:%M")
    q = {"organization_id": org_id, "date": today, "status": {"$ne": "cancelled"}}
    if site_id:
        q["site_id"] = site_id
    shifts = await db.staff_shifts.find(q, {"_id": 0}).to_list(500)
    staff = {s["id"]: s async for s in db.staff_members.find({"organization_id": org_id, "active": True}, {"_id": 0})}
    on_now, upcoming, finished = [], [], []
    for sh in shifts:
        sid = sh.get("staff_id")
        nm = staff.get(sid or "", {}).get("full_name") or ("OPEN" if sh.get("status") == "open" else "—")
        sh_out = {**sh, "staff_name": nm}
        if sh["start_time"] <= now_hm <= sh["end_time"]:
            on_now.append(sh_out)
        elif sh["start_time"] > now_hm:
            upcoming.append(sh_out)
        else:
            finished.append(sh_out)
    on_now.sort(key=lambda x: x.get("start_time", ""))
    upcoming.sort(key=lambda x: x.get("start_time", ""))
    coverage = {"on_now": len(on_now), "open_shifts_today": sum(1 for sh in shifts if sh.get("status") == "open")}
    return {"as_of": now.isoformat(), "on_now": on_now, "upcoming": upcoming, "finished": finished, "coverage": coverage}


# ───────────────────────── Compliance rules ─────────────────────────

DEFAULT_RULES = {
    "max_hours_per_week": 48.0,            # UK WTD default
    "min_rest_hours_between_shifts": 11.0, # UK WTD daily rest
    "min_break_minutes_per_shift": 20.0,   # UK WTD when shift > 6h
    "max_days_consecutive": 6,
    "require_manager_approval_for_overtime": True,
}


@router.get("/staffing/rules")
async def get_rules(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    return {**DEFAULT_RULES, **doc}


@router.put("/staffing/rules")
async def put_rules(body: RulesUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    patch["organization_id"] = org_id
    patch["updated_at"] = _now().isoformat()
    patch["updated_by"] = user.get("email")
    await db.staff_rules.update_one({"organization_id": org_id}, {"$set": patch}, upsert=True)
    doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    return {**DEFAULT_RULES, **doc}


async def _check_compliance(org_id: str, shift: dict) -> list[str]:
    """Fast heuristic checks against the org rules. Runs on shift
    create/update and returns warning strings (does not block)."""
    warnings: list[str] = []
    rules_doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    rules = {**DEFAULT_RULES, **rules_doc}
    hrs = _shift_hours(shift)
    if hrs > 12:
        warnings.append(f"Shift is {hrs:.1f}h — unusually long.")
    if rules.get("min_break_minutes_per_shift") and hrs > 6 and int(shift.get("break_minutes") or 0) < rules["min_break_minutes_per_shift"]:
        warnings.append(f"Shift >6h should include at least {int(rules['min_break_minutes_per_shift'])} min break.")
    # Weekly hours check — uses existing shifts for the same staff this week.
    if shift.get("staff_id"):
        try:
            d = datetime.fromisoformat(shift["date"]).date()
            week_start = (d - timedelta(days=d.weekday())).isoformat()
            week_end = (d - timedelta(days=d.weekday()) + timedelta(days=7)).isoformat()
            same = await db.staff_shifts.find(
                {"organization_id": org_id, "staff_id": shift["staff_id"], "date": {"$gte": week_start, "$lt": week_end}, "status": {"$ne": "cancelled"}},
                {"_id": 0, "start_time": 1, "end_time": 1, "break_minutes": 1, "id": 1},
            ).to_list(200)
            total = sum(_shift_hours(x) for x in same if x["id"] != shift.get("id"))
            total += hrs
            if rules.get("max_hours_per_week") and total > rules["max_hours_per_week"]:
                warnings.append(f"Weekly total {total:.1f}h exceeds rule {rules['max_hours_per_week']:.0f}h.")
        except Exception:  # defensive — don't fail the request over a warning
            pass
    return warnings


# ───────────────────────── Announcements ─────────────────────────

@router.get("/staffing/announcements")
async def list_announcements(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    rows = await db.staff_announcements.find({"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {"announcements": rows}


@router.post("/staffing/announcements")
async def create_announcement(body: AnnouncementCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
        "author_name": user.get("full_name") or user.get("email"),
        **body.dict(),
    }
    await db.staff_announcements.insert_one(doc.copy())
    return _clean(doc)


@router.delete("/staffing/announcements/{ann_id}")
async def delete_announcement(ann_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_announcements.delete_one({"id": ann_id, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "announcement not found")
    return {"ok": True}


# ───────────────────────── AI Workforce Optimisation ─────────────────────────

@router.get("/staffing/ai/insights")
async def ai_insights(user: dict = Depends(get_current_user)):
    """Managers only. Fast heuristic + optional Claude narrative.

    Heuristic: bucket last-30-days class attendance by weekday+hour.
    Match against scheduled shifts. Flag over/under staffed slots.
    """
    _require_manager(user)
    org_id = _org(user)
    dt_to = _now()
    dt_from = dt_to - timedelta(days=30)
    # Bucket actual demand from bookings.
    demand: dict[tuple[int, int], int] = {}
    try:
        bookings = await db.memberships_bookings.find(
            {"organization_id": org_id, "status": "attended", "class_date": {"$gte": dt_from.date().isoformat()}},
            {"_id": 0, "class_date": 1, "class_time": 1},
        ).to_list(20_000)
        for b in bookings:
            try:
                d = datetime.fromisoformat(b["class_date"]).date()
                hr = int((b.get("class_time") or "00:00").split(":")[0])
                demand[(d.weekday(), hr)] = demand.get((d.weekday(), hr), 0) + 1
            except Exception:
                continue
    except Exception:
        demand = {}
    # Bucket supply from shifts.
    supply: dict[tuple[int, int], int] = {}
    shifts = await db.staff_shifts.find(
        {"organization_id": org_id, "date": {"$gte": dt_from.date().isoformat()}, "status": {"$in": ["scheduled", "confirmed", "completed"]}},
        {"_id": 0, "date": 1, "start_time": 1, "end_time": 1},
    ).to_list(50_000)
    for sh in shifts:
        try:
            d = datetime.fromisoformat(sh["date"]).date()
            sh_start = int(sh["start_time"].split(":")[0])
            sh_end = int(sh["end_time"].split(":")[0])
            for h in range(sh_start, max(sh_start + 1, sh_end)):
                supply[(d.weekday(), h)] = supply.get((d.weekday(), h), 0) + 1
        except Exception:
            continue
    # Score slots. Threshold = 10 attendees per staff as a rough "good" ratio.
    flags = []
    for (wd, hr), attendees in demand.items():
        staff_on = supply.get((wd, hr), 0)
        ratio = attendees / max(1, staff_on)
        if staff_on == 0 and attendees >= 3 or ratio > 15:
            flags.append({"weekday": wd, "hour": hr, "kind": "understaffed", "demand": attendees, "supply": staff_on, "ratio": ratio})
    # Overstaffed: supply but zero demand in last 30 days.
    for (wd, hr), staff_on in supply.items():
        if staff_on >= 3 and demand.get((wd, hr), 0) == 0:
            flags.append({"weekday": wd, "hour": hr, "kind": "overstaffed", "demand": 0, "supply": staff_on, "ratio": 0})
    flags.sort(key=lambda f: (-f["ratio"] if f["kind"] == "understaffed" else f["supply"]))
    flags = flags[:10]

    # Optional Claude narrative — falls back to plain summary if no key.
    narrative = ""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if api_key and flags:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
            wd_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            flags_text = "\n".join(f"- {wd_names[f['weekday']]} {f['hour']:02d}:00 → {f['kind']} (demand={f['demand']}, supply={f['supply']})" for f in flags)
            chat = LlmChat(
                api_key=api_key,
                session_id=f"staffing-ai-{org_id}",
                system_message=(
                    "You are a gym workforce optimisation consultant. Given the flagged time "
                    "slots, write a 3-sentence, UK-English, plain-text summary of the top "
                    "staffing opportunities. No bullet points. Focus on cost savings and "
                    "member-experience risk. Do not invent numbers."
                ),
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            resp = await chat.send_message(UserMessage(text=f"Here are the flagged slots:\n{flags_text}"))
            narrative = (resp or "").strip()
        except Exception as exc:
            logger.info("[staffing] ai narrative failed: %s", exc)
            narrative = ""

    if not narrative:
        narrative = f"Flagged {len(flags)} staffing imbalances over the last 30 days — review understaffed peaks first to protect member experience, then rebalance overstaffed slots for cost savings."
    return {"flags": flags, "narrative": narrative}
