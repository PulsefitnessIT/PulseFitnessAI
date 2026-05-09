"""CRM 4-step Setup Wizard — Iter 216av · Phase 3 #6.

Parity with the Memberships SetupWizard at `/memberships/setup`. Each
step persists to the organisation document so the wizard is resumable.

Steps:
  1. Pipeline   — pipeline name + stage list (5 sensible defaults)
  2. Contacts   — first contact (or bulk CSV import — handled elsewhere)
  3. First deal — optional
  4. Done       — flips `crm_setup_completed` true, drops the user on
                  the CRM Pipeline tab.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _org(user: dict) -> str:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "User has no organization")
    return org_id


# ───────────────── status ────────────────────────────────────────


@router.get("/crm/setup/status", dependencies=[Depends(require_module("crm"))])
async def setup_status(user: dict = Depends(get_current_user)):
    org_id = await _org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
    pipelines = await db.crm_pipelines.count_documents({"organization_id": org_id})
    contacts = await db.crm_contacts.count_documents({"organization_id": org_id})
    deals = await db.crm_deals.count_documents({"organization_id": org_id})
    return {
        "organization": {
            "id": org.get("id"),
            "name": org.get("name"),
            "crm_setup_step": org.get("crm_setup_step") or "pipeline",
            "crm_setup_completed": bool(org.get("crm_setup_completed")),
        },
        "counts": {"pipelines": pipelines, "contacts": contacts, "deals": deals},
    }


# ───────────────── step 1: pipeline ──────────────────────────────


class PipelineBody(BaseModel):
    name: str = "Sales pipeline"
    stages: list[str] = [
        "Lead", "Qualified", "Proposal", "Negotiation", "Closed Won",
    ]


@router.post("/crm/setup/pipeline", dependencies=[Depends(require_module("crm"))])
async def setup_pipeline(body: PipelineBody, user: dict = Depends(get_current_user)):
    org_id = await _org(user)
    if not body.name.strip():
        raise HTTPException(400, "Pipeline name is required")
    if len(body.stages) < 2:
        raise HTTPException(400, "At least 2 stages are required")

    # Reuse first existing pipeline if present so re-running the wizard
    # doesn't create duplicates.
    existing = await db.crm_pipelines.find_one(
        {"organization_id": org_id}, {"_id": 0, "id": 1},
    )
    if existing:
        await db.crm_pipelines.update_one(
            {"id": existing["id"]},
            {"$set": {
                "name": body.name.strip(),
                "stages": [
                    {"id": str(uuid.uuid4()), "name": s.strip(), "order": i}
                    for i, s in enumerate(body.stages) if s.strip()
                ],
                "updated_at": _now().isoformat(),
            }},
        )
        pipeline_id = existing["id"]
    else:
        pipeline_id = str(uuid.uuid4())
        await db.crm_pipelines.insert_one({
            "id": pipeline_id,
            "organization_id": org_id,
            "name": body.name.strip(),
            "stages": [
                {"id": str(uuid.uuid4()), "name": s.strip(), "order": i}
                for i, s in enumerate(body.stages) if s.strip()
            ],
            "is_default": True,
            "created_at": _now().isoformat(),
            "created_by": user.get("email"),
        })

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"crm_setup_step": "contacts", "crm_setup_started_at": _now().isoformat()}},
    )
    return {"ok": True, "pipeline_id": pipeline_id}


# ───────────────── step 2: contacts ──────────────────────────────


class ContactBody(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None


@router.post("/crm/setup/contact", dependencies=[Depends(require_module("crm"))])
async def setup_first_contact(body: ContactBody, user: dict = Depends(get_current_user)):
    org_id = await _org(user)
    if not body.full_name.strip():
        raise HTTPException(400, "Contact name is required")
    cid = str(uuid.uuid4())
    await db.crm_contacts.insert_one({
        "id": cid,
        "organization_id": org_id,
        "full_name": body.full_name.strip(),
        "email": (body.email or "").strip().lower() or None,
        "phone": (body.phone or "").strip() or None,
        "company": (body.company or "").strip() or None,
        "source": "setup_wizard",
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
    })
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"crm_setup_step": "deal"}},
    )
    return {"ok": True, "contact_id": cid}


# ───────────────── step 3: deal (optional) ───────────────────────


class DealBody(BaseModel):
    title: str
    contact_id: Optional[str] = None
    value_pence: int = 0


@router.post("/crm/setup/deal", dependencies=[Depends(require_module("crm"))])
async def setup_first_deal(body: DealBody, user: dict = Depends(get_current_user)):
    org_id = await _org(user)
    if not body.title.strip():
        raise HTTPException(400, "Deal title is required")
    pipeline = await db.crm_pipelines.find_one(
        {"organization_id": org_id, "is_default": True}, {"_id": 0},
    ) or await db.crm_pipelines.find_one({"organization_id": org_id}, {"_id": 0})
    if not pipeline:
        raise HTTPException(400, "No pipeline yet — finish step 1 first")
    first_stage = (pipeline.get("stages") or [{}])[0].get("id")
    deal_id = str(uuid.uuid4())
    await db.crm_deals.insert_one({
        "id": deal_id,
        "organization_id": org_id,
        "pipeline_id": pipeline["id"],
        "stage_id": first_stage,
        "title": body.title.strip(),
        "contact_id": body.contact_id,
        "value_pence": int(body.value_pence or 0),
        "currency": "GBP",
        "status": "open",
        "source": "setup_wizard",
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
    })
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"crm_setup_step": "done"}},
    )
    return {"ok": True, "deal_id": deal_id}


# ───────────────── step 4: complete ──────────────────────────────


@router.post("/crm/setup/complete", dependencies=[Depends(require_module("crm"))])
async def setup_complete(user: dict = Depends(get_current_user)):
    org_id = await _org(user)
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "crm_setup_completed": True,
            "crm_setup_completed_at": _now().isoformat(),
            "crm_setup_step": "done",
        }},
    )
    return {"ok": True}


# ───────────────── skip ───────────────────────────────────────────


@router.post("/crm/setup/skip", dependencies=[Depends(require_module("crm"))])
async def setup_skip(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Skip the wizard outright — set completed=true with a marker so
    we can still nudge them to fill it in later."""
    org_id = await _org(user)
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "crm_setup_completed": True,
            "crm_setup_completed_at": _now().isoformat(),
            "crm_setup_skipped": True,
            "crm_setup_step": "done",
        }},
    )
    return {"ok": True}
