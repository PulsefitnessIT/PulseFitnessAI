"""
GymAxis Service Operations — Parts Inventory deepening.

Iter 215dr (Phase 4).

Builds on the Phase 3 catalogue + van stock with:
  • Warehouse stock per (location × sku)
  • Reorder rules (min/max) per (location × sku)
  • Low-stock detection (warehouse + every engineer's van)
  • Supplier purchase orders — draft → submitted → received
  • Receipt of a PO line increments warehouse stock + audits the
    `svc_part_movements` log.

Field mapping authoritative in `/app/memory/SVC_FIELD_MAPPING.md`.
"""
__integration_fields__ = {
    # svc_warehouse_stock (one row per location × sku)
    "warehouse_stock.id":             "gymaxis_only: local uuid",
    "warehouse_stock.organization_id": "gymaxis_only: tenant scoping",
    "warehouse_stock.location":       "sage: WarehouseCode · sicon: SubLocationID · bidirectional",
    "warehouse_stock.part_sku":       "sicon: PartCode · sage: StockCode · bidirectional",
    "warehouse_stock.qty":            "sage: StockBalance.OnHandQuantity · bidirectional (Sage owns truth, GymAxis mirrors)",
    # svc_van_stock (one row per engineer × sku) — same shape, different location
    "van_stock.id":                   "gymaxis_only: local uuid",
    "van_stock.engineer_id":          "sicon: AppointmentResourceID · sage: Employee.Reference · bidirectional",
    "van_stock.part_sku":             "sicon: PartCode · sage: StockCode · bidirectional",
    "van_stock.qty":                  "sage: StockBalance.OnHandQuantity (van warehouse) · bidirectional",
    # svc_reorder_rules (per location × sku reorder thresholds)
    "reorder_rules.id":               "gymaxis_only: local uuid",
    "reorder_rules.part_sku":         "sicon: PartCode · sage: StockCode · GymAxis → both (read-only on Sage)",
    "reorder_rules.location":         "sage: WarehouseCode · GymAxis → Sage",
    "reorder_rules.engineer_id":      "sicon: AppointmentResourceID (van rules) · GymAxis → Sicon",
    "reorder_rules.min_qty":          "sage: ReorderLevel · gymaxis_only when richer than Sage",
    "reorder_rules.max_qty":          "sage: ReorderQuantity · gymaxis_only when richer than Sage",
    "reorder_rules.supplier":         "sage: SuppliersAccountID (text, resolved on PO) · GymAxis → Sage",
    # svc_purchase_orders (header)
    "purchase_orders.id":             "sage: POPOrderID · GymAxis → Sage",
    "purchase_orders.organization_id": "gymaxis_only: tenant scoping",
    "purchase_orders.reference":      "sage: POPOrder.Reference · GymAxis → Sage",
    "purchase_orders.supplier":       "sage: POPOrder.SupplierName · GymAxis → Sage",
    "purchase_orders.supplier_email": "gymaxis_only: comms-hub recipient (Resend)",
    "purchase_orders.status":         "sage: POPOrder.Status (draft|submitted|received|cancelled) · GymAxis → Sage",
    "purchase_orders.lines":          "sage: POPOrderLine[] (rolled per line) · GymAxis → Sage",
    "purchase_orders.notes":          "sage: POPOrder.Notes · GymAxis → Sage",
    "purchase_orders.total":          "sage: POPOrder.GrossTotal · GymAxis → Sage",
    "purchase_orders.created_by_id":  "sage: Employee.Reference · GymAxis → Sage",
    "purchase_orders.submitted_at":   "sage: POPOrder.PostedAt · GymAxis → Sage",
    "purchase_orders.received_at":    "sage: POPOrder.ReceivedAt · GymAxis → Sage",
    "purchase_orders.supplier_email_sent_at": "gymaxis_only: comms-hub send timestamp",
    # svc_purchase_orders.lines[]
    "po_lines.id":                    "sage: POPOrderLineID · GymAxis → Sage",
    "po_lines.part_sku":              "sicon: PartCode · sage: StockCode fallback · GymAxis → both",
    "po_lines.part_name":             "sage: POPOrderLine.Description · GymAxis → Sage",
    "po_lines.qty":                   "sage: POPOrderLine.Quantity · GymAxis → Sage",
    "po_lines.received_qty":          "sage: POPOrderLine.QuantityReceived · GymAxis → Sage",
    "po_lines.unit_cost":             "sage: POPOrderLine.UnitCost · GymAxis → Sage",
    "po_lines.description":           "sage: POPOrderLine.Description override · GymAxis → Sage",
    "po_lines.sage_stock_code":       "sage: POPOrderLine.StockCode · GymAxis → Sage",
    "po_lines.sicon_part_id":         "sicon: PartID (legacy mapping) · GymAxis → Sicon",
    # svc_part_movements rows written by adjust + receive (also defined in parts.py manifest)
    "movements.adjust.movement_type": "sicon: MovementTypeID=adjust (PART_MOVEMENT_CROSSWALK) · GymAxis → Sicon",
    "movements.adjust.reason":         "sicon: AdjustmentReason · GymAxis → Sicon",
    "movements.po_receipt.movement_type": "sicon: MovementTypeID=receive (PART_MOVEMENT_CROSSWALK) · sage: StockTransfer.IN · GymAxis → both",
    "movements.po_receipt.po_id":      "sage: POPOrderID (back-reference) · GymAxis → Sage",
    "movements.po_receipt.po_reference": "sage: POPOrder.Reference · GymAxis → Sage",
}

from datetime import datetime, timezone
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.security_plus import safe_regex

from utils.database import db
from utils.auth import get_current_user
from routes.svc.integrations import sicon_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/inventory", tags=["Service Ops · Inventory"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Warehouse stock
# ─────────────────────────────────────────────────────────────────

@router.get("/stock")
async def list_stock(
    location: str = Query("warehouse", description="warehouse | van | site"),
    engineer_id: str = Query(""),
    search: str = Query(""),
    user=Depends(get_current_user),
):
    """List stock at a given location, joined with the catalogue.

    location='van' requires `engineer_id`. location='warehouse' returns
    the central warehouse rolled-up across all warehouses (Phase 4 has
    a single warehouse per org; multi-warehouse is a Phase 8 follow-up).
    """
    of = _of(user)
    if location == "van":
        if not engineer_id:
            raise HTTPException(400, "engineer_id required for van stock")
        rows = await db.svc_van_stock.find({**of, "engineer_id": engineer_id}, {"_id": 0}).to_list(500)
    else:
        rows = await db.svc_warehouse_stock.find({**of, "location": location}, {"_id": 0}).to_list(500)
    if not rows:
        return {"stock": [], "location": location, "engineer_id": engineer_id}
    skus = {r["part_sku"] for r in rows}
    cat_q = {**of, "sku": {"$in": list(skus)}}
    if search:
        cat_q["$or"] = [
            {"sku": safe_regex(search)},
            {"name": safe_regex(search)},
        ]
    catalogue = await db.svc_parts.find(cat_q, {"_id": 0}).to_list(len(skus))
    by_sku = {p["sku"]: p for p in catalogue}
    out = []
    for r in rows:
        if search and r["part_sku"] not in by_sku:
            continue
        r["part"] = by_sku.get(r["part_sku"], {})
        out.append(r)
    return {"stock": out, "location": location, "engineer_id": engineer_id, "count": len(out)}


@router.post("/stock/adjust")
async def adjust_stock(data: dict, user=Depends(get_current_user)):
    """Manual stock adjustment (count, write-off, transfer).

    Body: {part_sku, qty (signed delta), location: 'warehouse'|'van',
           engineer_id?, reason}
    """
    of = _of(user)
    sku = ((data or {}).get("part_sku") or "").strip().upper()
    delta = int((data or {}).get("qty") or 0)
    location = ((data or {}).get("location") or "warehouse").lower()
    engineer_id = (data or {}).get("engineer_id") or ""
    reason = (data or {}).get("reason") or ""
    if not sku or delta == 0:
        raise HTTPException(400, "part_sku + non-zero qty required")
    part = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
    if not part:
        raise HTTPException(404, f"Part {sku} not in catalogue")
    if location == "van":
        if not engineer_id:
            raise HTTPException(400, "engineer_id required for van adjustment")
        await db.svc_van_stock.update_one(
            {**of, "engineer_id": engineer_id, "part_sku": sku},
            {
                "$inc": {"qty": delta},
                "$set": {"updated_at": _now()},
                "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()},
            },
            upsert=True,
        )
    else:
        await db.svc_warehouse_stock.update_one(
            {**of, "location": location, "part_sku": sku},
            {
                "$inc": {"qty": delta},
                "$set": {"updated_at": _now()},
                "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()},
            },
            upsert=True,
        )
    await db.svc_part_movements.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "movement_type": "adjust",
        "part_sku": sku,
        "qty": delta,
        "location": location,
        "engineer_id": engineer_id,
        "reason": reason,
        "actor_id": user["id"],
        "actor_name": user.get("full_name") or "",
        "at": _now(),
    })
    return {"ok": True, "part_sku": sku, "delta": delta, "location": location}


# ─────────────────────────────────────────────────────────────────
# Reorder rules
# ─────────────────────────────────────────────────────────────────

@router.get("/reorder-rules")
async def list_rules(user=Depends(get_current_user)):
    of = _of(user)
    rules = await db.svc_reorder_rules.find(of, {"_id": 0}).sort("part_sku", 1).to_list(1000)
    return {"rules": rules, "count": len(rules)}


@router.post("/reorder-rules")
async def upsert_rule(data: dict, user=Depends(get_current_user)):
    """Create or update a reorder rule.

    Body: {part_sku, location: 'warehouse'|'van', engineer_id?,
           min_qty, max_qty, supplier?}
    """
    of = _of(user)
    sku = ((data or {}).get("part_sku") or "").strip().upper()
    location = ((data or {}).get("location") or "warehouse").lower()
    if not sku:
        raise HTTPException(400, "part_sku required")
    if location not in ("warehouse", "van"):
        raise HTTPException(400, "location must be warehouse | van")
    min_qty = int((data or {}).get("min_qty") or 0)
    max_qty = int((data or {}).get("max_qty") or 0)
    if max_qty and max_qty < min_qty:
        raise HTTPException(400, "max_qty cannot be less than min_qty")
    engineer_id = (data or {}).get("engineer_id") or ""
    if location == "van" and not engineer_id:
        raise HTTPException(400, "engineer_id required when location=van")
    key = {**of, "part_sku": sku, "location": location, "engineer_id": engineer_id}
    await db.svc_reorder_rules.update_one(
        key,
        {
            "$set": {
                **key,
                "min_qty": min_qty,
                "max_qty": max_qty,
                "supplier": (data.get("supplier") or "").strip(),
                "updated_at": _now(),
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "created_at": _now(),
            },
        },
        upsert=True,
    )
    rule = await db.svc_reorder_rules.find_one(key, {"_id": 0})
    return rule


@router.delete("/reorder-rules/{rule_id}")
async def delete_rule(rule_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_reorder_rules.delete_one({**of, "id": rule_id})
    return {"deleted": res.deleted_count}


# ─────────────────────────────────────────────────────────────────
# Low-stock detection + reorder suggestions
# ─────────────────────────────────────────────────────────────────

async def _low_stock_rows(of: dict) -> list[dict]:
    """Combine reorder rules with current stock and return rows that
    are below `min_qty`. Used by both `/low-stock` and the daily
    notification job (Phase 7).
    """
    rules = await db.svc_reorder_rules.find(of, {"_id": 0}).to_list(1000)
    if not rules:
        return []
    out: list[dict] = []
    for r in rules:
        sku = r.get("part_sku")
        loc = r.get("location")
        eng_id = r.get("engineer_id") or ""
        if loc == "van":
            stock = await db.svc_van_stock.find_one(
                {**of, "engineer_id": eng_id, "part_sku": sku}, {"_id": 0},
            )
        else:
            stock = await db.svc_warehouse_stock.find_one(
                {**of, "location": loc, "part_sku": sku}, {"_id": 0},
            )
        on_hand = int((stock or {}).get("qty") or 0)
        if on_hand < int(r.get("min_qty") or 0):
            part = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
            shortfall = max(0, int(r.get("max_qty") or r.get("min_qty") or 0) - on_hand)
            out.append({
                **r,
                "on_hand": on_hand,
                "shortfall": shortfall,
                "part": part or {},
            })
    return out


@router.get("/low-stock")
async def low_stock(user=Depends(get_current_user)):
    """Real-time low-stock + suggested reorder qty (max - on_hand)."""
    of = _of(user)
    rows = await _low_stock_rows(of)
    return {"rows": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# Purchase orders — supplier-facing
# ─────────────────────────────────────────────────────────────────

_VALID_PO_STATES = ("draft", "submitted", "received", "cancelled")


def _po_total(lines: list[dict]) -> float:
    return round(sum(float(line.get("unit_cost") or 0) * int(line.get("qty") or 0) for line in lines), 2)


async def _next_po_reference(organization_id: str) -> str:
    res = await db.svc_counters.find_one_and_update(
        {"organization_id": organization_id, "key": "po_seq"},
        {"$inc": {"value": 1}, "$setOnInsert": {"created_at": _now()}},
        upsert=True, return_document=True,
    )
    seq = (res or {}).get("value", 1)
    return f"PO-{seq:05d}"


@router.get("/purchase-orders")
async def list_pos(
    status: str = Query(""),
    user=Depends(get_current_user),
):
    of = _of(user)
    q = {**of}
    if status:
        if status not in _VALID_PO_STATES:
            raise HTTPException(400, f"status must be one of {_VALID_PO_STATES}")
        q["status"] = status
    rows = (
        await db.svc_purchase_orders.find(q, {"_id": 0})
        .sort("created_at", -1).limit(200).to_list(200)
    )
    return {"purchase_orders": rows, "count": len(rows)}


@router.post("/purchase-orders")
async def create_po(data: dict, user=Depends(get_current_user)):
    """Create a draft PO.

    Body: {supplier, supplier_email?, lines: [{part_sku, qty, unit_cost?,
           description?}], notes?}
    """
    of = _of(user)
    supplier = ((data or {}).get("supplier") or "").strip()
    raw_lines = (data or {}).get("lines") or []
    if not supplier or not raw_lines:
        raise HTTPException(400, "supplier and at least one line required")
    lines = []
    for raw in raw_lines:
        sku = (raw.get("part_sku") or "").strip().upper()
        qty = int(raw.get("qty") or 0)
        if not sku or qty <= 0:
            continue
        part = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
        unit_cost = float(raw.get("unit_cost") or (part or {}).get("cost") or 0)
        lines.append({
            "id": str(uuid.uuid4()),
            "part_sku": sku,
            "part_name": (part or {}).get("name") or raw.get("description") or sku,
            "qty": qty,
            "received_qty": 0,
            "unit_cost": unit_cost,
            "description": (raw.get("description") or "").strip(),
            "sage_stock_code": (part or {}).get("sage_stock_code") or "",
            "sicon_part_id": (part or {}).get("sicon_part_id") or "",
        })
    if not lines:
        raise HTTPException(400, "no valid lines")
    reference = await _next_po_reference(of["organization_id"])
    po = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "reference": reference,
        "supplier": supplier,
        "supplier_email": (data.get("supplier_email") or "").strip(),
        "status": "draft",
        "lines": lines,
        "notes": (data.get("notes") or "").strip(),
        "total": _po_total(lines),
        "created_by_id": user["id"],
        "created_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
        "updated_at": _now(),
        "submitted_at": None,
        "received_at": None,
    }
    await db.svc_purchase_orders.insert_one(po)
    po.pop("_id", None)
    return po


@router.post("/purchase-orders/from-low-stock")
async def create_po_from_low_stock(data: dict, user=Depends(get_current_user)):
    """One-click PO generation from current low-stock list.

    Body: {supplier} — groups all low-stock SKUs whose reorder-rule
    `supplier` matches (or all of them if `supplier='ALL'`) into a
    single draft PO with `qty = shortfall`.
    """
    of = _of(user)
    supplier = ((data or {}).get("supplier") or "").strip()
    if not supplier:
        raise HTTPException(400, "supplier required (or 'ALL')")
    low = await _low_stock_rows(of)
    if not low:
        raise HTTPException(409, "No low-stock parts to reorder")
    matched = [r for r in low if (supplier == "ALL") or (r.get("supplier") or "").lower() == supplier.lower()]
    if not matched:
        raise HTTPException(409, f"No low-stock parts match supplier {supplier!r}")
    lines = [
        {
            "part_sku": r["part_sku"],
            "qty": r["shortfall"],
            "unit_cost": float((r.get("part") or {}).get("cost") or 0),
            "description": (r.get("part") or {}).get("name") or r["part_sku"],
        }
        for r in matched if r.get("shortfall", 0) > 0
    ]
    return await create_po(
        {"supplier": supplier if supplier != "ALL" else "Mixed",
         "lines": lines,
         "notes": f"Auto-generated from low-stock alert ({len(lines)} lines)"},
        user=user,
    )


@router.put("/purchase-orders/{po_id}")
async def update_po(po_id: str, data: dict, user=Depends(get_current_user)):
    """Edit a draft PO (lines, notes, supplier, supplier_email)."""
    of = _of(user)
    po = await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po["status"] != "draft":
        raise HTTPException(409, "Only draft POs are editable")
    updates: dict = {"updated_at": _now()}
    for k in ("supplier", "supplier_email", "notes"):
        if k in data:
            updates[k] = (data.get(k) or "").strip()
    if "lines" in data:
        new_lines = []
        for raw in data["lines"]:
            sku = (raw.get("part_sku") or "").strip().upper()
            qty = int(raw.get("qty") or 0)
            if not sku or qty <= 0:
                continue
            part = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
            new_lines.append({
                "id": raw.get("id") or str(uuid.uuid4()),
                "part_sku": sku,
                "part_name": (part or {}).get("name") or raw.get("description") or sku,
                "qty": qty,
                "received_qty": int(raw.get("received_qty") or 0),
                "unit_cost": float(raw.get("unit_cost") or (part or {}).get("cost") or 0),
                "description": (raw.get("description") or "").strip(),
                "sage_stock_code": (part or {}).get("sage_stock_code") or "",
                "sicon_part_id": (part or {}).get("sicon_part_id") or "",
            })
        updates["lines"] = new_lines
        updates["total"] = _po_total(new_lines)
    await db.svc_purchase_orders.update_one({"id": po_id}, {"$set": updates})
    return await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})


@router.post("/purchase-orders/{po_id}/submit")
async def submit_po(po_id: str, user=Depends(get_current_user)):
    """Move a PO from draft to submitted (intent: emailed to supplier).

    Live email send lands in Phase 7 (Comms Hub). For now we just record
    the state change; the supplier outbox endpoint exposes the PO PDF
    payload for the comms layer to pick up.
    """
    of = _of(user)
    po = await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po["status"] != "draft":
        raise HTTPException(409, "Only draft POs may be submitted")
    await db.svc_purchase_orders.update_one(
        {"id": po_id},
        {"$set": {"status": "submitted", "submitted_at": _now(), "updated_at": _now()}},
    )
    # Sage outbox push (POPOrder draft) — the worker emits the actual
    # POST in Phase 8.
    try:
        await db.svc_sage_po_outbox.update_one(
            {"organization_id": of["organization_id"], "po_id": po_id},
            {
                "$set": {
                    "organization_id": of["organization_id"],
                    "po_id": po_id,
                    "po_reference": po.get("reference"),
                    "payload": {
                        "Reference": po.get("reference"),
                        "SupplierName": po.get("supplier"),
                        "SupplierEmail": po.get("supplier_email"),
                        "Notes": po.get("notes"),
                        "Lines": [
                            {
                                "StockCode": line.get("sage_stock_code") or line.get("part_sku"),
                                "Description": line.get("part_name"),
                                "Quantity": line.get("qty"),
                                "UnitCost": line.get("unit_cost"),
                            }
                            for line in (po.get("lines") or [])
                        ],
                    },
                    "status": "pending",
                    "updated_at": _now(),
                },
                "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now(), "attempts": 0},
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning("Sage POPOrder outbox push failed: %s", e)
    return await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})


@router.post("/purchase-orders/{po_id}/receive")
async def receive_po(po_id: str, data: dict, user=Depends(get_current_user)):
    """Record receipt of (some or all) lines.

    Body: {receipts: [{line_id, qty}], full?: bool}
    Increments warehouse stock + writes part movements + flips status
    to 'received' once every line is fully received.
    """
    of = _of(user)
    po = await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po["status"] not in ("submitted", "draft"):
        raise HTTPException(409, "Only submitted (or draft) POs can be received")
    receipts = (data or {}).get("receipts") or []
    full = bool((data or {}).get("full"))
    by_line = {r.get("line_id"): int(r.get("qty") or 0) for r in receipts}
    new_lines = []
    for line in po.get("lines", []):
        outstanding = max(0, int(line.get("qty") or 0) - int(line.get("received_qty") or 0))
        recv = int(by_line.get(line["id"], outstanding if full else 0))
        recv = max(0, min(recv, outstanding))
        if recv > 0:
            await db.svc_warehouse_stock.update_one(
                {**of, "location": "warehouse", "part_sku": line["part_sku"]},
                {
                    "$inc": {"qty": recv},
                    "$set": {"updated_at": _now()},
                    "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()},
                },
                upsert=True,
            )
            await db.svc_part_movements.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": of["organization_id"],
                "movement_type": "po_receipt",
                "po_id": po_id,
                "po_reference": po.get("reference"),
                "po_line_id": line["id"],
                "part_sku": line["part_sku"],
                "qty": recv,
                "location": "warehouse",
                "actor_id": user["id"],
                "actor_name": user.get("full_name") or "",
                "at": _now(),
            })
            # Iter 216h153 — push the goods-receipt to Sicon so its
            # stock ledger stays in sync with our warehouse.
            try:
                await sicon_sync.push_part_movement({
                    "id": str(uuid.uuid4()),
                    "organization_id": of["organization_id"],
                    "movement_type": "po_receipt",
                    "po_id": po_id,
                    "po_reference": po.get("reference"),
                    "part_sku": line["part_sku"],
                    "qty": recv,
                    "from_location": "supplier",
                    "to_location": "warehouse",
                    "actor_id": user["id"],
                    "actor_name": user.get("full_name") or "",
                    "at": _now(),
                })
            except Exception as e:
                logger.warning("[svc→sicon] po_receipt push failed: %s", e)
        line["received_qty"] = int(line.get("received_qty") or 0) + recv
        new_lines.append(line)
    fully_received = all(int(line.get("received_qty") or 0) >= int(line.get("qty") or 0) for line in new_lines)
    set_doc = {"lines": new_lines, "updated_at": _now()}
    if fully_received:
        set_doc["status"] = "received"
        set_doc["received_at"] = _now()
    await db.svc_purchase_orders.update_one({"id": po_id}, {"$set": set_doc})
    return await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_po(po_id: str, user=Depends(get_current_user)):
    of = _of(user)
    po = await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po["status"] == "received":
        raise HTTPException(409, "Cannot cancel a received PO")
    await db.svc_purchase_orders.update_one(
        {"id": po_id},
        {"$set": {"status": "cancelled", "updated_at": _now()}},
    )
    return await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})


__all__ = ["router"]
