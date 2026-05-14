"""Master Admin — Communications Inbox (iter 216h94).

A centralised hub for every inbound sales enquiry submitted through the
public marketing site's contact form. Pairs with ``routes/contact.py``
which writes the records into ``public_contact_submissions``.

Endpoints (all gated by ``require_master_admin``):

  GET    /api/master-admin/communications              List with filters
  GET    /api/master-admin/communications/summary       Counts-per-status
  GET    /api/master-admin/communications/{id}          Fetch single enquiry
  PATCH  /api/master-admin/communications/{id}          Update status / notes
  POST   /api/master-admin/communications/{id}/reply    Send reply via Resend

Design decisions:

* Status machine: ``new`` → ``read`` → ``replied`` → ``closed``. Any
  transition is allowed (UI lets ops re-open / archive). Sending a
  reply auto-promotes the row to ``replied`` and stamps a
  ``last_replied_at`` field for sort.
* Outbound replies are sent through ``utils.email.send_email`` (Resend)
  and persisted as ``replies[]`` so the timeline survives even when the
  Resend dashboard rotates.
* Read-only by default — no delete endpoint. ``closed`` is the archival
  state. Keeps an immutable record of every prospect interaction.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from utils.security import sanitise_string

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin/communications", tags=["master-admin-communications"])


_STATUSES = {"new", "read", "replied", "closed"}


class StatusUpdate(BaseModel):
    status: Optional[str] = Field(default=None)
    internal_notes: Optional[str] = Field(default=None, max_length=4000)


class ReplyPayload(BaseModel):
    subject: str = Field(..., min_length=2, max_length=200)
    body: str = Field(..., min_length=2, max_length=10000)
    cc: Optional[EmailStr] = None


def _summary_row(doc: dict) -> dict:
    """Trim the full document to the fields the list view needs.

    Strips PII like raw IP, message body etc. (the detail endpoint
    returns the full record for the drawer).
    """
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
    }


@router.get("")
async def list_enquiries(
    user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="filter: new | read | replied | closed"),
    interest: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="case-insensitive substring across name/email/company/message"),
    limit: int = Query(100, ge=1, le=500),
):
    """Return the inbox feed — newest first."""
    require_master_admin(user)
    q: dict = {}
    if status and status in _STATUSES:
        q["status"] = status
    if interest:
        q["interest"] = interest.lower().strip()
    if search:
        s = search.strip()
        q["$or"] = [
            {"name":    {"$regex": s, "$options": "i"}},
            {"email":   {"$regex": s, "$options": "i"}},
            {"company": {"$regex": s, "$options": "i"}},
            {"message": {"$regex": s, "$options": "i"}},
        ]
    cursor = (
        db.public_contact_submissions
        .find(q, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    rows = [_summary_row(d) async for d in cursor]
    return {"count": len(rows), "items": rows}


@router.get("/summary")
async def inbox_summary(user: dict = Depends(get_current_user)):
    """Tile counts for the inbox header. Cheap — one pipeline."""
    require_master_admin(user)
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    counts = {s: 0 for s in _STATUSES}
    async for row in db.public_contact_submissions.aggregate(pipeline):
        key = row.get("_id") or "new"
        if key in counts:
            counts[key] = row.get("n", 0)
    total = sum(counts.values())
    return {"total": total, "by_status": counts}


@router.get("/{enquiry_id}")
async def get_enquiry(enquiry_id: str, user: dict = Depends(get_current_user)):
    """Return the full enquiry record + reply timeline.

    Side-effect: silently promote ``new`` → ``read`` so unread counts
    track operator activity without an extra click.
    """
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
    return doc


@router.patch("/{enquiry_id}")
async def update_enquiry(
    enquiry_id: str,
    payload: StatusUpdate,
    user: dict = Depends(get_current_user),
):
    """Mutate status / internal notes. UI uses this to close / re-open
    rows and to attach a private operator note."""
    require_master_admin(user)
    updates: dict = {}
    if payload.status:
        if payload.status not in _STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_STATUSES)}")
        updates["status"] = payload.status
    if payload.internal_notes is not None:
        updates["internal_notes"] = sanitise_string(payload.internal_notes)
    if not updates:
        raise HTTPException(status_code=400, detail="No updatable fields supplied")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = user.get("email")
    result = await db.public_contact_submissions.update_one({"id": enquiry_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return {"ok": True, "updates": list(updates.keys())}


def _reply_html(reply_body: str, original_message: str, sender_name: str) -> str:
    """Wrap the operator's reply in a branded shell quoting the original
    enquiry. ``send_email`` will further wrap this in the co-brand
    header so the customer sees both GymAxis + the operator brand.
    """
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
        # Surface a 502 so the UI can react but still keep the attempt
        # in the audit log via the ``email_events`` collection that
        # send_email populates on failure.
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
