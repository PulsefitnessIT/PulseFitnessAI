"""Membership plan definitions — operator-side CRUD.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module
from utils.site_scope import build_site_filter, get_requested_site_id, resolve_stamp_site_id
from utils.sites_isolation import get_primary_site_id

from routes.memberships.helpers import (
    _now_iso,
    _require_operator_org,
    _uuid,
)

router = APIRouter(tags=["memberships"])


def _parse_iso_date(s: str) -> date:
    """Parse YYYY-MM-DD or full ISO datetime → a ``date``."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%d").date()


# ═════════════════════ Membership plans (operator) ═════════════════════

class PlanIn(BaseModel):
    name: str
    kind: Literal["recurring", "fixed_term", "class_pack", "payg", "course", "bundle"]
    price_pence: int = Field(ge=0)
    billing_cycle: Literal["monthly", "annual", "oneoff"] = "monthly"
    upfront_fee_pence: int = 0
    duration_days: int | None = None
    credits_count: int | None = None
    included_classes: Literal["unlimited", "limited", "credits_only"] = "unlimited"
    freeze_allowed: bool = True
    freeze_max_days: int = 90
    cancel_notice_days: int = 30
    site_scope: list[str] | Literal["all_sites"] = "all_sites"
    description: str | None = None
    colour: str | None = "#19CDFF"
    display_order: int = 0
    # ── Phase 1: revenue-structure extensions ──────────────────────────
    trial_days: int | None = Field(default=None, ge=0, le=90)
    """Free-trial period (recurring plans only). Member checkouts pass this
    to Stripe via subscription_data.trial_period_days; Stripe takes care of
    delaying the first invoice and our existing webhook handles conversion."""

    pt_credits_count: int | None = Field(default=None, ge=0)
    """Hybrid bundles — PT (or alt) credits granted ALONGSIDE class credits.
    Stored on member_memberships.pt_credits_remaining. Bookings against
    PT-only sessions decrement this pool; class bookings decrement
    credits_remaining."""

    pack_expiry_days: int | None = Field(default=None, ge=1, le=730)
    """For class_pack: credits expire N days after the pack is activated.
    The booking flow rejects bookings against expired packs."""

    course_template_id: str | None = None
    """For kind=course: the class_template the course is built from."""

    course_session_count: int | None = Field(default=None, ge=1, le=104)
    """For kind=course: total number of weekly sessions (e.g. 8 for an
    8-week beginners course)."""

    course_start_date: str | None = None
    """For kind=course: ISO date the first session runs (used to
    materialise the N occurrences when the plan is created)."""

    course_occurrence_ids: list[str] | None = None
    """Populated by the backend after course creation — the actual
    materialised occurrence ids. Bookings get auto-created against these
    on successful payment."""

    course_excluded_dates: list[str] = Field(default_factory=list)
    """Iter 215x — ISO date strings (YYYY-MM-DD) to skip when
    materialising a course. Perfect for school holidays / bank
    holidays so the studio doesn't have to cancel sessions one by one.
    Each excluded date pushes the session count outwards by one week."""

    # Iter 215s — Pro-rata / "smoothed" billing. When set, the monthly
    # pence is (annual / months) regardless of term/holiday cadence.
    # Gives members a predictable fixed monthly debit — standard in UK
    # swim schools and dance academies.
    smoothed: bool = False
    """When true, Stripe is invoiced at (smoothed_annual / smoothed_months)
    per month instead of `price_pence` per month."""

    smoothed_annual_pence: int | None = Field(default=None, ge=0)
    """Total the member pays across the year (e.g. 52 * weekly_class * rate)."""

    smoothed_months: int = Field(default=12, ge=1, le=24)
    """Number of months the annual total is spread across (default 12)."""

    per_class_pence: int | None = Field(default=None, ge=0)
    """Optional: per-class rate used when billing monthly class invoices
    for members on this plan. Falls back to the studio's cheapest
    `payg` plan price, then £10, if unset."""

    # Iter 215r — Waivers / PARQ.
    waiver_required: bool = False
    """When True, members must sign `waiver_text` before their first
    booking on this plan. Dance schools, youth classes, wellness
    coaches typically need this."""

    waiver_text: str | None = None
    """Markdown-lite waiver / PARQ text shown to the member on checkout
    and in their portal. Changes to this text invalidate prior
    signatures (we store a text hash) so re-signature is required."""


@router.get("/memberships/plans", dependencies=[Depends(require_module("memberships"))])
async def plans_list(
    site_id: str | None = Depends(get_requested_site_id),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    plans = await db.membership_plans.find(
        {"organization_id": org_id, "archived": {"$ne": True}, **build_site_filter(site_id)},
        {"_id": 0},
    ).sort("display_order", 1).to_list(200)
    return {"plans": plans}


@router.post("/memberships/plans", dependencies=[Depends(require_module("memberships"))])
async def plans_create(
    body: PlanIn,
    site_id: str | None = Depends(get_requested_site_id),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    payload = body.model_dump()
    payload["site_id"] = resolve_stamp_site_id(payload.get("site_id") or site_id, await get_primary_site_id(org_id))

    # ── kind=course: materialise the N weekly occurrences from the
    # supplied template + start date so we have concrete bookable slots
    # to enrol paying members into.
    if payload.get("kind") == "course":
        tpl_id = payload.get("course_template_id")
        n_sessions = int(payload.get("course_session_count") or 0)
        start_iso = (payload.get("course_start_date") or "").strip()
        if not tpl_id or n_sessions < 1 or not start_iso:
            raise HTTPException(
                400,
                "Course plans require course_template_id, course_session_count "
                "and course_start_date (ISO date).",
            )
        tpl = await db.class_templates.find_one(
            {"id": tpl_id, "organization_id": org_id, "archived": {"$ne": True}},
            {"_id": 0},
        )
        if not tpl:
            raise HTTPException(404, "Course template not found")
        try:
            start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        except Exception as exc:
            raise HTTPException(400, f"Invalid course_start_date: {exc}") from exc
        # Iter 215x — ensure timezone awareness so downstream date math is
        # safe (the Mongo records are compared against tz-aware `datetime`s
        # in the invoicing / timetable code).
        if start.tzinfo is None:
            from datetime import timezone as _tz
            start = start.replace(tzinfo=_tz.utc)
        # Iter 215x — skip excluded dates (school/bank holidays). Each
        # skipped week pushes the final session forward by 7 days, so a
        # 10-session course with 2 holidays covers 12 calendar weeks.
        excluded = {
            _parse_iso_date(d) for d in (payload.get("course_excluded_dates") or [])
        }
        occ_ids: list[str] = []
        h, m = (tpl.get("start_time") or "07:00").split(":")
        i = 0
        sessions_booked = 0
        max_weeks = n_sessions + len(excluded) + 4  # safety stop
        while sessions_booked < n_sessions and i < max_weeks:
            candidate = (start + timedelta(weeks=i)).replace(
                hour=int(h), minute=int(m), second=0, microsecond=0,
            )
            if candidate.date() in excluded:
                i += 1
                continue
            occ_ends = candidate + timedelta(minutes=int(tpl.get("duration_min") or 45))
            occ_id = _uuid()
            await db.class_occurrences.insert_one({
                "id": occ_id,
                "organization_id": org_id,
                "template_id": tpl_id,
                "site_id": tpl.get("site_id"),
                "starts_at": candidate.isoformat(),
                "ends_at": occ_ends.isoformat(),
                "capacity": int(tpl.get("capacity") or 20),
                "bookings_count": 0,
                "waitlist_count": 0,
                "status": "scheduled",
                "is_course_session": True,
                "course_session_index": sessions_booked + 1,
                "course_session_total": n_sessions,
                "instructor_id": tpl.get("instructor_id"),
                "instructor_user_id": tpl.get("instructor_user_id"),
                "instructor_name": tpl.get("instructor_name"),
                "room_name": tpl.get("room_name"),
                "name": tpl.get("name"),
            })
            occ_ids.append(occ_id)
            sessions_booked += 1
            i += 1
        payload["course_occurrence_ids"] = occ_ids

    doc = {"id": _uuid(), "organization_id": org_id, "active": True,
           "created_at": _now_iso(), **payload}
    await db.membership_plans.insert_one(doc)
    return {"plan": {k: v for k, v in doc.items() if k != "_id"}}


@router.patch("/memberships/plans/{plan_id}", dependencies=[Depends(require_module("memberships"))])
async def plans_update(plan_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    allowed = {"name", "price_pence", "billing_cycle", "upfront_fee_pence", "duration_days",
               "credits_count", "included_classes", "freeze_allowed", "freeze_max_days",
               "cancel_notice_days", "description", "colour", "display_order", "active", "site_scope",
               "trial_days", "pt_credits_count", "pack_expiry_days",
               "course_template_id", "course_session_count", "course_start_date",
               "course_occurrence_ids", "course_excluded_dates",
               "smoothed", "smoothed_annual_pence", "smoothed_months", "per_class_pence",
               "waiver_required", "waiver_text"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(400, "No allowed fields supplied")
    await db.membership_plans.update_one(
        {"id": plan_id, "organization_id": org_id},
        {"$set": {**update, "updated_at": _now_iso()}},
    )
    return {"ok": True}


@router.delete("/memberships/plans/{plan_id}", dependencies=[Depends(require_module("memberships"))])
async def plans_archive(plan_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    await db.membership_plans.update_one(
        {"id": plan_id, "organization_id": org_id},
        {"$set": {"archived": True, "active": False, "archived_at": _now_iso()}},
    )
    return {"ok": True}


# ═════════════════════ Course enrolment (iter 215x) ═════════════════════

class EnrolIn(BaseModel):
    member_ids: list[str] = Field(min_length=1)
    """Pupils to enrol in this course. Each one will be booked into
    every materialised occurrence."""


@router.post(
    "/memberships/plans/{plan_id}/enrol",
    dependencies=[Depends(require_module("memberships"))],
)
async def enrol_members_in_course(
    plan_id: str, body: EnrolIn, user: dict = Depends(get_current_user),
):
    """Bulk-enrol members into a course plan.

    For each pupil × each materialised occurrence we create a
    `bookings` row with `status='booked'`, `source='course_enrolment'`.
    Existing bookings (e.g. pupil already enrolled) are left alone —
    the operator can safely re-run this to add latecomers.

    If the plan is *smoothed*, we also stamp a `member_memberships` row
    so the monthly invoice generator picks up the installment line.
    """
    org_id = await _require_operator_org(user)
    plan = await db.membership_plans.find_one(
        {"id": plan_id, "organization_id": org_id}, {"_id": 0},
    )
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan.get("kind") != "course":
        raise HTTPException(400, "Not a course plan")
    occ_ids = plan.get("course_occurrence_ids") or []
    if not occ_ids:
        raise HTTPException(400, "Course has no materialised sessions yet")

    # Guard: members must belong to the operator's org.
    members = await db.members.find(
        {"id": {"$in": body.member_ids}, "organization_id": org_id},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    ).to_list(len(body.member_ids))
    if len(members) != len(body.member_ids):
        found = {m["id"] for m in members}
        missing = [i for i in body.member_ids if i not in found]
        raise HTTPException(400, f"Unknown member ids: {missing}")

    bookings_created = 0
    bookings_skipped = 0
    memberships_created = 0

    for m in members:
        # Stamp the smoothed membership row so monthly invoicing picks up
        # the installment line. Non-smoothed courses are billed upfront
        # through the plan's price_pence (handled at checkout); we don't
        # need a membership row for those.
        if plan.get("smoothed"):
            existing = await db.member_memberships.find_one(
                {"organization_id": org_id, "member_id": m["id"],
                 "plan_id": plan_id, "status": "active"},
                {"_id": 0},
            )
            if not existing:
                await db.member_memberships.insert_one({
                    "id": _uuid(),
                    "organization_id": org_id,
                    "member_id": m["id"],
                    "plan_id": plan_id,
                    "status": "active",
                    "source": "course_enrolment",
                    "started_at": _now_iso(),
                    "created_at": _now_iso(),
                })
                memberships_created += 1

        # Materialise bookings across every session (deduplicate against
        # the existing state so re-running is idempotent).
        existing_bookings = {
            b["occurrence_id"] for b in await db.bookings.find(
                {"organization_id": org_id, "member_id": m["id"],
                 "occurrence_id": {"$in": occ_ids},
                 "status": {"$in": ["booked", "attended", "waitlist"]}},
                {"_id": 0, "occurrence_id": 1},
            ).to_list(len(occ_ids))
        }
        for occ_id in occ_ids:
            if occ_id in existing_bookings:
                bookings_skipped += 1
                continue
            await db.bookings.insert_one({
                "id": _uuid(),
                "organization_id": org_id,
                "member_id": m["id"],
                "occurrence_id": occ_id,
                "status": "booked",
                "credits_charged": 0,
                "source": "course_enrolment",
                "plan_id": plan_id,
                "created_at": _now_iso(),
                "booked_at": _now_iso(),
            })
            bookings_created += 1
        # Update occurrence bookings_count reactively.
        for occ_id in occ_ids:
            await db.class_occurrences.update_one(
                {"id": occ_id},
                [{"$set": {"bookings_count": {
                    "$add": [{"$ifNull": ["$bookings_count", 0]},
                             0 if occ_id in existing_bookings else 1]}}}],
            )

    return {
        "ok": True,
        "enrolled_member_count": len(members),
        "bookings_created": bookings_created,
        "bookings_skipped_already_enrolled": bookings_skipped,
        "smoothed_memberships_created": memberships_created,
        "course_sessions": len(occ_ids),
    }


@router.get(
    "/memberships/plans/{plan_id}/enrolments",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_course_enrolments(plan_id: str, user: dict = Depends(get_current_user)):
    """Show the roster of pupils enrolled in a course plus a
    materialised-session summary."""
    org_id = await _require_operator_org(user)
    plan = await db.membership_plans.find_one(
        {"id": plan_id, "organization_id": org_id}, {"_id": 0},
    )
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan.get("kind") != "course":
        raise HTTPException(400, "Not a course plan")
    occ_ids = plan.get("course_occurrence_ids") or []

    occs = await db.class_occurrences.find(
        {"id": {"$in": occ_ids}},
        {"_id": 0, "id": 1, "starts_at": 1, "ends_at": 1,
         "bookings_count": 1, "capacity": 1, "course_session_index": 1},
    ).sort("starts_at", 1).to_list(len(occ_ids) + 1)

    # Distinct pupils with at least one course booking.
    member_ids = await db.bookings.distinct(
        "member_id",
        {"organization_id": org_id, "occurrence_id": {"$in": occ_ids},
         "status": {"$in": ["booked", "attended"]},
         "source": "course_enrolment"},
    )
    pupils = await db.members.find(
        {"id": {"$in": member_ids}},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    ).to_list(len(member_ids) + 1)

    return {
        "plan_id": plan_id,
        "sessions": occs,
        "enrolled": pupils,
        "pupil_count": len(pupils),
        "smoothed": bool(plan.get("smoothed")),
    }


@router.delete(
    "/memberships/plans/{plan_id}/enrolments/{member_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def unenrol_member_from_course(
    plan_id: str, member_id: str, user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    plan = await db.membership_plans.find_one(
        {"id": plan_id, "organization_id": org_id}, {"_id": 0},
    )
    if not plan or plan.get("kind") != "course":
        raise HTTPException(404, "Course not found")
    occ_ids = plan.get("course_occurrence_ids") or []
    # Cancel the member's course bookings for this plan (don't touch
    # attended historic rows).
    res = await db.bookings.update_many(
        {"organization_id": org_id, "member_id": member_id,
         "occurrence_id": {"$in": occ_ids},
         "status": "booked", "source": "course_enrolment"},
        {"$set": {"status": "cancelled", "cancelled_at": _now_iso()}},
    )
    # Decrement bookings_count on each affected occurrence so capacity
    # stays accurate.
    if res.modified_count:
        await db.class_occurrences.update_many(
            {"id": {"$in": occ_ids}},
            [{"$set": {"bookings_count": {
                "$max": [{"$subtract": [{"$ifNull": ["$bookings_count", 0]}, 1]}, 0],
            }}}],
        )
    await db.member_memberships.update_many(
        {"organization_id": org_id, "member_id": member_id,
         "plan_id": plan_id, "status": "active",
         "source": "course_enrolment"},
        {"$set": {"status": "cancelled", "cancelled_at": _now_iso()}},
    )
    return {"ok": True, "bookings_cancelled": res.modified_count}
