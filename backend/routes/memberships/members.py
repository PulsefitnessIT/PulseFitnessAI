"""Operator-side member CRUD: list, create, freeze, cancel, bulk import, plan assign.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module
from utils.security import sanitise_string

logger = logging.getLogger(__name__)

from routes.memberships.helpers import (
    _load_member,
    _now_iso,
    _public_member,
    _require_operator_org,
    _uuid,
    pwd_ctx,
)

router = APIRouter(tags=["memberships"])


# ═════════════════════ Corporate invites (CRM → Memberships hand-off) ═════════════════════

@router.get("/memberships/corporate-invites", dependencies=[Depends(require_module("memberships"))])
async def list_corporate_invites(user: dict = Depends(get_current_user)):
    """Iter 215by — Pending corporate invites pushed by the CRM when a
    corporate deal closes won. The Memberships team uses this list to
    one-click bulk-invite the company's employees and convert the deal
    into actual gym memberships, closing the loop CRM → Memberships.
    """
    org_id = await _require_operator_org(user)
    rows = await db.memberships_corporate_invites.find(
        {"organization_id": org_id, "status": "pending_invite"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    return {"invites": rows, "count": len(rows)}


@router.post("/memberships/corporate-invites/{invite_id}/dismiss",
             dependencies=[Depends(require_module("memberships"))])
async def dismiss_corporate_invite(invite_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    res = await db.memberships_corporate_invites.update_one(
        {"id": invite_id, "organization_id": org_id, "status": "pending_invite"},
        {"$set": {"status": "dismissed", "dismissed_at": _now_iso(), "dismissed_by": user.get("id")}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"ok": True}


# ═════════════════════ Members (operator) ═════════════════════

@router.get("/memberships/members", dependencies=[Depends(require_module("memberships"))])
async def members_list(
    q: str | None = None,
    status_f: str | None = Query(None, alias="status"),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    query: dict = {"organization_id": org_id}
    if status_f:
        query["status"] = status_f
    if q:
        ql = q.lower()
        query["$or"] = [
            {"email": {"$regex": ql, "$options": "i"}},
            {"first_name": {"$regex": ql, "$options": "i"}},
            {"last_name": {"$regex": ql, "$options": "i"}},
            {"phone": {"$regex": ql, "$options": "i"}},
        ]
    rows = await db.members.find(query, {"_id": 0, "password": 0}).sort("created_at", -1).limit(200).to_list(200)
    # Iter 216h174 — Payload-size + N+1 pass. Previously we shipped the
    # full member_membership doc per member (freeze_history, pause_log,
    # cancel_history, metadata can balloon over a member's lifetime) and
    # ran 2 sequential lookups per row (200 members → 400 round-trips).
    # The members table only reads .status, .credits_remaining,
    # .plan.{name, colour} — project to just those and bulk-load in two
    # round-trips total.
    _MM_LIST_PROJ = {"_id": 0, "status": 1, "credits_remaining": 1, "plan_id": 1, "member_id": 1}
    _PLAN_LIST_PROJ = {"_id": 0, "id": 1, "name": 1, "kind": 1, "colour": 1}
    member_ids = [r["id"] for r in rows]
    if member_ids:
        # Iter 216h200 — Craig's bug: "Assigned plan" appears in activity
        # but the list column showed "No plan". Root cause: recurring
        # plans land as `pending_payment` until a payment is recorded,
        # and the list join only matched `active`/`frozen`. Now we also
        # surface pending_payment so the column never lies — the
        # StatusPill ("Pending payment", amber) cues the operator to
        # finish the payment step.
        mms = await db.member_memberships.find(
            {"member_id": {"$in": member_ids},
             "status": {"$in": ["active", "frozen", "pending_payment"]}},
            _MM_LIST_PROJ,
        ).to_list(len(member_ids) * 2)
        # Iter 216h200 — Prioritise active > frozen > pending_payment
        # when a member has multiple rows (Craig's screenshot showed
        # 3 pending_payment + 1 active for the same member). Without
        # this the dict comprehension kept whichever row Mongo returned
        # last → could've been a stale pending_payment masking the
        # actual active membership.
        _MM_STATUS_RANK = {"active": 0, "frozen": 1, "pending_payment": 2}
        mm_by_member: dict = {}
        for mm in mms:
            mid = mm["member_id"]
            current = mm_by_member.get(mid)
            if (current is None
                or _MM_STATUS_RANK.get(mm.get("status"), 99)
                   < _MM_STATUS_RANK.get(current.get("status"), 99)):
                mm_by_member[mid] = mm
        plan_ids = list({mm["plan_id"] for mm in mms if mm.get("plan_id")})
        plan_by_id: dict = {}
        if plan_ids:
            plans = await db.membership_plans.find(
                {"id": {"$in": plan_ids}}, _PLAN_LIST_PROJ,
            ).to_list(len(plan_ids))
            plan_by_id = {p["id"]: p for p in plans if p.get("id")}
        for r in rows:
            mm = mm_by_member.get(r["id"])
            if mm:
                plan = plan_by_id.get(mm.get("plan_id"))
                r["active_membership"] = {**mm, "plan": plan}
    return {"members": rows}


@router.get("/memberships/members/csv-template", dependencies=[Depends(require_module("memberships"))])
async def members_csv_template(user: dict = Depends(get_current_user)):
    """Return the CSV template gym managers should fill in for bulk member
    import. The first row is the header; the second is an example."""
    from fastapi.responses import Response
    await _require_operator_org(user)
    rows = [
        ("member_number", "first_name", "last_name", "email", "mobile",
         "address_line1", "address_line2", "city", "postcode", "dob",
         "plan_name", "joined_date"),
        ("M-1001", "Emma", "Wright", "emma.wright@example.com", "+447700900100",
         "12 High Street", "", "London", "SW1A 1AA", "1990-04-22",
         "Monthly Unlimited", "2026-01-15"),
    ]
    body = "\n".join(",".join(f'"{c}"' for c in row) for row in rows) + "\n"
    return Response(
        content=body, media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="members-import-template.csv"'},
    )


@router.post("/memberships/members/bulk-import", dependencies=[Depends(require_module("memberships"))])
async def members_bulk_import(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Bulk-create members from a CSV. Required: first_name + last_name +
    (email OR mobile). Plan name is matched (case-insensitive) against this
    org's existing membership_plans; unknown plans skip the assignment but
    still create the member.

    Returns per-row results so the operator can fix the bad rows and re-upload.
    """
    import csv as _csv
    import io as _io
    org_id = await _require_operator_org(user)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    reader = _csv.DictReader(_io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV is empty or missing a header row")
    # Normalise headers (case-insensitive, snake_case)
    norm = {f: (f or "").strip().lower().replace(" ", "_") for f in reader.fieldnames}

    plans = await db.membership_plans.find(
        {"organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(200)
    plan_by_name = {(p.get("name") or "").lower().strip(): p["id"] for p in plans}

    created = 0
    skipped = 0
    rows_report: list[dict] = []
    seen_emails: set[str] = set()

    for idx, raw_row in enumerate(reader, start=2):
        row = {norm[k]: (v or "").strip() for k, v in raw_row.items() if k}
        first = row.get("first_name") or ""
        last = row.get("last_name") or ""
        email = (row.get("email") or "").lower()
        mobile = row.get("mobile") or row.get("phone") or ""
        plan_name = row.get("plan_name") or ""

        if not first or not last:
            rows_report.append({"row": idx, "ok": False, "reason": "missing first_name or last_name"})
            skipped += 1
            continue
        if not email and not mobile:
            rows_report.append({"row": idx, "ok": False, "reason": "row needs email OR mobile"})
            skipped += 1
            continue
        if email and email in seen_emails:
            rows_report.append({"row": idx, "ok": False, "reason": f"duplicate email '{email}' earlier in file"})
            skipped += 1
            continue
        if email:
            seen_emails.add(email)
            existing = await db.members.find_one({"email": email}, {"_id": 0, "id": 1})
            if existing:
                rows_report.append({"row": idx, "ok": False, "reason": "email already registered"})
                skipped += 1
                continue

        member = {
            "id": _uuid(),
            "email": email or None,
            "password": pwd_ctx.hash(secrets.token_urlsafe(16)) if email else None,
            "first_name": sanitise_string(first),
            "last_name": sanitise_string(last),
            "phone": mobile or None,
            "organization_id": org_id,
            "account_type": "member",
            "status": "active",
            "member_number": row.get("member_number") or None,
            "address": {
                "line1": row.get("address_line1") or None,
                "line2": row.get("address_line2") or None,
                "city": row.get("city") or None,
                "postcode": (row.get("postcode") or "").upper() or None,
            } if any(row.get(k) for k in ("address_line1", "address_line2", "city", "postcode")) else None,
            "date_of_birth": row.get("dob") or None,
            "joined_at": row.get("joined_date") or _now_iso(),
            "no_show_count": 0,
            "lifetime_value_pence": 0,
            "tags": ["bulk_import"],
            "imported_at": _now_iso(),
            "imported_by": user.get("id"),
            "created_at": _now_iso(),
        }
        await db.members.insert_one(member)
        if email:
            await db.qr_rotation_secret.insert_one({
                "member_id": member["id"], "secret_b32": pyotp.random_base32(),
                "created_at": _now_iso(),
            })
        plan_assigned = False
        if plan_name:
            plan_id = plan_by_name.get(plan_name.lower().strip())
            if plan_id:
                await db.member_memberships.insert_one({
                    "id": _uuid(), "member_id": member["id"], "plan_id": plan_id,
                    "organization_id": org_id, "status": "active",
                    "joined_at": _now_iso(), "via": "bulk_import",
                })
                plan_assigned = True
        rows_report.append({
            "row": idx, "ok": True, "member_id": member["id"],
            "name": f"{first} {last}",
            "plan_assigned": plan_assigned,
            "plan_unmatched": bool(plan_name) and not plan_assigned,
        })
        created += 1

    return {"created": created, "skipped": skipped, "total": created + skipped, "rows": rows_report}


@router.post("/memberships/members", dependencies=[Depends(require_module("memberships"))])
async def members_create(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    email = (body.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(400, "email required")
    # Iter 216h200 — Craig's screenshot called out missing format
    # validation. Enforce a basic RFC-5322-ish email pattern server-side
    # so a typo'd address doesn't silently land in the DB.
    import re as _re
    if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Invalid email format")
    # Iter 216h200 — phone is now mandatory (PT visit, fault alerts,
    # SOS calls all rely on it). Strip whitespace before validating.
    phone = (body.get("phone") or "").strip()
    if not phone:
        raise HTTPException(400, "phone required")
    # Iter 216h200 — emergency contact phone is now mandatory on create
    # (gym duty-of-care: a member can't sign up without an in-case-of-
    # accident number on file).
    eg_phone = (body.get("emergency_contact_phone") or "").strip()
    if not eg_phone:
        raise HTTPException(400, "emergency_contact_phone required")
    # Iter 216h200 — GDPR consent. Must explicitly accept T&Cs.
    # Marketing consent stored separately so we can honour opt-outs
    # (defaults to False if absent — never opt people in by accident).
    if not bool(body.get("gdpr_consent")):
        raise HTTPException(400, "GDPR consent (T&Cs acceptance) required")
    if await db.members.find_one({"email": email}):
        raise HTTPException(409, "Email already registered")

    # Iter 215bq — Add member captures the full record (parity with the
    # edit drawer). Validate parent_member_id (if supplied) the same way
    # the PATCH handler does so child memberships can be linked at
    # creation time without a follow-up PATCH.
    parent_member_id = body.get("parent_member_id")
    if parent_member_id:
        parent = await db.members.find_one(
            {"id": parent_member_id, "organization_id": org_id},
            {"_id": 0, "id": 1},
        )
        if not parent:
            raise HTTPException(404, "Parent member not found in this org")

    raw_tags = body.get("tags") or []
    tags = []
    if isinstance(raw_tags, list):
        tags = [sanitise_string(t)[:40] for t in raw_tags if isinstance(t, str)][:30]

    member = {
        "id": _uuid(),
        "email": email,
        "password": pwd_ctx.hash(secrets.token_urlsafe(16)),  # placeholder — member sets via magic link
        "first_name": sanitise_string(body.get("first_name") or "—"),
        "last_name": sanitise_string(body.get("last_name") or ""),
        "phone": phone,
        "organization_id": org_id,
        "site_id": body.get("site_id"),
        "account_type": "member",
        "status": "active",
        "tags": tags,
        "no_show_count": 0,
        "lifetime_value_pence": 0,
        "created_at": _now_iso(),
        "created_by_operator": user.get("id"),
        # Iter 215bq — extended profile fields, all optional.
        "dob": body.get("dob") or None,
        "address_line1": sanitise_string(body.get("address_line1") or ""),
        "address_line2": sanitise_string(body.get("address_line2") or ""),
        "city": sanitise_string(body.get("city") or ""),
        "postcode": sanitise_string(body.get("postcode") or "").upper(),
        "country": sanitise_string(body.get("country") or ""),
        "emergency_contact_name": sanitise_string(body.get("emergency_contact_name") or ""),
        "emergency_contact_phone": eg_phone,
        "notes": sanitise_string(body.get("notes") or ""),
        "parent_member_id": parent_member_id or None,
        # Iter 216h200 — GDPR consent (T&Cs is mandatory, marketing is opt-in).
        "gdpr_consent": True,
        "gdpr_consent_at": _now_iso(),
        "gdpr_consent_actor_id": user.get("id"),
        "marketing_consent": bool(body.get("marketing_consent")),
        "marketing_consent_at": _now_iso() if body.get("marketing_consent") else None,
    }
    await db.members.insert_one(member)
    await db.qr_rotation_secret.insert_one({
        "member_id": member["id"],
        "secret_b32": pyotp.random_base32(),
        "created_at": _now_iso(),
    })
    # Iter 215bx — auto-mirror new members into CRM v2 so retention /
    # corporate-sales pipelines have visibility from day one. Best-effort:
    # CRM may not be enabled on the org's plan, in which case the helper
    # silently inserts into crm2_contacts which is gated by the CRM
    # module on read so the data is harmless until activation.
    try:
        from utils.crm_sync import upsert_crm_contact, upsert_crm_company
        employer = sanitise_string(body.get("employer") or "")
        company_id = None
        if employer:
            company_id = await upsert_crm_company(
                org_id, name=employer, source="memberships",
            )
        if member.get("email"):
            await upsert_crm_contact(
                org_id,
                email=member["email"],
                first_name=member.get("first_name"),
                last_name=member.get("last_name"),
                phone=member.get("phone"),
                source="memberships:new_member",
                lifecycle="Customer",
                tags=["memberships", "new_member"],
                company_id=company_id,
                company_name=employer or None,
                custom_fields={
                    "memberships_member_id": member["id"],
                    "job_title": sanitise_string(body.get("job_title") or "") or None,
                },
            )
    except Exception as exc:
        # Never block member creation on CRM mirror.
        logger.info("CRM mirror for new member failed (non-fatal): %s", exc)

    # Iter 215d4 — activation funnel event. Best-effort, never raises.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            org_id, "first_member_added",
            trigger_user_id=user.get("id"),
            payload={"member_id": member["id"]},
        )
    except Exception:
        pass
    return {"member": _public_member(member)}


@router.get("/memberships/members/{member_id}", dependencies=[Depends(require_module("memberships"))])
async def members_get(member_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    m = await _load_member(member_id, org_id)
    memberships = await db.member_memberships.find({"member_id": member_id}, {"_id": 0}).sort("joined_at", -1).to_list(50)
    for mm in memberships:
        plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0, "name": 1, "kind": 1})
        mm["plan"] = plan
    recent_bookings = await db.bookings.find({"member_id": member_id}, {"_id": 0}).sort("booked_at", -1).limit(20).to_list(20)
    for b in recent_bookings:
        occ = await db.class_occurrences.find_one({"id": b["occurrence_id"]}, {"_id": 0, "name": 1, "starts_at": 1})
        b["occurrence"] = occ
    return {"member": _public_member(m), "memberships": memberships, "recent_bookings": recent_bookings}


# Iter 215bk — full member profile editor.
# Whitelisted fields the operator-side member edit drawer can update.
# Phone, address fields, DOB (calculates age in UI), emergency contact, link
# to a parent member (for child memberships), and freeform tags / notes.
_MEMBER_PATCH_ALLOWED = {
    "first_name", "last_name", "phone", "email",
    "address_line1", "address_line2", "city", "postcode", "country",
    "dob", "emergency_contact_name", "emergency_contact_phone",
    "parent_member_id", "notes", "tags",
}


@router.patch("/memberships/members/{member_id}", dependencies=[Depends(require_module("memberships"))])
async def members_patch(
    member_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Update an operator-managed member record. Pulled out into PATCH so the
    new MemberDetailDrawer (iter 215bk) can edit Profile / Family fields without
    needing a per-field endpoint per attribute."""
    org_id = await _require_operator_org(user)
    await _load_member(member_id, org_id)  # 404 if not in this org
    updates: dict = {}
    for key, val in (body or {}).items():
        if key not in _MEMBER_PATCH_ALLOWED:
            continue
        if key == "email":
            new_email = (val or "").strip().lower()
            if not new_email:
                continue
            # No clash with another member of any org
            clash = await db.members.find_one(
                {"email": new_email, "id": {"$ne": member_id}},
                {"_id": 0, "id": 1},
            )
            if clash:
                raise HTTPException(409, "Email already registered to another member")
            updates["email"] = new_email
        elif key == "parent_member_id" and val:
            # Ensure parent exists and belongs to the same org
            parent = await db.members.find_one(
                {"id": val, "organization_id": org_id}, {"_id": 0, "id": 1, "first_name": 1},
            )
            if not parent:
                raise HTTPException(404, "Parent member not found in this org")
            if val == member_id:
                raise HTTPException(400, "A member cannot be their own parent")
            updates["parent_member_id"] = val
        elif key == "tags":
            if isinstance(val, list):
                updates["tags"] = [sanitise_string(t)[:40] for t in val if isinstance(t, str)][:30]
        elif key == "dob" and val:
            # Accept ISO date string; store as-is, frontend formats it.
            updates["dob"] = val
        elif key in {"first_name", "last_name", "phone",
                     "address_line1", "address_line2", "city", "postcode",
                     "country", "emergency_contact_name", "emergency_contact_phone",
                     "notes"}:
            updates[key] = sanitise_string(val) if isinstance(val, str) else val
    # Allow explicit null clears for parent_member_id and dob
    if body.get("parent_member_id") in (None, ""):
        updates["parent_member_id"] = None

    if updates:
        updates["updated_at"] = _now_iso()
        await db.members.update_one({"id": member_id}, {"$set": updates})

    fresh = await _load_member(member_id, org_id)
    return {"member": _public_member(fresh)}


@router.get(
    "/memberships/members/{member_id}/payments",
    dependencies=[Depends(require_module("memberships"))],
)
async def members_payments(member_id: str, user: dict = Depends(get_current_user)):
    """Iter 215bk — payments + invoices history for the member edit drawer."""
    org_id = await _require_operator_org(user)
    await _load_member(member_id, org_id)
    payments = await db.payments.find(
        {"member_id": member_id, "organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).limit(50).to_list(50)
    invoices = await db.invoices.find(
        {"member_id": member_id, "organization_id": org_id}, {"_id": 0},
    ).sort("issued_at", -1).limit(50).to_list(50)
    total_paid = sum(int(p.get("amount_pence") or 0) for p in payments if (p.get("status") or "").lower() in {"paid", "succeeded", "captured"})
    outstanding = sum(int(i.get("amount_pence") or 0) for i in invoices if (i.get("status") or "").lower() not in {"paid", "void"})
    return {
        "payments": payments,
        "invoices": invoices,
        "totals": {"paid_pence": total_paid, "outstanding_pence": outstanding},
    }


@router.get(
    "/memberships/members/{member_id}/children",
    dependencies=[Depends(require_module("memberships"))],
)
async def members_children(member_id: str, user: dict = Depends(get_current_user)):
    """Iter 215bk — return members whose `parent_member_id` is this member.
    Used by the Family tab in the member edit drawer."""
    org_id = await _require_operator_org(user)
    await _load_member(member_id, org_id)
    children = await db.members.find(
        {"organization_id": org_id, "parent_member_id": member_id},
        {"_id": 0, "password": 0},
    ).sort("first_name", 1).to_list(100)
    return {"children": [_public_member(c) for c in children]}


@router.post("/memberships/members/{member_id}/assign-plan", dependencies=[Depends(require_module("memberships"))])
async def members_assign_plan(member_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    await _load_member(member_id, org_id)  # 404 if not on this org
    plan_id = body.get("plan_id")
    plan = await db.membership_plans.find_one({"id": plan_id, "organization_id": org_id}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Plan not found")
    # Iter 216h200 — Idempotency fix (Craig's screenshot showed 3x
    # "Assigned plan 'Gym Membership'" in the activity feed). Clicking
    # the assign button twice on the same plan previously created two
    # rows + two audit-log entries. Now we no-op when an open (active /
    # frozen / pending_payment) row already exists for this plan.
    existing = await db.member_memberships.find_one(
        {"member_id": member_id,
         "plan_id": plan_id,
         "status": {"$in": ["active", "frozen", "pending_payment"]}},
        {"_id": 0},
    )
    if existing:
        return {
            "membership": existing,
            "requires_payment": existing.get("status") == "pending_payment",
            "idempotent": True,
        }
    # Cancel any currently-open membership on a DIFFERENT plan. Now
    # also retires pending_payment rows (previously left orphaned, which
    # caused the audit-log to accumulate stale "Assigned" entries).
    await db.member_memberships.update_many(
        {"member_id": member_id,
         "status": {"$in": ["active", "frozen", "pending_payment"]}},
        {"$set": {"status": "cancelled", "cancel_effective_date": _now_iso(),
                  "cancel_reason": "replaced_by_new_plan"}},
    )
    now = datetime.now(timezone.utc)
    end_date = None
    if plan["kind"] == "fixed_term" and plan.get("duration_days"):
        end_date = (now + timedelta(days=int(plan["duration_days"]))).isoformat()
    mm = {
        "id": _uuid(),
        "member_id": member_id,
        "plan_id": plan_id,
        "organization_id": org_id,
        "status": "active" if plan["kind"] != "recurring" else "pending_payment",
        "start_date": now.isoformat(),
        "end_date": end_date,
        "billing_status": "pending",
        "credits_remaining": plan.get("credits_count") or 0,
        "credits_used": 0,
        "joined_at": now.isoformat(),
        "next_billing_at": None if plan["kind"] != "recurring" else (
            now + (timedelta(days=365) if plan.get("billing_cycle") == "annual" else timedelta(days=30))
        ).isoformat(),
        "audit_log": [{"at": _now_iso(), "actor_id": user.get("id"), "action": "assigned", "plan_name": plan["name"]}],
    }
    await db.member_memberships.insert_one(mm)
    await db.members.update_one({"id": member_id}, {"$set": {"status": "active"}})
    return {"membership": {k: v for k, v in mm.items() if k != "_id"}, "requires_payment": plan["kind"] == "recurring"}


@router.post("/memberships/members/{member_id}/freeze", dependencies=[Depends(require_module("memberships"))])
async def members_freeze(member_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    days = int(body.get("days", 30))
    mm = await db.member_memberships.find_one({"member_id": member_id, "organization_id": org_id, "status": "active"}, {"_id": 0})
    if not mm:
        raise HTTPException(404, "No active membership")
    plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0})
    if plan and not plan.get("freeze_allowed", True):
        raise HTTPException(400, "This plan does not allow freezes")
    if plan and days > plan.get("freeze_max_days", 90):
        raise HTTPException(400, f"Max freeze is {plan.get('freeze_max_days', 90)} days")
    now = datetime.now(timezone.utc)
    frozen_until = (now + timedelta(days=days)).isoformat()
    await db.member_memberships.update_one(
        {"id": mm["id"]},
        {"$set": {"status": "frozen", "frozen_from": now.isoformat(), "frozen_until": frozen_until},
         "$push": {"audit_log": {"at": _now_iso(), "actor_id": user.get("id"), "action": "frozen", "days": days}}},
    )
    return {"ok": True, "frozen_until": frozen_until}


@router.post("/memberships/members/{member_id}/cancel", dependencies=[Depends(require_module("memberships"))])
async def members_cancel(member_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    mm = await db.member_memberships.find_one({"member_id": member_id, "organization_id": org_id, "status": {"$in": ["active", "frozen"]}}, {"_id": 0})
    if not mm:
        raise HTTPException(404, "No active membership")
    plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0})
    notice = int((plan or {}).get("cancel_notice_days", 30))
    effective = (datetime.now(timezone.utc) + timedelta(days=notice)).isoformat()
    immediate = bool(body.get("immediate", False))
    update = {
        "cancel_effective_date": _now_iso() if immediate else effective,
        "cancel_reason": body.get("reason", "member_request"),
    }
    if immediate:
        update["status"] = "cancelled"
    else:
        update["billing_status"] = "cancelled_future"
    await db.member_memberships.update_one({"id": mm["id"]},
        {"$set": update,
         "$push": {"audit_log": {"at": _now_iso(), "actor_id": user.get("id"), "action": "cancel_requested", "immediate": immediate}}})
    if immediate:
        await db.members.update_one({"id": member_id}, {"$set": {"status": "cancelled"}})
    return {"ok": True, "effective": update["cancel_effective_date"]}


# ═════════════════════ Class templates + occurrences ═════════════════════


# ═════════════ Parent / member portal invite (iter 216ak · G5) ═════════════

_INVITE_TTL_DAYS = 21


@router.post(
    "/memberships/members/{member_id}/invite-portal",
    dependencies=[Depends(require_module("memberships"))],
)
async def invite_member_portal(
    member_id: str,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Operator-triggered — email the member a magic-link that lets them
    set a password and sign into the parent/member portal.

    Idempotent: calling twice re-issues a fresh token (old tokens die).
    Body (optional):
      { "note": "See you Saturday!" }  — appended to the email.

    Stamps `members.portal_invited_at` + `portal_invite_token_hash` so
    the onboarding checklist's `invite_portal` step flips to done.
    """
    import hashlib
    import os as _os
    from utils.email import send_email

    org_id = await _require_operator_org(user)
    m = await db.members.find_one(
        {"id": member_id, "organization_id": org_id}, {"_id": 0},
    )
    if not m:
        raise HTTPException(404, "Member not found")
    if not m.get("email"):
        raise HTTPException(400, "Add an email on the member before inviting them")

    token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(days=_INVITE_TTL_DAYS)).isoformat()

    await db.members.update_one(
        {"id": member_id},
        {"$set": {
            "portal_invited_at": _now_iso(),
            "portal_invited_by": user.get("id"),
            "portal_invite_token_hash": token_hash,
            "portal_invite_expires_at": expires,
            "portal_access_enabled": True,
        }},
    )

    # Sprint C — log to memberships_member_events so the activity
    # timeline can surface every invite (single + bulk) uniformly.
    try:
        await db.memberships_member_events.insert_one({
            "id": _uuid(),
            "organization_id": org_id,
            "member_id": member_id,
            "kind": "portal_invited",
            "actor_id": user.get("id"),
            "actor_email": user.get("email"),
            "at": _now_iso(),
        })
    except Exception:
        pass

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1, "primary_color": 1, "slug": 1,
                         "membership_app_slug": 1, "logo_url": 1},
    ) or {}
    # Resolve site-level branding so multi-site operators send the venue's
    # name + colour (iter 216af/ag groundwork re-used).
    from routes.sites import _effective_site_branding
    site_doc = None
    if m.get("site_id"):
        site_doc = await db.sites.find_one(
            {"id": m["site_id"], "organization_id": org_id}, {"_id": 0},
        )
    eff = _effective_site_branding(org, site_doc)
    brand_name = eff.get("name") or org.get("name") or "Your studio"
    primary = eff.get("primary_color") or "#19CDFF"

    frontend = (
        _os.environ.get("FRONTEND_URL")
        or _os.environ.get("REACT_APP_BACKEND_URL")
        or "https://gymaxisai.com"
    ).rstrip("/")
    slug = org.get("membership_app_slug") or org.get("slug") or org_id
    claim_url = f"{frontend}/m/{slug}/claim?t={token}"

    note_line = ""
    raw_note = (body or {}).get("note")
    if isinstance(raw_note, str) and raw_note.strip():
        safe = sanitise_string(raw_note)[:300]
        note_line = f"<p style='background:rgba(255,255,255,0.05);padding:10px 14px;border-left:3px solid {primary};border-radius:6px;font-size:13px'><em>{safe}</em></p>"

    first = sanitise_string(m.get("first_name") or "there")
    html = (
        f"<div style='font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;color:#0A0C10'>"
        f"<div style='background:{primary};padding:22px 26px;border-radius:12px 12px 0 0'>"
        f"<h1 style='margin:0;font-size:22px'>Welcome to {brand_name}</h1></div>"
        f"<div style='padding:24px;background:#0A0C10;color:#fff;border-radius:0 0 12px 12px'>"
        f"<p>Hi {first},</p>"
        f"<p>Your studio has set up a portal account for you. Tap the button below to set your password and start booking classes, managing your family, and paying invoices on your phone.</p>"
        f"{note_line}"
        f"<p style='margin:24px 0'>"
        f"<a href='{claim_url}' style='display:inline-block;background:{primary};color:#0A0C10;padding:14px 26px;border-radius:999px;text-decoration:none;font-weight:800;font-size:15px'>Set up my portal →</a>"
        f"</p>"
        f"<p style='opacity:0.6;font-size:12px'>This link expires in {_INVITE_TTL_DAYS} days. If you weren't expecting this, you can safely ignore the email.</p>"
        f"</div></div>"
    )
    sent = await send_email(m["email"], f"Your {brand_name} portal is ready", html)

    return {
        "ok": True,
        "member_id": member_id,
        "email": m["email"],
        "expires_at": expires,
        "email_sent": bool(sent),
        "claim_url": claim_url,  # returned so operators can copy-paste if email bounces
    }


@router.post(
    "/memberships/members/{member_id}/revoke-portal",
    dependencies=[Depends(require_module("memberships"))],
)
async def revoke_member_portal(member_id: str, user: dict = Depends(get_current_user)):
    """Kill switch — invalidates any outstanding invite token and blocks
    portal sign-in. Used for disputed accounts, offboarded parents, etc."""
    org_id = await _require_operator_org(user)
    res = await db.members.update_one(
        {"id": member_id, "organization_id": org_id},
        {"$set": {
            "portal_access_enabled": False,
            "portal_invite_token_hash": None,
            "portal_invite_revoked_at": _now_iso(),
            "portal_invite_revoked_by": user.get("id"),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Member not found")
    return {"ok": True}

