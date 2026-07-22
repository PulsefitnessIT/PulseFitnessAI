"""
Global Dealer Distribution, Inventory & Asset Deployment — Phase 1 (Foundation + Manual Orders).

Lives under Service Desk → Inventory & Distribution.  Everything here is a
CONTEXTUAL operational layer over the EXISTING platform records — it never
duplicates dealers (CRM `crm2_companies`), the product/machine catalogue
(`crm_products`), the equipment/asset register (`equipment`) or the parts
stock ledger.  New operational-only collections (prefix `inv_`):

  • inv_warehouses / inv_locations   — Pulse warehouse + zone/aisle/rack/shelf/bin model
  • inv_distribution_orders          — operational order (manual now, Sage-linked later)
  • inv_distribution_order_lines     — order lines (product type classified)
  • inv_equipment_units              — provisional → serial-assigned units (become the asset)
  • inv_reservations                 — operational stock reservations
  • inv_stock_holdings               — per (warehouse × product) on-hand / reserved
  • inv_stock_movements              — the operational stock-movement ledger
  • sage_connections                 — Sage 200 connection + capability discovery (scaffold)
  • inv_settings                     — per-org module settings, country profiles

SYSTEM OF RECORD:  Sage 200 stays authoritative for commercial/accounting fields;
PulseFitness.ai is authoritative for the operational workflow.  The field-ownership
matrix is exposed read-only at GET /field-ownership.  Nothing writes back to Sage.
"""
from __future__ import annotations

import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/inventory", tags=["Inventory & Distribution"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    """Org scope filter (multi-tenant isolation)."""
    return {"organization_id": user.get("organization_id")}


def _uid() -> str:
    return str(uuid.uuid4())


def _normalise_serial(serial: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (serial or "").upper())


async def _next_ref(user: dict, prefix: str, collection) -> str:
    """Per-org sequential reference, e.g. DO-000001."""
    n = await collection.count_documents(_of(user))
    return f"{prefix}-{n + 1:06d}"


async def _org_currency(user: dict) -> str:
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0, "currency": 1, "default_currency": 1}
    ) or {}
    return org.get("currency") or org.get("default_currency") or "GBP"


def _require_ops_role(user: dict):
    """Pulse operational roles for write actions."""
    if user.get("is_master_admin"):
        return
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager", "master_admin", "master", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for inventory operations")


async def _audit(user: dict, action: str, record_type: str, record_id: str, detail: dict | None = None):
    try:
        await db.inv_audit_log.insert_one({
            "id": _uid(),
            "organization_id": user.get("organization_id"),
            "user_id": user.get("id"),
            "user_email": user.get("email"),
            "action": action,
            "record_type": record_type,
            "record_id": record_id,
            "detail": detail or {},
            "at": _now(),
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("[inventory] audit write failed: %s", exc)


# Product classification the spec asks for.
PRODUCT_TYPES = [
    "serialised_machine", "non_serialised_equipment", "spare_part", "accessory",
    "installation_item", "service_item", "delivery_charge", "warranty_parts_allowance",
    "promotional_item", "packaging", "other",
]
SERIALISED_TYPES = {"serialised_machine"}
PHYSICAL_TYPES = {"serialised_machine", "non_serialised_equipment", "spare_part", "accessory", "installation_item", "promotional_item", "packaging"}


# Field-ownership matrix (system-of-record). Static, read-only for Phase 1.
FIELD_OWNERSHIP_MATRIX = [
    # field, record_type, authoritative_system, direction, override, reconciliation
    {"field": "sage_customer_account", "record": "order", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Match on Sage account ref"},
    {"field": "dealer_account_reference", "record": "order", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Idempotency key"},
    {"field": "sales_order_number", "record": "order", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Idempotency key"},
    {"field": "order_date", "record": "order", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Last-write Sage"},
    {"field": "unit_selling_price", "record": "order_line", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "Approval only", "reconciliation": "Never overwrite Sage"},
    {"field": "discounts", "record": "order_line", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Never overwrite Sage"},
    {"field": "tax_values", "record": "order_line", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Never overwrite Sage"},
    {"field": "currency", "record": "order", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Store original, never recalc"},
    {"field": "commercial_invoice_reference", "record": "order", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Read-only"},
    {"field": "financial_posting_status", "record": "order", "authoritative": "Sage 200", "direction": "Sage → Pulse", "override": "No", "reconciliation": "Awaiting/Posted/Failed"},
    {"field": "distribution_status", "record": "order", "authoritative": "PulseFitness.ai", "direction": "Pulse only", "override": "Yes (reason)", "reconciliation": "Operational"},
    {"field": "serial_number", "record": "equipment_unit", "authoritative": "PulseFitness.ai", "direction": "Pulse (may import from Sage)", "override": "Approval", "reconciliation": "Global dedupe"},
    {"field": "warehouse_task_status", "record": "pick/pack", "authoritative": "PulseFitness.ai", "direction": "Pulse only", "override": "Yes", "reconciliation": "Operational"},
    {"field": "barcode_scan", "record": "movement", "authoritative": "PulseFitness.ai", "direction": "Pulse only", "override": "No", "reconciliation": "Immutable"},
    {"field": "dealer_receipt_confirmation", "record": "receipt", "authoritative": "PulseFitness.ai", "direction": "Pulse only", "override": "Yes (reason)", "reconciliation": "Operational"},
    {"field": "customer_allocation", "record": "allocation", "authoritative": "PulseFitness.ai", "direction": "Pulse only", "override": "Yes", "reconciliation": "Operational"},
    {"field": "installed_location", "record": "asset", "authoritative": "PulseFitness.ai", "direction": "Pulse only", "override": "Yes", "reconciliation": "Operational"},
    {"field": "warranty_activation", "record": "asset", "authoritative": "PulseFitness.ai", "direction": "Pulse only", "override": "Approval", "reconciliation": "Operational"},
]

SAGE_POSTING_STATES = ["Operationally Completed", "Awaiting Sage Posting", "Posted to Sage", "Sage Posting Failed", "Reconciliation Required"]

ORDER_STATUSES = [
    "manual_entry", "imported_from_sage", "needs_validation", "needs_product_mapping",
    "needs_dealer_mapping", "awaiting_stock", "partially_available", "fully_available",
    "reserved", "released_to_warehouse", "picking", "partially_picked", "picked",
    "quality_control", "quality_issue", "packing", "partially_packed", "packed",
    "awaiting_dispatch", "partially_dispatched", "dispatched", "in_transit",
    "partially_received", "received_by_dealer", "awaiting_customer_allocation",
    "partially_allocated", "fully_allocated", "installation_in_progress", "completed",
    "on_hold", "cancelled", "archived",
]

UNIT_STATUSES = [
    "provisional", "serial_pending", "serial_assigned", "reserved", "picked",
    "quality_checked", "packed", "dispatched", "dealer_held", "customer_allocated",
    "installed", "active_asset", "returned",
]


# ──────────────────────────────────────────────────────────────────────────
# Settings + reference data
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_COUNTRY_PROFILES = [
    {"code": "GB", "name": "United Kingdom", "language": "en", "currency": "GBP", "measurement": "metric", "date_format": "DD/MM/YYYY"},
    {"code": "FR", "name": "France", "language": "fr", "currency": "EUR", "measurement": "metric", "date_format": "DD/MM/YYYY"},
    {"code": "US", "name": "United States", "language": "en", "currency": "USD", "measurement": "imperial", "date_format": "MM/DD/YYYY"},
]


async def _get_settings(user: dict) -> dict:
    s = await db.inv_settings.find_one(_of(user), {"_id": 0})
    if not s:
        s = {
            "id": _uid(),
            "organization_id": user.get("organization_id"),
            "module_enabled": True,
            "sage_integration_enabled": False,
            "automatic_order_import": False,
            "default_warehouse_id": None,
            "serial_tracking": "required_for_machines",
            "qc_required": True,
            "dealer_receipt_required": True,
            "dealer_allocation_required": True,
            "warranty_activation_rule": "installation_date",
            "currency_display": await _org_currency(user),
            "language": "en",
            "measurement_system": "metric",
            "country_profiles": DEFAULT_COUNTRY_PROFILES,
            "created_at": _now(),
        }
        await db.inv_settings.insert_one({**s})
    s.pop("_id", None)
    return s


class SettingsPatch(BaseModel):
    sage_integration_enabled: Optional[bool] = None
    automatic_order_import: Optional[bool] = None
    default_warehouse_id: Optional[str] = None
    serial_tracking: Optional[str] = None
    qc_required: Optional[bool] = None
    dealer_receipt_required: Optional[bool] = None
    dealer_allocation_required: Optional[bool] = None
    warranty_activation_rule: Optional[str] = None
    currency_display: Optional[str] = None
    language: Optional[str] = None
    measurement_system: Optional[str] = None
    country_profiles: Optional[List[dict]] = None


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    return await _get_settings(user)


@router.put("/settings")
async def update_settings(patch: SettingsPatch, user=Depends(get_current_user)):
    _require_ops_role(user)
    await _get_settings(user)  # ensure exists
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if updates:
        await db.inv_settings.update_one(_of(user), {"$set": updates})
        await _audit(user, "settings_updated", "settings", user.get("organization_id"), updates)
    return await _get_settings(user)


@router.get("/field-ownership")
async def field_ownership(user=Depends(get_current_user)):
    return {"matrix": FIELD_OWNERSHIP_MATRIX, "sage_posting_states": SAGE_POSTING_STATES}


@router.get("/meta")
async def meta(user=Depends(get_current_user)):
    """Enum/reference data for the frontend (statuses, product types)."""
    return {
        "product_types": PRODUCT_TYPES,
        "serialised_types": list(SERIALISED_TYPES),
        "order_statuses": ORDER_STATUSES,
        "unit_statuses": UNIT_STATUSES,
        "sage_posting_states": SAGE_POSTING_STATES,
        "country_profiles": DEFAULT_COUNTRY_PROFILES,
    }


# ──────────────────────────────────────────────────────────────────────────
# Dealers & products — CONTEXTUAL views over existing records (no duplication)
# ──────────────────────────────────────────────────────────────────────────
@router.get("/dealers")
async def list_dealers(q: Optional[str] = None, user=Depends(get_current_user)):
    """Dealers come from the existing CRM company register (crm2_companies)."""
    flt = _of(user)
    if q:
        flt["name"] = {"$regex": re.escape(q), "$options": "i"}
    rows = await db.crm2_companies.find(
        flt, {"_id": 0, "id": 1, "name": 1, "country": 1, "company_type": 1, "sector": 1}
    ).sort("name", 1).limit(50).to_list(50)
    return {"dealers": rows}


@router.get("/products")
async def list_products(q: Optional[str] = None, user=Depends(get_current_user)):
    """Machine models / products come from the existing crm_products catalogue."""
    flt = _of(user)
    if q:
        flt["$or"] = [
            {"name": {"$regex": re.escape(q), "$options": "i"}},
            {"sku": {"$regex": re.escape(q), "$options": "i"}},
        ]
    rows = await db.crm_products.find(
        flt, {"_id": 0, "id": 1, "sku": 1, "name": 1, "category": 1, "unit_price": 1, "price": 1}
    ).sort("name", 1).limit(50).to_list(50)
    for r in rows:
        r["unit_price"] = r.get("unit_price") or r.get("price") or 0
    return {"products": rows}


# ──────────────────────────────────────────────────────────────────────────
# Warehouses & locations
# ──────────────────────────────────────────────────────────────────────────
class WarehouseIn(BaseModel):
    code: str
    name: str
    type: str = "main"  # main, finished_goods, quarantine, returns, spare_parts, 3pl, dealer
    country: str = "GB"
    currency: Optional[str] = None
    is_active: bool = True


class LocationIn(BaseModel):
    code: str
    zone: Optional[str] = None
    aisle: Optional[str] = None
    rack: Optional[str] = None
    shelf: Optional[str] = None
    bin: Optional[str] = None
    description: Optional[str] = None
    pick_sequence: Optional[int] = 0
    quarantine: bool = False
    active: bool = True


@router.get("/warehouses")
async def list_warehouses(user=Depends(get_current_user)):
    rows = await db.inv_warehouses.find(_of(user), {"_id": 0}).sort("name", 1).to_list(200)
    for w in rows:
        w["location_count"] = await db.inv_locations.count_documents({**_of(user), "warehouse_id": w["id"]})
    return {"warehouses": rows}


@router.post("/warehouses")
async def create_warehouse(body: WarehouseIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    doc = {
        "id": _uid(),
        "organization_id": user.get("organization_id"),
        **body.model_dump(),
        "created_at": _now(),
    }
    if not doc.get("currency"):
        doc["currency"] = await _org_currency(user)
    await db.inv_warehouses.insert_one({**doc})
    await _audit(user, "warehouse_created", "warehouse", doc["id"], {"code": doc["code"]})
    doc.pop("_id", None)
    return doc


@router.get("/warehouses/{warehouse_id}/locations")
async def list_locations(warehouse_id: str, user=Depends(get_current_user)):
    rows = await db.inv_locations.find(
        {**_of(user), "warehouse_id": warehouse_id}, {"_id": 0}
    ).sort("pick_sequence", 1).to_list(1000)
    return {"locations": rows}


@router.post("/warehouses/{warehouse_id}/locations")
async def create_location(warehouse_id: str, body: LocationIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    wh = await db.inv_warehouses.find_one({**_of(user), "id": warehouse_id})
    if not wh:
        raise HTTPException(404, "Warehouse not found")
    doc = {
        "id": _uid(),
        "organization_id": user.get("organization_id"),
        "warehouse_id": warehouse_id,
        **body.model_dump(),
        "barcode": f"LOC-{body.code}",
        "created_at": _now(),
    }
    await db.inv_locations.insert_one({**doc})
    doc.pop("_id", None)
    return doc


# ──────────────────────────────────────────────────────────────────────────
# Distribution orders (manual entry — the "no Sage yet" path)
# ──────────────────────────────────────────────────────────────────────────
class OrderLineIn(BaseModel):
    product_code: str
    description: str
    product_type: str = "serialised_machine"
    quantity: int = 1
    unit_price: float = 0
    discount: float = 0
    tax: float = 0
    model: Optional[str] = None
    warehouse_id: Optional[str] = None


class OrderIn(BaseModel):
    dealer_id: Optional[str] = None
    dealer_name: str
    dealer_country: str = "GB"
    currency: Optional[str] = None
    language: str = "en"
    customer_po: Optional[str] = None
    order_date: Optional[str] = None
    requested_delivery_date: Optional[str] = None
    delivery_address: Optional[str] = None
    sales_rep: Optional[str] = None
    notes: Optional[str] = None
    warehouse_id: Optional[str] = None
    lines: List[OrderLineIn] = Field(default_factory=list)


def _line_status(pt: str) -> str:
    if pt in SERIALISED_TYPES:
        return "awaiting_stock"
    if pt in PHYSICAL_TYPES:
        return "awaiting_stock"
    return "not_stock"  # service / delivery charge


@router.post("/orders")
async def create_order(body: OrderIn, user=Depends(get_current_user)):
    """Create an operational Distribution Order manually (before Sage is wired)."""
    _require_ops_role(user)
    if not body.lines:
        raise HTTPException(400, "At least one order line is required")
    currency = body.currency or await _org_currency(user)
    ref = await _next_ref(user, "DO", db.inv_distribution_orders)
    order_id = _uid()
    order = {
        "id": order_id,
        "organization_id": user.get("organization_id"),
        "reference": ref,
        "source": "manual",
        "sage_order_id": None,
        "sage_order_number": None,
        "sage_status": None,
        "sage_posting_status": "Operationally Completed",
        "dealer_id": body.dealer_id,
        "dealer_name": body.dealer_name,
        "dealer_country": body.dealer_country,
        "currency": currency,
        "language": body.language,
        "customer_po": body.customer_po,
        "order_date": body.order_date or _now(),
        "requested_delivery_date": body.requested_delivery_date,
        "delivery_address": body.delivery_address,
        "sales_rep": body.sales_rep,
        "notes": body.notes,
        "warehouse_id": body.warehouse_id,
        "status": "needs_validation",
        "lines_count": len(body.lines),
        "created_by": user.get("id"),
        "created_by_email": user.get("email"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.inv_distribution_orders.insert_one({**order})

    line_docs = []
    unit_docs = []
    for idx, ln in enumerate(body.lines, start=1):
        line_id = _uid()
        serialised = ln.product_type in SERIALISED_TYPES
        line_doc = {
            "id": line_id,
            "organization_id": user.get("organization_id"),
            "order_id": order_id,
            "line_number": idx,
            "product_code": ln.product_code,
            "description": ln.description,
            "product_type": ln.product_type,
            "model": ln.model or ln.description,
            "quantity": ln.quantity,
            "unit_price": ln.unit_price,
            "currency": currency,
            "discount": ln.discount,
            "tax": ln.tax,
            "warehouse_id": ln.warehouse_id or body.warehouse_id,
            "serial_tracked": serialised,
            "status": _line_status(ln.product_type),
            "qty_allocated": 0,
            "qty_dispatched": 0,
            "created_at": _now(),
        }
        line_docs.append(line_doc)
        # Provisional equipment units for serialised machines (one per qty).
        if serialised:
            for _ in range(max(1, ln.quantity)):
                unit_docs.append({
                    "id": _uid(),
                    "organization_id": user.get("organization_id"),
                    "order_id": order_id,
                    "line_id": line_id,
                    "product_code": ln.product_code,
                    "model": ln.model or ln.description,
                    "serial_number": None,
                    "normalised_serial": None,
                    "status": "provisional",
                    "warehouse_id": ln.warehouse_id or body.warehouse_id,
                    "location_id": None,
                    "commercial_owner": "dealer",
                    "physical_location": "pulse_warehouse",
                    "asset_id": None,
                    "history": [{"status": "provisional", "at": _now(), "by": user.get("email")}],
                    "created_at": _now(),
                    "updated_at": _now(),
                })
    if line_docs:
        await db.inv_distribution_order_lines.insert_many([{**d} for d in line_docs])
    if unit_docs:
        await db.inv_equipment_units.insert_many([{**d} for d in unit_docs])

    await _audit(user, "order_created", "order", order_id, {"ref": ref, "lines": len(line_docs), "provisional_units": len(unit_docs)})
    order.pop("_id", None)
    return {"order": order, "line_count": len(line_docs), "provisional_units": len(unit_docs)}


@router.get("/orders")
async def list_orders(
    status: Optional[str] = None,
    q: Optional[str] = None,
    user=Depends(get_current_user),
):
    flt = _of(user)
    if status and status != "all":
        flt["status"] = status
    if q:
        flt["$or"] = [
            {"reference": {"$regex": re.escape(q), "$options": "i"}},
            {"dealer_name": {"$regex": re.escape(q), "$options": "i"}},
            {"customer_po": {"$regex": re.escape(q), "$options": "i"}},
            {"sage_order_number": {"$regex": re.escape(q), "$options": "i"}},
        ]
    rows = await db.inv_distribution_orders.find(flt, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"orders": rows}


@router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    order = await db.inv_distribution_orders.find_one({**_of(user), "id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    lines = await db.inv_distribution_order_lines.find(
        {**_of(user), "order_id": order_id}, {"_id": 0}
    ).sort("line_number", 1).to_list(500)
    units = await db.inv_equipment_units.find(
        {**_of(user), "order_id": order_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(2000)
    reservations = await db.inv_reservations.find(
        {**_of(user), "order_id": order_id}, {"_id": 0}
    ).to_list(500)
    return {"order": order, "lines": lines, "units": units, "reservations": reservations}


class StatusIn(BaseModel):
    status: str
    reason: Optional[str] = None


@router.post("/orders/{order_id}/status")
async def set_order_status(order_id: str, body: StatusIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    if body.status not in ORDER_STATUSES:
        raise HTTPException(400, f"Unknown status '{body.status}'")
    order = await db.inv_distribution_orders.find_one({**_of(user), "id": order_id})
    if not order:
        raise HTTPException(404, "Order not found")
    await db.inv_distribution_orders.update_one(
        {**_of(user), "id": order_id},
        {"$set": {"status": body.status, "updated_at": _now()}},
    )
    await _audit(user, "order_status_changed", "order", order_id,
                 {"from": order.get("status"), "to": body.status, "reason": body.reason})
    return {"ok": True, "status": body.status}


# ── Order validation (Phase 2 rules, runnable now on manual orders) ──
@router.post("/orders/{order_id}/validate")
async def validate_order(order_id: str, user=Depends(get_current_user)):
    order = await db.inv_distribution_orders.find_one({**_of(user), "id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    lines = await db.inv_distribution_order_lines.find({**_of(user), "order_id": order_id}, {"_id": 0}).to_list(500)
    checks = []

    # dealer exists / mapped
    dealer_ok = bool(order.get("dealer_id"))
    checks.append({"check": "dealer_mapped", "ok": dealer_ok,
                   "message": "Dealer linked to a CRM company record" if dealer_ok else "Dealer is free-text — link to a CRM company record"})
    # currency supported
    cur_ok = order.get("currency") in ("GBP", "EUR", "USD")
    checks.append({"check": "currency_supported", "ok": cur_ok, "message": f"Currency {order.get('currency')}"})
    # delivery address
    addr_ok = bool(order.get("delivery_address"))
    checks.append({"check": "delivery_address", "ok": addr_ok, "message": "Delivery address present" if addr_ok else "Missing delivery address"})
    # products recognised (exist in catalogue)
    unknown = []
    for ln in lines:
        exists = await db.crm_products.find_one({**_of(user), "$or": [{"sku": ln["product_code"]}, {"id": ln["product_code"]}]})
        if not exists:
            unknown.append(ln["product_code"])
    prod_ok = len(unknown) == 0
    checks.append({"check": "products_recognised", "ok": prod_ok,
                   "message": "All product codes recognised" if prod_ok else f"Unknown product codes: {', '.join(unknown)}"})
    # quantities valid
    qty_ok = all((ln.get("quantity") or 0) > 0 for ln in lines)
    checks.append({"check": "quantities_valid", "ok": qty_ok, "message": "All quantities valid" if qty_ok else "One or more lines has zero quantity"})

    blocking = [c for c in checks if not c["ok"] and c["check"] in ("currency_supported", "quantities_valid")]
    warnings = [c for c in checks if not c["ok"] and c not in blocking]
    if blocking:
        outcome = "blocked"
    elif warnings:
        outcome = "ready_with_warnings"
    else:
        outcome = "ready"

    new_status = "needs_validation"
    if outcome in ("ready", "ready_with_warnings"):
        new_status = "awaiting_stock"
    await db.inv_distribution_orders.update_one(
        {**_of(user), "id": order_id},
        {"$set": {"validation": {"outcome": outcome, "checks": checks, "at": _now()},
                  "status": new_status, "updated_at": _now()}},
    )
    return {"outcome": outcome, "checks": checks, "status": new_status}


# ──────────────────────────────────────────────────────────────────────────
# Stock holdings, availability & reservations
# ──────────────────────────────────────────────────────────────────────────
class StockIn(BaseModel):
    warehouse_id: str
    product_code: str
    quantity: int
    unit_cost: Optional[float] = None


@router.post("/stock/receive")
async def receive_stock(body: StockIn, user=Depends(get_current_user)):
    """Simple Phase-1 receipt to seed availability (full receiving flow = Phase 3)."""
    _require_ops_role(user)
    holding = await db.inv_stock_holdings.find_one(
        {**_of(user), "warehouse_id": body.warehouse_id, "product_code": body.product_code}
    )
    if holding:
        await db.inv_stock_holdings.update_one(
            {"id": holding["id"]},
            {"$inc": {"qty_on_hand": body.quantity}, "$set": {"updated_at": _now()}},
        )
        hid = holding["id"]
    else:
        hid = _uid()
        await db.inv_stock_holdings.insert_one({
            "id": hid,
            "organization_id": user.get("organization_id"),
            "warehouse_id": body.warehouse_id,
            "product_code": body.product_code,
            "qty_on_hand": body.quantity,
            "qty_reserved": 0,
            "unit_cost": body.unit_cost,
            "created_at": _now(),
            "updated_at": _now(),
        })
    await db.inv_stock_movements.insert_one({
        "id": _uid(),
        "organization_id": user.get("organization_id"),
        "movement_ref": await _next_ref(user, "MOV", db.inv_stock_movements),
        "type": "warehouse_receipt",
        "product_code": body.product_code,
        "serial_number": None,
        "quantity": body.quantity,
        "source": "supplier/production",
        "destination": body.warehouse_id,
        "source_status": "expected",
        "destination_status": "available",
        "order_id": None,
        "user": user.get("email"),
        "reason": "Phase-1 stock receipt",
        "sage_posting_status": "Operationally Completed",
        "created_at": _now(),
    })
    await _audit(user, "stock_received", "stock", hid, {"product": body.product_code, "qty": body.quantity})
    return {"ok": True, "holding_id": hid}


@router.get("/stock/availability")
async def stock_availability(
    warehouse_id: Optional[str] = None,
    q: Optional[str] = None,
    user=Depends(get_current_user),
):
    flt = _of(user)
    if warehouse_id:
        flt["warehouse_id"] = warehouse_id
    if q:
        flt["product_code"] = {"$regex": re.escape(q), "$options": "i"}
    holdings = await db.inv_stock_holdings.find(flt, {"_id": 0}).to_list(1000)
    for h in holdings:
        h["qty_available"] = max(0, (h.get("qty_on_hand") or 0) - (h.get("qty_reserved") or 0))
    return {"holdings": holdings}


@router.post("/orders/{order_id}/reserve")
async def reserve_stock(order_id: str, user=Depends(get_current_user)):
    """Reserve available stock against each serialised/physical line; mark shortfall as awaiting stock."""
    _require_ops_role(user)
    order = await db.inv_distribution_orders.find_one({**_of(user), "id": order_id})
    if not order:
        raise HTTPException(404, "Order not found")
    lines = await db.inv_distribution_order_lines.find({**_of(user), "order_id": order_id}, {"_id": 0}).to_list(500)
    results = []
    all_available = True
    any_reserved = False
    for ln in lines:
        if ln["product_type"] not in PHYSICAL_TYPES:
            continue
        wh = ln.get("warehouse_id") or order.get("warehouse_id")
        need = ln.get("quantity") or 0
        holding = await db.inv_stock_holdings.find_one(
            {**_of(user), "warehouse_id": wh, "product_code": ln["product_code"]}
        ) if wh else None
        avail = max(0, (holding.get("qty_on_hand", 0) - holding.get("qty_reserved", 0))) if holding else 0
        take = min(need, avail)
        if take > 0:
            await db.inv_stock_holdings.update_one({"id": holding["id"]}, {"$inc": {"qty_reserved": take}})
            await db.inv_reservations.insert_one({
                "id": _uid(),
                "organization_id": user.get("organization_id"),
                "order_id": order_id,
                "line_id": ln["id"],
                "product_code": ln["product_code"],
                "quantity": take,
                "warehouse_id": wh,
                "status": "reserved" if take == need else "partially_reserved",
                "priority": "normal",
                "required_date": order.get("requested_delivery_date"),
                "expiry": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
                "created_at": _now(),
            })
            any_reserved = True
        line_status = "fully_available" if take >= need else ("partially_available" if take > 0 else "awaiting_stock")
        if take < need:
            all_available = False
        await db.inv_distribution_order_lines.update_one(
            {"id": ln["id"]}, {"$set": {"status": line_status, "qty_allocated": take}}
        )
        results.append({"line": ln["line_number"], "product": ln["product_code"], "needed": need, "reserved": take, "status": line_status})

    order_status = "reserved" if (any_reserved and all_available) else ("partially_available" if any_reserved else "awaiting_stock")
    await db.inv_distribution_orders.update_one(
        {**_of(user), "id": order_id}, {"$set": {"status": order_status, "updated_at": _now()}}
    )
    await _audit(user, "stock_reserved", "order", order_id, {"results": results})
    return {"results": results, "order_status": order_status}


# ──────────────────────────────────────────────────────────────────────────
# Serial-number control (unified register + dedupe guard) & unit binding
# ──────────────────────────────────────────────────────────────────────────
@router.get("/serials/check")
async def check_serial(serial: str = Query(...), user=Depends(get_current_user)):
    """Dedupe guard across the equipment/asset register + operational units (tenant-scoped)."""
    norm = _normalise_serial(serial)
    if not norm:
        return {"classification": "clear", "matches": []}
    matches = []
    # existing asset register
    eq = await db.equipment.find_one(
        {**_of(user), "serial_number": {"$regex": f"^{re.escape(serial)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "name": 1, "serial_number": 1},
    )
    if eq:
        matches.append({"source": "asset_register", "id": eq["id"], "serial": eq.get("serial_number"), "name": eq.get("name")})
    # operational units
    unit = await db.inv_equipment_units.find_one(
        {**_of(user), "normalised_serial": norm}, {"_id": 0, "id": 1, "serial_number": 1, "order_id": 1}
    )
    if unit:
        matches.append({"source": "equipment_unit", "id": unit["id"], "serial": unit.get("serial_number"), "order_id": unit.get("order_id")})

    if matches:
        exact = any(_normalise_serial(m.get("serial") or "") == norm for m in matches)
        classification = "exact_duplicate" if exact else "normalised_duplicate"
    else:
        classification = "clear"
    return {"classification": classification, "normalised": norm, "matches": matches}


class AssignSerialIn(BaseModel):
    serial_number: str
    location_id: Optional[str] = None
    override_duplicate: bool = False


@router.get("/orders/{order_id}/units")
async def order_units(order_id: str, user=Depends(get_current_user)):
    units = await db.inv_equipment_units.find({**_of(user), "order_id": order_id}, {"_id": 0}).to_list(2000)
    return {"units": units}


@router.post("/units/{unit_id}/assign-serial")
async def assign_serial(unit_id: str, body: AssignSerialIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    unit = await db.inv_equipment_units.find_one({**_of(user), "id": unit_id})
    if not unit:
        raise HTTPException(404, "Equipment unit not found")
    norm = _normalise_serial(body.serial_number)
    if not norm:
        raise HTTPException(400, "Serial number is required")
    # Dedupe guard
    dup = await db.inv_equipment_units.find_one(
        {**_of(user), "normalised_serial": norm, "id": {"$ne": unit_id}}
    )
    eq_dup = await db.equipment.find_one(
        {**_of(user), "serial_number": {"$regex": f"^{re.escape(body.serial_number)}$", "$options": "i"}}
    )
    if (dup or eq_dup) and not body.override_duplicate:
        raise HTTPException(409, {
            "error": "duplicate_serial",
            "message": "This serial number already exists in the platform. Override requires authorisation.",
        })
    await db.inv_equipment_units.update_one(
        {**_of(user), "id": unit_id},
        {"$set": {
            "serial_number": body.serial_number,
            "normalised_serial": norm,
            "status": "serial_assigned",
            "location_id": body.location_id or unit.get("location_id"),
            "updated_at": _now(),
        }, "$push": {"history": {"status": "serial_assigned", "serial": body.serial_number, "at": _now(), "by": user.get("email")}}},
    )
    await db.inv_stock_movements.insert_one({
        "id": _uid(),
        "organization_id": user.get("organization_id"),
        "movement_ref": await _next_ref(user, "MOV", db.inv_stock_movements),
        "type": "serial_assigned",
        "product_code": unit.get("product_code"),
        "serial_number": body.serial_number,
        "quantity": 1,
        "source": None,
        "destination": unit.get("warehouse_id"),
        "source_status": "provisional",
        "destination_status": "serial_assigned",
        "order_id": unit.get("order_id"),
        "unit_id": unit_id,
        "user": user.get("email"),
        "reason": "Serial bound to provisional unit",
        "sage_posting_status": "Operationally Completed",
        "created_at": _now(),
    })
    await _audit(user, "serial_assigned", "equipment_unit", unit_id,
                 {"serial": body.serial_number, "override": body.override_duplicate})
    updated = await db.inv_equipment_units.find_one({**_of(user), "id": unit_id}, {"_id": 0})
    return {"unit": updated}


# ──────────────────────────────────────────────────────────────────────────
# Sage 200 connection + capability discovery (scaffold — no write-back)
# ──────────────────────────────────────────────────────────────────────────
class SageConnIn(BaseModel):
    edition: str = "standard"  # standard | professional
    version: Optional[str] = None
    company: Optional[str] = None
    api_base: Optional[str] = None
    limitations: Optional[str] = None


@router.get("/sage/connection")
async def sage_connection(user=Depends(get_current_user)):
    conn = await db.sage_connections.find_one(_of(user), {"_id": 0})
    return {"connection": conn, "configured": bool(conn)}


@router.post("/sage/connection")
async def save_sage_connection(body: SageConnIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    existing = await db.sage_connections.find_one(_of(user))
    doc = {
        "organization_id": user.get("organization_id"),
        **body.model_dump(),
        "auth_status": "not_connected",
        "updated_at": _now(),
    }
    if existing:
        await db.sage_connections.update_one({"id": existing["id"]}, {"$set": doc})
        cid = existing["id"]
    else:
        cid = _uid()
        doc.update({"id": cid, "created_at": _now()})
        await db.sage_connections.insert_one({**doc})
    await _audit(user, "sage_connection_saved", "sage_connection", cid, {"edition": body.edition})
    conn = await db.sage_connections.find_one({"id": cid}, {"_id": 0})
    return {"connection": conn}


@router.get("/sage/capabilities/discover")
async def sage_capability_discover(user=Depends(get_current_user)):
    """
    Capability discovery — reports what a Sage 200 deployment CAN expose.
    Live probing runs once credentials are provided; today it returns the
    capability template so ops can review scope before go-live.
    """
    conn = await db.sage_connections.find_one(_of(user), {"_id": 0})
    template = {
        "sales_order_read": {"available": None, "note": "GET SalesOrders — pending credentials"},
        "sales_order_lines_read": {"available": None, "note": "GET SalesOrderLines — pending credentials"},
        "stock_read": {"available": None, "note": "GET StockItems / StockBalances — pending credentials"},
        "traceable_items": {"available": None, "note": "Serial/batch capability varies by deployment"},
        "despatch_read": {"available": None, "note": "GET Despatches — pending credentials"},
        "warehouse_read": {"available": None, "note": "GET Warehouses — pending credentials"},
        "write_back": {"available": False, "note": "Disabled by design (no unauthorised Sage write-back)"},
    }
    return {
        "connected": bool(conn and conn.get("auth_status") == "connected"),
        "edition": (conn or {}).get("edition"),
        "capabilities": template,
        "message": "Live capability probe runs when Sage credentials are configured. Write-back stays disabled until an approved endpoint + workflow is enabled.",
    }


# ──────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    of = _of(user)
    orders_total = await db.inv_distribution_orders.count_documents(of)
    needs_validation = await db.inv_distribution_orders.count_documents({**of, "status": "needs_validation"})
    awaiting_stock = await db.inv_distribution_orders.count_documents({**of, "status": {"$in": ["awaiting_stock", "partially_available"]}})
    reserved = await db.inv_distribution_orders.count_documents({**of, "status": "reserved"})
    in_transit = await db.inv_distribution_orders.count_documents({**of, "status": "in_transit"})
    units_total = await db.inv_equipment_units.count_documents(of)
    units_provisional = await db.inv_equipment_units.count_documents({**of, "status": {"$in": ["provisional", "serial_pending"]}})
    units_serialised = await db.inv_equipment_units.count_documents({**of, "status": {"$nin": ["provisional", "serial_pending"]}})
    warehouses = await db.inv_warehouses.count_documents(of)

    # by-country breakdown
    country_pipe = [{"$match": of}, {"$group": {"_id": "$dealer_country", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    by_country = [{"country": r["_id"] or "—", "count": r["count"]} async for r in db.inv_distribution_orders.aggregate(country_pipe)]

    recent = await db.inv_distribution_orders.find(of, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)

    return {
        "cards": {
            "orders_total": orders_total,
            "needs_validation": needs_validation,
            "awaiting_stock": awaiting_stock,
            "reserved": reserved,
            "in_transit": in_transit,
            "units_total": units_total,
            "units_provisional": units_provisional,
            "units_serialised": units_serialised,
            "warehouses": warehouses,
        },
        "by_country": by_country,
        "recent_orders": recent,
    }
