"""Payment plans (instalment scheduler) — Phase B (iter 216aa).

Lets a studio operator define an "instalment plan" once (e.g. termly fee
£600 split into 3 monthly payments) and assign it to specific members.
The autopay cron will issue one invoice per period until the plan is
completed.

Collections:
  • payment_plans          { id, organization_id, name, total_pence,
                             instalments, frequency:"monthly",
                             archived, created_at, updated_at }
  • payment_plan_assignments { id, organization_id, plan_id, member_id,
                               attendee_sub_profile_id?, started_on,
                               instalment_no, paid_count,
                               status:"active"|"completed"|"cancelled",
                               last_invoiced_period }

Endpoints:
  GET    /api/memberships/payment-plans
  POST   /api/memberships/payment-plans
  PUT    /api/memberships/payment-plans/{id}
  DELETE /api/memberships/payment-plans/{id}                   (archive)
  POST   /api/memberships/payment-plans/{id}/assign            (member_id, attendee?)
  GET    /api/memberships/payment-plans/assignments?member_id=
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_operator_org,
    _uuid,
)

router = APIRouter(tags=["memberships-payment-plans"])


# ─────────────────────────────────────────────────────────────────
# Plans
# ─────────────────────────────────────────────────────────────────

class PaymentPlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    total_pence: int = Field(ge=1, le=10_000_000)
    instalments: int = Field(ge=2, le=24)
    frequency: Literal["weekly", "monthly"] = "monthly"
    notes: Optional[str] = None


@router.get(
    "/memberships/payment-plans",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_plans(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rows = await db.payment_plans.find(
        {"organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    ).sort("name", 1).to_list(200)
    return {"plans": rows, "count": len(rows)}


@router.post(
    "/memberships/payment-plans",
    dependencies=[Depends(require_module("memberships"))],
)
async def create_plan(body: PaymentPlanIn, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can manage payment plans.")
    instalment_pence = body.total_pence // body.instalments
    last_pence = body.total_pence - (instalment_pence * (body.instalments - 1))
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "name": body.name.strip(),
        "total_pence": body.total_pence,
        "instalments": body.instalments,
        "frequency": body.frequency,
        "instalment_pence": instalment_pence,
        "last_instalment_pence": last_pence,
        "notes": (body.notes or "").strip(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "created_by_id": user.get("id"),
    }
    await db.payment_plans.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put(
    "/memberships/payment-plans/{plan_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def update_plan(
    plan_id: str, body: PaymentPlanIn = Body(...),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can manage payment plans.")
    instalment_pence = body.total_pence // body.instalments
    last_pence = body.total_pence - (instalment_pence * (body.instalments - 1))
    res = await db.payment_plans.update_one(
        {"id": plan_id, "organization_id": org_id},
        {"$set": {
            "name": body.name.strip(),
            "total_pence": body.total_pence,
            "instalments": body.instalments,
            "frequency": body.frequency,
            "instalment_pence": instalment_pence,
            "last_instalment_pence": last_pence,
            "notes": (body.notes or "").strip(),
            "updated_at": _now_iso(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Payment plan not found")
    return await db.payment_plans.find_one({"id": plan_id}, {"_id": 0})


@router.delete(
    "/memberships/payment-plans/{plan_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def archive_plan(plan_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can manage payment plans.")
    res = await db.payment_plans.update_one(
        {"id": plan_id, "organization_id": org_id},
        {"$set": {"archived": True, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Payment plan not found")
    return {"ok": True, "id": plan_id}


# ─────────────────────────────────────────────────────────────────
# Assignments
# ─────────────────────────────────────────────────────────────────

class AssignmentIn(BaseModel):
    member_id: str
    attendee_sub_profile_id: Optional[str] = None
    started_on: Optional[str] = None  # YYYY-MM-DD; defaults to today


@router.post(
    "/memberships/payment-plans/{plan_id}/assign",
    dependencies=[Depends(require_module("memberships"))],
)
async def assign_plan(
    plan_id: str, body: AssignmentIn = Body(...),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    plan = await db.payment_plans.find_one(
        {"id": plan_id, "organization_id": org_id, "archived": {"$ne": True}},
    )
    if not plan:
        raise HTTPException(404, "Payment plan not found")
    member = await db.members.find_one(
        {"id": body.member_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    )
    if not member:
        raise HTTPException(404, "Member not found")
    started = body.started_on or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "plan_id": plan_id,
        "member_id": body.member_id,
        "attendee_sub_profile_id": body.attendee_sub_profile_id,
        "started_on": started,
        "instalment_no": 0,
        "paid_count": 0,
        "status": "active",
        "last_invoiced_period": None,
        "created_at": _now_iso(),
        "created_by_id": user.get("id"),
    }
    await db.payment_plan_assignments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get(
    "/memberships/payment-plans/assignments",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_assignments(
    member_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    q: dict = {"organization_id": org_id}
    if member_id:
        q["member_id"] = member_id
    rows = await db.payment_plan_assignments.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    plan_ids = list({r["plan_id"] for r in rows if r.get("plan_id")})
    plans = await db.payment_plans.find(
        {"id": {"$in": plan_ids}}, {"_id": 0, "id": 1, "name": 1, "instalments": 1,
                                     "instalment_pence": 1, "total_pence": 1},
    ).to_list(len(plan_ids) + 1) if plan_ids else []
    plan_by_id = {p["id"]: p for p in plans}
    for r in rows:
        r["plan"] = plan_by_id.get(r.get("plan_id"))
    return {"assignments": rows, "count": len(rows)}


@router.delete(
    "/memberships/payment-plans/assignments/{assign_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def cancel_assignment(assign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    res = await db.payment_plan_assignments.update_one(
        {"id": assign_id, "organization_id": org_id},
        {"$set": {"status": "cancelled", "cancelled_at": _now_iso(),
                  "cancelled_by_id": user.get("id")}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Assignment not found")
    return {"ok": True, "id": assign_id}


__all__ = ["router"]
