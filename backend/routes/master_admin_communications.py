"""Master Admin — Communications Inbox (iter 216h94 → 216h100).

A centralised hub for every inbound sales enquiry submitted through the
public marketing site's contact form. Pairs with ``routes/contact.py``
which writes the records into ``public_contact_submissions``.

Endpoints (all gated by ``require_master_admin``):

  GET    /api/master-admin/communications              List with filters
  GET    /api/master-admin/communications/summary       Counts-per-status
  GET    /api/master-admin/communications/settings      SLA + admins list
  PUT    /api/master-admin/communications/settings      Update SLA hours
  GET    /api/master-admin/communications/{id}          Fetch single enquiry
  PATCH  /api/master-admin/communications/{id}          Update status/notes/assignee
  POST   /api/master-admin/communications/{id}/reply    Send reply via Resend

  GET    /api/master-admin/canned-replies               List templates
  POST   /api/master-admin/canned-replies               Create template
  PUT    /api/master-admin/canned-replies/{id}          Update template
  DELETE /api/master-admin/canned-replies/{id}          Delete template

Design decisions:

* Status machine: ``new`` → ``read`` → ``replied`` → ``closed``.
* SLA: configurable warning_hours / breach_hours stored on a singleton
  ``inbox_settings`` doc. List endpoint stamps every open row with an
  ``sla`` field (``ok`` | ``warning`` | ``breached``) computed from
  ``created_at``.
* Assignment: single ``assigned_to`` email per enquiry. Eligible
  assignees = users with ``is_master_admin: True``.
* Canned replies are global (any Master Admin can use any template),
  authored / edited by Master Admin only.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.security_plus import safe_regex
from pydantic import BaseModel, EmailStr, Field

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from utils.security import sanitise_string

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin/communications", tags=["master-admin-communications"])


_STATUSES = {"new", "read", "replied", "closed"}
_OPEN_STATUSES = {"new", "read"}  # treated as SLA-eligible

# Sensible defaults if no inbox_settings doc exists yet.
_DEFAULT_WARNING_HOURS = 4
_DEFAULT_BREACH_HOURS = 24


class StatusUpdate(BaseModel):
    status: Optional[str] = Field(default=None)
    internal_notes: Optional[str] = Field(default=None, max_length=4000)
    assigned_to: Optional[str] = Field(default=None, description="Email of a master admin, or empty string to unassign")


class ReplyPayload(BaseModel):
    subject: str = Field(..., min_length=2, max_length=200)
    body: str = Field(..., min_length=2, max_length=10000)
    cc: Optional[EmailStr] = None


class InboxSettings(BaseModel):
    warning_hours: int = Field(default=_DEFAULT_WARNING_HOURS, ge=1, le=168)
    breach_hours: int = Field(default=_DEFAULT_BREACH_HOURS, ge=1, le=720)


async def _load_settings() -> dict:
    """Return the inbox SLA settings, falling back to sensible defaults."""
    doc = await db.inbox_settings.find_one({"_id": "default"}, {"_id": 0})
    if not doc:
        return {"warning_hours": _DEFAULT_WARNING_HOURS, "breach_hours": _DEFAULT_BREACH_HOURS}
    return {
        "warning_hours": int(doc.get("warning_hours") or _DEFAULT_WARNING_HOURS),
        "breach_hours":  int(doc.get("breach_hours")  or _DEFAULT_BREACH_HOURS),
    }


def _compute_sla(doc: dict, settings: dict) -> dict:
    """Return ``{status: ok|warning|breached|none, hours_open: float}``.

    SLA is only applied to ``new`` / ``read`` enquiries — once a reply
    has gone out or the row has been closed, the clock stops.
    """
    if (doc.get("status") or "new") not in _OPEN_STATUSES:
        return {"sla": "none", "hours_open": 0}
    created = doc.get("created_at")
    if not created:
        return {"sla": "ok", "hours_open": 0}
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return {"sla": "ok", "hours_open": 0}
    hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    if hours >= settings["breach_hours"]:
        return {"sla": "breached", "hours_open": round(hours, 1)}
    if hours >= settings["warning_hours"]:
        return {"sla": "warning",  "hours_open": round(hours, 1)}
    return {"sla": "ok", "hours_open": round(hours, 1)}


def _summary_row(doc: dict, settings: dict) -> dict:
    """Trim the full document to the fields the list view needs."""
    sla = _compute_sla(doc, settings)
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "company": doc.get("company"),
        "interest": doc.get("interest"),
        "status": doc.get("status") or "new",
        "preview": (doc.get("message") or "")[:180],
        "created_at": doc.get("created_at"),
        "last_replied_at": doc.get("last_replied_at"),
        "reply_count": len(doc.get("replies") or []),
        "assigned_to": doc.get("assigned_to") or None,
        "sla": sla["sla"],
        "hours_open": sla["hours_open"],
    }


@router.get("")
async def list_enquiries(
    user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="filter: new | read | replied | closed"),
    interest: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None, description="filter by assignee email; pass 'unassigned' for null"),
    sla: Optional[str] = Query(None, description="filter: warning | breached"),
    search: Optional[str] = Query(None, description="case-insensitive substring across name/email/company/message"),
    limit: int = Query(100, ge=1, le=500),
):
    """Return the inbox feed — newest first, with SLA + assignee tags."""
    require_master_admin(user)
    q: dict = {}
    if status and status in _STATUSES:
        q["status"] = status
    if interest:
        q["interest"] = interest.lower().strip()
    if assigned_to:
        if assigned_to.lower() == "unassigned":
            q["$or"] = [{"assigned_to": None}, {"assigned_to": ""}, {"assigned_to": {"$exists": False}}]
        else:
            q["assigned_to"] = assigned_to.lower().strip()
    if search:
        s = search.strip()
        # Don't clobber a $or set by the unassigned filter.
        clause = [
            {"name":    safe_regex(s)},
            {"email":   safe_regex(s)},
            {"company": safe_regex(s)},
            {"message": safe_regex(s)},
        ]
        if "$or" in q:
            q = {"$and": [q, {"$or": clause}]}
        else:
            q["$or"] = clause

    settings = await _load_settings()
    cursor = (
        db.public_contact_submissions
        .find(q, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    rows = [_summary_row(d, settings) async for d in cursor]
    if sla in ("warning", "breached"):
        rows = [r for r in rows if r["sla"] == sla]
    return {"count": len(rows), "items": rows, "sla_settings": settings}


@router.get("/summary")
async def inbox_summary(user: dict = Depends(get_current_user)):
    """Tile counts for the inbox header. Adds SLA breach counters."""
    require_master_admin(user)
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    counts = {s: 0 for s in _STATUSES}
    async for row in db.public_contact_submissions.aggregate(pipeline):
        key = row.get("_id") or "new"
        if key in counts:
            counts[key] = row.get("n", 0)
    total = sum(counts.values())

    # SLA roll-up across all open rows. Cheap: only inspects open ones.
    settings = await _load_settings()
    warning = 0
    breached = 0
    async for d in db.public_contact_submissions.find(
        {"status": {"$in": list(_OPEN_STATUSES)}},
        {"_id": 0, "status": 1, "created_at": 1},
    ):
        sla = _compute_sla(d, settings)["sla"]
        if sla == "warning":
            warning += 1
        elif sla == "breached":
            breached += 1
    return {
        "total": total,
        "by_status": counts,
        "sla": {"warning": warning, "breached": breached},
        "sla_settings": settings,
    }


@router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    """Return inbox SLA settings + the eligible-assignees list."""
    require_master_admin(user)
    settings = await _load_settings()
    admins_cursor = db.users.find(
        {"is_master_admin": True},
        {"_id": 0, "email": 1, "name": 1},
    )
    admins = [
        {"email": a.get("email"), "name": a.get("name") or a.get("email")}
        async for a in admins_cursor if a.get("email")
    ]
    return {"settings": settings, "admins": admins}


@router.put("/settings")
async def put_settings(payload: InboxSettings, user: dict = Depends(get_current_user)):
    """Persist SLA warning + breach thresholds (hours)."""
    require_master_admin(user)
    await db.inbox_settings.update_one(
        {"_id": "default"},
        {
            "$set": {
                "warning_hours": payload.warning_hours,
                "breach_hours":  payload.breach_hours,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": user.get("email"),
            },
        },
        upsert=True,
    )
    return {"ok": True, "settings": {"warning_hours": payload.warning_hours, "breach_hours": payload.breach_hours}}


@router.get("/{enquiry_id}")
async def get_enquiry(enquiry_id: str, user: dict = Depends(get_current_user)):
    """Return the full enquiry record + reply timeline + SLA badge."""
    require_master_admin(user)
    doc = await db.public_contact_submissions.find_one({"id": enquiry_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if (doc.get("status") or "new") == "new":
        await db.public_contact_submissions.update_one(
            {"id": enquiry_id},
            {"$set": {"status": "read", "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        doc["status"] = "read"
    settings = await _load_settings()
    sla = _compute_sla(doc, settings)
    doc["sla"] = sla["sla"]
    doc["hours_open"] = sla["hours_open"]
    doc["sla_settings"] = settings
    return doc


@router.patch("/{enquiry_id}")
async def update_enquiry(
    enquiry_id: str,
    payload: StatusUpdate,
    user: dict = Depends(get_current_user),
):
    """Mutate status / notes / assignee."""
    require_master_admin(user)
    updates: dict = {}
    unsets: dict = {}
    if payload.status:
        if payload.status not in _STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_STATUSES)}")
        updates["status"] = payload.status
    if payload.internal_notes is not None:
        updates["internal_notes"] = sanitise_string(payload.internal_notes)
    if payload.assigned_to is not None:
        target = (payload.assigned_to or "").strip().lower()
        if target == "":
            unsets["assigned_to"] = ""
            unsets["assigned_at"] = ""
        else:
            # Ensure the assignee is actually a master admin to prevent
            # accidental assignment to a random user.
            admin = await db.users.find_one(
                {"email": target, "is_master_admin": True},
                {"_id": 0, "email": 1},
            )
            if not admin:
                raise HTTPException(status_code=400, detail="Assignee must be an existing master admin")
            updates["assigned_to"] = target
            updates["assigned_at"] = datetime.now(timezone.utc).isoformat()
    if not updates and not unsets:
        raise HTTPException(status_code=400, detail="No updatable fields supplied")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = user.get("email")
    op: dict = {"$set": updates}
    if unsets:
        op["$unset"] = unsets
    result = await db.public_contact_submissions.update_one({"id": enquiry_id}, op)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return {"ok": True, "updates": list(updates.keys()) + list(unsets.keys())}


def _reply_html(reply_body: str, original_message: str, sender_name: str) -> str:
    body_html = reply_body.replace("\n", "<br/>")
    quoted_html = (original_message or "").replace("\n", "<br/>")
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;">
  <div style="padding:8px 0 24px;color:#0f172a;font-size:15px;line-height:1.6;">
    {body_html}
  </div>
  <div style="margin-top:8px;padding-top:18px;border-top:1px solid #e5e7eb;color:#64748b;font-size:13px;">
    <div style="font-weight:600;color:#475569;margin-bottom:6px;">— {sender_name}</div>
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.12em;color:#94a3b8;margin-top:18px;margin-bottom:6px;">Your original message</div>
    <div style="padding-left:12px;border-left:3px solid #e2e8f0;color:#475569;font-style:italic;">{quoted_html}</div>
  </div>
</div>"""


@router.post("/{enquiry_id}/reply")
async def reply_to_enquiry(
    enquiry_id: str,
    payload: ReplyPayload,
    user: dict = Depends(get_current_user),
):
    """Send an outbound reply via Resend and append it to the timeline."""
    require_master_admin(user)
    doc = await db.public_contact_submissions.find_one({"id": enquiry_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    sender_name = (user.get("name") or user.get("email") or "GymAxis Sales").split("@")[0].title()
    html = _reply_html(payload.body, doc.get("message") or "", sender_name)
    ok = await send_email(doc["email"], payload.subject, html)
    if not ok:
        raise HTTPException(status_code=502, detail="Email dispatch failed — check Resend credentials")

    reply_entry = {
        "id": str(uuid.uuid4()),
        "subject": sanitise_string(payload.subject),
        "body": sanitise_string(payload.body),
        "sent_by": user.get("email"),
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.public_contact_submissions.update_one(
        {"id": enquiry_id},
        {
            "$push": {"replies": reply_entry},
            "$set": {
                "status": "replied",
                "last_replied_at": now_iso,
                "last_replied_by": user.get("email"),
            },
        },
    )
    return {"ok": True, "reply": reply_entry}


# ── Canned replies ──────────────────────────────────────────────────


canned_router = APIRouter(prefix="/master-admin/canned-replies", tags=["master-admin-canned-replies"])


class CannedReplyPayload(BaseModel):
    label: str = Field(..., min_length=2, max_length=80)
    subject: str = Field(..., min_length=2, max_length=200)
    body: str = Field(..., min_length=2, max_length=10000)


@canned_router.get("")
async def list_canned(user: dict = Depends(get_current_user)):
    """List all global canned replies, ordered by label."""
    require_master_admin(user)
    cursor = db.canned_replies.find({}, {"_id": 0}).sort("label", 1)
    items = [d async for d in cursor]
    return {"count": len(items), "items": items}


@canned_router.post("")
async def create_canned(payload: CannedReplyPayload, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    record = {
        "id": str(uuid.uuid4()),
        "label": sanitise_string(payload.label),
        "subject": sanitise_string(payload.subject),
        "body": sanitise_string(payload.body),
        "created_by": user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.canned_replies.insert_one(record)
    record.pop("_id", None)
    return {"ok": True, "item": record}


@canned_router.put("/{template_id}")
async def update_canned(template_id: str, payload: CannedReplyPayload, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    result = await db.canned_replies.update_one(
        {"id": template_id},
        {"$set": {
            "label": sanitise_string(payload.label),
            "subject": sanitise_string(payload.subject),
            "body": sanitise_string(payload.body),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user.get("email"),
        }},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}


@canned_router.delete("/{template_id}")
async def delete_canned(template_id: str, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    result = await db.canned_replies.delete_one({"id": template_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}

