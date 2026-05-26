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

import csv
import io
from datetime import datetime, timezone
from typing import Optional
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
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


def _contact_or_clauses(email: Optional[str], phone: Optional[str]) -> list[dict]:
    """Build the $or clauses used to match quotes/invoices by customer."""
    clauses: list[dict] = []
    if email:
        clauses.append({"customer_email": email})
    if phone:
        clauses.append({"customer_phone": phone})
    return clauses


async def _recent_quotes(org_id: str, email: Optional[str], phone: Optional[str], limit: int = 5):
    clauses = _contact_or_clauses(email, phone)
    if not clauses:
        return []
    cur = db.svc_engineer_quotes.find(
        {"organization_id": org_id, "$or": clauses},
        {
            "_id": 0, "id": 1, "quote_number": 1, "status": 1, "total": 1,
            "created_at": 1, "updated_at": 1, "case_reference": 1,
            "description_of_work": 1,
        },
    ).sort("created_at", -1).limit(limit)
    return await cur.to_list(length=limit)


async def _recent_invoices(org_id: str, email: Optional[str], phone: Optional[str], limit: int = 5):
    clauses = _contact_or_clauses(email, phone)
    if not clauses:
        return []
    cur = db.svc_engineer_invoices.find(
        {"organization_id": org_id, "$or": clauses},
        {
            "_id": 0, "id": 1, "invoice_number": 1, "status": 1, "total": 1,
            "created_at": 1, "issue_date": 1, "case_reference": 1,
        },
    ).sort("created_at", -1).limit(limit)
    return await cur.to_list(length=limit)


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


@router.get("/lookup")
async def lookup_customer(
    user=Depends(get_current_user),
    email: Optional[str] = Query(default=None, max_length=200),
    phone: Optional[str] = Query(default=None, max_length=80),
    name: Optional[str] = Query(default=None, max_length=200),
    site_name: Optional[str] = Query(default=None, max_length=200),
):
    """Cheap probe used by the Quote/Invoice builders + New Job card to
    decide whether to nudge the engineer to save a new customer.
    Returns the matching row if one exists, else `{found: false}`.

    Iter 220h — also matches on case-insensitive `name` (and optionally
    `site_name`) so the New Job card can prompt the engineer the moment
    they type a customer who isn't in the saved book.
    """
    org_id = _of(user)
    norm_email = _norm_email(email)
    norm_phone = _norm_phone(phone)
    needle_name = (name or "").strip()
    needle_site = (site_name or "").strip()

    # Pass 1 — strong signals (email/phone). Always wins if it matches.
    if norm_email or norm_phone:
        strong = await _find_duplicate(org_id, norm_email, norm_phone)
        if strong:
            return {"found": True, "match_via": "contact", "customer": _strip(strong)}

    # Pass 2 — name match. Case-insensitive exact-name (with optional
    # site disambiguation). We don't do fuzzy here — the typeahead
    # already covers "looks similar".
    if needle_name:
        q: dict = {
            "organization_id": org_id,
            "name": {"$regex": f"^{re.escape(needle_name)}$", "$options": "i"},
        }
        if needle_site:
            q["site_name"] = {"$regex": f"^{re.escape(needle_site)}$", "$options": "i"}
        match = await db.svc_engineer_customers.find_one(q)
        if match:
            return {"found": True, "match_via": "name", "customer": _strip(match)}

    return {"found": False}


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


@router.get("/typeahead")
async def typeahead_customers(
    user=Depends(get_current_user),
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=8, ge=1, le=30),
):
    """Iter 220f — Combined typeahead used by the New Job card.

    Sources (merged, deduped on name+site, max `limit` rows):
      1. `svc_engineer_customers` — the saved address book (highest
         priority, gets `source='saved'`).
      2. `svc_cases` distinct customer_name / site_name matches —
         covers customers logged via the email-parse flow, an admin,
         or the public intake card that haven't been promoted into the
         saved book yet. `source='history'`.

    Postcode is pulled from the most recent matching case so the
    engineer doesn't have to type the postcode either.
    """
    org_id = _of(user)
    needle = re.escape(q.strip())
    if not needle:
        return {"results": []}

    # 1. Saved customers
    saved = await db.svc_engineer_customers.find(
        {
            "organization_id": org_id,
            "$or": [
                {"name":      {"$regex": needle, "$options": "i"}},
                {"email":     {"$regex": needle, "$options": "i"}},
                {"phone":     {"$regex": needle, "$options": "i"}},
                {"site_name": {"$regex": needle, "$options": "i"}},
            ],
        },
        {
            "_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
            "site_name": 1, "site_address": 1, "last_job_at": 1,
        },
    ).sort("updated_at", -1).limit(limit).to_list(limit)
    results: list[dict] = []
    dedupe: set[tuple] = set()
    for r in saved:
        key = ((r.get("name") or "").lower(), (r.get("site_name") or "").lower())
        dedupe.add(key)
        results.append({**r, "source": "saved", "site_postcode": None})

    # 2. Case-history fallback — only if we still need more rows.
    remaining = limit - len(results)
    if remaining > 0:
        cases = await db.svc_cases.find(
            {
                "organization_id": org_id,
                "$or": [
                    {"customer_name":  {"$regex": needle, "$options": "i"}},
                    {"customer_email": {"$regex": needle, "$options": "i"}},
                    {"customer_phone": {"$regex": needle, "$options": "i"}},
                    {"site_name":      {"$regex": needle, "$options": "i"}},
                    {"site_postcode":  {"$regex": needle, "$options": "i"}},
                ],
            },
            {
                "_id": 0, "id": 1,
                "customer_name": 1, "customer_email": 1, "customer_phone": 1,
                "site_name": 1, "site_address": 1, "site_postcode": 1,
                "created_at": 1, "updated_at": 1,
            },
        ).sort([("updated_at", -1), ("created_at", -1)]).limit(remaining * 5).to_list(remaining * 5)

        for c in cases:
            name = (c.get("customer_name") or "").strip()
            if not name:
                continue
            key = (name.lower(), (c.get("site_name") or "").lower())
            if key in dedupe:
                continue
            dedupe.add(key)
            results.append({
                "id": None,
                "name": name,
                "email": c.get("customer_email"),
                "phone": c.get("customer_phone"),
                "site_name": c.get("site_name"),
                "site_address": c.get("site_address"),
                "site_postcode": c.get("site_postcode"),
                "last_job_at": c.get("updated_at") or c.get("created_at"),
                "source": "history",
            })
            if len(results) >= limit:
                break
    return {"results": results[:limit]}


@router.get("/template.csv")
async def template_csv(_user=Depends(get_current_user)):
    """Canonical CSV template for the bulk-import workflow."""
    header = [
        "name", "email", "phone", "site_name", "site_address",
        "notes", "equipment_list",
    ]
    example = [
        "Acme Gyms Ltd",
        "manager@acme.co.uk",
        "+44 7700 900 001",
        "Acme HQ · Leeds",
        "12 Industrial Way, Leeds LS10 1AB",
        "Access via side gate. Manager: Sarah.",
        "Life Fitness 95Ti #1234 | Concept2 RowErg | Wattbike Atom",
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerow(example)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="engineer-customers-template.csv"'},
    )


@router.post("/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Bulk-create customers from a CSV upload.

    Accepted columns (case-insensitive, any subset, in any order):
      name, email, phone, site_name, site_address, notes, equipment_list

    `equipment_list` is split on `|`, `;`, or newline. Idempotent on
    (org × email) and (org × phone) — duplicate rows update the
    existing record instead of inserting a new one.
    """
    org_id = _of(user)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception as e:
            raise HTTPException(400, "Could not decode CSV file") from e

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV has no header row")
    norm_fields = {(h or "").strip().lower(): (h or "") for h in reader.fieldnames}
    if "name" not in norm_fields:
        raise HTTPException(400, "CSV must include a 'name' column")

    def _get(row: dict, key: str) -> str:
        src_key = norm_fields.get(key)
        if not src_key:
            return ""
        return (row.get(src_key) or "").strip()

    imported = 0
    merged = 0
    skipped: list[dict] = []
    errors: list[dict] = []

    for idx, row in enumerate(reader, start=2):  # row 1 = header
        name = _get(row, "name")
        if not name:
            skipped.append({"row": idx, "reason": "missing name"})
            continue
        email = _norm_email(_get(row, "email"))
        phone = _norm_phone(_get(row, "phone"))
        equipment_raw = _get(row, "equipment_list")
        equipment = [
            chunk.strip()
            for chunk in re.split(r"[|;\n]+", equipment_raw)
            if chunk and chunk.strip()
        ]
        doc_base = {
            "name": name,
            "email": email,
            "phone": phone,
            "site_name": (_get(row, "site_name") or "").strip() or None,
            "site_address": (_get(row, "site_address") or "").strip() or None,
            "notes": (_get(row, "notes") or "").strip() or None,
            "equipment_list": equipment,
        }
        try:
            dupe = await _find_duplicate(org_id, email, phone)
            if dupe:
                updates = {
                    k: v for k, v in doc_base.items() if v not in (None, "", [])
                }
                updates["updated_at"] = _now_iso()
                await db.svc_engineer_customers.update_one(
                    {"organization_id": org_id, "id": dupe["id"]},
                    {"$set": updates},
                )
                merged += 1
            else:
                new_doc = {
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "created_by_id": user["id"],
                    **doc_base,
                    "last_job_at": None,
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
                await db.svc_engineer_customers.insert_one(new_doc)
                imported += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"row": idx, "error": str(exc)[:200]})

    return {
        "imported": imported,
        "merged": merged,
        "skipped": skipped,
        "errors": errors,
        "total_processed": imported + merged + len(skipped) + len(errors),
    }


@router.get("/{customer_id}")
async def get_customer(customer_id: str, user=Depends(get_current_user)):
    org_id = _of(user)
    doc = await db.svc_engineer_customers.find_one(
        {"organization_id": org_id, "id": customer_id}
    )
    if not doc:
        raise HTTPException(404, "Customer not found")
    doc = _strip(doc)
    # Iter 216h260 — surface recent quotes + invoices inline for repeat-business view
    try:
        doc["recent_quotes"] = await _recent_quotes(org_id, doc.get("email"), doc.get("phone"))
    except Exception:
        doc["recent_quotes"] = []
    try:
        doc["recent_invoices"] = await _recent_invoices(org_id, doc.get("email"), doc.get("phone"))
    except Exception:
        doc["recent_invoices"] = []
    return doc


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
