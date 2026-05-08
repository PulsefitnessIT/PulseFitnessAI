"""GymAxis Memberships — Phase 3 operator endpoints.

Four capabilities live here:

1. Class announcements — operator broadcasts a message to every booked
   attendee of a single occurrence (email + in-app inbox).

2. Operator-side manual attendance — front-desk staff with the
   memberships module access can mark attendance / no-show even when
   they aren't the assigned instructor.

3. Instructor performance dashboard — per-instructor 30/90 day
   aggregates: classes taught, avg fill rate, attendance rate, no-show
   rate, total revenue impact (capacity × £-per-class proxy).

4. Cover-requests admin — assign a cover request to a specific
   instructor (rather than waiting for someone to claim it).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-phase3"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


# ───────────────────────── Class announcements ─────────────────────────


class AnnouncementIn(BaseModel):
    message: str = Field(min_length=2, max_length=1500)
    title: str = Field(default="", max_length=120)
    """Optional headline. If blank we use 'Update from {gym_name}'."""

    channels: list[str] = Field(default_factory=lambda: ["email", "in_app"])
    """Subset of {'email', 'in_app'}. Other channels reserved for Phase 4."""


@router.post(
    "/memberships/occurrences/{occ_id}/announce",
    dependencies=[Depends(require_module("memberships"))],
)
async def announce_to_class(
    occ_id: str, body: AnnouncementIn,
    background: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Broadcast a message to every booked attendee of one class.

    Use cases:
      • "Tonight's class moved to Studio B"
      • "Bring water — heatwave"
      • "Substitute instructor: Jamie taking over from Sam"

    Sends to attendees with status in {booked, attended, waitlist}.
    Returns: { sent_count, channel_breakdown }
    """
    org_id = await _require_operator_org(user)
    occ = await db.class_occurrences.find_one(
        {"id": occ_id, "organization_id": org_id}, {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class not found")
    if not body.message.strip():
        raise HTTPException(400, "message is required")

    bookings = await db.bookings.find(
        {"occurrence_id": occ_id, "organization_id": org_id,
         "status": {"$in": ["booked", "waitlist", "attended"]}},
        {"_id": 0, "member_id": 1, "attendee_email": 1, "id": 1},
    ).to_list(500)
    if not bookings:
        return {"sent_count": 0, "channel_breakdown": {}}
    member_ids = list({b["member_id"] for b in bookings})
    members = {m["id"]: m for m in await db.members.find(
        {"id": {"$in": member_ids}, "organization_id": org_id},
        {"_id": 0, "id": 1, "first_name": 1, "email": 1},
    ).to_list(500)}

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1, "primary_color": 1},
    ) or {}
    org_name = org.get("name") or "your gym"
    title = body.title.strip() or f"Update from {org_name}"
    tpl = await db.class_templates.find_one(
        {"id": occ.get("template_id")}, {"_id": 0, "name": 1},
    ) or {}
    class_name = tpl.get("name") or "your class"
    starts_h = ""
    if occ.get("starts_at"):
        try:
            starts_h = datetime.fromisoformat(
                occ["starts_at"].replace("Z", "+00:00"),
            ).astimezone().strftime("%a %d %b · %H:%M")
        except Exception:
            starts_h = occ.get("starts_at") or ""

    # Persist the announcement so the operator audit trail / analytics
    # can show what was sent and to whom.
    ann_id = str(uuid.uuid4())
    ann_doc = {
        "id": ann_id,
        "organization_id": org_id,
        "occurrence_id": occ_id,
        "class_name": class_name,
        "title": title,
        "message": body.message.strip(),
        "channels": [c for c in (body.channels or []) if c in ("email", "in_app")],
        "sent_by": user.get("id"),
        "sent_at": _now_iso(),
        "recipient_count": len(member_ids),
    }
    await db.class_announcements.insert_one(ann_doc)

    # In-app inbox is fast and reliable; email is best-effort.
    in_app_count = 0
    if "in_app" in ann_doc["channels"]:
        for mid in member_ids:
            await db.member_inbox.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "member_id": mid,
                "kind": "class_announcement",
                "title": title,
                "body": f"{class_name} · {starts_h}\n\n{body.message.strip()}",
                "occurrence_id": occ_id,
                "announcement_id": ann_id,
                "read": False,
                "created_at": _now_iso(),
            })
            in_app_count += 1

    email_count = 0
    if "email" in ann_doc["channels"]:
        primary_color = org.get("primary_color") or "#0055FF"
        for mid in member_ids:
            m = members.get(mid)
            if not m or not m.get("email"):
                continue
            first = m.get("first_name") or "there"
            html = (
                f'<div style="font-family:system-ui,-apple-system,Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px;">'
                f'<p style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:{primary_color};font-weight:800;margin:0 0 6px;">'
                f'{org_name}'
                f'</p>'
                f'<h2 style="margin:0 0 12px;font-size:22px;color:#0a0c10;">{title}</h2>'
                f'<p style="font-size:14px;color:#444;margin:0 0 6px;">Hi {first},</p>'
                f'<p style="font-size:14px;color:#444;margin:0 0 16px;">'
                f'Quick update about your <strong>{class_name}</strong> ({starts_h}):'
                f'</p>'
                f'<div style="border-left:3px solid {primary_color};padding:12px 16px;background:#f6f8fb;border-radius:6px;margin-bottom:18px;">'
                f'<p style="margin:0;color:#1a1f2e;font-size:14px;line-height:1.5;white-space:pre-wrap;">'
                f'{_html_safe(body.message)}</p>'
                f'</div>'
                f'<p style="font-size:12px;color:#94a3b8;margin:0;">See you there,<br/>{org_name}</p>'
                f'</div>'
            )
            background.add_task(send_email, m["email"], f"{class_name} · {title}", html)
            email_count += 1

    return {
        "sent_count": len(member_ids),
        "channel_breakdown": {
            "in_app": in_app_count, "email": email_count,
        },
        "announcement_id": ann_id,
    }


def _html_safe(s: str) -> str:
    """Minimal HTML escape — enough for the announcement template above."""
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


@router.get(
    "/memberships/occurrences/{occ_id}/announcements",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_announcements(
    occ_id: str, user: dict = Depends(get_current_user),
):
    """All past announcements for one occurrence — drives the audit
    log on the class detail screen."""
    org_id = await _require_operator_org(user)
    rows = await db.class_announcements.find(
        {"occurrence_id": occ_id, "organization_id": org_id},
        {"_id": 0},
    ).sort("sent_at", -1).to_list(50)
    return {"announcements": rows, "count": len(rows)}


# ───────────────────────── Operator manual attendance ─────────────────────────


class OperatorAttendanceItem(BaseModel):
    booking_id: str
    status: str  # 'attended' | 'no_show' | 'late_cancel'


@router.post(
    "/memberships/occurrences/{occ_id}/attendance",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_mark_attendance(
    occ_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Operator-side attendance marker — used by reception / managers.

    Mirrors the instructor endpoint but doesn't require the caller to
    be the assigned instructor. Behaviour is otherwise identical:
    updates booking statuses, snapshots counts on the occurrence,
    bumps `member.no_show_count` for no-shows.

    Body: { items: [{booking_id, status}] }
    """
    org_id = await _require_operator_org(user)
    occ = await db.class_occurrences.find_one(
        {"id": occ_id, "organization_id": org_id}, {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class not found")
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "items[] required")
    valid_statuses = {"attended", "no_show", "late_cancel"}
    attended = no_show = late = 0
    no_show_member_ids: list[str] = []

    for it in items:
        bid = it.get("booking_id")
        status = it.get("status")
        if not bid or status not in valid_statuses:
            continue
        bk = await db.bookings.find_one(
            {"id": bid, "occurrence_id": occ_id, "organization_id": org_id},
            {"_id": 0, "member_id": 1, "status": 1},
        )
        if not bk:
            continue
        await db.bookings.update_one(
            {"id": bid},
            {"$set": {"status": status, "marked_by": user["id"],
                      "marked_at": _now_iso(),
                      "marked_via": "operator_console"}},
        )
        if status == "attended":
            attended += 1
        elif status == "no_show":
            no_show += 1
            if bk.get("status") != "no_show":
                no_show_member_ids.append(bk["member_id"])
        else:
            late += 1
    attended_total = await db.bookings.count_documents(
        {"occurrence_id": occ_id, "status": "attended"},
    )
    no_show_total = await db.bookings.count_documents(
        {"occurrence_id": occ_id, "status": "no_show"},
    )
    await db.class_occurrences.update_one(
        {"id": occ_id},
        {"$set": {
            "attended_count": attended_total,
            "no_show_count": no_show_total,
            "status": "completed",
            "completed_at": _now_iso(),
            "completed_by": user["id"],
            "completed_via": "operator_console",
        }},
    )
    if no_show_member_ids:
        await db.members.update_many(
            {"id": {"$in": no_show_member_ids}},
            {"$inc": {"no_show_count": 1}},
        )
    return {
        "ok": True,
        "attended_added": attended, "no_show_added": no_show,
        "late_cancel_added": late,
        "totals": {"attended": attended_total, "no_show": no_show_total},
    }


# ───────────────────────── Instructor performance ─────────────────────────


@router.get(
    "/memberships/instructors/performance",
    dependencies=[Depends(require_module("memberships"))],
)
async def instructor_performance(
    days: int = 30,
    user: dict = Depends(get_current_user),
):
    """Operator-only — per-instructor stats over the last `days` days.
    Returns one row per instructor with class count, attendance, fill
    rate, and pay due (commission). Sorted by fill rate desc so the top
    performers surface immediately."""
    org_id = await _require_operator_org(user)
    days = max(7, min(int(days or 30), 365))
    since_iso = (datetime.now(timezone.utc)
                 - timedelta(days=days)).isoformat()

    occs = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": since_iso},
         "instructor_user_id": {"$exists": True, "$ne": None}},
        {"_id": 0, "id": 1, "instructor_user_id": 1, "instructor_name": 1,
         "capacity": 1, "bookings_count": 1, "waitlist_count": 1,
         "attended_count": 1, "no_show_count": 1, "status": 1,
         "template_id": 1, "starts_at": 1},
    ).to_list(2000)

    # Pay-rate lookup — first try template-level, fall back to user-level
    tpl_ids = list({o.get("template_id") for o in occs if o.get("template_id")})
    tpl_rates: dict[str, int] = {}
    if tpl_ids:
        async for tpl in db.class_templates.find(
            {"id": {"$in": tpl_ids}, "instructor_rate_pence": {"$exists": True}},
            {"_id": 0, "id": 1, "instructor_rate_pence": 1},
        ):
            tpl_rates[tpl["id"]] = int(tpl.get("instructor_rate_pence") or 0)
    user_ids = list({o["instructor_user_id"] for o in occs if o.get("instructor_user_id")})
    user_rates: dict[str, int] = {}
    user_meta: dict[str, dict] = {}
    if user_ids:
        async for u in db.users.find(
            {"id": {"$in": user_ids}},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1,
             "avatar_url": 1, "instructor_rate_pence": 1},
        ):
            user_rates[u["id"]] = int(u.get("instructor_rate_pence") or 0)
            user_meta[u["id"]] = u

    # Aggregate per instructor
    agg: dict[str, dict] = {}
    for o in occs:
        iid = o["instructor_user_id"]
        a = agg.setdefault(iid, {
            "instructor_user_id": iid,
            "name": (o.get("instructor_name") or
                     ((user_meta.get(iid) or {}).get("first_name", "") + " "
                      + (user_meta.get(iid) or {}).get("last_name", "")).strip()
                     or (user_meta.get(iid) or {}).get("email") or "Instructor"),
            "email": (user_meta.get(iid) or {}).get("email"),
            "avatar_url": (user_meta.get(iid) or {}).get("avatar_url"),
            "classes_total": 0,
            "classes_completed": 0,
            "classes_cancelled": 0,
            "capacity_sum": 0,
            "bookings_sum": 0,
            "waitlist_sum": 0,
            "attended_sum": 0,
            "no_show_sum": 0,
            "pay_due_pence": 0,
        })
        a["classes_total"] += 1
        if o.get("status") == "completed":
            a["classes_completed"] += 1
            rate = tpl_rates.get(o.get("template_id") or "") or user_rates.get(iid, 0)
            a["pay_due_pence"] += int(rate)
        elif o.get("status") == "cancelled":
            a["classes_cancelled"] += 1
        a["capacity_sum"] += int(o.get("capacity") or 0)
        a["bookings_sum"] += int(o.get("bookings_count") or 0)
        a["waitlist_sum"] += int(o.get("waitlist_count") or 0)
        a["attended_sum"] += int(o.get("attended_count") or 0)
        a["no_show_sum"] += int(o.get("no_show_count") or 0)

    # Derive percentages
    rows: list[dict] = []
    for a in agg.values():
        cap = a["capacity_sum"] or 1
        booked = a["bookings_sum"]
        attended = a["attended_sum"]
        no_show = a["no_show_sum"]
        booking_base = max(booked, 1)
        a["fill_rate_pct"] = round(100.0 * booked / cap, 1)
        a["attendance_rate_pct"] = round(100.0 * attended / booking_base, 1)
        a["no_show_rate_pct"] = round(100.0 * no_show / booking_base, 1)
        a["pay_due_gbp"] = round(a["pay_due_pence"] / 100.0, 2)
        rows.append(a)

    rows.sort(key=lambda r: -r["fill_rate_pct"])
    return {
        "rows": rows, "count": len(rows),
        "window_days": days, "since": since_iso,
    }


# ───────────────────────── Cover-request assignment ─────────────────────────


@router.post(
    "/memberships/cover-requests/{req_id}/assign",
    dependencies=[Depends(require_module("memberships"))],
)
async def assign_cover_request(
    req_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Operator picks an instructor to cover a class. Updates the
    occurrence's `instructor_user_id` + the cover request status."""
    org_id = await _require_operator_org(user)
    instructor_id = (body.get("instructor_user_id") or "").strip()
    if not instructor_id:
        raise HTTPException(400, "instructor_user_id is required")

    req = await db.cover_requests.find_one(
        {"id": req_id, "organization_id": org_id}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Cover request not found")
    if req.get("status") not in ("open", "open_to_all"):
        raise HTTPException(400, f"Cover request is already {req.get('status')}")

    instructor = await db.users.find_one(
        {"id": instructor_id, "organization_id": org_id, "role": "instructor"},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    )
    if not instructor:
        raise HTTPException(404, "Instructor not found")

    name = f"{instructor.get('first_name', '')} {instructor.get('last_name', '')}".strip() or instructor["email"]
    await db.cover_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "covered", "assigned_to": instructor_id,
                  "assigned_by_operator": user["id"],
                  "covered_at": _now_iso()}},
    )
    await db.class_occurrences.update_one(
        {"id": req["occurrence_id"]},
        {"$set": {"instructor_user_id": instructor_id,
                  "instructor_name": name,
                  "covered_from_user_id": req.get("from_user_id"),
                  "cover_request_id": req_id}},
    )
    return {"ok": True, "assigned_to": instructor_id, "name": name}


__all__ = ["router"]
