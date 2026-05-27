"""CRM Contact → Enrol in journey quick-action — Iter 220al.

Adds two endpoints scoped to the calling user's organisation:

  * ``GET  /api/crm/contacts/{contact_id}/journey-options``
      Returns the catalogue of non-archived ``marketing_journeys`` the
      rep can fire for this contact, plus whether the contact is
      already enrolled in each (so the UI can dim the option and
      show "Enrolled" instead of letting them double-enrol).

  * ``POST /api/crm/contacts/{contact_id}/enrol``
      Body: ``{"journey_id": "..."}``. Inserts a
      ``marketing_journey_enrolments`` row, stamps a
      ``crm_activities`` "journey_enrolled" event on the contact's
      timeline, and bumps the journey's ``metrics.entered`` counter
      so the Growth Hub journey cards update live.

The endpoints reuse ``get_crm_user`` from the existing CRM routes —
all writes are organisation-scoped, no master-admin gating required.

This is what turns the 4 B2B templates launched in Iter 220ah from
"great to look at" into "actively converting prospects from the
rep's inbox".
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.database import db
from routes.crm_core import get_crm_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm", tags=["crm-journey-enrol"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EnrolPayload(BaseModel):
    journey_id: str = Field(..., min_length=1, max_length=64)


async def _load_contact(contact_id: str, org_id: str) -> dict:
    # The CRM UI uses ``crm2_contacts`` (Iter 216h+ schema) so we look
    # there first. Fall back to the legacy ``crm_contacts`` collection
    # (which the public demo-request endpoint still writes into) so
    # both contact shapes work seamlessly.
    contact = await db.crm2_contacts.find_one(
        {"id": contact_id, "organization_id": org_id}, {"_id": 0},
    )
    if not contact:
        contact = await db.crm_contacts.find_one(
            {"id": contact_id, "organization_id": org_id}, {"_id": 0},
        )
    if not contact:
        raise HTTPException(404, "Contact not found")
    return contact


@router.get("/contacts/{contact_id}/journey-options")
async def list_journey_options(
    contact_id: str, user=Depends(get_crm_user),
):
    org_id = user.get("organization_id")
    # Soft lookup — check both contact collections (v2 + legacy).
    # If still missing, the row is a member-portal record rendered
    # by the same list; return empty journeys + a flag so the button
    # silently hides.
    contact = await db.crm2_contacts.find_one(
        {"id": contact_id, "organization_id": org_id}, {"_id": 0},
    )
    if not contact:
        contact = await db.crm_contacts.find_one(
            {"id": contact_id, "organization_id": org_id}, {"_id": 0},
        )
    if not contact:
        return {
            "contact": {"id": contact_id, "email": "", "first_name": ""},
            "journeys": [],
            "non_crm_contact": True,
        }

    # Surface journeys for this org (non-archived). Tenant operators
    # see their own journeys; the master admin viewing the master-
    # admin CRM sees the 4 B2B templates we shipped in Iter 220ah.
    journeys = await db.marketing_journeys.find(
        {"organization_id": org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "description": 1,
         "template_id": 1, "status": 1, "metrics": 1, "nodes": 1},
    ).sort("name", 1).to_list(50)

    # Per-journey: has this contact ever been enrolled (active)?
    enrolled_ids: set[str] = set()
    async for row in db.marketing_journey_enrolments.find(
        {"contact_id": contact_id, "organization_id": org_id,
         "status": {"$in": ["active", "completed"]}},
        {"_id": 0, "journey_id": 1},
    ):
        if row.get("journey_id"):
            enrolled_ids.add(str(row["journey_id"]))

    out = []
    for j in journeys:
        out.append({
            "id": j["id"],
            "name": j.get("name") or "Untitled journey",
            "description": j.get("description") or "",
            "template_id": j.get("template_id"),
            "node_count": len(j.get("nodes") or []),
            "metrics": j.get("metrics") or {},
            "already_enrolled": j["id"] in enrolled_ids,
        })
    return {
        "contact": {"id": contact["id"], "email": contact.get("email"),
                    "first_name": contact.get("first_name", "")},
        "journeys": out,
    }


@router.post("/contacts/{contact_id}/enrol")
async def enrol_contact(
    contact_id: str, payload: EnrolPayload,
    user=Depends(get_crm_user),
):
    org_id = user.get("organization_id")
    contact = await _load_contact(contact_id, org_id)

    journey = await db.marketing_journeys.find_one(
        {"id": payload.journey_id, "organization_id": org_id,
         "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "template_id": 1},
    )
    if not journey:
        raise HTTPException(404, "Journey not found in your organisation")

    # Idempotency — refuse to spawn duplicate active enrolments for
    # the same (contact, journey). Returns 409 so the UI can surface
    # "Already enrolled" without double-charging metrics.
    existing = await db.marketing_journey_enrolments.find_one(
        {"contact_id": contact_id, "journey_id": payload.journey_id,
         "organization_id": org_id, "status": {"$in": ["active", "completed"]}},
        {"_id": 0, "id": 1, "status": 1},
    )
    if existing:
        raise HTTPException(
            409, f"Contact is already enrolled in this journey ({existing['status']})",
        )

    now = _now_iso()
    enrolment_id = str(uuid.uuid4())
    await db.marketing_journey_enrolments.insert_one({
        "id": enrolment_id,
        "journey_id": payload.journey_id,
        "organization_id": org_id,
        "contact_id": contact_id,
        "contact_email": contact.get("email") or "",
        "deal_id": None,
        "source": "crm-contact-enrol",
        "status": "active",
        "current_step_index": 0,
        "enrolled_by": user.get("id"),
        "enrolled_by_name": user.get("full_name", ""),
        "created_at": now,
    })

    # Activity stamp on the contact timeline. CRMv2 timeline reads
    # from ``crm2_activities``; the legacy CRM reads ``crm_activities``.
    # We write to whichever matches the contact's home collection.
    activity_doc = {
        "id": str(uuid.uuid4()),
        "type": "journey_enrolled",
        "contact_id": contact_id,
        "deal_id": None,
        "company_id": contact.get("company_id"),
        "description": f"Enrolled in journey '{journey['name']}'",
        "created_by": user.get("id"),
        "created_by_name": user.get("full_name", ""),
        "created_at": now,
    }
    # If we found the contact in v2, write to crm2_activities so the
    # CRM UI's timeline view picks it up.
    v2_hit = await db.crm2_contacts.find_one(
        {"id": contact_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    )
    if v2_hit:
        await db.crm2_activities.insert_one({
            **activity_doc,
            "organization_id": org_id,
            "subject": activity_doc["description"],
        })
    else:
        await db.crm_activities.insert_one(activity_doc)

    # Bump the journey's "entered" counter so the Growth Hub journey
    # card metric updates live without us rebuilding it from scratch.
    await db.marketing_journeys.update_one(
        {"id": payload.journey_id},
        {"$inc": {"metrics.entered": 1},
         "$set": {"updated_at": now}},
    )

    return {
        "ok": True,
        "enrolment_id": enrolment_id,
        "journey_id": payload.journey_id,
        "contact_id": contact_id,
    }


__all__ = ["router"]
