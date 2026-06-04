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

# Iter 220 p1 — extended Master Price List fields preserved on create/edit.
_EXTENDED_STR_FIELDS = {
    "sage_code", "model", "sub_category", "product_family", "manufacturer",
    "supplier_part_number", "manufacturer_part_number", "warranty",
    "compatibility", "internal_notes", "customer_notes", "status",
    "effective_date",
}
_EXTENDED_NUM_FIELDS = {
    "retail_price", "trade_price", "list_price", "discount", "margin",
    "installation_cost", "delivery_cost",
}
_PROVENANCE_FIELDS = {
    "source_sheet", "source_row", "section", "import_batch_id", "version_id",
    "unmapped_fields",
}


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
    supplier: str = "",
    status: str = "",
    import_batch: str = "",
    has_unmapped: bool | None = None,
    missing_sage: bool | None = None,
    missing_price: bool | None = None,
    sort: str = "",
    skip: int = 0,
    limit: int = 100,
    user=Depends(get_crm_user),
) -> dict:
    """Paged list with text search + Master Price List filters."""
    q: dict[str, Any] = {**_of(user)}
    if category:
        q["category"] = category
    if active is not None:
        q["active"] = active
    if supplier:
        q["supplier_name"] = supplier
    if import_batch:
        q["import_batch_id"] = import_batch
    if status:
        q["status"] = status
    if has_unmapped:
        q["unmapped_fields.0"] = {"$exists": True}
    if missing_sage:
        q["$and"] = q.get("$and", []) + [{"$or": [{"sage_code": {"$exists": False}}, {"sage_code": ""}]}]
    if missing_price:
        q["sell_price"] = {"$lte": 0}
        q["cost_price"] = {"$lte": 0}
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"name": rx}, {"sku": rx}, {"description": rx},
                    {"sage_code": rx}, {"manufacturer": rx}, {"model": rx}]

    sort_map = {
        "name": [("name", 1)], "sku": [("sku", 1)],
        "cost": [("cost_price", 1)], "sell": [("sell_price", 1)],
        "updated": [("updated_at", -1)],
    }
    order = sort_map.get(sort, [("sort_order", 1), ("name", 1)])
    cursor = db.crm_products.find(q, {"_id": 0}).sort(order).skip(skip).limit(limit)
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


@router.get("/{product_id}/expand")
async def expand_product(product_id: str, user=Depends(get_crm_user)) -> dict:
    """Iter 216h267 — explode a bundle into resolved component lines.

    For a non-bundle product, returns a single-item list with the
    product itself. For a bundle, hydrates each `bundle_items` entry
    with the current cost_price / sell_price / tax_rate from the
    catalogue. Override prices on the bundle line replace `sell_price`.

    Used by the quote builder: drop a bundle into a quote and it
    explodes into one line per component (so margin maths stays
    truthful and the supplier routing on each line is preserved).
    """
    bundle = await db.crm_products.find_one(
        {"id": product_id, **_of(user)}, {"_id": 0}
    )
    if not bundle:
        raise HTTPException(404, "Product not found")
    if not bundle.get("is_bundle"):
        return {"is_bundle": False, "items": [
            {
                "product_id": bundle["id"],
                "sku": bundle.get("sku"),
                "name": bundle["name"],
                "category": bundle.get("category"),
                "unit": bundle.get("unit"),
                "quantity": 1,
                "cost_price": bundle.get("cost_price", 0),
                "sell_price": bundle.get("sell_price", 0),
                "tax_rate": bundle.get("tax_rate", 0),
                "supplier_id": bundle.get("supplier_id"),
                "supplier_name": bundle.get("supplier_name"),
                "image_url": bundle.get("image_url"),
            }
        ]}
    item_ids = [it["product_id"] for it in (bundle.get("bundle_items") or [])]
    rows: list[dict] = []
    if item_ids:
        cur = db.crm_products.find(
            {"id": {"$in": item_ids}, **_of(user)},
            {"_id": 0},
        )
        rows = await cur.to_list(len(item_ids))
    by_id = {p["id"]: p for p in rows}
    expanded: list[dict] = []
    for entry in (bundle.get("bundle_items") or []):
        p = by_id.get(entry["product_id"])
        if not p:
            # Component was deleted — surface a stub so the manager
            # notices, but don't 404 the whole bundle.
            expanded.append({
                "product_id": entry["product_id"],
                "name": "(missing product)",
                "missing": True,
                "quantity": entry["quantity"],
                "cost_price": 0,
                "sell_price": 0,
                "tax_rate": 0,
            })
            continue
        sell_price = p.get("sell_price", 0)
        if entry.get("override_sell_price") is not None:
            sell_price = entry["override_sell_price"]
        expanded.append({
            "product_id": p["id"],
            "sku": p.get("sku"),
            "name": p["name"],
            "category": p.get("category"),
            "unit": p.get("unit"),
            "quantity": entry["quantity"],
            "cost_price": p.get("cost_price", 0),
            "sell_price": sell_price,
            "tax_rate": p.get("tax_rate", 0),
            "supplier_id": p.get("supplier_id"),
            "supplier_name": p.get("supplier_name"),
            "image_url": p.get("image_url"),
            "from_bundle_id": bundle["id"],
            "from_bundle_name": bundle["name"],
        })
    rollup_cost = sum(float(e["cost_price"]) * float(e["quantity"]) for e in expanded)
    rollup_sell = sum(float(e["sell_price"]) * float(e["quantity"]) for e in expanded)
    return {
        "is_bundle": True,
        "bundle_id": bundle["id"],
        "bundle_name": bundle["name"],
        "items": expanded,
        "rollup_cost": round(rollup_cost, 2),
        "rollup_sell": round(rollup_sell, 2),
        "rollup_margin_percent": round(
            ((rollup_sell - rollup_cost) / rollup_sell * 100) if rollup_sell > 0 else 0,
            2,
        ),
    }


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
    # Iter 216h267 — bundle / kit support. A bundle product carries
    # `is_bundle: True` plus a `bundle_items` array of:
    #   { product_id: str, quantity: float, override_sell_price?: float }
    # When a bundle is added to a quote we expand the items into
    # individual line items (still hydrated from the master price
    # list) so margin maths and supplier routing stay correct.
    is_bundle = bool(data.get("is_bundle"))
    raw_items = data.get("bundle_items") or []
    bundle_items: list[dict] = []
    if is_bundle:
        if not isinstance(raw_items, list) or not raw_items:
            raise HTTPException(422, "Bundles must include at least one bundle_items entry")
        for idx, it in enumerate(raw_items):
            if not isinstance(it, dict):
                raise HTTPException(422, f"bundle_items[{idx}] must be an object")
            pid = (it.get("product_id") or "").strip()
            if not pid:
                raise HTTPException(422, f"bundle_items[{idx}].product_id is required")
            qty_raw = it.get("quantity", 1)
            if qty_raw in (None, ""):
                qty_raw = 1
            try:
                qty = float(qty_raw)
            except (TypeError, ValueError) as exc:
                raise HTTPException(422, f"bundle_items[{idx}].quantity must be numeric") from exc
            if qty <= 0:
                raise HTTPException(422, f"bundle_items[{idx}].quantity must be > 0")
            entry = {"product_id": pid, "quantity": qty}
            override = it.get("override_sell_price")
            if override not in (None, ""):
                try:
                    entry["override_sell_price"] = float(override)
                except (TypeError, ValueError) as exc:
                    raise HTTPException(422, f"bundle_items[{idx}].override_sell_price must be numeric") from exc
            bundle_items.append(entry)
    out = {
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
        "is_bundle": is_bundle,
        "bundle_items": bundle_items,
    }
    # Iter 220 p1 — Master Price List migration: carry through the extended
    # catalogue fields + spreadsheet provenance + preserved unmapped data so
    # an in-CRM edit never strips imported information.
    for f in _EXTENDED_STR_FIELDS:
        if f in data and data.get(f) not in (None,):
            out[f] = str(data.get(f) or "").strip()
    for f in _EXTENDED_NUM_FIELDS:
        if f in data and data.get(f) not in (None, ""):
            try:
                out[f] = round(float(data.get(f)), 2)
            except (TypeError, ValueError):
                pass
    for f in _PROVENANCE_FIELDS:
        if f in data:
            out[f] = data.get(f)
    if "archived" in data:
        out["archived"] = bool(data.get("archived"))
    return out


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


@router.post("/{product_id}/restore")
async def restore_product(product_id: str, user=Depends(get_crm_user)) -> dict:
    """Restore an archived (soft-deleted) product back to active."""
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins / owners can manage the master price list")
    res = await db.crm_products.update_one(
        {"id": product_id, **_of(user)},
        {"$set": {"active": True, "archived": False, "updated_at": _now()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Product not found")
    await log_audit(user, "product", product_id, "restored")
    return {"restored": True, "id": product_id}


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
