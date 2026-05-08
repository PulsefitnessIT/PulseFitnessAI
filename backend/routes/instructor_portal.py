"""GymAxis Memberships — Instructor portal.

Scope: any logged-in user whose `id` matches `instructor_user_id` on one or
more `class_templates` / `class_occurrences`. No separate login — they
authenticate through the standard GymAxis JWT and the routes filter by
`instructor_user_id == user.id`.

Routes:
  • GET  /instructor/me                      — profile + rate
  • GET  /instructor/classes?from&to         — my classes in a window
  • GET  /instructor/occurrences/{id}/roster — bookings on that class
  • POST /instructor/occurrences/{id}/attendance — mark {bookings:[{id,status}]}
  • GET  /instructor/commission?month=YYYY-MM — my commission for a month

Plus operator endpoints:
  • GET /memberships/commission?month=YYYY-MM — whole-org commission report
    grouped by instructor (rate × attended_count)
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["instructor-portal"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_bounds(month: str) -> tuple[str, str]:
    """'2026-04' → (first day ISO, last day ISO) in UTC."""
    y, m = [int(x) for x in month.split("-")[:2]]
    first = datetime(y, m, 1, tzinfo=timezone.utc)
    last_day = monthrange(y, m)[1]
    last = datetime(y, m, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return first.isoformat(), last.isoformat()


async def _require_instructor(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_instructor"):
        # Allow fall-through if the user owns at least one template as instructor
        owns = await db.class_templates.find_one({"instructor_user_id": user["id"]}, {"_id": 1})
        if not owns:
            raise HTTPException(403, "Not an instructor")
    return user


@router.get("/instructor/me")
async def instructor_me(user: dict = Depends(_require_instructor)):
    # Count assigned templates and upcoming classes for a quick header
    now = _now_iso()
    tpl_count = await db.class_templates.count_documents({"instructor_user_id": user["id"], "archived": {"$ne": True}})
    upcoming = await db.class_occurrences.count_documents({
        "instructor_user_id": user["id"],
        "starts_at": {"$gte": now},
        "status": "scheduled",
    })
    return {
        "id": user["id"],
        "name": user.get("full_name") or user.get("email"),
        "email": user["email"],
        "rate_pence": int(user.get("instructor_rate_pence") or 0),
        "template_count": tpl_count,
        "upcoming_classes": upcoming,
        "organization_id": user.get("organization_id"),
    }


@router.get("/instructor/classes")
async def instructor_classes(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    user: dict = Depends(_require_instructor),
):
    """My classes within [from, to]. Default window = today → +7d."""
    now = datetime.now(timezone.utc)
    start = from_ or now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = to or (now + timedelta(days=7)).isoformat()
    occs = await db.class_occurrences.find(
        {"instructor_user_id": user["id"], "starts_at": {"$gte": start, "$lte": end}},
        {"_id": 0},
    ).sort("starts_at", 1).to_list(500)
    return {"occurrences": occs}


@router.get("/instructor/occurrences/{occ_id}/roster")
async def instructor_roster(occ_id: str, user: dict = Depends(_require_instructor)):
    occ = await db.class_occurrences.find_one(
        {"id": occ_id, "instructor_user_id": user["id"]}, {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found or not yours")
    bookings = await db.bookings.find(
        {"occurrence_id": occ_id, "status": {"$in": ["booked", "attended", "no_show", "late_cancel"]}},
        {"_id": 0},
    ).to_list(500)
    # Hydrate member name + email
    member_ids = [b["member_id"] for b in bookings]
    members = {m["id"]: m async for m in db.members.find(
        {"id": {"$in": member_ids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1})}
    for b in bookings:
        m = members.get(b["member_id"]) or {}
        b["member"] = {
            "id": b["member_id"],
            "name": f"{m.get('first_name','')} {m.get('last_name','')}".strip() or m.get("email", "—"),
            "email": m.get("email"),
        }
    return {"occurrence": occ, "roster": bookings}


@router.post("/instructor/occurrences/{occ_id}/attendance")
async def instructor_mark_attendance(
    occ_id: str,
    body: dict = Body(...),
    user: dict = Depends(_require_instructor),
):
    """Body: {items: [{booking_id: str, status: 'attended' | 'no_show'}]}"""
    occ = await db.class_occurrences.find_one(
        {"id": occ_id, "instructor_user_id": user["id"]}, {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found or not yours")
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "items[] required")
    attended = 0
    no_show = 0
    for it in items:
        bid = it.get("booking_id")
        status = it.get("status")
        if not bid or status not in ("attended", "no_show"):
            continue
        res = await db.bookings.update_one(
            {"id": bid, "occurrence_id": occ_id},
            {"$set": {"status": status, "marked_by": user["id"], "marked_at": _now_iso()}},
        )
        if res.matched_count:
            if status == "attended":
                attended += 1
            else:
                no_show += 1
    # Snapshot counts on the occurrence
    attended_total = await db.bookings.count_documents(
        {"occurrence_id": occ_id, "status": "attended"})
    no_show_total = await db.bookings.count_documents(
        {"occurrence_id": occ_id, "status": "no_show"})
    await db.class_occurrences.update_one(
        {"id": occ_id},
        {"$set": {"attended_count": attended_total, "no_show_count": no_show_total,
                  "status": "completed", "completed_at": _now_iso(),
                  "completed_by": user["id"]}},
    )
    # Bump member.no_show_count for tracked no-shows (one bump per new no-show)
    for it in items:
        if it.get("status") == "no_show":
            bk = await db.bookings.find_one({"id": it["booking_id"]}, {"_id": 0, "member_id": 1})
            if bk:
                await db.members.update_one({"id": bk["member_id"]}, {"$inc": {"no_show_count": 1}})
    return {"ok": True, "attended_added": attended, "no_show_added": no_show,
            "totals": {"attended": attended_total, "no_show": no_show_total}}


# ═════════════════════ Commission ═════════════════════

async def _commission_for_user(user_id: str, rate_pence: int, month: str, org_id: str) -> dict:
    start_iso, end_iso = _month_bounds(month)
    occs = await db.class_occurrences.find(
        {"instructor_user_id": user_id,
         "organization_id": org_id,
         "starts_at": {"$gte": start_iso, "$lte": end_iso},
         "status": {"$in": ["completed", "scheduled"]}},
        {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "attended_count": 1, "status": 1},
    ).sort("starts_at", 1).to_list(500)
    total_attended = sum(int(o.get("attended_count") or 0) for o in occs)
    completed_class_count = sum(1 for o in occs if o.get("status") == "completed")
    pay_pence = completed_class_count * rate_pence
    return {
        "month": month,
        "rate_pence": rate_pence,
        "class_count": completed_class_count,
        "scheduled_count": len(occs),
        "total_attended": total_attended,
        "pay_pence": pay_pence,
        "occurrences": occs,
    }


@router.get("/instructor/commission")
async def instructor_commission(month: str, user: dict = Depends(_require_instructor)):
    rate = int(user.get("instructor_rate_pence") or 0)
    return await _commission_for_user(user["id"], rate, month, user.get("organization_id") or "")


@router.get("/memberships/commission")
async def org_commission(month: str, user: dict = Depends(get_current_user)):
    """Operator — commission across all instructors for a month."""
    org_id = await _require_operator_org(user)
    instructors = await db.users.find(
        {"organization_id": org_id, "is_instructor": True},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "instructor_rate_pence": 1},
    ).to_list(100)
    rows = []
    grand_total_pence = 0
    for ins in instructors:
        row = await _commission_for_user(ins["id"], int(ins.get("instructor_rate_pence") or 0), month, org_id)
        row["instructor"] = {"id": ins["id"], "name": ins.get("full_name") or ins["email"], "email": ins["email"]}
        row["occurrences"] = []  # strip detail in the roll-up
        rows.append(row)
        grand_total_pence += row["pay_pence"]
    return {"month": month, "grand_total_pence": grand_total_pence, "rows": rows}


@router.get("/memberships/commission.csv")
async def org_commission_csv(month: str, user: dict = Depends(get_current_user)):
    """Payroll-ready CSV of the same commission data."""
    data = await org_commission(month, user)  # reuse rollup
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Instructor", "Email", "Rate (GBP)", "Completed classes",
                     "Scheduled classes", "Total attended", "Payout (GBP)"])
    for r in data["rows"]:
        ins = r["instructor"]
        writer.writerow([
            ins["name"], ins["email"], f"{r['rate_pence']/100:.2f}",
            r["class_count"], r["scheduled_count"], r["total_attended"],
            f"{r['pay_pence']/100:.2f}",
        ])
    writer.writerow([])
    writer.writerow(["", "", "", "", "", "TOTAL", f"{data['grand_total_pence']/100:.2f}"])
    buf.seek(0)
    filename = f"commission-{month}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═════════════════════ Cover requests ═════════════════════

@router.post("/instructor/occurrences/{occ_id}/request-cover")
async def request_cover(
    occ_id: str,
    body: dict = Body(default={}),
    user: dict = Depends(_require_instructor),
):
    """Instructor can't make it — ping ops and open the class for pickup."""
    occ = await db.class_occurrences.find_one(
        {"id": occ_id, "instructor_user_id": user["id"]},
        {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found or not yours")
    if occ.get("status") == "cancelled":
        raise HTTPException(400, "Class already cancelled")
    existing = await db.cover_requests.find_one({"occurrence_id": occ_id, "status": "open"}, {"_id": 0})
    if existing:
        return {"cover_request": existing, "already_open": True}
    req = {
        "id": str(uuid.uuid4()),
        "occurrence_id": occ_id,
        "occurrence_name": occ.get("name"),
        "starts_at": occ.get("starts_at"),
        "organization_id": occ.get("organization_id"),
        "requested_by_user_id": user["id"],
        "requester_name": user.get("full_name") or user.get("email"),
        "reason": (body.get("reason") or "").strip() or None,
        "status": "open",
        "created_at": _now_iso(),
    }
    await db.cover_requests.insert_one(req)
    await db.class_occurrences.update_one(
        {"id": occ_id},
        {"$set": {"cover_needed": True, "cover_request_id": req["id"]}},
    )
    req.pop("_id", None)
    return {"cover_request": req, "already_open": False}


@router.get("/instructor/cover-board")
async def cover_board(user: dict = Depends(_require_instructor)):
    """Open pickups across my org (excluding my own requests)."""
    reqs = await db.cover_requests.find(
        {"organization_id": user.get("organization_id"),
         "status": "open",
         "requested_by_user_id": {"$ne": user["id"]}},
        {"_id": 0},
    ).sort("starts_at", 1).to_list(100)
    return {"requests": reqs}


@router.post("/instructor/cover/{req_id}/accept")
async def accept_cover(req_id: str, user: dict = Depends(_require_instructor)):
    req = await db.cover_requests.find_one({"id": req_id, "status": "open"}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Cover request not open")
    if req["requested_by_user_id"] == user["id"]:
        raise HTTPException(400, "Can't accept your own request")
    # Flip the occurrence to this instructor and resolve the request
    await db.class_occurrences.update_one(
        {"id": req["occurrence_id"]},
        {"$set": {"instructor_user_id": user["id"],
                  "instructor_name": user.get("full_name") or user.get("email"),
                  "cover_needed": False},
         "$unset": {"cover_request_id": ""}},
    )
    await db.cover_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "accepted",
                  "covered_by_user_id": user["id"],
                  "covered_by_name": user.get("full_name") or user.get("email"),
                  "accepted_at": _now_iso()}},
    )
    return {"ok": True, "occurrence_id": req["occurrence_id"]}


@router.post("/instructor/cover/{req_id}/cancel")
async def cancel_my_cover_request(req_id: str, user: dict = Depends(_require_instructor)):
    """The original instructor changed their mind — cancel the cover request."""
    req = await db.cover_requests.find_one(
        {"id": req_id, "status": "open", "requested_by_user_id": user["id"]}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Cover request not open or not yours")
    await db.cover_requests.update_one({"id": req_id},
        {"$set": {"status": "cancelled", "cancelled_at": _now_iso()}})
    await db.class_occurrences.update_one(
        {"id": req["occurrence_id"]},
        {"$set": {"cover_needed": False}, "$unset": {"cover_request_id": ""}},
    )
    return {"ok": True}


# ═════════════════════ Operator — cover requests oversight ═════════════════════

@router.get("/memberships/cover-requests")
async def ops_cover_requests(user: dict = Depends(get_current_user)):
    """All cover-requests in the operator's org — latest first."""
    org_id = await _require_operator_org(user)
    reqs = await db.cover_requests.find(
        {"organization_id": org_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return {"requests": reqs}
