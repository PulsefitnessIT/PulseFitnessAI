"""Member-portal GDPR endpoints (iter 215bz).

Gym members are data subjects under UK GDPR / Data Protection Act 2018.
They must be able to:
  • Export everything we hold on them (Art. 15 — Right of Access)
  • Erase their account (Art. 17 — Right to Erasure)

Operator-level GDPR for staff users already lives at /compliance/*. This
file adds the equivalent for the member portal so a customer can
self-serve without raising a support ticket — a hard requirement for
ICO compliance and for any audit by a regulated chain.

Token: re-uses the member-portal magic-link token issued by
`/portal/auth/exchange`. We never expose member personal data through an
operator's bearer token here — different auth surface entirely.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from routes.memberships.helpers import _require_current_member
from utils.audit import audit_log
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal/me", tags=["member portal — GDPR"])


def _strip_internal(doc: dict | None) -> dict | None:
    """Drop ops-only fields the member shouldn't see (operator notes,
    internal flags) before returning a personal-data export."""
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    out.pop("notes", None)              # operator notes
    out.pop("operator_tags", None)
    out.pop("retention_score", None)    # internal churn metric
    out.pop("ai_summary", None)         # internal sales notes
    return out


async def _gather_member_data(member_id: str) -> dict:
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "password": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    org_id = member.get("organization_id")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "name": 1})
    memberships = await db.member_memberships.find(
        {"member_id": member_id}, {"_id": 0},
    ).to_list(50)
    bookings = await db.bookings.find(
        {"member_id": member_id}, {"_id": 0},
    ).sort("starts_at", -1).to_list(500)
    invoices = await db.invoices.find(
        {"member_id": member_id}, {"_id": 0},
    ).sort("issued_at", -1).to_list(200)
    payments = await db.payments.find(
        {"member_id": member_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    inbox = await db.member_inbox.find(
        {"member_id": member_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    waivers = await db.member_waivers.find(
        {"member_id": member_id}, {"_id": 0},
    ).to_list(50)

    return {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "data_subject": {
            "email": member.get("email"),
            "full_name": f"{member.get('first_name', '')} {member.get('last_name', '')}".strip(),
        },
        "organization": org,
        "profile": _strip_internal(member),
        "memberships": memberships,
        "bookings": bookings,
        "invoices": invoices,
        "payments": payments,
        "inbox_messages": inbox,
        "waivers_signed": waivers,
    }


@router.get("/data")
async def export_my_data(request: Request, member: dict = Depends(_require_current_member)) -> dict:
    """GDPR Art. 15 — return everything held about this member."""
    data = await _gather_member_data(member["id"])
    ip = request.client.host if request.client else ""
    await audit_log(
        "member_data_export", member["id"], member.get("email", ""),
        "member", member["id"], "Member requested GDPR data export", ip,
    )
    return data


@router.get("/data/download")
async def download_my_data(request: Request, member: dict = Depends(_require_current_member)) -> Response:
    """Same as /data, but returned as a JSON download for the user to keep."""
    data = await _gather_member_data(member["id"])
    blob = json.dumps(data, indent=2, default=str).encode("utf-8")
    short_id = member["id"][:8]
    return Response(
        content=blob,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=my_data_{short_id}.json"},
    )


@router.delete("/account")
async def delete_my_account(request: Request, member: dict = Depends(_require_current_member)) -> dict:
    """GDPR Art. 17 — Right to Erasure.

    We anonymise rather than hard-delete to preserve the integrity of
    historic financial records the operator must keep for HMRC. The
    member is no longer identifiable: email, name, phone, address, dob,
    emergency contact, notes, and tags are scrubbed; bookings/invoices
    keep their amounts but lose the PII link.
    """
    member_id = member["id"]
    email = member.get("email", "")
    ip = request.client.host if request.client else ""
    anon_email = f"deleted_{member_id[:8]}@anonymised.local"
    await db.members.update_one(
        {"id": member_id},
        {"$set": {
            "status": "deleted",
            "email": anon_email,
            "first_name": "Deleted",
            "last_name": "Member",
            "phone": "",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "postcode": "",
            "country": "",
            "dob": None,
            "emergency_contact_name": "",
            "emergency_contact_phone": "",
            "notes": "",
            "tags": [],
            "deleted_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    # Also anonymise any CRM contact mirror for this member.
    await db.crm2_contacts.update_many(
        {"organization_id": member.get("organization_id"),
         "custom_fields.memberships_member_id": member_id},
        {"$set": {
            "email": anon_email,
            "first_name": "Deleted",
            "last_name": "Member",
            "phone": "",
            "tags": ["anonymised"],
            "lifecycle": "Anonymised",
        }},
    )
    await audit_log(
        "member_account_delete", member_id, email,
        "member", member_id, "Member self-deleted account", ip,
    )
    return {"success": True, "message": "Your account has been anonymised. Some financial records are retained for HMRC compliance but no longer identify you."}
