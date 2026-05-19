"""CRM · Master Price List / Product Catalogue (Iter 216h224).

Backs the new quote-builder margin calc and the "Master price list"
feature from the user's Phase 2 prompt.

Data model — single collection `crm_products`:
  {
    id: uuid,
    organization_id: <uuid>,             # required — products are
                                         # always org-scoped (unlike
                                         # picklists). Defaults across
                                         # tenants leak commercial info.
    sku: "GA-EQUIP-001",                 # optional, unique-per-org
    name: "Technogym Run 1000",
    description: "string",
    category: "Equipment" | "Service" |
              "Labour" | "Callout" |
              "Maintenance Plan" |
              "Membership" | "Other",
    unit: "each" | "hour" | "day" | "month" | "km",
    cost_price: 1200.00,                 # what we pay the supplier
    sell_price: 1800.00,                 # default list price
    currency: "GBP",
    markup_percent: 50.0,                # derived but stored for
                                         # quick filtering
    tax_rate: 20.0,                      # VAT %
    supplier_id: <uuid> | null,
    supplier_name: "Technogym UK",
    image_url: null,
    active: true,
    notes: "...",
    sort_order: int,
    created_at, created_by, updated_at,
  }

Endpoints:
  GET    /crm/products                  list + filter + search
  GET    /crm/products/{id}
  POST   /crm/products                  create (admin)
  PATCH  /crm/products/{id}             update (admin)
  DELETE /crm/products/{id}             soft-delete (sets active=false)
  POST   /crm/products/bulk-import      CSV bulk import (admin)
  GET    /crm/products/categories       distinct categories list

Quote-builder integration is in `crm_cpq.py` — when a line item carries
a `product_id` we hydrate the cost/sell/tax from the catalogue (line
items still allow free-form items for one-off services).
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/products", tags=["CRM Products"])


PRODUCT_CATEGORIES: list[str] = [
    "Equipment", "Service", "Labour", "Callout",
    "Maintenance Plan", "Membership", "Parts", "Discount", "Other",
]


# ── Helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _is_admin(user: dict) -> bool:
    return (
        bool(user.get("is_master_admin"))
        or bool(user.get("is_pulse_admin"))
        or (user.get("role") or "").lower() in ("admin", "owner", "manager")
    )


def _calc_markup(cost: float, sell: float) -> float:
    """Markup % = (sell − cost) / cost × 100. Returns 0 when cost is 0
    so the value remains numeric and sortable (vs +inf)."""
    if not cost or cost <= 0:
        return 0.0
    return round(((sell - cost) / cost) * 100, 2)


# ── Read ───────────────────────────────────────────────────────────


@router.get("")
async def list_products(
    search: str = "",
    category: str = "",
    active: bool | None = None,
    skip: int = 0,
    limit: int = 100,
    user=Depends(get_crm_user),
) -> dict:
    """Paged list with text search across name / sku / description."""
    q: dict[str, Any] = {**_of(user)}
    if category:
        q["category"] = category
    if active is not None:
        q["active"] = active
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"name": rx}, {"sku": rx}, {"description": rx}]

    cursor = db.crm_products.find(q, {"_id": 0}).sort([("sort_order", 1), ("name", 1)]).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    total = await db.crm_products.count_documents(q)
    return {"products": items, "total": total, "skip": skip, "limit": limit}


@router.get("/categories")
async def list_categories(user=Depends(get_crm_user)) -> dict:
    """Return the canonical category list (mixed with any org-custom
    categories that already exist on records)."""
    custom = await db.crm_products.distinct("category", _of(user))
    merged = list(PRODUCT_CATEGORIES)
    for c in custom:
        if c and c not in merged:
            merged.append(c)
    return {"categories": merged}


@router.get("/{product_id}")
async def get_product(product_id: str, user=Depends(get_crm_user)) -> dict:
    p = await db.crm_products.find_one({"id": product_id, **_of(user)}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Product not found")
    return p


# ── Write ──────────────────────────────────────────────────────────


def _validate(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "name is required")
    category = (data.get("category") or "Other").strip() or "Other"
    cost = float(data.get("cost_price", 0) or 0)
    sell = float(data.get("sell_price", 0) or 0)
    if cost < 0 or sell < 0:
        raise HTTPException(422, "Prices cannot be negative")
    sku = (data.get("sku") or "").strip() or None
    return {
        "name": name,
        "description": (data.get("description") or "").strip(),
        "category": category,
        "unit": (data.get("unit") or "each").strip(),
        "sku": sku,
        "cost_price": round(cost, 2),
        "sell_price": round(sell, 2),
        "currency": (data.get("currency") or "GBP").upper(),
        "markup_percent": _calc_markup(cost, sell),
        "tax_rate": float(data.get("tax_rate", 20) or 0),
        "supplier_id": data.get("supplier_id"),
        "supplier_name": (data.get("supplier_name") or "").strip(),
        "image_url": data.get("image_url"),
        "active": bool(data.get("active", True)),
        "notes": (data.get("notes") or "").strip(),
        "sort_order": int(data.get("sort_order", 100)),
    }


@router.post("")
async def create_product(data: dict, user=Depends(get_crm_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins / owners can manage the master price list")
    fields = _validate(data)
    sku = fields.get("sku")
    # Reject SKU collisions within the same org.
    if sku:
        dup = await db.crm_products.find_one({"sku": sku, **_of(user)})
        if dup:
            raise HTTPException(409, f"A product with SKU '{sku}' already exists")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": user.get("organization_id"),
        **fields,
        "created_at": _now(),
        "created_by": user.get("id", ""),
        "updated_at": _now(),
    }
    await db.crm_products.insert_one(doc)
    await log_audit(user, "product", doc["id"], "created", {"name": doc["name"]})
    doc.pop("_id", None)
    return doc


@router.patch("/{product_id}")
async def update_product(product_id: str, data: dict, user=Depends(get_crm_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins / owners can manage the master price list")
    existing = await db.crm_products.find_one({"id": product_id, **_of(user)}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Product not found")

    # Merge the incoming subset onto the existing fields, then re-validate.
    merged = {**existing, **{k: v for k, v in data.items() if k != "id"}}
    fields = _validate(merged)
    # SKU uniqueness — only check when the SKU actually changed.
    if fields.get("sku") and fields["sku"] != existing.get("sku"):
        dup = await db.crm_products.find_one(
            {"sku": fields["sku"], **_of(user), "id": {"$ne": product_id}},
        )
        if dup:
            raise HTTPException(409, f"A product with SKU '{fields['sku']}' already exists")

    updates = {**fields, "updated_at": _now()}
    await db.crm_products.update_one(
        {"id": product_id, **_of(user)},
        {"$set": updates},
    )
    await log_audit(user, "product", product_id, "updated")
    return {**existing, **updates}


@router.delete("/{product_id}")
async def delete_product(product_id: str, user=Depends(get_crm_user)) -> dict:
    """Soft-delete — flips `active=false`. Preserves the relational
    link from quotes that already reference this product."""
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins / owners can manage the master price list")
    res = await db.crm_products.update_one(
        {"id": product_id, **_of(user)},
        {"$set": {"active": False, "updated_at": _now()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Product not found")
    await log_audit(user, "product", product_id, "deactivated")
    return {"deactivated": True, "id": product_id}


@router.post("/bulk-import")
async def bulk_import_products(
    file: UploadFile = File(...),
    user=Depends(get_crm_user),
) -> dict:
    """CSV bulk-import. Required columns: name. Optional: sku,
    description, category, unit, cost_price, sell_price, tax_rate,
    supplier_name. SKU collisions update the existing row in-place
    so re-running the same CSV is idempotent.
    """
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins / owners can manage the master price list")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    created = updated = skipped = 0
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):
        try:
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("name"):
                skipped += 1
                errors.append(f"Row {idx}: missing name")
                continue
            payload = _validate(row)
            sku = payload.get("sku")
            if sku:
                existing = await db.crm_products.find_one({"sku": sku, **_of(user)})
                if existing:
                    await db.crm_products.update_one(
                        {"id": existing["id"]}, {"$set": {**payload, "updated_at": _now()}},
                    )
                    updated += 1
                    continue
            await db.crm_products.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": user.get("organization_id"),
                **payload,
                "created_at": _now(),
                "created_by": user.get("id", ""),
                "updated_at": _now(),
            })
            created += 1
        except HTTPException as e:
            errors.append(f"Row {idx}: {e.detail}")
            skipped += 1
        except Exception as e:
            errors.append(f"Row {idx}: {e}")
            skipped += 1

    await log_audit(user, "product", "bulk-import", "imported", {"created": created, "updated": updated, "skipped": skipped})
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors[:25]}


# ── Indexes ────────────────────────────────────────────────────────


async def ensure_product_indexes() -> None:
    try:
        await db.crm_products.create_index([("organization_id", 1), ("sku", 1)], sparse=True)
        await db.crm_products.create_index([("organization_id", 1), ("name", 1)])
        await db.crm_products.create_index([("organization_id", 1), ("active", 1)])
    except Exception:
        logger.exception("ensure_product_indexes failed (non-fatal)")
