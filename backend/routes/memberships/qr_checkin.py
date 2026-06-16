"""Rotating-TOTP member QR pass + operator verify endpoint.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _require_operator_org,
    _uuid,
)

router = APIRouter(tags=["memberships"])


@router.get("/member/qr")
async def member_qr(member: dict = Depends(_require_current_member)):
    rec = await db.qr_rotation_secret.find_one({"member_id": member["id"]}, {"_id": 0})
    if not rec:
        # lazy-create
        secret = pyotp.random_base32()
        await db.qr_rotation_secret.insert_one({"member_id": member["id"], "secret_b32": secret, "created_at": _now_iso()})
    else:
        secret = rec["secret_b32"]
    code = pyotp.TOTP(secret).now()
    return {
        "member_id": member["id"],
        "code": code,
        "expires_in": 30 - int(datetime.now(timezone.utc).timestamp()) % 30,
        "payload": f"GXM|{member['id']}|{code}",
    }


class CheckinVerify(BaseModel):
    payload: str
    occurrence_id: str | None = None  # optional — if staff is checking a specific class


@router.post("/memberships/checkin/verify", dependencies=[Depends(require_module("memberships"))])
async def checkin_verify(body: CheckinVerify, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    try:
        prefix, member_id, code = body.payload.split("|", 2)
    except ValueError:
        raise HTTPException(400, "Invalid QR payload")
    if prefix != "GXM":
        raise HTTPException(400, "Not a Pulse Fitness member pass")
    rec = await db.qr_rotation_secret.find_one({"member_id": member_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Unknown member pass")
    if not pyotp.TOTP(rec["secret_b32"]).verify(code, valid_window=1):
        raise HTTPException(401, "Expired code — ask the member to refresh")
    member = await db.members.find_one({"id": member_id, "organization_id": org_id}, {"_id": 0})
    if not member:
        raise HTTPException(404, "Member not on this site")
    # Check-in the occurrence booking if provided & matches
    checked_booking = None
    if body.occurrence_id:
        b = await db.bookings.find_one({"member_id": member_id, "occurrence_id": body.occurrence_id, "status": "booked"}, {"_id": 0})
        if b:
            await db.bookings.update_one({"id": b["id"]}, {"$set": {"status": "attended", "checked_in_at": _now_iso()}})
            await db.class_occurrences.update_one({"id": body.occurrence_id}, {"$inc": {"attended_count": 1}})
            checked_booking = b["id"]
    # Record a raw check-in for audit
    await db.member_checkins.insert_one({
        "id": _uuid(),
        "member_id": member_id,
        "organization_id": org_id,
        "occurrence_id": body.occurrence_id,
        "at": _now_iso(),
        "operator_id": user.get("id"),
    })
    return {
        "ok": True,
        "member": {k: v for k, v in member.items() if k not in {"_id", "password"}},
        "checked_booking_id": checked_booking,
    }
