"""
GymAxis Service Operations — Engineer Lite CRM.

Iter 216h259. Field engineers needed a lightweight saved-customer book
so they stop retyping the same name / phone / address into every
quote and invoice. Org-wide shared list (any engineer on the same org
can see / save / use a customer) keyed by `svc_engineer_customers`.

Scope (per user choice on fork):
  • Name + email + phone + site name/address
  • Notes (free-form, multi-line)
  • Last job date (auto-stamped when a quote / invoice references the
    customer via `touch_for_quote`)
  • Equipment list (free text list — e.g. "Life Fitness 95Ti #1234")

Routes (all gated by `require_engineer_app_access`):
  GET   /api/svc/engineer/customers
  GET   /api/svc/engineer/customers/search?q=...
  GET   /api/svc/engineer/customers/{customer_id}
  POST  /api/svc/engineer/customers            (upsert on email/phone)
  PATCH /api/svc/engineer/customers/{customer_id}
  DELETE /api/svc/engineer/customers/{customer_id}
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.database import db
from utils.auth import get_current_user
from routes.partners import require_engineer_app_access

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/svc/engineer/customers",
    tags=["Service Ops · Engineer Lite CRM"],
    dependencies=[Depends(require_engineer_app_access)],
)


# ─────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────


class CustomerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=80)
    site_name: Optional[str] = Field(default=None, max_length=200)
    site_address: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=4000)
    equipment_list: Optional[list[str]] = None


class CustomerPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=80)
    site_name: Optional[str] = Field(default=None, max_length=200)
    site_address: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=4000)
    equipment_list: Optional[list[str]] = None


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> str:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _norm_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    return email.strip().lower() or None


def _norm_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    return re.sub(r"[^0-9+]", "", phone.strip()) or None


def _strip(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def _to_doc(payload: CustomerIn, *, org_id: str, user_id: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "created_by_id": user_id,
        "name": payload.name.strip(),
        "email": _norm_email(payload.email),
        "phone": _norm_phone(payload.phone),
        "site_name": (payload.site_name or "").strip() or None,
        "site_address": (payload.site_address or "").strip() or None,
        "notes": (payload.notes or "").strip() or None,
        "equipment_list": [e.strip() for e in (payload.equipment_list or []) if e and e.strip()],
        "last_job_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


async def _find_duplicate(org_id: str, email: Optional[str], phone: Optional[str]) -> Optional[dict]:
    """Look up an existing customer in the org by email OR phone."""
    if not email and not phone:
        return None
    or_clauses: list[dict] = []
    if email:
        or_clauses.append({"email": email})
    if phone:
        or_clauses.append({"phone": phone})
    if not or_clauses:
        return None
    return await db.svc_engineer_customers.find_one(
        {"organization_id": org_id, "$or": or_clauses}
    )


# ─────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_customers(
    user=Depends(get_current_user),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Org-wide list of saved customers, newest first."""
    org_id = _of(user)
    query: dict = {"organization_id": org_id}
    if q:
        needle = re.escape(q.strip())
        if needle:
            query["$or"] = [
                {"name":  {"$regex": needle, "$options": "i"}},
                {"email": {"$regex": needle, "$options": "i"}},
                {"phone": {"$regex": needle, "$options": "i"}},
                {"site_name":    {"$regex": needle, "$options": "i"}},
                {"site_address": {"$regex": needle, "$options": "i"}},
            ]
    cur = db.svc_engineer_customers.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit)
    rows = await cur.to_list(length=limit)
    return {"customers": rows, "total": len(rows)}


@router.get("/search")
async def search_customers(
    user=Depends(get_current_user),
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Compact autocomplete results for Quote / Invoice builders."""
    org_id = _of(user)
    needle = re.escape(q.strip())
    if not needle:
        return {"results": []}
    cur = db.svc_engineer_customers.find(
        {
            "organization_id": org_id,
            "$or": [
                {"name":  {"$regex": needle, "$options": "i"}},
                {"email": {"$regex": needle, "$options": "i"}},
                {"phone": {"$regex": needle, "$options": "i"}},
                {"site_name":    {"$regex": needle, "$options": "i"}},
            ],
        },
        {
            "_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
            "site_name": 1, "site_address": 1, "last_job_at": 1,
        },
    ).sort("updated_at", -1).limit(limit)
    rows = await cur.to_list(length=limit)
    return {"results": rows}


@router.get("/{customer_id}")
async def get_customer(customer_id: str, user=Depends(get_current_user)):
    org_id = _of(user)
    doc = await db.svc_engineer_customers.find_one(
        {"organization_id": org_id, "id": customer_id}
    )
    if not doc:
        raise HTTPException(404, "Customer not found")
    return _strip(doc)


@router.post("", status_code=201)
async def create_customer(payload: CustomerIn, user=Depends(get_current_user)):
    """Create a customer. Idempotent on (org × email) or (org × phone):
    if a match exists we PATCH the matching row with any new fields
    instead of inserting a duplicate."""
    org_id = _of(user)
    doc = _to_doc(payload, org_id=org_id, user_id=user["id"])

    dupe = await _find_duplicate(org_id, doc["email"], doc["phone"])
    if dupe:
        updates = {
            k: v for k, v in doc.items()
            if k in ("name", "email", "phone", "site_name", "site_address",
                     "notes", "equipment_list") and v
        }
        updates["updated_at"] = _now_iso()
        await db.svc_engineer_customers.update_one(
            {"organization_id": org_id, "id": dupe["id"]},
            {"$set": updates},
        )
        fresh = await db.svc_engineer_customers.find_one(
            {"organization_id": org_id, "id": dupe["id"]}
        )
        return {"customer": _strip(fresh), "merged": True}

    await db.svc_engineer_customers.insert_one(doc.copy())
    return {"customer": _strip(doc), "merged": False}


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: str,
    payload: CustomerPatch,
    user=Depends(get_current_user),
):
    org_id = _of(user)
    existing = await db.svc_engineer_customers.find_one(
        {"organization_id": org_id, "id": customer_id}
    )
    if not existing:
        raise HTTPException(404, "Customer not found")
    raw = payload.model_dump(exclude_unset=True)
    updates: dict = {}
    if "name" in raw and raw["name"] is not None:
        if not raw["name"].strip():
            raise HTTPException(400, "Name cannot be empty")
        updates["name"] = raw["name"].strip()
    if "email" in raw:
        updates["email"] = _norm_email(raw["email"])
    if "phone" in raw:
        updates["phone"] = _norm_phone(raw["phone"])
    for k in ("site_name", "site_address", "notes"):
        if k in raw:
            v = raw[k]
            updates[k] = (v or "").strip() or None
    if "equipment_list" in raw and raw["equipment_list"] is not None:
        updates["equipment_list"] = [e.strip() for e in raw["equipment_list"] if e and e.strip()]
    if updates:
        updates["updated_at"] = _now_iso()
        await db.svc_engineer_customers.update_one(
            {"organization_id": org_id, "id": customer_id},
            {"$set": updates},
        )
    fresh = await db.svc_engineer_customers.find_one(
        {"organization_id": org_id, "id": customer_id}
    )
    return _strip(fresh)


@router.delete("/{customer_id}")
async def delete_customer(customer_id: str, user=Depends(get_current_user)):
    org_id = _of(user)
    r = await db.svc_engineer_customers.delete_one(
        {"organization_id": org_id, "id": customer_id}
    )
    if not r.deleted_count:
        raise HTTPException(404, "Customer not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Public helpers (used by quote/invoice builders to stamp last_job_at)
# ─────────────────────────────────────────────────────────────────


async def touch_last_job(org_id: str, *, email: Optional[str], phone: Optional[str]) -> None:
    """Best-effort stamp `last_job_at` on a matching customer row."""
    if not org_id:
        return
    email = _norm_email(email)
    phone = _norm_phone(phone)
    if not email and not phone:
        return
    try:
        match = await _find_duplicate(org_id, email, phone)
        if match:
            await db.svc_engineer_customers.update_one(
                {"organization_id": org_id, "id": match["id"]},
                {"$set": {"last_job_at": _now_iso(), "updated_at": _now_iso()}},
            )
    except Exception:
        logger.debug("touch_last_job failed", exc_info=True)


async def ensure_indexes() -> None:
    try:
        await db.svc_engineer_customers.create_index(
            [("organization_id", 1), ("email", 1)],
            name="svc_eng_customers_org_email",
        )
        await db.svc_engineer_customers.create_index(
            [("organization_id", 1), ("phone", 1)],
            name="svc_eng_customers_org_phone",
        )
        await db.svc_engineer_customers.create_index(
            [("organization_id", 1), ("updated_at", -1)],
            name="svc_eng_customers_org_recent",
        )
    except Exception:
        logger.debug("svc_engineer_customers index creation skipped", exc_info=True)


__all__ = ["router", "ensure_indexes", "touch_last_job"]
