"""
GymAxis Service Operations — Engineer Mobile API.

Iter 215dp (Phase 2).

Mobile-tuned endpoints used by the React PWA at `/svc/engineer`. Designed
for spotty connectivity:
  • Every write accepts an `Idempotency-Key` header so the offline queue
    can replay safely.
  • Reads are snapshot-friendly (today's jobs in one round-trip).
  • Writes return 200/201 even when the object already existed under the
    same key (200) — the offline queue treats that as success.

Engineer identity:
  An engineer is any user with a row in `svc_engineers` keyed by
  `id == user.id`. If the user has no row yet we auto-create a minimal
  profile from their account on first call (this matches Sage's
  Employee → AppointmentResource auto-mirror behaviour).

All field names map 1:1 to /app/memory/SVC_FIELD_MAPPING.md (§4, §5, §6, §7).
"""
__integration_fields__ = {
    # svc_engineers (mirrors Sage Employee per SVC_FIELD_MAPPING §4)
    "engineers.id":                  "sage: Employee.ID · sicon: AppointmentResourceID · bidirectional",
    "engineers.organization_id":     "gymaxis_only: tenant scoping",
    "engineers.sage_user_id":        "sage: Employee.Reference · bidirectional",
    "engineers.full_name":           "sage: Employee.FullName · sicon: AppointmentResourceName · bidirectional",
    "engineers.email":               "sage: Employee.Email · GymAxis → Sage",
    "engineers.mobile":               "sage: Employee.Mobile · GymAxis → Sage",
    "engineers.home_address":        "sage: Employee.Address (postcode used by scheduler scoring) · GymAxis → Sage",
    "engineers.vehicle_reg":         "gymaxis_only: van identifier",
    "engineers.skills":              "sicon: ResourceSkills[] · GymAxis → Sicon",
    "engineers.working_hours":       "sicon: ResourceCalendar · GymAxis → Sicon",
    "engineers.active":              "sage: Employee.IsActive · bidirectional",
    # svc_time_entries (one per engineer × case × shift) — §6
    "time_entries.id":               "sicon: TimeEntryID · GymAxis → Sicon",
    "time_entries.organization_id":  "gymaxis_only: tenant scoping",
    "time_entries.case_id":          "sicon: ServiceCallID · GymAxis → Sicon",
    "time_entries.case_reference":   "sicon: ServiceCallReference · sage: line description fragment · GymAxis → both",
    "time_entries.engineer_id":      "sicon: AppointmentResourceID · sage: Employee.Reference · GymAxis → both",
    "time_entries.engineer_sage_user_id": "sage: Employee.Reference · GymAxis → Sage",
    "time_entries.engineer_name":    "sicon: AppointmentResourceName · GymAxis → Sicon",
    "time_entries.category":         "sicon: TimeEntryCategory (travel|on_site|admin) · GymAxis → Sicon",
    "time_entries.chargeable":       "sage: BillableFlag (drives whether labour line lands on SLInvoice) · GymAxis → Sage",
    "time_entries.start_at":         "sicon: TimeEntryStart · sage: Timesheet.StartAt · GymAxis → both",
    "time_entries.end_at":           "sicon: TimeEntryEnd · sage: Timesheet.EndAt · GymAxis → both",
    "time_entries.duration_minutes": "sicon: TimeEntryDurationMinutes · sage: Quantity (hours converted on quote) · GymAxis → both",
    "time_entries.notes":            "sicon: TimeEntryNotes · GymAxis → Sicon",
    "time_entries.idempotency_key":  "gymaxis_only: offline-queue replay guard",
    # svc_engineer_photos — §7
    "photos.id":                     "sicon: AttachmentID · GymAxis → Sicon",
    "photos.case_id":                "sicon: ServiceCallID · GymAxis → Sicon",
    "photos.case_reference":         "sicon: ServiceCallReference · GymAxis → Sicon",
    "photos.file_url":               "sicon: AttachmentURL · GymAxis → Sicon",
    "photos.mime_type":              "sicon: AttachmentMimeType · GymAxis → Sicon",
    "photos.caption":                "sicon: AttachmentDescription · GymAxis → Sicon",
    "photos.geo":                    "sicon: AttachmentGeo (lat,lng) · GymAxis → Sicon",
    "photos.taken_at":               "sicon: AttachmentTakenAt · GymAxis → Sicon",
    "photos.taken_by_id":            "sicon: AttachmentTakenByID · GymAxis → Sicon",
    "photos.ai":                     "gymaxis_only: persisted AI photo classification (tags/severity/summary)",
    # svc_signatures — §7
    "signatures.id":                 "sicon: SignatureID · GymAxis → Sicon",
    "signatures.case_id":            "sicon: ServiceCallID · GymAxis → Sicon",
    "signatures.case_reference":     "sicon: ServiceCallReference · GymAxis → Sicon",
    "signatures.signed_by_name":     "sicon: SignedByName · sage: SLInvoice.SignedByName · GymAxis → both",
    "signatures.signed_by_role":     "sicon: SignedByRole · GymAxis → Sicon",
    "signatures.signed_at":          "sicon: SignedAt · sage: SLInvoice.SignedAt · GymAxis → both",
    "signatures.image_data":         "sicon: SignatureImageData (base64) · GymAxis → Sicon",
    "signatures.summary":            "sicon: SignatureSummary · GymAxis → Sicon",
    "signatures.captured_by_id":     "sicon: CapturedByID · GymAxis → Sicon",
}

from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.audit import audit_log
from utils.svc_state import (
    transition as state_transition,
    append_event,
    OPEN_STATES, EN_ROUTE, ON_SITE, REPAIRED, AWAITING_SIGN_OFF, CLOSED,
)
from routes.svc.integrations import sicon_sync, sage_invoice

logger = logging.getLogger(__name__)
# Iter 216h77 — Engineer App access guard. Every endpoint under this
# router requires the caller to either:
#   • have an active Partner Engineer Plan subscription, OR
#   • qualify for the free tier (10+ active referrals), OR
#   • have at least one active customer-added grant, OR
#   • be a master/pulse admin (support & QA access).
# On denial we return 402 with a structured body so the PWA can redirect
# the engineer to the subscription page rather than silently 401.
from routes.partners import require_engineer_app_access  # noqa: E402

router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Mobile"],
    dependencies=[Depends(require_engineer_app_access)],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Iter 220dr · Auto-attach customer-logged machines ─────────────
#
# When a case is created via the customer portal / inbound email /
# service-desk intake the operator picks the affected machine(s)
# via ``asset_id`` (single) or ``equipment_ids`` (multi). The
# engineer used to land on an empty Equipment tab because nothing
# fanned those IDs out into ``svc_work_visit_machines`` until the
# engineer tapped "From site" manually.
#
# This helper closes the gap: on every engineer GET of the case it
# ensures the customer-logged machines are mirrored as work-visit
# rows — idempotent (skips IDs already attached) and best-effort
# (failures log and continue; never break the case load).

async def _ensure_customer_machines_attached(case: dict, of: dict) -> None:
    candidate_ids: list[str] = []
    primary = case.get("asset_id")
    if primary:
        candidate_ids.append(primary)
    for eq_id in (case.get("equipment_ids") or []):
        if eq_id and eq_id not in candidate_ids:
            candidate_ids.append(eq_id)
    if not candidate_ids:
        return
    case_id = case["id"]
    try:
        existing = await db.svc_work_visit_machines.find(
            {**of, "case_id": case_id, "asset_id": {"$in": candidate_ids}},
            {"_id": 0, "asset_id": 1},
        ).to_list(100)
        existing_ids = {r.get("asset_id") for r in existing if r.get("asset_id")}
        to_attach = [eid for eid in candidate_ids if eid not in existing_ids]
        if not to_attach:
            return
        equipment_rows = await db.equipment.find(
            {**of, "id": {"$in": to_attach}},
            {"_id": 0, "id": 1, "name": 1, "equipment_type": 1,
             "manufacturer": 1, "model": 1, "serial_number": 1},
        ).to_list(100)
        eq_by_id = {r["id"]: r for r in equipment_rows}
        order_index = await db.svc_work_visit_machines.count_documents(
            {**of, "case_id": case_id},
        )
        now = _now()
        rows = []
        for eid in to_attach:
            eq = eq_by_id.get(eid) or {}
            label = (
                f"{eq.get('manufacturer') or ''} {eq.get('model') or eq.get('name') or ''}".strip()
                or eq.get("name")
                or case.get("asset_name")
                or "Equipment"
            )
            rows.append({
                "id": str(uuid.uuid4()),
                **of,
                "case_id": case_id,
                "asset_id": eid,
                "asset_name": label[:200],
                "asset_serial": (eq.get("serial_number") or "")[:120] or None,
                "asset_type": (eq.get("equipment_type") or "")[:120] or None,
                "manufacturer": eq.get("manufacturer") or None,
                "model": eq.get("model") or None,
                "serviced": False,
                "cleaned": False,
                "notes": None,
                "custom_fields": {},
                "order_index": order_index,
                "created_at": now,
                "updated_at": now,
                "source": "customer_logged",
            })
            order_index += 1
        if rows:
            await db.svc_work_visit_machines.insert_many(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[engineer] customer-machine auto-attach failed for case=%s: %s",
            case.get("id"), exc,
        )


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Engineer profile (auto-mirrored from user account)
# ─────────────────────────────────────────────────────────────────

async def _ensure_engineer(user: dict) -> dict:
    """Look up or auto-create an `svc_engineers` row for the caller.

    Maps 1:1 to Sage `Employee` per SVC_FIELD_MAPPING.md §4.
    """
    of = _of(user)
    eng = await db.svc_engineers.find_one({**of, "id": user["id"]})
    if eng:
        return _strip(eng)
    profile = {
        "id": user["id"],
        "organization_id": of["organization_id"],
        "sage_user_id": user.get("sage_user_id") or user.get("id"),
        "full_name": user.get("full_name") or user.get("email") or "Engineer",
        "email": user.get("email") or "",
        "mobile": user.get("phone") or "",
        "home_address": {},
        "vehicle_reg": "",
        "skills": [],
        "working_hours": {},
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_engineers.insert_one(profile)
    profile.pop("_id", None)
    return profile


@router.get("/me")
async def engineer_me(user=Depends(get_current_user)):
    """Profile + today's job count for the home screen."""
    eng = await _ensure_engineer(user)
    of = _of(user)
    # Iter 261 — org identity for the app header + internal/partner split.
    # Internal engineers (provisioned by an org that runs the Service Desk)
    # see their organisation's name in the header and DON'T need the
    # legacy-report self-upload (the desk imports history via Settings).
    org = await db.organizations.find_one(
        {"id": of["organization_id"]}, {"_id": 0, "name": 1},
    )
    partner = await db.partner_engineers.find_one(
        {"user_id": user["id"]}, {"_id": 0, "id": 1},
    )
    is_partner = bool(partner) or bool(user.get("is_partner_engineer"))
    today = datetime.now(timezone.utc).date().isoformat()
    open_q = {**of, "assigned_engineer_id": user["id"], "status": {"$in": list(OPEN_STATES)}}
    today_count = await db.svc_cases.count_documents({**open_q, "scheduled_at": {"$regex": f"^{today}"}})
    open_count = await db.svc_cases.count_documents(open_q)
    # Active timer (an entry with no end_at) — drives the "you're on the clock" pill.
    active = await db.svc_time_entries.find_one(
        {**of, "engineer_id": user["id"], "end_at": None}, {"_id": 0},
    )
    return {
        "engineer": eng,
        "organization_name": (org or {}).get("name"),
        "is_partner_engineer": is_partner,
        "internal_engineer": not is_partner,
        "stats": {
            "today_jobs": today_count,
            "open_jobs": open_count,
        },
        "active_timer": active,
    }


# Iter 220cu — "My day" briefing.
# Composes the next stop + miles + pending parts + unread inbox into
# a single one-glance summary for the EngineerHomeV2 strip. Reuses
# data already in the engineer endpoints; no new collections.
@router.get("/me/briefing")
async def engineer_my_day_briefing(user=Depends(get_current_user)):
    of = _of(user)
    today_iso = datetime.now(timezone.utc).date().isoformat()
    open_q = {**of, "assigned_engineer_id": user["id"],
              "status": {"$in": list(OPEN_STATES)}}

    # Next stop = earliest scheduled job today (or right now-ish for
    # en_route / on_site jobs without a scheduled_at).
    next_stop_doc = await db.svc_cases.find_one(
        {
            **open_q,
            "$or": [
                {"scheduled_at": {"$regex": f"^{today_iso}"}},
                {"scheduled_at": None, "status": {"$in": [EN_ROUTE, ON_SITE]}},
            ],
        },
        {
            "_id": 0, "id": 1, "reference": 1, "title": 1,
            "site_name": 1, "site_address": 1, "site_postcode": 1,
            "scheduled_at": 1, "customer_name": 1, "asset_name": 1,
            "priority": 1, "status": 1,
        },
        sort=[("scheduled_at", 1)],
    )

    # Pending parts requests the engineer raised (awaiting admin approval).
    pending_parts_count = 0
    try:
        pending_parts_count = await db.svc_parts_requests.count_documents({
            **of, "engineer_id": user["id"], "status": "pending",
        })
    except Exception:  # noqa: BLE001
        pending_parts_count = 0

    # Inbox unread count (engineer notifications).
    unread_inbox_count = 0
    try:
        unread_inbox_count = await db.svc_engineer_notifications.count_documents({
            **of, "engineer_id": user["id"], "read_at": None,
        })
    except Exception:  # noqa: BLE001
        unread_inbox_count = 0

    # Quotes awaiting customer reply / acceptance.
    pending_quotes_count = 0
    try:
        pending_quotes_count = await db.svc_engineer_quotes.count_documents({
            **of, "engineer_id": user["id"], "status": {"$in": ["sent", "viewed"]},
        })
    except Exception:  # noqa: BLE001
        pending_quotes_count = 0

    # Iter 220cx — Closed-but-not-invoiced alert. Jobs the engineer
    # closed but for which no invoice was issued. Surfaces a recovery
    # action card so we never silently lose billable work.
    not_invoiced: list[dict] = []
    try:
        # We treat the case as "not invoiced" when:
        #   • status ∈ {closed, repaired, awaiting_sign_off}
        #   • closed within the last 7 days
        #   • no draft invoice exists linked back to this case_id
        from datetime import timedelta
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        async for c in db.svc_cases.find(
            {
                **of,
                "assigned_engineer_id": user["id"],
                "status": {"$in": ["closed", "repaired", "awaiting_sign_off"]},
                "closed_at": {"$gte": cutoff_iso},
            },
            {
                "_id": 0, "id": 1, "reference": 1, "title": 1,
                "customer_name": 1, "closed_at": 1, "status": 1,
            },
            sort=[("closed_at", -1)],
            limit=20,
        ):
            invoice = await db.svc_engineer_invoices.find_one(
                {**of, "case_id": c["id"]},
                {"_id": 0, "id": 1},
            )
            if not invoice:
                not_invoiced.append(c)
            if len(not_invoiced) >= 5:
                break
    except Exception:  # noqa: BLE001
        not_invoiced = []

    # Total jobs scheduled today (open or closed) so we can say
    # "3 jobs today" even after the first one is done.
    jobs_today_total = await db.svc_cases.count_documents({
        **of, "assigned_engineer_id": user["id"],
        "scheduled_at": {"$regex": f"^{today_iso}"},
    })
    jobs_today_remaining = await db.svc_cases.count_documents({
        **open_q, "scheduled_at": {"$regex": f"^{today_iso}"},
    })

    return {
        "jobs_today_total":     jobs_today_total,
        "jobs_today_remaining": jobs_today_remaining,
        "next_stop":            next_stop_doc,
        "pending_parts_count":  pending_parts_count,
        "pending_quotes_count": pending_quotes_count,
        "unread_inbox_count":   unread_inbox_count,
        # Iter 220cx — closed jobs that never got an invoice.
        "not_invoiced":         not_invoiced,
        "not_invoiced_count":   len(not_invoiced),
    }


# Iter 220cu — End-of-day timesheet roll-up.
# Single-screen daily summary for the EngineerEndOfDay page. Returns
# hours by category, miles, jobs touched / closed, and revenue
# invoiced today.
@router.get("/me/today-rollup")
async def engineer_today_rollup(user=Depends(get_current_user)):
    of = _of(user)
    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()

    # Time entries that started today (whether or not they've ended).
    minutes_by_cat: dict[str, int] = {"on_site": 0, "travel": 0, "admin": 0}
    case_ids_touched: set[str] = set()
    async for e in db.svc_time_entries.find(
        {**of, "engineer_id": user["id"],
         "start_at": {"$regex": f"^{today_iso}"}},
        {"_id": 0, "category": 1, "duration_minutes": 1, "case_id": 1},
    ):
        cat = e.get("category") or "on_site"
        minutes_by_cat[cat] = minutes_by_cat.get(cat, 0) + int(e.get("duration_minutes") or 0)
        if e.get("case_id"):
            case_ids_touched.add(e["case_id"])

    # Mileage today.
    miles_today = 0.0
    try:
        async for m in db.svc_mileage_entries.find(
            {**of, "engineer_id": user["id"],
             "created_at": {"$regex": f"^{today_iso}"}},
            {"_id": 0, "miles": 1},
        ):
            miles_today += float(m.get("miles") or 0)
    except Exception:  # noqa: BLE001
        miles_today = 0.0

    # Jobs closed today.
    closed_today = await db.svc_cases.count_documents({
        **of, "assigned_engineer_id": user["id"],
        "status": {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off"]},
        "closed_at": {"$regex": f"^{today_iso}"},
    })

    # Invoices issued today + revenue (gross).
    revenue_today = 0.0
    invoices_today = 0
    try:
        async for inv in db.svc_engineer_invoices.find(
            {**of, "engineer_id": user["id"],
             "issue_date": {"$regex": f"^{today_iso}"}},
            {"_id": 0, "total": 1},
        ):
            invoices_today += 1
            revenue_today += float(inv.get("total") or 0)
    except Exception:  # noqa: BLE001
        revenue_today = 0.0

    return {
        "date": today_iso,
        "minutes_by_category": minutes_by_cat,
        "hours_total": round(sum(minutes_by_cat.values()) / 60.0, 2),
        "hours_on_site": round(minutes_by_cat.get("on_site", 0) / 60.0, 2),
        "hours_travel":  round(minutes_by_cat.get("travel", 0) / 60.0, 2),
        "hours_admin":   round(minutes_by_cat.get("admin", 0) / 60.0, 2),
        "miles":         round(miles_today, 1),
        "jobs_touched":  len(case_ids_touched),
        "jobs_closed":   closed_today,
        "invoices_today": invoices_today,
        "revenue_today_gbp": round(revenue_today, 2),
    }


# ─────────────────────────────────────────────────────────────────
# Today's jobs feed
# ─────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def engineer_jobs(
    when: str = Query("today", description="today | upcoming | open | overdue | return_to_fix | closed"),
    user=Depends(get_current_user),
):
    """List jobs assigned to the calling engineer, mobile-friendly subset."""
    of = _of(user)
    # Iter 220ec — "closed" lets engineers browse/re-open their recently
    # completed jobs (closed / invoiced / repaired / awaiting sign-off),
    # which were previously invisible once they left the open states.
    if when == "closed":
        q = {**of, "assigned_engineer_id": user["id"],
             "status": {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off", "cancelled"]}}
    elif when in ("return_to_fix", "awaiting_parts"):
        # Iter 278d — "Return to Fix": jobs needing a further visit to
        # complete (engineer flagged a return, or parked for parts). Matches
        # the dashboard KPI definition exactly. ``awaiting_parts`` is kept as
        # an alias so older deep-links keep working.
        q = {**of, "assigned_engineer_id": user["id"],
             "status": {"$nin": ["closed", "invoiced", "cancelled", "rejected"]},
             "$or": [
                 {"return_to_fix": {"$ne": None}},
                 {"status": {"$in": ["paused_parts", "awaiting_parts"]}},
             ]}
    elif when == "overdue":
        # Iter 278c — the "Overdue" KPI tile must show ONLY jobs scheduled in
        # the past that are still open. Mirrors the dashboard KPI definition
        # (status set + scheduled_at < today) so the count and the list agree.
        today = datetime.now(timezone.utc).date().isoformat()
        q = {**of, "assigned_engineer_id": user["id"],
             "status": {"$in": ["assigned", "en_route", "on_site",
                                 "in_progress", "awaiting_parts", "quote_required"]},
             "scheduled_at": {"$lt": today, "$ne": None}}
    else:
        q = {**of, "assigned_engineer_id": user["id"], "status": {"$in": list(OPEN_STATES)}}
    if when == "today":
        today = datetime.now(timezone.utc).date().isoformat()
        q["$or"] = [
            {"scheduled_at": {"$regex": f"^{today}"}},
            {"scheduled_at": None, "status": {"$in": [EN_ROUTE, ON_SITE]}},
        ]
    elif when == "upcoming":
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        q["scheduled_at"] = {"$gte": tomorrow}
    projection = {
        "_id": 0,
        # Keep payload lean for mobile.
        "id": 1, "reference": 1, "title": 1, "priority": 1, "status": 1,
        "site_name": 1, "asset_name": 1, "fault_code": 1, "scheduled_at": 1,
        "estimated_minutes": 1, "sla_resolve_at": 1, "customer_name": 1,
        "customer_phone": 1, "closed_at": 1,
    }
    if when == "closed":
        rows = (
            await db.svc_cases.find(q, projection)
            .sort([("closed_at", -1), ("updated_at", -1)]).to_list(100)
        )
    else:
        rows = (
            await db.svc_cases.find(q, projection)
            .sort([("scheduled_at", 1), ("sla_resolve_at", 1)]).to_list(200)
        )
    return {"jobs": rows, "count": len(rows)}


@router.get("/jobs/{case_id}")
async def engineer_job_detail(case_id: str, user=Depends(get_current_user)):
    """Full job context for the engineer detail screen."""
    of = _of(user)
    case = _strip(await db.svc_cases.find_one({"id": case_id, **of}))
    if not case:
        raise HTTPException(404, "Job not found")
    if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != user["id"] \
            and not user.get("is_master_admin"):
        # Iter 220az · F-29 / F-33 — engineers may only see their own
        # jobs. Return 404 (not 403) so attackers can't enumerate
        # case IDs by status code.
        raise HTTPException(404, "Job not found")
    # Iter 220dr — auto-attach the customer-logged asset(s) the very
    # first time the engineer opens the case, so the Equipment tab
    # is never empty when the operator already picked the machine.
    await _ensure_customer_machines_attached(case, of)
    events = (
        await db.svc_case_events
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("at", -1).limit(50).to_list(50)
    )
    photos = (
        await db.svc_engineer_photos
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("taken_at", -1).limit(50).to_list(50)
    )
    time_entries = (
        await db.svc_time_entries
        .find({"case_id": case_id, **of, "engineer_id": user["id"]}, {"_id": 0})
        .sort("start_at", -1).limit(20).to_list(20)
    )
    # Iter 216h85 — Asset history (last 3 prior cases on the same asset)
    asset_history: list = []
    asset_id = case.get("asset_id") or ""
    asset_name = (case.get("asset_name") or "").strip()
    if asset_id or asset_name:
        history_q: dict = {
            **of,
            "id": {"$ne": case_id},
            "status": {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off"]},
        }
        if asset_id:
            history_q["asset_id"] = asset_id
        else:
            history_q["asset_name"] = asset_name
        asset_history = (
            await db.svc_cases.find(
                history_q,
                {
                    "_id": 0, "id": 1, "reference": 1, "title": 1,
                    "fault_code": 1, "status": 1, "closed_at": 1,
                    "created_at": 1, "customer_rating": 1, "resolution_notes": 1,
                },
            ).sort([("closed_at", -1), ("created_at", -1)]).limit(3).to_list(3)
        )
    # Iter 216h89 — Pre-job H&S signoff state (so PWA gates on-site timer)
    safety_signoff = await db.svc_case_safety_signoffs.find_one(
        {"case_id": case_id, **of, "engineer_id": user["id"]},
        {"_id": 0, "id": 1, "signed_at": 1, "ticked_item_ids": 1, "remarks": 1},
        sort=[("signed_at", -1)],
    )
    safety_template = None
    # Iter 220ea·10 — Skip template attachment when the engineer
    # has explicitly waived the H&S signoff on this job. The
    # Summary banner reads `safety_template` to decide whether to
    # show; suppressing it here means the banner disappears the
    # moment the waiver is recorded.
    safety_waived = bool(case.get("safety_signoff_waived"))
    if not safety_signoff and not safety_waived:
        from routes.svc.safety import _resolve_template
        tpl = await _resolve_template(of["organization_id"])
        safety_template = {"id": tpl["id"], "items": tpl["items"]}
    # Iter 220cz — Job overrun + multi-job-same-site signal so the
    # JobAtAGlance card can warn the engineer (a) when actual labour
    # has run beyond the estimate and (b) when the same customer
    # already has open jobs at this site.
    on_site_minutes_used = 0
    for e in time_entries:
        if e.get("category") == "on_site":
            on_site_minutes_used += int(e.get("duration_minutes") or 0)
    estimated_minutes = int(case.get("estimated_minutes") or 0)
    overrun = {
        "estimated_minutes":  estimated_minutes,
        "on_site_minutes":    on_site_minutes_used,
        "is_overrun":         bool(estimated_minutes and on_site_minutes_used > estimated_minutes),
        "is_approaching":     bool(
            estimated_minutes
            and on_site_minutes_used >= int(estimated_minutes * 0.85)
            and on_site_minutes_used <= estimated_minutes
        ),
        "percent_used":       round((on_site_minutes_used / estimated_minutes) * 100, 1) if estimated_minutes else 0,
    }

    # Other open jobs at this site (same customer + same site name).
    # Helps the engineer combine visits or hand off a job to themselves.
    sibling_jobs: list = []
    customer_key = (case.get("customer_email") or case.get("customer_name") or "").strip()
    site_key = (case.get("site_name") or "").strip()
    if customer_key and site_key:
        from re import escape as _re_escape
        sibling_jobs = (
            await db.svc_cases.find(
                {
                    **of,
                    "id": {"$ne": case_id},
                    "status": {"$in": [
                        "new", "scheduled", "in_progress", "on_hold", "awaiting_parts",
                    ]},
                    "$or": [
                        {"customer_email": case.get("customer_email") or ""},
                        {"customer_name": {
                            "$regex": f"^{_re_escape(case.get('customer_name') or '')}$",
                            "$options": "i",
                        }},
                    ],
                    "site_name": {"$regex": f"^{_re_escape(site_key)}$", "$options": "i"},
                },
                {
                    "_id": 0, "id": 1, "reference": 1, "title": 1,
                    "priority": 1, "status": 1, "scheduled_at": 1,
                },
            ).sort([("scheduled_at", 1), ("created_at", 1)]).limit(5).to_list(5)
        )

    # Iter 220ed — completed-job recap data (read-only). Surface the
    # captured customer signature + the resolution summary so a closed
    # job's Complete tab can show the engineer's notes & sign-off.
    signature_recap = await db.svc_signatures.find_one(
        {"case_id": case_id, **of}, {"_id": 0},
        sort=[("signed_at", -1)],
    )
    fix_summary_recap = case.get("resolution_notes") or ""
    if not fix_summary_recap:
        try:
            from routes.svc.service_report import _resolve_fix_summary
            fix_summary_recap = await _resolve_fix_summary(case_id, of)
        except Exception:
            fix_summary_recap = ""
    if not fix_summary_recap and signature_recap:
        fix_summary_recap = signature_recap.get("summary") or ""

    return {
        **case,
        "events": events,
        "photos": photos,
        "time_entries": time_entries,
        "asset_history": asset_history,
        "safety_signoff": safety_signoff,
        "safety_template": safety_template,
        "overrun": overrun,
        "sibling_jobs": sibling_jobs,
        # Iter 220ed — completed-job recap (read-only) for the Complete
        # tab: the captured customer signature + the work summary so a
        # closed job still shows the engineer's notes & sign-off.
        "signature": signature_recap,
        "fix_summary": fix_summary_recap,
        # Iter 220ds — surface the current viewer's id so the
        # Engineer App can filter handoff notes to "from the
        # previous engineer" on the Summary tab.
        "viewer_user_id": user.get("id"),
    }


# ─────────────────────────────────────────────────────────────────
# Time tracking — start / stop
# ─────────────────────────────────────────────────────────────────

async def _idempotent_insert(collection, doc: dict, idem_key: str | None) -> dict | None:
    """Insert under an idempotency key; if a row exists return it (None == proceed)."""
    if idem_key:
        existing = await collection.find_one({"idempotency_key": idem_key}, {"_id": 0})
        if existing:
            return existing
        doc["idempotency_key"] = idem_key
    await collection.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _check_idempotent(collection, idem_key: str | None) -> dict | None:
    """Pre-check for idempotent replay so the caller can short-circuit
    expensive side effects (timer auto-stop, SLA transitions, sicon push).
    """
    if not idem_key:
        return None
    return await collection.find_one({"idempotency_key": idem_key}, {"_id": 0})


@router.post("/time/start")
async def time_start(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Start a work timer.

    Body: {case_id, category?: 'travel'|'on_site'|'admin', notes?: str}
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    if not case_id:
        raise HTTPException(400, "case_id required")
    # Idempotent replay short-circuit (must run before auto-stop side effects).
    replay = await _check_idempotent(db.svc_time_entries, idempotency_key)
    if replay:
        return replay
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    # Iter 216h89 — H&S gate. Engineers must complete the pre-job safety
    # signoff before starting the on_site timer. Travel/admin timers are
    # not gated (the gate fires when the engineer arrives on site).
    # Iter 220ea·10 — Waiver bypasses the gate when the engineer
    # explicitly marked this visit as not needing H&S.
    if (
        (data.get("category") or "on_site") == "on_site"
        and not case.get("safety_signoff_at")
        and not case.get("safety_signoff_waived")
    ):
        raise HTTPException(
            status_code=412,
            detail={
                "code": "safety_signoff_required",
                "message": "Complete the H&S checklist before starting the on-site timer.",
            },
        )
    # Stop any open timer on this engineer first — only one active at a time.
    await db.svc_time_entries.update_many(
        {**of, "engineer_id": user["id"], "end_at": None},
        {"$set": {"end_at": _now(), "auto_stopped": True, "updated_at": _now()}},
    )
    eng = await _ensure_engineer(user)
    entry = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "engineer_id": user["id"],
        "engineer_sage_user_id": eng.get("sage_user_id") or "",
        "engineer_name": eng.get("full_name") or "",
        "category": (data.get("category") or "on_site"),
        "chargeable": bool(data.get("chargeable")),
        "start_at": _now(),
        "end_at": None,
        "duration_minutes": 0,
        "notes": (data.get("notes") or "").strip(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    entry = await _idempotent_insert(db.svc_time_entries, entry, idempotency_key)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="time_start", actor=user,
        body=f"Engineer started {entry['category']} timer",
        extra={"time_entry_id": entry["id"], "category": entry["category"]},
    )
    # If engineer not yet on site, transition appropriately.
    target = ON_SITE if entry["category"] == "on_site" else EN_ROUTE if entry["category"] == "travel" else None
    if target and case.get("status") != target:
        try:
            await state_transition(
                case_id=case_id, organization_id=of["organization_id"],
                target_state=target, actor=user, reason="auto: engineer started timer",
            )
        except ValueError:
            # Illegal transition (e.g., from on_site→en_route) — ignore and keep current state.
            pass
    await sicon_sync.push_time_entry(entry, case_reference=case.get("reference"))
    return entry


@router.post("/time/manual")
async def time_manual(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Log a completed time entry manually (duration + category).

    Field fallback for when the live timer wasn't running (engineer
    forgot to start it, or worked offline). Inserts an already-closed
    entry so it appears in the History + report totals immediately.

    Body: {case_id, category?: 'on_site'|'travel'|'admin', minutes: int,
           notes?: str, chargeable?: bool}
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    if not case_id:
        raise HTTPException(400, "case_id required")
    try:
        minutes = int(round(float((data or {}).get("minutes") or 0)))
    except (TypeError, ValueError):
        raise HTTPException(400, "minutes must be a number")
    if minutes <= 0:
        raise HTTPException(400, "minutes must be a positive number")
    if minutes > 24 * 60:
        raise HTTPException(400, "minutes cannot exceed 24 hours")
    category = (data.get("category") or "on_site")
    if category not in ("on_site", "travel", "admin"):
        category = "on_site"
    replay = await _check_idempotent(db.svc_time_entries, idempotency_key)
    if replay:
        return replay
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    eng = await _ensure_engineer(user)
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(minutes=minutes)
    entry = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "engineer_id": user["id"],
        "engineer_sage_user_id": eng.get("sage_user_id") or "",
        "engineer_name": eng.get("full_name") or "",
        "category": category,
        "chargeable": bool(data.get("chargeable")),
        "start_at": start_dt.isoformat(),
        "end_at": now.isoformat(),
        "duration_minutes": minutes,
        "manual_entry": True,
        "notes": (data.get("notes") or "").strip(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    entry = await _idempotent_insert(db.svc_time_entries, entry, idempotency_key)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="time_manual", actor=user,
        body=f"Engineer logged {minutes}m {category} manually",
        extra={"time_entry_id": entry["id"], "category": category,
               "duration_minutes": minutes, "manual": True},
    )
    await sicon_sync.push_time_entry(entry, case_reference=case.get("reference"))
    return entry


@router.post("/time/stop")
async def time_stop(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Stop the active timer (or a specific entry by id)."""
    of = _of(user)
    entry_id = (data or {}).get("entry_id")
    q = {**of, "engineer_id": user["id"]}
    if entry_id:
        q["id"] = entry_id
    else:
        q["end_at"] = None
    entry = await db.svc_time_entries.find_one(q)
    if not entry:
        raise HTTPException(404, "No active time entry")
    end_at = _now()
    start_dt = datetime.fromisoformat(entry["start_at"])
    duration_minutes = max(0, int((datetime.fromisoformat(end_at) - start_dt).total_seconds() // 60))
    await db.svc_time_entries.update_one(
        {"id": entry["id"]},
        {"$set": {
            "end_at": end_at,
            "duration_minutes": duration_minutes,
            "notes": (data.get("notes") or entry.get("notes") or "").strip(),
            "updated_at": _now(),
        }},
    )
    entry["end_at"] = end_at
    entry["duration_minutes"] = duration_minutes
    await append_event(
        case_id=entry["case_id"], organization_id=of["organization_id"],
        event_type="time_stop", actor=user,
        body=f"Stopped {entry['category']} timer ({duration_minutes}m)",
        extra={"time_entry_id": entry["id"], "duration_minutes": duration_minutes},
    )
    await sicon_sync.push_time_entry(entry, case_reference=entry.get("case_reference") or "")
    entry.pop("_id", None)
    return entry


# ─────────────────────────────────────────────────────────────────
# Photo & signature capture
# ─────────────────────────────────────────────────────────────────

@router.post("/photos")
async def add_photo(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Attach a photo or short video (already uploaded via /api/files/upload)
    to a case.

    Body: {case_id, file_url, mime_type?, caption?, geo?: {lat,lng},
           taken_at?, duration_seconds?}

    The `kind` field is derived from `mime_type`:
      * `image/*` → kind="photo" (default)
      * `video/*` → kind="video"
    The frontend uses this to render a play overlay on video tiles.
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    file_url = (data or {}).get("file_url")
    if not case_id or not file_url:
        raise HTTPException(400, "case_id and file_url required")
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    mime = (data.get("mime_type") or "image/jpeg").lower()
    kind = "video" if mime.startswith("video/") else "photo"
    # Iter 220e — optional per-machine tagging. Engineers can attach a
    # photo to a specific row in the Machines card so the Service Report
    # PDF prints it next to that machine's notes.
    machine_row_id = (data.get("machine_row_id") or "").strip() or None
    if machine_row_id:
        existing = await db.svc_work_visit_machines.find_one(
            {"id": machine_row_id, "case_id": case_id, **of},
            {"_id": 0, "id": 1},
        )
        if not existing:
            raise HTTPException(404, "Machine row not found")
    photo = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "machine_row_id": machine_row_id,
        "file_url": file_url,
        "mime_type": mime,
        "kind": kind,
        "duration_seconds": data.get("duration_seconds"),
        "caption": (data.get("caption") or "").strip(),
        "geo": data.get("geo") or {},
        "taken_at": data.get("taken_at") or _now(),
        "taken_by_id": user["id"],
        "taken_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
    }
    photo = await _idempotent_insert(db.svc_engineer_photos, photo, idempotency_key)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="photo" if kind == "photo" else "note",
        actor=user,
        body=photo.get("caption") or ("Video attached" if kind == "video" else "Photo attached"),
        extra={"photo_id": photo["id"], "file_url": file_url, "kind": kind},
    )
    await sicon_sync.push_attachment(photo, case_reference=case.get("reference"))
    return photo


@router.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, user=Depends(get_current_user)):
    """Iter 220e — Soft delete: remove the photo doc from
    `svc_engineer_photos`. The underlying file in object storage stays
    around (so audit history isn't broken); only the link disappears.
    """
    of = _of(user)
    res = await db.svc_engineer_photos.delete_one({"id": photo_id, **of})
    if not res.deleted_count:
        raise HTTPException(404, "Photo not found")
    return {"ok": True, "id": photo_id}


@router.post("/signature")
async def add_signature(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Record a customer sign-off signature.

    Body: {case_id, signed_by_name, signed_by_role?, image_data (base64),
           summary?}
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    signed_by_name = ((data or {}).get("signed_by_name") or "").strip()
    image_data = (data or {}).get("image_data") or ""
    if not case_id or not signed_by_name or not image_data:
        raise HTTPException(400, "case_id, signed_by_name, image_data required")
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    sig = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "signed_by_name": signed_by_name,
        "signed_by_role": (data.get("signed_by_role") or "").strip(),
        "signed_at": _now(),
        "image_data": image_data,
        "summary": (data.get("summary") or "").strip(),
        "device_meta": data.get("device_meta") or {},
        "captured_by_id": user["id"],
        "captured_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
    }
    sig = await _idempotent_insert(db.svc_signatures, sig, idempotency_key)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="signature", actor=user,
        body=f"Signed by {signed_by_name}",
        extra={"signature_id": sig["id"], "summary": sig["summary"]},
    )
    await sicon_sync.push_signature(sig, case_reference=case.get("reference"))
    # Iter 216h155 — compliance audit. Customer signature is a legally
    # binding sign-off — must be in the immutable audit ledger.
    try:
        await audit_log(
            action="svc.case.signature_captured",
            user_id=user.get("id", ""),
            user_email=user.get("email", ""),
            resource_type="svc_signature",
            resource_id=sig["id"],
            details=f"case={case.get('reference', '')} · "
                    f"signed_by={signed_by_name}",
        )
    except Exception as e:
        logger.warning("[audit] signature failed: %s", e)
    return sig


# ─────────────────────────────────────────────────────────────────
# Job complete / sign-off
# ─────────────────────────────────────────────────────────────────

@router.post("/jobs/{case_id}/complete")
async def engineer_complete(
    case_id: str,
    data: dict,
    user=Depends(get_current_user),
):
    """Engineer flags the job as repaired/closed.

    Body: {summary, chargeable?, target?: 'repaired'|'awaiting_sign_off'|'closed'}
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != user["id"] \
            and not user.get("is_master_admin"):
        # Iter 220az · F-29 / F-33 — 404 (not 403) on cross-engineer.
        raise HTTPException(404, "Case not found")
    summary = ((data or {}).get("summary") or "").strip()
    if not summary:
        raise HTTPException(400, "summary required")
    target = (data.get("target") or "awaiting_sign_off").lower()
    if target not in (REPAIRED, AWAITING_SIGN_OFF, CLOSED):
        raise HTTPException(400, "target must be repaired | awaiting_sign_off | closed")

    # Iter 220 — Validate & normalise work-report custom fields before any
    # state transitions, so required-field errors don't leave half-applied
    # side effects (timer stop, status change) behind.
    raw_custom_fields = data.get("custom_fields")
    custom_fields_clean: dict | None = None
    if raw_custom_fields is not None:
        from routes.svc.work_report_fields import validate_and_normalise_custom_field_values
        custom_fields_clean = await validate_and_normalise_custom_field_values(
            organization_id=of["organization_id"],
            case=case,
            raw_values=raw_custom_fields,
        )

    # Stop any open timer first.
    await db.svc_time_entries.update_many(
        {**of, "engineer_id": user["id"], "end_at": None},
        {"$set": {"end_at": _now(), "duration_minutes": 0, "updated_at": _now()}},
    )
    # Append the engineer's fix summary to the timeline so it's captured even
    # before the customer sign-off completes.
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=summary,
        extra={"visibility": "customer", "kind": "fix_summary"},
    )
    if data.get("chargeable") is not None:
        await db.svc_cases.update_one(
            {"id": case_id}, {"$set": {"chargeable": bool(data["chargeable"]), "updated_at": _now()}},
        )
    # Iter 220 — Persist sanitised work-report custom fields onto the case.
    if custom_fields_clean is not None:
        await db.svc_cases.update_one(
            {"id": case_id, **of},
            {"$set": {
                "work_report_custom_fields": custom_fields_clean,
                "work_report_custom_fields_updated_at": _now(),
                "updated_at": _now(),
            }},
        )
    # If the engineer is still en_route or assigned, walk through on_site
    # first — the engineer is clearly on site (about to complete).
    current = case.get("status")
    if current in ("assigned", "en_route") and target != ON_SITE:
        try:
            case = await state_transition(
                case_id=case_id, organization_id=of["organization_id"],
                target_state=ON_SITE, actor=user, reason="auto: engineer wrap-up",
            )
        except ValueError:
            pass
    try:
        case = await state_transition(
            case_id=case_id, organization_id=of["organization_id"],
            target_state=target, actor=user, reason=summary[:200],
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await sicon_sync.push_case(case)
    if target == CLOSED:
        await sage_invoice.enqueue_invoice_for_case(case)
    # Iter 220c — successful complete → drop the engineer's in-flight
    # draft so the form isn't pre-filled with old text the next time
    # they open the case.
    await db.svc_engineer_job_drafts.delete_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
    )
    case.pop("_id", None)
    return case


# ─────────────────────────────────────────────────────────────────
# Iter 220c — Engineer draft autosave (data-loss prevention)
# ─────────────────────────────────────────────────────────────────
# Engineers were losing their Work Summary text when switching between
# tabs in the job detail (the React component unmounts on tab change).
# We persist a debounced draft per (engineer, case) here so an offline
# device crash, app close, or tab navigation never wipes mid-job notes.


@router.get("/jobs/{case_id}/draft")
async def get_engineer_draft(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    doc = await db.svc_engineer_job_drafts.find_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
        {"_id": 0},
    )
    return doc or {"case_id": case_id, "engineer_id": user["id"], "draft": {}}


@router.put("/jobs/{case_id}/draft")
async def upsert_engineer_draft(
    case_id: str,
    data: dict,
    user=Depends(get_current_user),
):
    """Body: {draft: {summary?, target?, signature_name?, custom_fields?, ...}}

    The draft blob is opaque to the backend — the frontend owns its
    shape — but we cap the size to keep one runaway client from
    flooding the collection. 32 KB is plenty for the longest plausible
    work-summary + custom-fields blob.
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    draft = (data or {}).get("draft") or {}
    if not isinstance(draft, dict):
        raise HTTPException(400, "draft must be an object")
    import json as _json
    try:
        payload_size = len(_json.dumps(draft).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "draft is not JSON-serialisable") from exc
    if payload_size > 32 * 1024:
        raise HTTPException(413, "draft too large (max 32 KB)")
    now_iso = _now()
    await db.svc_engineer_job_drafts.update_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
        {"$set": {
            **of,
            "case_id": case_id,
            "engineer_id": user["id"],
            "draft": draft,
            "updated_at": now_iso,
            "bytes": payload_size,
        }, "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    return {"ok": True, "case_id": case_id, "saved_at": now_iso, "bytes": payload_size}


@router.delete("/jobs/{case_id}/draft")
async def clear_engineer_draft(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    await db.svc_engineer_job_drafts.delete_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
    )
    return {"ok": True, "case_id": case_id}


__all__ = ["router"]
