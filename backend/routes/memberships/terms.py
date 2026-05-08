"""Terms, seasons & holiday blocks for studio operators.

Iter 216z — Phase A (Studio Identity & Term/Season Engine).

A *term* is a continuous teaching window (e.g. "Autumn Term 2026") with
optional *holiday blocks* during which classes auto-pause. The
materialise-occurrences worker in `classes.py` consults the active term
to skip dates inside any holiday block, so an operator can configure
half-term weeks once and never manually cancel a row again.

Endpoints:

  GET    /api/memberships/terms
  POST   /api/memberships/terms
  PUT    /api/memberships/terms/{term_id}
  DELETE /api/memberships/terms/{term_id}
  POST   /api/memberships/terms/{term_id}/holidays
  DELETE /api/memberships/terms/{term_id}/holidays/{block_id}

  POST   /api/memberships/terms/rematerialise   — rebuild all occurrences
                                                   from active templates
                                                   inside the active term,
                                                   honouring holidays.

Industry presets (consumed by the frontend wizard) are seeded the first
time a studio chooses an industry (see `studio.py`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _assert_timetable_write,
    _now_iso,
    _require_operator_org,
    _uuid,
)

router = APIRouter(tags=["memberships-terms"])


class HolidayBlockIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    starts_on: str  # YYYY-MM-DD
    ends_on: str    # YYYY-MM-DD inclusive


class TermIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    starts_on: str  # YYYY-MM-DD
    ends_on: str    # YYYY-MM-DD inclusive
    colour: str = "#0055ff"
    holiday_blocks: List[HolidayBlockIn] = Field(default_factory=list)
    is_default: bool = False
    notes: Optional[str] = None


def _validate_iso_date(s: str) -> str:
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid date {s!r} — expected YYYY-MM-DD") from exc
    return s


def _validate_term(body: TermIn) -> dict:
    starts = _validate_iso_date(body.starts_on)
    ends = _validate_iso_date(body.ends_on)
    if starts > ends:
        raise HTTPException(400, "Term start must be on or before end")
    blocks = []
    for h in body.holiday_blocks or []:
        hs = _validate_iso_date(h.starts_on)
        he = _validate_iso_date(h.ends_on)
        if hs > he:
            raise HTTPException(400, f"Holiday {h.name!r}: start must be on or before end")
        if hs < starts or he > ends:
            raise HTTPException(400, f"Holiday {h.name!r} must lie inside the term window")
        blocks.append({
            "id": _uuid(),
            "name": h.name.strip(),
            "starts_on": hs,
            "ends_on": he,
        })
    return {
        "name": body.name.strip(),
        "starts_on": starts,
        "ends_on": ends,
        "colour": body.colour or "#0055ff",
        "holiday_blocks": blocks,
        "is_default": bool(body.is_default),
        "notes": (body.notes or "").strip(),
    }


@router.get("/memberships/terms", dependencies=[Depends(require_module("memberships"))])
async def list_terms(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rows = await db.membership_terms.find(
        {"organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    ).sort("starts_on", 1).to_list(100)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active = next((r for r in rows if r["starts_on"] <= today <= r["ends_on"]), None)
    return {"terms": rows, "count": len(rows), "active_term_id": (active or {}).get("id")}


@router.post("/memberships/terms", dependencies=[Depends(require_module("memberships"))])
async def create_term(body: TermIn, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    valid = _validate_term(body)
    if valid["is_default"]:
        await db.membership_terms.update_many(
            {"organization_id": org_id}, {"$set": {"is_default": False}},
        )
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        **valid,
        "created_at": _now_iso(),
        "created_by_id": user.get("id"),
        "updated_at": _now_iso(),
    }
    await db.membership_terms.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/memberships/terms/{term_id}", dependencies=[Depends(require_module("memberships"))])
async def update_term(
    term_id: str,
    body: TermIn = Body(...),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    valid = _validate_term(body)
    if valid["is_default"]:
        await db.membership_terms.update_many(
            {"organization_id": org_id, "id": {"$ne": term_id}},
            {"$set": {"is_default": False}},
        )
    res = await db.membership_terms.update_one(
        {"organization_id": org_id, "id": term_id},
        {"$set": {**valid, "updated_at": _now_iso(), "updated_by_id": user.get("id")}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Term not found")
    row = await db.membership_terms.find_one({"id": term_id}, {"_id": 0})
    return row


@router.delete(
    "/memberships/terms/{term_id}", dependencies=[Depends(require_module("memberships"))],
)
async def archive_term(term_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    res = await db.membership_terms.update_one(
        {"organization_id": org_id, "id": term_id},
        {"$set": {"archived": True, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Term not found")
    return {"ok": True, "id": term_id}


@router.post(
    "/memberships/terms/{term_id}/holidays",
    dependencies=[Depends(require_module("memberships"))],
)
async def add_holiday_block(
    term_id: str,
    body: HolidayBlockIn = Body(...),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    term = await db.membership_terms.find_one({"id": term_id, "organization_id": org_id})
    if not term:
        raise HTTPException(404, "Term not found")
    hs = _validate_iso_date(body.starts_on)
    he = _validate_iso_date(body.ends_on)
    if hs > he:
        raise HTTPException(400, "Holiday start must be on or before end")
    if hs < term["starts_on"] or he > term["ends_on"]:
        raise HTTPException(400, "Holiday must lie inside the term window")
    block = {"id": _uuid(), "name": body.name.strip(), "starts_on": hs, "ends_on": he}
    await db.membership_terms.update_one(
        {"id": term_id, "organization_id": org_id},
        {"$push": {"holiday_blocks": block}, "$set": {"updated_at": _now_iso()}},
    )
    return block


@router.delete(
    "/memberships/terms/{term_id}/holidays/{block_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def remove_holiday_block(
    term_id: str, block_id: str, user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    res = await db.membership_terms.update_one(
        {"id": term_id, "organization_id": org_id},
        {"$pull": {"holiday_blocks": {"id": block_id}},
         "$set": {"updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Term not found")
    return {"ok": True, "id": block_id}


@router.post(
    "/memberships/terms/rematerialise",
    dependencies=[Depends(require_module("memberships"))],
)
async def rematerialise_active_term(user: dict = Depends(get_current_user)):
    """Drop all *future* scheduled occurrences and rebuild from active
    templates inside the currently-active term, honouring holiday blocks.

    Bookings on already-booked occurrences are preserved by skipping any
    occurrence whose ``bookings_count`` > 0.
    """
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    term = await db.membership_terms.find_one(
        {"organization_id": org_id, "archived": {"$ne": True},
         "starts_on": {"$lte": today}, "ends_on": {"$gte": today}},
        sort=[("starts_on", 1)],
    )
    if not term:
        raise HTTPException(409, "No active term — set a default term first")

    # Drop empty future occurrences only.
    await db.class_occurrences.delete_many({
        "organization_id": org_id,
        "starts_at": {"$gte": _now_iso()},
        "status": "scheduled",
        "bookings_count": {"$lte": 0},
    })

    from routes.memberships.classes import _materialise_occurrences  # avoid cycle

    templates = await db.class_templates.find(
        {"organization_id": org_id, "archived": {"$ne": True}},
    ).to_list(500)
    weeks = max(
        1,
        (datetime.strptime(term["ends_on"], "%Y-%m-%d") - datetime.utcnow()).days // 7 + 2,
    )
    total = 0
    for tpl in templates:
        total += await _materialise_occurrences(tpl, weeks=weeks)
    return {"ok": True, "term_id": term["id"], "occurrences_made": total}


__all__ = ["router"]
