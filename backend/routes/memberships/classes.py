"""Class templates and the materialise-occurrences worker.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends
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

router = APIRouter(tags=["memberships"])



class ClassTemplateIn(BaseModel):
    name: str
    category: str = "Group"
    description: str | None = None
    site_id: str | None = None
    instructor_user_id: str | None = None
    instructor_id: str | None = None  # iter 215w: membership_instructors.id
    instructor_name: str | None = None
    room_name: str | None = None
    duration_min: int = Field(ge=5, le=240, default=45)
    capacity: int = Field(ge=1, default=20)
    colour: str = "#19CDFF"
    recurs_days: list[int] = Field(default_factory=list)  # 0=Mon ... 6=Sun
    start_time: str = "07:00"  # HH:MM local
    booking_opens_hours_before: int = 168
    cancellation_cutoff_hours_before: int = 12
    waitlist_enabled: bool = True
    max_waitlist: int = 10
    credits_to_book: int = 1
    access_plans: list[str] | None = None
    # Iter 216z — Phase A studio enhancements
    min_age: int | None = Field(default=None, ge=0, le=100)
    max_age: int | None = Field(default=None, ge=0, le=100)
    skill_level: str | None = None  # "beginner" | "intermediate" | "advanced" | free-text
    discipline: str | None = None   # e.g. "Ballet", "Tap" — industry-aware tag
    term_id: str | None = None      # restrict materialisation to a term


@router.get("/memberships/classes/templates", dependencies=[Depends(require_module("memberships"))])
async def class_templates_list(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rows = await db.class_templates.find({"organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0}).sort("name", 1).to_list(200)
    return {"templates": rows}


@router.post("/memberships/classes/templates", dependencies=[Depends(require_module("memberships"))])
async def class_templates_create(body: ClassTemplateIn, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    doc = {"id": _uuid(), "organization_id": org_id, "created_at": _now_iso(), **body.model_dump()}
    await db.class_templates.insert_one(doc)
    # Materialise 8 weeks of occurrences up front.
    await _materialise_occurrences(doc, weeks=8)
    # Iter 215d4 — activation funnel event. Best-effort, never raises.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            org_id, "first_class_scheduled",
            trigger_user_id=user.get("id"),
            payload={"template_id": doc["id"]},
        )
    except Exception:
        pass
    return {"template": {k: v for k, v in doc.items() if k != "_id"}}


@router.patch("/memberships/classes/templates/{tpl_id}", dependencies=[Depends(require_module("memberships"))])
async def class_templates_update(tpl_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    allowed = {"name", "category", "description", "instructor_user_id", "instructor_id", "instructor_name", "room_name",
               "duration_min", "capacity", "colour", "recurs_days", "start_time",
               "booking_opens_hours_before", "cancellation_cutoff_hours_before",
               "waitlist_enabled", "max_waitlist", "credits_to_book", "access_plans",
               "min_age", "max_age", "skill_level", "discipline", "term_id", "site_id"}
    update = {k: v for k, v in body.items() if k in allowed}
    await db.class_templates.update_one({"id": tpl_id, "organization_id": org_id}, {"$set": {**update, "updated_at": _now_iso()}})
    return {"ok": True}


@router.delete("/memberships/classes/templates/{tpl_id}", dependencies=[Depends(require_module("memberships"))])
async def class_templates_archive(tpl_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    _assert_timetable_write(user)
    await db.class_templates.update_one({"id": tpl_id, "organization_id": org_id}, {"$set": {"archived": True}})
    # Cancel any future occurrences
    await db.class_occurrences.update_many(
        {"template_id": tpl_id, "starts_at": {"$gte": _now_iso()}, "status": "scheduled"},
        {"$set": {"status": "cancelled", "cancelled_reason": "template_archived"}},
    )
    return {"ok": True}


async def _materialise_occurrences(template: dict, weeks: int = 8) -> int:
    """Insert scheduled occurrences for `template` over the next `weeks`.

    Iter 216z (Phase A): respect the template's bound term and skip
    dates inside any of its holiday blocks. If no term is bound, we
    fall back to the org-default term when one exists, otherwise we
    materialise the full window unconditionally.
    """
    if not template.get("recurs_days"):
        return 0
    now = datetime.now(timezone.utc)
    try:
        hh, mm = [int(x) for x in (template.get("start_time") or "07:00").split(":", 1)]
    except Exception:
        hh, mm = 7, 0
    duration = int(template.get("duration_min") or 45)
    days_set = set(int(d) for d in template["recurs_days"])
    end_horizon = now + timedelta(weeks=weeks)
    made = 0

    # ── Term + holiday lookup ─────────────────────────────────────
    term = None
    if template.get("term_id"):
        term = await db.membership_terms.find_one(
            {"id": template["term_id"], "organization_id": template["organization_id"]},
            {"_id": 0},
        )
    if not term:
        term = await db.membership_terms.find_one(
            {"organization_id": template["organization_id"],
             "is_default": True, "archived": {"$ne": True}},
            {"_id": 0},
        )
    term_start_iso = term.get("starts_on") if term else None
    term_end_iso = term.get("ends_on") if term else None
    holidays = (term or {}).get("holiday_blocks") or []

    def _in_holiday(d_iso: str) -> bool:
        for h in holidays:
            if h.get("starts_on", "") <= d_iso <= h.get("ends_on", ""):
                return True
        return False

    cursor = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    while cursor < end_horizon:
        d_iso = cursor.strftime("%Y-%m-%d")
        in_term = (
            (term_start_iso is None or d_iso >= term_start_iso)
            and (term_end_iso is None or d_iso <= term_end_iso)
        )
        if cursor.weekday() in days_set and in_term and not _in_holiday(d_iso):
            starts = cursor.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if starts >= now - timedelta(hours=1):
                existing = await db.class_occurrences.find_one({
                    "template_id": template["id"], "starts_at": starts.isoformat(),
                })
                if not existing:
                    occ = {
                        "id": _uuid(),
                        "template_id": template["id"],
                        "organization_id": template["organization_id"],
                        "site_id": template.get("site_id"),
                        "name": template["name"],
                        "colour": template.get("colour", "#19CDFF"),
                        "starts_at": starts.isoformat(),
                        "ends_at": (starts + timedelta(minutes=duration)).isoformat(),
                        "instructor_name": template.get("instructor_name"),
                        "instructor_user_id": template.get("instructor_user_id"),
                        "instructor_id": template.get("instructor_id"),
                        "room_name": template.get("room_name"),
                        "capacity": template.get("capacity", 20),
                        "bookings_count": 0,
                        "waitlist_count": 0,
                        "attended_count": 0,
                        "no_show_count": 0,
                        "status": "scheduled",
                        "created_at": _now_iso(),
                        # Iter 216z — restrictions surfaced for filtering
                        "min_age": template.get("min_age"),
                        "max_age": template.get("max_age"),
                        "skill_level": template.get("skill_level"),
                        "discipline": template.get("discipline"),
                        "term_id": (term or {}).get("id"),
                    }
                    await db.class_occurrences.insert_one(occ)
                    made += 1
        cursor += timedelta(days=1)
    return made


# ═════════════════════ Timetable (operator + member) ═════════════════════
