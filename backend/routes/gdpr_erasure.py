"""GDPR Article 17 — Right-to-erasure workflow.

Master-admin-only workflow for fulfilling a Data Subject Erasure
Request ("right to be forgotten") against any of the three PII-bearing
record types in the platform:

  * ``member``      → ``db.members``
  * ``instructor``  → ``db.membership_instructors``
  * ``crm_contact`` → ``db.crm2_contacts``

We do **not** hard-delete the row (Art. 17(3)(b) — legal/financial
records). Instead we anonymise PII in place:

  * names → ``[REDACTED]``
  * email → ``erased+{sha8}@gdpr.local``
  * phone / mobile / emergency phone → ``None``
  * dob / address / postcode / notes → ``None`` / ``""``

The original row keeps its ``id`` so linked invoices, bookings,
opportunities and audit logs stay referentially intact.

Workflow:

  1. ``POST /api/gdpr/erasure/preview`` — preview what would be
     scrubbed and which fields will survive.
  2. ``POST /api/gdpr/erasure/requests`` — file a request. Status
     starts as ``pending`` with a 30-day ``execute_after`` deadline
     (UK ICO guidance). The request is reversible until executed.
  3. ``POST /api/gdpr/erasure/requests/{id}/execute`` — performs the
     scrub. Master-admin only. Honours the 30-day cooling-off window
     unless ``force=True`` is passed (used by the operator to fast-
     track at the data subject's explicit request).
  4. ``POST /api/gdpr/erasure/requests/{id}/cancel`` — cancels a
     pending request before execution.
  5. ``GET  /api/gdpr/erasure/requests`` — paginated list with
     optional ``status`` filter.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/api/gdpr/erasure", tags=["gdpr-erasure"])


# ── Constants ────────────────────────────────────────────────────

SUBJECT_TYPES = ("member", "instructor", "crm_contact")
COOLING_OFF_DAYS = 30

# Subject-type → collection + PII spec.
#   - ``hashable``: fields that get replaced with deterministic hashes
#     (e.g. email — so we can still detect re-import attempts).
#   - ``redact``: fields replaced with ``[REDACTED]`` placeholder.
#   - ``clear``: fields set to ``None`` (numeric/date/free-text).
_SUBJECT_SPEC = {
    "member": {
        "collection": "members",
        "id_field": "id",
        "hashable": ("email",),
        "redact": ("first_name", "last_name"),
        "clear": (
            "phone", "mobile", "dob", "address_line1", "address_line2",
            "city", "postcode", "country",
            "emergency_contact_name", "emergency_contact_phone",
            "notes", "photo_url",
        ),
    },
    "instructor": {
        "collection": "membership_instructors",
        "id_field": "id",
        "hashable": ("email",),
        "redact": ("name", "first_name", "last_name"),
        "clear": (
            "phone", "mobile", "dob", "address_line1", "address_line2",
            "city", "postcode", "country", "headline", "bio",
            "specialties", "photo_url",
        ),
    },
    "crm_contact": {
        "collection": "crm2_contacts",
        "id_field": "id",
        "hashable": ("email",),
        "redact": ("first_name", "last_name"),
        "clear": (
            "phone", "mobile", "dob", "address_line1", "address_line2",
            "city", "postcode", "country", "job_title", "notes",
            "linkedin_url", "twitter_url", "photo_url",
        ),
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(403, "GDPR erasure workflow is master-admin only.")


def _spec(subject_type: str) -> dict:
    if subject_type not in _SUBJECT_SPEC:
        raise HTTPException(
            400,
            f"Unsupported subject_type. Expected one of {list(SUBJECT_TYPES)}.",
        )
    return _SUBJECT_SPEC[subject_type]


def _email_hash(email: str | None) -> str | None:
    if not email:
        return None
    digest = hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()[:8]
    return f"erased+{digest}@gdpr.local"


def _scrub_summary(spec: dict, subject: dict) -> dict:
    """Build a preview-friendly summary of what *would* change without
    touching the DB. Surfaces both current (truncated) PII and the
    planned post-scrub value so the master admin can audit before
    pressing Execute."""
    plan = {}
    for f in spec["redact"]:
        before = subject.get(f)
        if before is None:
            continue
        plan[f] = {"before": str(before)[:50], "after": "[REDACTED]"}
    for f in spec["hashable"]:
        before = subject.get(f)
        if not before:
            continue
        plan[f] = {"before": str(before), "after": _email_hash(before)}
    for f in spec["clear"]:
        before = subject.get(f)
        if before in (None, "", [], {}):
            continue
        plan[f] = {"before": str(before)[:50], "after": None}
    return plan


# ── Pydantic models ──────────────────────────────────────────────

class PreviewPayload(BaseModel):
    subject_type: str
    subject_id: str


class CreateRequestPayload(BaseModel):
    subject_type: str
    subject_id: str
    reason: str = Field(default="", max_length=1000)


class ExecutePayload(BaseModel):
    force: bool = False  # bypass 30-day cooling window


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/preview")
async def preview_erasure(
    payload: PreviewPayload,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    spec = _spec(payload.subject_type)
    subject = await db[spec["collection"]].find_one(
        {spec["id_field"]: payload.subject_id}, {"_id": 0},
    )
    if not subject:
        raise HTTPException(404, "Subject not found")
    return {
        "subject_type": payload.subject_type,
        "subject_id": payload.subject_id,
        "label": _label_for(payload.subject_type, subject),
        "already_erased": bool(subject.get("gdpr_erased")),
        "plan": _scrub_summary(spec, subject),
        "retains": _retained_fields(payload.subject_type),
    }


@router.post("/requests")
async def create_request(
    payload: CreateRequestPayload,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    spec = _spec(payload.subject_type)
    subject = await db[spec["collection"]].find_one(
        {spec["id_field"]: payload.subject_id}, {"_id": 0},
    )
    if not subject:
        raise HTTPException(404, "Subject not found")
    if subject.get("gdpr_erased"):
        raise HTTPException(400, "Subject already erased")

    # Reject if there's already a pending request for the same subject —
    # prevents accidental duplicates and keeps the audit trail clean.
    existing = await db.gdpr_erasure_requests.find_one({
        "subject_type": payload.subject_type,
        "subject_id": payload.subject_id,
        "status": "pending",
    }, {"_id": 0})
    if existing:
        raise HTTPException(
            409,
            "A pending erasure request already exists for this subject.",
        )

    now_dt = datetime.now(timezone.utc)
    request = {
        "id": _id(),
        "organization_id": user.get("organization_id"),
        "subject_type": payload.subject_type,
        "subject_id": payload.subject_id,
        "subject_label": _label_for(payload.subject_type, subject),
        "reason": payload.reason,
        "status": "pending",
        "requested_by": user.get("id"),
        "requested_by_email": user.get("email"),
        "requested_at": now_dt.isoformat(),
        "execute_after": (now_dt + timedelta(days=COOLING_OFF_DAYS)).isoformat(),
        "executed_at": None,
        "executed_by": None,
        "cancelled_at": None,
        "cancelled_by": None,
        "scrub_summary": None,
    }
    await db.gdpr_erasure_requests.insert_one(request)
    return {k: v for k, v in request.items() if k != "_id"}


@router.get("/requests")
async def list_requests(
    status: Optional[str] = None,
    subject_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    q: dict = {}
    if status:
        q["status"] = status
    if subject_type:
        q["subject_type"] = subject_type
    total = await db.gdpr_erasure_requests.count_documents(q)
    items = await db.gdpr_erasure_requests.find(
        q, {"_id": 0},
    ).sort("requested_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"requests": items, "total": total}


@router.get("/requests/{request_id}")
async def get_request(
    request_id: str,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    req = await db.gdpr_erasure_requests.find_one(
        {"id": request_id}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Request not found")
    # Refresh the plan in case the subject changed between request +
    # execution windows (e.g. a CRM contact got a new phone number that
    # also needs scrubbing).
    spec = _spec(req["subject_type"])
    subject = await db[spec["collection"]].find_one(
        {spec["id_field"]: req["subject_id"]}, {"_id": 0},
    )
    if subject and req["status"] == "pending":
        req["plan"] = _scrub_summary(spec, subject)
    return req


@router.post("/requests/{request_id}/execute")
async def execute_request(
    request_id: str,
    payload: ExecutePayload,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    req = await db.gdpr_erasure_requests.find_one(
        {"id": request_id}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "pending":
        raise HTTPException(
            400, f"Request is not pending (current status: {req['status']}).",
        )

    # Cooling-off window enforcement.
    if not payload.force:
        execute_after = datetime.fromisoformat(req["execute_after"])
        if datetime.now(timezone.utc) < execute_after:
            raise HTTPException(
                400,
                f"Cooling-off window not yet elapsed (executes after "
                f"{req['execute_after']}). Pass force=true to fast-track.",
            )

    spec = _spec(req["subject_type"])
    subject = await db[spec["collection"]].find_one(
        {spec["id_field"]: req["subject_id"]}, {"_id": 0},
    )
    if not subject:
        # The row has been deleted out from under us — still mark the
        # request executed so it's not stuck in pending forever.
        scrub_summary = {"note": "Subject row not found at execution time"}
    else:
        scrub_summary = _scrub_summary(spec, subject)
        updates: dict = {
            "gdpr_erased": True,
            "gdpr_erased_at": _now(),
            "gdpr_erased_by": user.get("id"),
            "gdpr_erasure_request_id": req["id"],
        }
        for f in spec["redact"]:
            if subject.get(f) is not None:
                updates[f] = "[REDACTED]"
        for f in spec["hashable"]:
            if subject.get(f):
                updates[f] = _email_hash(subject[f])
        for f in spec["clear"]:
            if subject.get(f) not in (None, "", [], {}):
                updates[f] = None
        await db[spec["collection"]].update_one(
            {spec["id_field"]: req["subject_id"]},
            {"$set": updates},
        )

    await db.gdpr_erasure_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "executed",
            "executed_at": _now(),
            "executed_by": user.get("id"),
            "scrub_summary": scrub_summary,
            "forced": bool(payload.force),
        }},
    )
    return {
        "id": request_id,
        "status": "executed",
        "scrub_summary": scrub_summary,
    }


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    req = await db.gdpr_erasure_requests.find_one(
        {"id": request_id}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "pending":
        raise HTTPException(
            400,
            f"Only pending requests can be cancelled (current status: {req['status']}).",
        )
    await db.gdpr_erasure_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": _now(),
            "cancelled_by": user.get("id"),
        }},
    )
    return {"id": request_id, "status": "cancelled"}


# ── Helpers ──────────────────────────────────────────────────────

def _label_for(subject_type: str, subject: dict) -> str:
    """Human-friendly label used in the request list + emails. Falls
    back to the id when nothing PII-shaped is on the record (e.g.
    already-erased subject re-previewed)."""
    if subject_type == "instructor":
        return (
            subject.get("name")
            or f"{subject.get('first_name', '')} {subject.get('last_name', '')}".strip()
            or subject.get("id", "")
        )
    return (
        f"{subject.get('first_name', '')} {subject.get('last_name', '')}".strip()
        or subject.get("email")
        or subject.get("id", "")
    )


def _retained_fields(subject_type: str) -> list[str]:
    """Whitelist of fields that survive erasure (Art. 17(3)(b) —
    financial / legal records). Surfaced in the preview so the operator
    can explain to the data subject exactly what is being kept."""
    common = [
        "id", "organization_id", "site_id", "status", "created_at",
        "updated_at",
    ]
    if subject_type == "member":
        return common + [
            "member_number", "lifetime_value_pence", "no_show_count",
            "subscription_id", "stripe_customer_id",
        ]
    if subject_type == "instructor":
        return common + ["slug", "is_active"]
    return common + ["company_id", "owner_id", "lead_status"]
