"""Operator-side timetable: list, cancel an occurrence, roster lookup.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module
from utils.memberships_emails import (
    send_class_cancelled,
)

from routes.memberships.helpers import (
    _assert_timetable_write,
    _now_iso,
    _require_operator_org,
)

router = APIRouter(tags=["memberships"])



@router.get("/memberships/timetable", dependencies=[Depends(require_module("memberships"))])
async def timetable(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    site: str | None = None,
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    frm = from_ or datetime.now(timezone.utc).isoformat()
    toh = to or (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    q = {"organization_id": org_id, "starts_at": {"$gte": frm, "$lte": toh}}
    if site:
        q["site_id"] = site
    occs = await db.class_occurrences.find(q, {"_id": 0}).sort("starts_at", 1).to_list(500)
    return {"occurrences": occs}


@router.post("/memberships/classes/{occ_id}/cancel", dependencies=[Depends(require_module("memberships"))])
async def occurrence_cancel(occ_id: str, body: dict = Body(default={}), background: BackgroundTasks = None, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    occ = await db.class_occurrences.find_one({"id": occ_id, "organization_id": org_id}, {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found")
    reason = body.get("reason", "operator")
    # Capture booked members BEFORE we flip their status so we can email them.
    booked_members: list[dict] = []
    async for b in db.bookings.find({"occurrence_id": occ_id, "status": "booked"}, {"_id": 0, "member_id": 1}):
        mem = await db.members.find_one({"id": b["member_id"]}, {"_id": 0, "password": 0})
        if mem:
            booked_members.append(mem)
    await db.class_occurrences.update_one({"id": occ_id}, {"$set": {"status": "cancelled", "cancelled_reason": reason}})
    # Refund all bookings (credits return, status cancelled)
    await db.bookings.update_many({"occurrence_id": occ_id, "status": {"$in": ["booked", "waitlist"]}},
                                   {"$set": {"status": "cancelled", "cancelled_at": _now_iso(), "cancelled_reason": "class_cancelled"}})
    # Refund credits for booked bookings
    async for b in db.bookings.find({"occurrence_id": occ_id, "credits_charged": {"$gt": 0}}, {"_id": 0, "member_id": 1, "credits_charged": 1}):
        await db.member_memberships.update_one(
            {"member_id": b["member_id"], "status": {"$in": ["active", "frozen"]}},
            {"$inc": {"credits_remaining": b["credits_charged"], "credits_used": -b["credits_charged"]}},
        )
    if background is not None:
        for mem in booked_members:
            background.add_task(send_class_cancelled, mem, occ, reason)
    return {"ok": True, "notified": len(booked_members)}


@router.get("/memberships/occurrences/{occ_id}/roster", dependencies=[Depends(require_module("memberships"))])
async def occurrence_roster(occ_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    occ = await db.class_occurrences.find_one({"id": occ_id, "organization_id": org_id}, {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found")
    bookings = await db.bookings.find({"occurrence_id": occ_id}, {"_id": 0}).to_list(200)
    for b in bookings:
        mem = await db.members.find_one({"id": b["member_id"]}, {"_id": 0, "first_name": 1, "last_name": 1, "email": 1, "phone": 1, "no_show_count": 1})
        b["member"] = mem
    return {"occurrence": occ, "bookings": bookings}
