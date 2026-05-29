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
from utils.security_plus import audit_required

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


class CancelPayload(BaseModel):
    # Iter 220bq — ICO best practice: persist a cancellation reason so
    # the auditable trail captures *why* a pending erasure was killed.
    reason: str = Field(default="", max_length=1000)


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
    # Iter 220bq — fail-closed audit log so the regulator-grade trail
    # cannot silently drop a request. Same retry semantics as the
    # rest of the audit_required call sites.
    await audit_required("gdpr_erasure_audit", {
        "request_id": request["id"],
        "event": "request_created",
        "subject_type": payload.subject_type,
        "subject_id": payload.subject_id,
        "subject_label": request["subject_label"],
        "requested_by": user.get("id"),
        "requested_by_email": user.get("email"),
        "reason": payload.reason,
        "execute_after": request["execute_after"],
    })
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


async def _execute_request_impl(req: dict, *, force: bool, executed_by: str,
                                 executed_by_label: str | None = None) -> dict:
    """Core executor — used by both the manual ``/execute`` endpoint
    and the daily auto-execute background loop. Captures a pre-scrub
    PII snapshot inside the request row, then anonymises the subject.

    Returns the updated request document.
    """
    if req["status"] != "pending":
        raise HTTPException(
            400, f"Request is not pending (current status: {req['status']}).",
        )
    if not force:
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
    pre_scrub_snapshot: dict | None = None
    if not subject:
        scrub_summary = {"note": "Subject row not found at execution time"}
    else:
        # Iter 220bq — capture the full pre-scrub PII payload so the
        # org keeps an auditable "what was erased" record AFTER the
        # canonical row has lost the data. Stored on the request, not
        # the subject — and only the fields that this spec actually
        # touches (no need to snapshot e.g. internal counters).
        pre_scrub_snapshot = {
            f: subject.get(f) for f in
            list(spec["redact"]) + list(spec["hashable"]) + list(spec["clear"])
            if subject.get(f) not in (None, "", [], {})
        }
        scrub_summary = _scrub_summary(spec, subject)
        updates: dict = {
            "gdpr_erased": True,
            "gdpr_erased_at": _now(),
            "gdpr_erased_by": executed_by,
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
        {"id": req["id"]},
        {"$set": {
            "status": "executed",
            "executed_at": _now(),
            "executed_by": executed_by,
            "executed_by_label": executed_by_label or executed_by,
            "scrub_summary": scrub_summary,
            "pre_scrub_snapshot": pre_scrub_snapshot,
            "forced": bool(force),
        }},
    )
    # Iter 220bq — fail-closed audit trail.
    await audit_required("gdpr_erasure_audit", {
        "request_id": req["id"],
        "event": "request_executed",
        "subject_type": req.get("subject_type"),
        "subject_id": req.get("subject_id"),
        "subject_label": req.get("subject_label"),
        "executed_by": executed_by,
        "executed_by_label": executed_by_label,
        "forced": bool(force),
        "scrub_summary_keys": sorted(list((scrub_summary or {}).keys())),
        "snapshot_field_count": len(pre_scrub_snapshot or {}),
    })
    return {
        "id": req["id"],
        "status": "executed",
        "scrub_summary": scrub_summary,
        "snapshot_field_count": len(pre_scrub_snapshot or {}),
    }


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
    return await _execute_request_impl(
        req, force=payload.force, executed_by=user.get("id"),
        executed_by_label=user.get("email"),
    )


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    payload: CancelPayload | None = None,
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
    cancel_reason = (payload.reason if payload else "") or ""
    await db.gdpr_erasure_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": _now(),
            "cancelled_by": user.get("id"),
            "cancellation_reason": cancel_reason,
        }},
    )
    # Iter 220bq — fail-closed audit trail for cancellations too.
    await audit_required("gdpr_erasure_audit", {
        "request_id": request_id,
        "event": "request_cancelled",
        "subject_type": req.get("subject_type"),
        "subject_id": req.get("subject_id"),
        "subject_label": req.get("subject_label"),
        "cancelled_by": user.get("id"),
        "cancelled_by_email": user.get("email"),
        "cancellation_reason": cancel_reason,
    })
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



# ── Iter 220bq · Auto-execute scheduler ──────────────────────────

import asyncio  # noqa: E402  (deferred import — only needed by the loop)
import logging  # noqa: E402
import os  # noqa: E402

logger = logging.getLogger(__name__)


async def auto_execute_due_requests() -> dict:
    """Execute every ``pending`` erasure whose ``execute_after`` has
    elapsed. Idempotent — already-executed rows are skipped by the
    status filter. Returns counts for observability.

    The UK ICO requires a Data Subject Erasure Request to be fulfilled
    **within** one month. Leaving requests in ``pending`` past
    ``execute_after`` is a breach — this loop closes that gap.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    due_cursor = db.gdpr_erasure_requests.find(
        {"status": "pending", "execute_after": {"$lte": now_iso}},
        {"_id": 0},
    )
    due = await due_cursor.to_list(length=200)
    if not due:
        return {"executed": 0, "errors": 0}

    ok = 0
    errors = 0
    for req in due:
        try:
            await _execute_request_impl(
                req, force=False,
                executed_by="system:auto",
                executed_by_label="scheduler",
            )
            ok += 1
        except HTTPException as e:
            logger.warning(
                "[gdpr-erasure] auto-execute skipped %s: %s",
                req.get("id"), e.detail,
            )
            errors += 1
        except Exception:
            logger.exception(
                "[gdpr-erasure] auto-execute failed for %s", req.get("id"),
            )
            errors += 1
    logger.info("[gdpr-erasure] auto-execute swept %d due (ok=%d, errors=%d)",
                len(due), ok, errors)
    return {"executed": ok, "errors": errors, "total_due": len(due)}


async def run_gdpr_erasure_auto_executor(interval_minutes: int = 60) -> None:
    """Daemon — wakes every ``interval_minutes`` and calls
    ``auto_execute_due_requests``. Hourly is plenty (ICO deadline is
    1 month; granularity at the hour is well inside the tolerance).

    Gated by env ``GDPR_ERASURE_AUTOEXEC_ENABLED`` so an operator can
    pause it during incident-response / bulk-onboarding windows.
    """
    enabled = os.environ.get("GDPR_ERASURE_AUTOEXEC_ENABLED", "1") != "0"
    if not enabled:
        logger.info("[gdpr-erasure] auto-executor disabled by env")
        return
    interval = max(60, interval_minutes * 60)  # seconds — floor at 1 min
    logger.info(
        "[gdpr-erasure] auto-executor started (interval=%ds)", interval,
    )
    while True:
        try:
            await auto_execute_due_requests()
        except Exception:
            logger.exception("[gdpr-erasure] auto-executor iteration failed")
        await asyncio.sleep(interval)


@router.post("/auto-execute/run-now")
async def auto_execute_run_now(user: dict = Depends(get_current_user)):
    """Operator-triggered immediate sweep — useful in tests and when
    the master admin wants to flush the queue without waiting for the
    next tick. Master-admin only."""
    _require_master_admin(user)
    return await auto_execute_due_requests()
