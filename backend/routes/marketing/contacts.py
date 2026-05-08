"""Marketing-namespaced contacts CRUD — Iter 215bf (May 1, 2026).

Why this exists
----------------
Marketing-only customers (those without a CRM license, e.g. on the £49/mo
Marketing module alone) need a basic contact directory so they can:

  • see who's been captured by their lead-capture forms,
  • edit a contact's email / consent / tags / custom properties,
  • import contacts in bulk via CSV,
  • feed those contacts into audiences and campaigns.

Today the CRM app at `/crm` provides a full contact UI but it sits behind
its own JWT (`get_crm_user`) and a CRM license. We don't want to require
a CRM license just to manage your marketing contact list.

This module exposes the same `crm_contacts` collection under a new
``/api/marketing/contacts`` namespace gated by
``require_module(("crm", "marketing"))`` — so any org with **either**
license can list, view, edit, and bulk-import contacts. Pipelines, deals,
inbox, calendar, CPQ etc. remain CRM-strict (gated on `crm_core.py` /
`crm_inbox.py` / `crm_cpq.py` via `get_crm_user`).
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import _org_id


router = APIRouter()


# OR-semantics module guard: any of CRM or Marketing licenses grants access.
_LITE_GUARD = Depends(require_module(("crm", "marketing")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_id(d: dict) -> dict:
    d.pop("_id", None)
    return d


@router.get("/marketing/contacts", dependencies=[_LITE_GUARD])
async def list_marketing_contacts(
    search: str = "",
    skip: int = 0,
    limit: int = 50,
    user: dict = Depends(get_current_user),
) -> dict:
    """List contacts with optional substring search across name/email."""
    org_id = await _org_id(user)
    q: dict = {"organization_id": org_id}
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [
            {"first_name": rx}, {"last_name": rx}, {"email": rx}, {"phone": rx},
        ]
    total = await db.crm_contacts.count_documents(q)
    cur = (
        db.crm_contacts.find(q, {"_id": 0})
        .sort("created_at", -1)
        .skip(max(0, int(skip)))
        .limit(max(1, min(200, int(limit))))
    )
    items = await cur.to_list(length=limit)
    return {"contacts": [_strip_id(c) for c in items], "total": total}


@router.post("/marketing/contacts", dependencies=[_LITE_GUARD])
async def create_marketing_contact(
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    org_id = await _org_id(user)
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Email is required")
    existing = await db.crm_contacts.find_one(
        {"organization_id": org_id, "email": email}, {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(409, "A contact with this email already exists")
    contact = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "email": email,
        "first_name": (body.get("first_name") or "").strip(),
        "last_name": (body.get("last_name") or "").strip(),
        "phone": (body.get("phone") or "").strip() or None,
        "tags": list(body.get("tags") or []),
        "custom_fields": dict(body.get("custom_fields") or {}),
        "marketing_consent": {
            "email": bool(body.get("email_consent", True)),
            "sms": bool(body.get("sms_consent", False)),
        },
        "source": body.get("source") or "marketing_directory",
        "created_at": _now_iso(),
        "created_by": user["id"],
    }
    await db.crm_contacts.insert_one(dict(contact))
    return {"contact": contact}


@router.get("/marketing/contacts/{contact_id}", dependencies=[_LITE_GUARD])
async def get_marketing_contact(
    contact_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    org_id = await _org_id(user)
    c = await db.crm_contacts.find_one(
        {"id": contact_id, "organization_id": org_id}, {"_id": 0},
    )
    if not c:
        raise HTTPException(404, "Contact not found")
    return {"contact": c}


@router.put("/marketing/contacts/{contact_id}", dependencies=[_LITE_GUARD])
async def update_marketing_contact(
    contact_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    org_id = await _org_id(user)
    allowed = {
        "first_name", "last_name", "email", "phone", "tags",
        "custom_fields", "marketing_consent", "source",
    }
    update = {k: v for k, v in body.items() if k in allowed}
    if "email" in update:
        update["email"] = (update["email"] or "").strip().lower()
        if not update["email"]:
            raise HTTPException(400, "Email cannot be empty")
    update["updated_at"] = _now_iso()
    update["updated_by"] = user["id"]
    res = await db.crm_contacts.update_one(
        {"id": contact_id, "organization_id": org_id},
        {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Contact not found")
    c = await db.crm_contacts.find_one(
        {"id": contact_id, "organization_id": org_id}, {"_id": 0},
    )
    return {"contact": c}


@router.delete("/marketing/contacts/{contact_id}", dependencies=[_LITE_GUARD])
async def delete_marketing_contact(
    contact_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    org_id = await _org_id(user)
    res = await db.crm_contacts.delete_one(
        {"id": contact_id, "organization_id": org_id},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Contact not found")
    return {"deleted": True}


@router.post("/marketing/contacts/import", dependencies=[_LITE_GUARD])
async def import_marketing_contacts(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Bulk import contacts from a CSV file.

    Accepts: ``email``, ``first_name``, ``last_name``, ``phone``, ``tags``
    (comma-separated). ``email`` is required; everything else is optional.
    Existing contacts (matched by email + org) are upserted (no duplicates).
    Returns counts so the UI can render a clear summary.
    """
    org_id = await _org_id(user)
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    for i, row in enumerate(reader, start=2):  # start=2 to account for header row
        email = (row.get("email") or "").strip().lower()
        if not email:
            skipped += 1
            continue
        try:
            doc = {
                "organization_id": org_id,
                "email": email,
                "first_name": (row.get("first_name") or "").strip(),
                "last_name": (row.get("last_name") or "").strip(),
                "phone": (row.get("phone") or "").strip() or None,
                "tags": [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()],
                "marketing_consent": {"email": True, "sms": False},
                "source": "csv_import",
                "updated_at": _now_iso(),
                "updated_by": user["id"],
            }
            existing = await db.crm_contacts.find_one(
                {"organization_id": org_id, "email": email}, {"_id": 0, "id": 1},
            )
            if existing:
                await db.crm_contacts.update_one(
                    {"id": existing["id"]}, {"$set": doc},
                )
                updated += 1
            else:
                doc["id"] = str(uuid.uuid4())
                doc["created_at"] = _now_iso()
                doc["created_by"] = user["id"]
                await db.crm_contacts.insert_one(dict(doc))
                created += 1
        except Exception as e:  # noqa: BLE001 — best-effort import
            errors.append(f"Row {i}: {e}")
            skipped += 1
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors[:25]}


__all__ = ["router"]
