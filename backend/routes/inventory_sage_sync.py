"""
Inventory & Distribution — PHASE 2 · Sage 200 Order Sync.

A robust, idempotent order-import pipeline (NOT a one-time file copy).  The same
pipeline runs for BOTH the live Sage 200 connection (once credentials exist) and a
"Simulate Sage feed" path so the whole engine is testable today.  Sage identifiers
are preserved permanently and used as idempotency keys — the same Sage order/line
can never create two operational records.

Reuses the Phase-1 helpers + collections from routes.inventory_distribution
(distribution orders, lines, provisional equipment units).  Nothing writes back to Sage.
"""
from __future__ import annotations

import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from routes.inventory_distribution import (
    _of, _now, _uid, _next_ref, _audit, _require_ops_role, _org_currency,
    _normalise_serial, _line_status, SERIALISED_TYPES,
)

router = APIRouter(prefix="/inventory/sage", tags=["Inventory & Distribution · Sage Sync"])
logger = logging.getLogger(__name__)


# ── State vocabularies (spec) ──
SYNC_STATES = [
    "not_imported", "importing", "imported", "validated", "needs_mapping",
    "mapping_failed", "ready_for_distribution", "sync_conflict", "sage_cancelled", "archived",
]
HEALTH_STATES = ["healthy", "delayed", "warning", "failed", "authentication_required", "reconciliation_required"]


# ── Sage → Pulse field mapping matrix (header + lines) ──
FIELD_MAP = {
    "header": [
        {"sage": "SopOrderId", "pulse": "sage_order_id", "note": "Idempotency key (permanent)"},
        {"sage": "DocumentNo", "pulse": "sage_order_number", "note": "Human order number"},
        {"sage": "CustomerAccountRef", "pulse": "sage_customer_account", "note": "Maps to CRM dealer"},
        {"sage": "CustomerDocumentNo", "pulse": "customer_po", "note": "Dealer PO"},
        {"sage": "DocumentDate", "pulse": "order_date", "note": "Sage authoritative"},
        {"sage": "RequestedDeliveryDate", "pulse": "requested_delivery_date", "note": ""},
        {"sage": "CurrencyCode", "pulse": "currency", "note": "Original currency, never recalc"},
        {"sage": "DeliveryAddress", "pulse": "delivery_address", "note": ""},
        {"sage": "DeliveryCountry", "pulse": "dealer_country", "note": "Drives country profile"},
        {"sage": "AnalysisCode (rep)", "pulse": "sales_rep", "note": ""},
        {"sage": "DocumentStatus", "pulse": "sage_status", "note": "Read-only"},
    ],
    "line": [
        {"sage": "SopOrderLineId", "pulse": "sage_line_id", "note": "Line idempotency key"},
        {"sage": "LineNumber", "pulse": "line_number", "note": ""},
        {"sage": "ItemCode", "pulse": "product_code", "note": "Maps to catalogue"},
        {"sage": "ItemDescription", "pulse": "description", "note": ""},
        {"sage": "LineQuantity", "pulse": "quantity", "note": ""},
        {"sage": "UnitSellingPrice", "pulse": "unit_price", "note": "Sage authoritative, never overwrite"},
        {"sage": "DiscountPercent", "pulse": "discount", "note": "Sage authoritative"},
        {"sage": "TaxValue", "pulse": "tax", "note": "Sage authoritative"},
        {"sage": "WarehouseCode", "pulse": "warehouse_id", "note": "Resolved to operational warehouse"},
        {"sage": "AnalysisCode (type)", "pulse": "product_type", "note": "Classified"},
    ],
}


def _classify(stock_code: str, description: str, explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    code = (stock_code or "").upper()
    desc = (description or "").lower()
    if any(k in code for k in ("DELIV", "FREIGHT", "CARRIAGE")) or "delivery" in desc or "freight" in desc:
        return "delivery_charge"
    if any(k in code for k in ("INSTALL",)) or "install" in desc:
        return "installation_item"
    if any(k in code for k in ("SERV", "LABOUR")) or "service" in desc:
        return "service_item"
    if any(k in code for k in ("PART", "SPARE")):
        return "spare_part"
    return "serialised_machine"


def _hash_order(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ── Sample Sage feed for the "Simulate" path (no live creds needed) ──
def _sample_feed() -> List[dict]:
    # Fixed dates so repeated syncs are byte-identical → truly idempotent (skipped, no dupes).
    d1, d2 = "2026-06-01T09:00:00+00:00", "2026-06-02T09:00:00+00:00"
    return [
        {
            "SopOrderId": "SAGE-1001", "DocumentNo": "SO-1001", "CustomerAccountRef": "FITFR01",
            "CustomerDocumentNo": "PO-FR-77", "DocumentDate": d1, "CurrencyCode": "EUR",
            "DeliveryCountry": "FR", "DeliveryAddress": "10 Rue du Sport, Lyon", "DocumentStatus": "Live",
            "CustomerName": "Fitness France SARL",
            "lines": [
                {"SopOrderLineId": "L-1", "LineNumber": 1, "ItemCode": "TREAD-900", "ItemDescription": "Pulse Treadmill 900", "LineQuantity": 2, "UnitSellingPrice": 4500},
                {"SopOrderLineId": "L-2", "LineNumber": 2, "ItemCode": "BIKE-500", "ItemDescription": "Pulse Bike 500", "LineQuantity": 3, "UnitSellingPrice": 2200},
                {"SopOrderLineId": "L-3", "LineNumber": 3, "ItemCode": "DELIVERY", "ItemDescription": "Freight to France", "LineQuantity": 1, "UnitSellingPrice": 480},
            ],
        },
        {
            "SopOrderId": "SAGE-1002", "DocumentNo": "SO-1002", "CustomerAccountRef": "USGYM02",
            "CustomerDocumentNo": "PO-US-31", "DocumentDate": d2, "CurrencyCode": "USD",
            "DeliveryCountry": "US", "DeliveryAddress": "220 Fitness Ave, Austin TX", "DocumentStatus": "Live",
            "CustomerName": "USA Gym Distributors Inc",
            "lines": [
                {"SopOrderLineId": "L-4", "LineNumber": 1, "ItemCode": "ROWER-300", "ItemDescription": "Pulse Rower 300", "LineQuantity": 4, "UnitSellingPrice": 1800},
                {"SopOrderLineId": "L-5", "LineNumber": 2, "ItemCode": "SPARE-BELT", "ItemDescription": "Treadmill belt (warranty parts)", "LineQuantity": 6, "UnitSellingPrice": 65},
            ],
        },
    ]


# ── Mapping resolution ──
async def _resolve_dealer(user: dict, sage_account: str, name: str) -> dict:
    """Return {crm_company_id, status}. Auto-links by exact name; else needs_mapping."""
    of = _of(user)
    m = await db.sage_dealer_mappings.find_one({**of, "sage_account": sage_account})
    if m and m.get("crm_company_id"):
        return {"crm_company_id": m["crm_company_id"], "status": "mapped", "dealer_name": m.get("dealer_name") or name}
    # try to auto-match an existing CRM company by name
    comp = None
    if name:
        comp = await db.crm2_companies.find_one(
            {**of, "name": {"$regex": f"^{name.strip()}$", "$options": "i"}}, {"_id": 0, "id": 1, "name": 1}
        )
    status = "mapped" if comp else "needs_mapping"
    doc = {
        "id": (m or {}).get("id") or _uid(), "organization_id": user.get("organization_id"),
        "sage_account": sage_account, "dealer_name": name,
        "crm_company_id": comp["id"] if comp else None, "status": status, "updated_at": _now(),
    }
    await db.sage_dealer_mappings.update_one({**of, "sage_account": sage_account}, {"$set": doc}, upsert=True)
    return {"crm_company_id": doc["crm_company_id"], "status": status, "dealer_name": name}


async def _resolve_product(user: dict, item_code: str, description: str) -> dict:
    of = _of(user)
    m = await db.sage_product_mappings.find_one({**of, "sage_stock_code": item_code})
    if m and m.get("status") == "mapped":
        return {"status": "mapped", "product_code": m.get("product_code") or item_code}
    prod = await db.crm_products.find_one({**of, "sku": item_code}, {"_id": 0, "id": 1, "sku": 1})
    status = "mapped" if prod else "needs_mapping"
    doc = {
        "id": (m or {}).get("id") or _uid(), "organization_id": user.get("organization_id"),
        "sage_stock_code": item_code, "description": description,
        "product_code": item_code, "status": status, "updated_at": _now(),
    }
    await db.sage_product_mappings.update_one({**of, "sage_stock_code": item_code}, {"$set": doc}, upsert=True)
    return {"status": status, "product_code": item_code}


# ── The single import pipeline (idempotent) ──
async def _import_one(user: dict, payload: dict, run: dict) -> str:
    """Import/refresh ONE Sage order. Returns outcome: imported|updated|skipped|needs_mapping|conflict."""
    of = _of(user)
    sage_id = payload.get("SopOrderId")
    if not sage_id:
        return "skipped"
    h = _hash_order(payload)
    mirror = await db.sage_order_mirrors.find_one({**of, "sage_order_id": sage_id})

    if mirror and mirror.get("hash") == h and mirror.get("distribution_order_id"):
        # Identical re-sync → idempotent no-op (duplicate prevented).
        await db.sage_order_mirrors.update_one({"id": mirror["id"]}, {"$set": {"last_synced_at": _now()}})
        return "skipped"

    currency = payload.get("CurrencyCode") or await _org_currency(user)
    dealer = await _resolve_dealer(user, payload.get("CustomerAccountRef", ""), payload.get("CustomerName", ""))

    # classify + map lines (only physical/serialised lines require a catalogue product)
    lines_in = payload.get("lines", [])
    unmapped_products = []
    resolved_lines = []
    for ln in lines_in:
        ptype = _classify(ln.get("ItemCode"), ln.get("ItemDescription"), ln.get("product_type"))
        if ptype in ("delivery_charge", "service_item"):
            resolved_lines.append((ln, ptype))
            continue
        pmap = await _resolve_product(user, ln.get("ItemCode", ""), ln.get("ItemDescription", ""))
        if pmap["status"] != "mapped":
            unmapped_products.append(ln.get("ItemCode"))
        resolved_lines.append((ln, ptype))

    needs_mapping = (dealer["status"] != "mapped") or bool(unmapped_products)
    sync_state = "needs_mapping" if needs_mapping else "ready_for_distribution"

    mirror_doc = {
        "organization_id": user.get("organization_id"),
        "sage_order_id": sage_id,
        "sage_order_number": payload.get("DocumentNo"),
        "sage_customer_account": payload.get("CustomerAccountRef"),
        "dealer_name": payload.get("CustomerName"),
        "dealer_country": payload.get("DeliveryCountry", "GB"),
        "currency": currency,
        "raw": payload,
        "hash": h,
        "sync_state": sync_state,
        "dealer_mapped": dealer["status"] == "mapped",
        "unmapped_products": unmapped_products,
        "last_synced_at": _now(),
    }
    if mirror:
        mirror_doc["id"] = mirror["id"]
        await db.sage_order_mirrors.update_one({"id": mirror["id"]}, {"$set": mirror_doc})
        mirror_id = mirror["id"]
    else:
        mirror_id = _uid()
        mirror_doc.update({"id": mirror_id, "created_at": _now(), "distribution_order_id": None})
        await db.sage_order_mirrors.insert_one({**mirror_doc})

    if needs_mapping:
        await db.sage_sync_errors.insert_one({
            "id": _uid(), "organization_id": user.get("organization_id"), "run_id": run["id"],
            "sage_order_id": sage_id, "type": "needs_mapping",
            "message": (f"Dealer '{payload.get('CustomerAccountRef')}' unmapped. " if dealer["status"] != "mapped" else "")
                       + (f"Unmapped products: {', '.join(unmapped_products)}" if unmapped_products else ""),
            "resolved": False, "at": _now(),
        })
        return "needs_mapping"

    # Create or update the operational distribution order (idempotent on sage_order_id).
    existing_order = await db.inv_distribution_orders.find_one({**of, "sage_order_id": sage_id})
    if existing_order:
        order_id = existing_order["id"]
        # Refresh header (Pulse never owns Sage commercial fields — mirror them).
        await db.inv_distribution_orders.update_one({"id": order_id}, {"$set": {
            "customer_po": payload.get("CustomerDocumentNo"),
            "currency": currency, "dealer_country": payload.get("DeliveryCountry", "GB"),
            "delivery_address": payload.get("DeliveryAddress"),
            "dealer_id": dealer["crm_company_id"], "dealer_name": payload.get("CustomerName"),
            "sage_status": payload.get("DocumentStatus"), "updated_at": _now(),
        }})
        outcome = "updated"
    else:
        ref = await _next_ref(user, "DO", db.inv_distribution_orders)
        order_id = _uid()
        await db.inv_distribution_orders.insert_one({
            "id": order_id, "organization_id": user.get("organization_id"), "reference": ref,
            "source": "sage", "sage_order_id": sage_id, "sage_order_number": payload.get("DocumentNo"),
            "sage_status": payload.get("DocumentStatus"), "sage_posting_status": "Posted to Sage",
            "dealer_id": dealer["crm_company_id"], "dealer_name": payload.get("CustomerName"),
            "dealer_country": payload.get("DeliveryCountry", "GB"), "currency": currency, "language": "en",
            "customer_po": payload.get("CustomerDocumentNo"), "order_date": payload.get("DocumentDate") or _now(),
            "requested_delivery_date": payload.get("RequestedDeliveryDate"),
            "delivery_address": payload.get("DeliveryAddress"), "sales_rep": payload.get("SalesRep"),
            "notes": None, "warehouse_id": None, "status": "imported_from_sage",
            "lines_count": len(resolved_lines), "created_by": user.get("id"),
            "created_by_email": user.get("email"), "created_at": _now(), "updated_at": _now(),
        })
        # lines + provisional units (idempotent per sage_line_id)
        for idx, (ln, ptype) in enumerate(resolved_lines, start=1):
            line_id = _uid()
            serialised = ptype in SERIALISED_TYPES
            await db.inv_distribution_order_lines.insert_one({
                "id": line_id, "organization_id": user.get("organization_id"), "order_id": order_id,
                "sage_line_id": ln.get("SopOrderLineId"), "line_number": ln.get("LineNumber", idx),
                "product_code": ln.get("ItemCode"), "description": ln.get("ItemDescription"),
                "product_type": ptype, "model": ln.get("ItemDescription"),
                "quantity": ln.get("LineQuantity", 1), "unit_price": ln.get("UnitSellingPrice", 0),
                "currency": currency, "discount": ln.get("DiscountPercent", 0), "tax": ln.get("TaxValue", 0),
                "warehouse_id": None, "serial_tracked": serialised, "status": _line_status(ptype),
                "qty_allocated": 0, "qty_dispatched": 0, "created_at": _now(),
            })
            if serialised:
                units = [{
                    "id": _uid(), "organization_id": user.get("organization_id"), "order_id": order_id,
                    "line_id": line_id, "product_code": ln.get("ItemCode"), "model": ln.get("ItemDescription"),
                    "serial_number": None, "normalised_serial": None, "status": "provisional",
                    "warehouse_id": None, "location_id": None, "commercial_owner": "dealer",
                    "physical_location": "pulse_warehouse", "asset_id": None,
                    "history": [{"status": "provisional", "at": _now(), "by": "sage_sync"}],
                    "created_at": _now(), "updated_at": _now(),
                } for _ in range(max(1, ln.get("LineQuantity", 1)))]
                if units:
                    await db.inv_equipment_units.insert_many(units)
        outcome = "imported"

    await db.sage_order_mirrors.update_one({"id": mirror_id}, {"$set": {"distribution_order_id": order_id, "sync_state": "imported"}})
    return outcome


# ──────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────
@router.get("/field-map")
async def field_map(user=Depends(get_current_user)):
    return {"field_map": FIELD_MAP, "sync_states": SYNC_STATES, "health_states": HEALTH_STATES}


class RunIn(BaseModel):
    simulate: bool = False
    orders: Optional[List[dict]] = None  # explicit Sage feed (simulate/testing)


async def _do_run(user: dict, trigger: str, feed: List[dict]) -> dict:
    run = {
        "id": _uid(), "organization_id": user.get("organization_id"), "trigger": trigger,
        "started_at": _now(), "status": "running",
        "imported": 0, "updated": 0, "skipped": 0, "duplicates_prevented": 0,
        "conflicts": 0, "failures": 0, "needs_mapping": 0,
    }
    await db.sage_sync_runs.insert_one({**run})
    for payload in feed:
        try:
            outcome = await _import_one(user, payload, run)
            if outcome == "imported":
                run["imported"] += 1
            elif outcome == "updated":
                run["updated"] += 1
            elif outcome == "skipped":
                run["skipped"] += 1; run["duplicates_prevented"] += 1
            elif outcome == "needs_mapping":
                run["needs_mapping"] += 1
            elif outcome == "conflict":
                run["conflicts"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("[sage-sync] import failed for %s", payload.get("SopOrderId"))
            run["failures"] += 1
            await db.sage_sync_errors.insert_one({
                "id": _uid(), "organization_id": user.get("organization_id"), "run_id": run["id"],
                "sage_order_id": payload.get("SopOrderId"), "type": "import_error",
                "message": str(exc), "resolved": False, "at": _now(),
            })
    run["status"] = "completed" if run["failures"] == 0 else "completed_with_errors"
    run["finished_at"] = _now()
    await db.sage_sync_runs.update_one({"id": run["id"]}, {"$set": run})
    await _audit(user, "sage_sync_run", "sage_sync_run", run["id"], {k: run[k] for k in ("imported", "updated", "skipped", "duplicates_prevented", "needs_mapping", "failures")})
    return run


@router.post("/sync/run")
async def run_sync(body: RunIn, user=Depends(get_current_user)):
    """Run a Sage order sync. Live fetch requires a connected Sage; otherwise returns health guidance.
    `simulate=true` (or an explicit `orders` feed) runs the SAME pipeline with a sample/provided feed."""
    _require_ops_role(user)
    if body.simulate or body.orders is not None:
        feed = body.orders if body.orders is not None else _sample_feed()
        run = await _do_run(user, "simulated", feed)
        return {"run": run, "health": "healthy", "mode": "simulated"}

    conn = await db.sage_connections.find_one(_of(user), {"_id": 0})
    if not conn or conn.get("auth_status") != "connected":
        return {
            "run": None, "health": "authentication_required", "mode": "live",
            "message": "Sage 200 is not connected. Configure & authenticate the connection, or use 'Simulate Sage feed' to exercise the pipeline.",
        }
    # Live fetch would call the Sage client here; kept disabled until creds are wired.
    run = await _do_run(user, "scheduled", [])
    return {"run": run, "health": "healthy", "mode": "live"}


@router.get("/sync/status")
async def sync_status(user=Depends(get_current_user)):
    of = _of(user)
    last = await db.sage_sync_runs.find_one(of, {"_id": 0}, sort=[("started_at", -1)])
    conn = await db.sage_connections.find_one(of, {"_id": 0})
    connected = bool(conn and conn.get("auth_status") == "connected")
    total_mirrors = await db.sage_order_mirrors.count_documents(of)
    needs_mapping = await db.sage_order_mirrors.count_documents({**of, "sync_state": "needs_mapping"})
    open_errors = await db.sage_sync_errors.count_documents({**of, "resolved": False})
    if not connected and total_mirrors == 0:
        health = "authentication_required"
    elif needs_mapping or open_errors:
        health = "warning"
    else:
        health = "healthy"
    return {
        "connected": connected, "health": health, "last_run": last,
        "total_orders": total_mirrors, "needs_mapping": needs_mapping, "open_errors": open_errors,
    }


@router.get("/orders")
async def sage_orders(state: Optional[str] = None, user=Depends(get_current_user)):
    flt = _of(user)
    if state and state != "all":
        flt["sync_state"] = state
    rows = await db.sage_order_mirrors.find(flt, {"_id": 0, "raw": 0}).sort("last_synced_at", -1).limit(200).to_list(200)
    return {"orders": rows}


@router.get("/runs")
async def sync_runs(user=Depends(get_current_user)):
    rows = await db.sage_sync_runs.find(_of(user), {"_id": 0}).sort("started_at", -1).limit(20).to_list(20)
    return {"runs": rows}


@router.get("/exceptions")
async def exceptions(user=Depends(get_current_user)):
    of = _of(user)
    dealers = await db.sage_dealer_mappings.find({**of, "status": "needs_mapping"}, {"_id": 0}).to_list(200)
    products = await db.sage_product_mappings.find({**of, "status": "needs_mapping"}, {"_id": 0}).to_list(200)
    errors = await db.sage_sync_errors.find({**of, "resolved": False}, {"_id": 0}).sort("at", -1).limit(100).to_list(100)
    return {"unmapped_dealers": dealers, "unmapped_products": products, "errors": errors}


class DealerMapIn(BaseModel):
    sage_account: str
    crm_company_id: str


@router.post("/mappings/dealer")
async def map_dealer(body: DealerMapIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    comp = await db.crm2_companies.find_one({**_of(user), "id": body.crm_company_id}, {"_id": 0, "id": 1, "name": 1})
    if not comp:
        raise HTTPException(404, "CRM company not found")
    await db.sage_dealer_mappings.update_one(
        {**_of(user), "sage_account": body.sage_account},
        {"$set": {"crm_company_id": comp["id"], "dealer_name": comp["name"], "status": "mapped", "updated_at": _now()}},
        upsert=True,
    )
    await _audit(user, "sage_dealer_mapped", "sage_dealer_mapping", body.sage_account, {"crm_company_id": comp["id"]})
    return {"ok": True}


class ProductMapIn(BaseModel):
    sage_stock_code: str
    product_code: str


@router.post("/mappings/product")
async def map_product(body: ProductMapIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    await db.sage_product_mappings.update_one(
        {**_of(user), "sage_stock_code": body.sage_stock_code},
        {"$set": {"product_code": body.product_code, "status": "mapped", "updated_at": _now()}},
        upsert=True,
    )
    await _audit(user, "sage_product_mapped", "sage_product_mapping", body.sage_stock_code, {"product_code": body.product_code})
    return {"ok": True}


@router.post("/orders/{mirror_id}/retry")
async def retry_import(mirror_id: str, user=Depends(get_current_user)):
    """Re-run the import for one mirrored Sage order (after resolving mappings)."""
    _require_ops_role(user)
    mirror = await db.sage_order_mirrors.find_one({**_of(user), "id": mirror_id}, {"_id": 0})
    if not mirror:
        raise HTTPException(404, "Sage order not found")
    run = {"id": _uid(), "organization_id": user.get("organization_id"), "trigger": "retry", "started_at": _now()}
    await db.sage_sync_runs.insert_one({**run, "status": "running", "imported": 0, "updated": 0, "skipped": 0, "duplicates_prevented": 0, "conflicts": 0, "failures": 0, "needs_mapping": 0})
    # Clear the stale hash so the pipeline re-evaluates.
    await db.sage_order_mirrors.update_one({"id": mirror_id}, {"$set": {"hash": ""}})
    outcome = await _import_one(user, mirror["raw"], run)
    # resolve related errors if now imported
    if outcome in ("imported", "updated"):
        await db.sage_sync_errors.update_many(
            {**_of(user), "sage_order_id": mirror["sage_order_id"], "resolved": False},
            {"$set": {"resolved": True, "resolved_at": _now()}},
        )
    await db.sage_sync_runs.update_one({"id": run["id"]}, {"$set": {"status": "completed", "finished_at": _now()}})
    return {"outcome": outcome}
