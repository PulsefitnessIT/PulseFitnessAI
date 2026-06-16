"""Pulse Fitness Memberships — Phase 2 family / sub-profiles.

A parent member can manage one or more sub-profiles (kids, partners,
dependents). For v1 they share the parent's billing & memberships —
bookings against a sub-profile draw from the parent's credit pool.

Why this matters
────────────────
This is Coacha's #1 differentiator vs the rest of the market. Parents
of multiple kids running a single membership reduce admin to zero and
unlock huge revenue (one membership → 3 bookings per week instead of 1).

Schema (member_sub_profiles)
────────────────────────────
  id, organization_id, parent_member_id,
  first_name, last_name, dob (ISO date), gender,
  relationship, allergies, medical_notes,
  emergency_contact_name, emergency_contact_phone,
  active, archived_at,
  created_at, updated_at

Endpoints
─────────
  GET    /api/member/sub-profiles
  POST   /api/member/sub-profiles
  PATCH  /api/member/sub-profiles/{id}
  DELETE /api/member/sub-profiles/{id}
  GET    /api/operator/members/{member_id}/sub-profiles  (operator-side view)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.memberships.helpers import _require_current_member, _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-family"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubProfileIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default="", max_length=80)
    dob: Optional[str] = None
    """ISO date (YYYY-MM-DD). Required for kids' classes that have age gating."""
    gender: Optional[str] = None
    relationship: str = Field(default="child", max_length=40)
    """Free text — typical values: 'child', 'partner', 'dependent', 'parent'."""
    allergies: Optional[str] = None
    medical_notes: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


# ───────────────────────── Member-facing endpoints ─────────────────────────


@router.get("/member/sub-profiles")
async def list_my_sub_profiles(
    member: dict = Depends(_require_current_member),
):
    """Sub-profiles the current member is the parent of. Sorted oldest
    first so siblings stay in the order they were added."""
    rows = await db.member_sub_profiles.find(
        {"parent_member_id": member["id"], "archived_at": None},
        {"_id": 0},
    ).sort("created_at", 1).to_list(50)
    return {"sub_profiles": rows, "count": len(rows)}


@router.post("/member/sub-profiles")
async def create_sub_profile(
    body: SubProfileIn, member: dict = Depends(_require_current_member),
):
    """Create a new sub-profile under the calling member. Hard cap of 12
    sub-profiles per parent — that's already a generous family."""
    cnt = await db.member_sub_profiles.count_documents(
        {"parent_member_id": member["id"], "archived_at": None},
    )
    if cnt >= 12:
        raise HTTPException(400, "Maximum 12 sub-profiles per member")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": member["organization_id"],
        "parent_member_id": member["id"],
        "active": True,
        "archived_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        **body.model_dump(),
    }
    await db.member_sub_profiles.insert_one(doc)
    return {"sub_profile": _strip(doc)}


@router.patch("/member/sub-profiles/{sub_id}")
async def update_sub_profile(
    sub_id: str, body: dict = Body(...),
    member: dict = Depends(_require_current_member),
):
    """Update editable fields. Only the parent member can edit."""
    allowed = {"first_name", "last_name", "dob", "gender", "relationship",
               "allergies", "medical_notes", "emergency_contact_name",
               "emergency_contact_phone", "active"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(400, "No allowed fields supplied")
    update["updated_at"] = _now_iso()
    res = await db.member_sub_profiles.update_one(
        {"id": sub_id, "parent_member_id": member["id"], "archived_at": None},
        {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Sub-profile not found")
    return {"ok": True, "updated": list(update.keys())}


@router.delete("/member/sub-profiles/{sub_id}")
async def archive_sub_profile(
    sub_id: str, member: dict = Depends(_require_current_member),
):
    """Soft-delete. Existing bookings remain on record so attendance
    history stays intact, but the sub-profile no longer appears in the
    booking attendee picker."""
    res = await db.member_sub_profiles.update_one(
        {"id": sub_id, "parent_member_id": member["id"], "archived_at": None},
        {"$set": {"archived_at": _now_iso(), "active": False,
                  "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Sub-profile not found")
    return {"ok": True}


# ───────────────────────── Operator-facing read ─────────────────────────


@router.get(
    "/operator/members/{member_id}/sub-profiles",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_list_sub_profiles(
    member_id: str, user: dict = Depends(get_current_user),
):
    """Operator view of a member's sub-profiles — used in the member
    detail drawer so reception/admin can see who's on the family plan."""
    org_id = await _require_operator_org(user)
    rows = await db.member_sub_profiles.find(
        {"parent_member_id": member_id, "organization_id": org_id,
         "archived_at": None},
        {"_id": 0},
    ).sort("created_at", 1).to_list(50)
    return {"sub_profiles": rows, "count": len(rows)}


# ───────────────────────── Helpers used by booking ─────────────────────────


async def resolve_attendee(
    *, kind: str, sub_profile_id: Optional[str], guest_name: Optional[str],
    guest_email: Optional[str], parent_member: dict,
) -> dict:
    """Validate one attendee in a multi-booking payload and return a
    dict ready to merge into the booking row.

    Returns:
      {
        attendee_kind,             # 'self' | 'sub_profile' | 'guest'
        attendee_sub_profile_id?,  # for sub_profile
        attendee_name,
        attendee_email?,
      }
    """
    if kind == "self":
        return {
            "attendee_kind": "self",
            "attendee_name": (parent_member.get("first_name", "") + " "
                              + parent_member.get("last_name", "")).strip(),
            "attendee_email": parent_member.get("email"),
        }
    if kind == "sub_profile":
        if not sub_profile_id:
            raise HTTPException(400, "sub_profile_id required for sub_profile attendee")
        sp = await db.member_sub_profiles.find_one(
            {"id": sub_profile_id, "parent_member_id": parent_member["id"],
             "archived_at": None}, {"_id": 0},
        )
        if not sp:
            raise HTTPException(404, f"Sub-profile {sub_profile_id} not found")
        return {
            "attendee_kind": "sub_profile",
            "attendee_sub_profile_id": sub_profile_id,
            "attendee_name": (sp.get("first_name", "") + " "
                              + sp.get("last_name", "")).strip() or "Sub-profile",
            "attendee_email": parent_member.get("email"),
        }
    if kind == "guest":
        if not guest_name:
            raise HTTPException(400, "guest_name required for guest attendee")
        return {
            "attendee_kind": "guest",
            "attendee_name": guest_name.strip(),
            "attendee_email": (guest_email or "").strip() or None,
        }
    raise HTTPException(400, f"Unknown attendee kind '{kind}'")


__all__ = ["router", "resolve_attendee"]
