"""CRM · Fulfilment for CPQ v2 quotes (Equipment Sales Phase 3).

Extends the EXISTING quote → purchase-order → equipment processes (no new
module):
  • Raise a purchase order straight from a won deal's equipment/spare lines
    (stored in the existing ``purchase_orders`` collection, linked by
    ``quote_id``; supplier is paid at cost).
  • Receive goods (GRN) → AUTO-CREATE ``equipment`` register records from the
    received PO items (one per serial), traceable back to the deal.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user
from utils.warranty import get_tier, compute_expiry

router = APIRouter(prefix="/crm/v2/quotes", tags=["CRM Quote Fulfilment"])

# Line types that are physically procured/fulfilled.
PROCURABLE = ("sale", "spare_part")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _id() -> str:
    return str(uuid.uuid4())


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _can_manage(user: dict) -> bool:
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return True
    return (user.get("role") or "").lower() in ("owner", "admin", "manager")


async def _audit(user: dict, quote_id: str, action: str, meta: dict | None = None) -> None:
    try:
        from routes.crm_core import log_audit
        await log_audit(user, "quote_fulfilment", quote_id, action, meta or {})
    except Exception:
        pass


async def _get_quote(quote_id: str, user: dict) -> dict:
    quote = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "Quote not found")
    # Heal legacy quotes whose lines were saved before stable line ids
    # existed — persist a uuid once so PO/GRN references stay consistent.
    lines = quote.get("lines", []) or []
    if any(not ln.get("id") for ln in lines):
        for ln in lines:
            if not ln.get("id"):
                ln["id"] = _id()
        await db.crm2_quotes.update_one(
            {"id": quote_id, **_of(user)},
            {"$set": {"lines": lines, "updated_at": _now()}},
        )
        quote["lines"] = lines
    return quote


def _procurable_lines(quote: dict) -> list[dict]:
    out = []
    for ln in quote.get("lines", []) or []:
        if (ln.get("line_type") or "sale") not in PROCURABLE:
            continue
        out.append({
            "line_id": ln.get("id") or _id(),
            "description": ln.get("description") or ln.get("product_name") or "Item",
            "line_type": ln.get("line_type") or "sale",
            "quantity": float(ln.get("quantity", 1) or 0),
            "cost_price": float(ln.get("cost_price", 0) or 0),
            "sell_price": float(ln.get("unit_price", 0) or 0),
            "manufacturer": ln.get("manufacturer") or "",
            "model": ln.get("model") or "",
            "sku": ln.get("sku") or "",
            "warranty_tier": (ln.get("warranty_tier") or "").strip() or None,
            "is_equipment": (ln.get("line_type") or "sale") == "sale",
        })
    return out


async def _build_view(quote: dict, user: dict) -> dict:
    pos = await db.purchase_orders.find(
        {"quote_id": quote["id"], **_of(user)}, {"_id": 0},
    ).sort("created_at", 1).to_list(100)
    equipment = await db.equipment.find(
        {"quote_id": quote["id"], **_of(user)},
        {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "manufacturer": 1,
         "model": 1, "po_number": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(200)
    procurable = _procurable_lines(quote)
    equip_lines = [p for p in procurable if p["is_equipment"]]
    return {
        "quote_id": quote["id"],
        "quote_number": quote.get("quote_number", ""),
        "currency": quote.get("currency", "GBP"),
        "procurable_lines": procurable,
        "purchase_orders": pos,
        "equipment": equipment,
        "summary": {
            "procurable_line_count": len(procurable),
            "equipment_line_count": len(equip_lines),
            "equipment_units_expected": sum(int(p["quantity"]) for p in equip_lines),
            "po_count": len(pos),
            "equipment_created": len(equipment),
        },
    }


# ── Read ───────────────────────────────────────────────────────────


@router.get("/{quote_id}/fulfilment")
async def get_fulfilment(quote_id: str, user=Depends(get_crm_user)):
    quote = await _get_quote(quote_id, user)
    return await _build_view(quote, user)


# ── Raise a purchase order from the quote ──────────────────────────


@router.post("/{quote_id}/purchase-orders")
async def raise_po(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Create a PO from the quote's equipment/spare lines. Body:
    {supplier_name, supplier_email?, delivery_address?, notes?, expected_date?,
     line_ids?: [ ... subset of procurable line ids ... ]}."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can raise purchase orders")
    quote = await _get_quote(quote_id, user)
    procurable = _procurable_lines(quote)
    if not procurable:
        raise HTTPException(400, "This quote has no equipment or spare-part lines to procure")

    wanted = set(data.get("line_ids") or [])
    chosen = [p for p in procurable if (not wanted or p["line_id"] in wanted)]
    if not chosen:
        raise HTTPException(400, "No matching lines to put on the purchase order")

    supplier_name = (data.get("supplier_name") or "").strip()
    if not supplier_name:
        raise HTTPException(422, "supplier_name is required")

    items = [{
        "line_id": p["line_id"],
        "name": p["description"],
        "manufacturer": p["manufacturer"],
        "model": p["model"],
        "sku": p["sku"],
        "quantity": p["quantity"],
        "unit_price": p["cost_price"],   # PO pays supplier at cost
        "sell_price": p["sell_price"],   # kept so GRN can value the asset
        "warranty_tier": p.get("warranty_tier"),
        "is_equipment": p["is_equipment"],
        "received_qty": 0,
    } for p in chosen]

    po_id = _id()
    subtotal = round(sum(i["quantity"] * i["unit_price"] for i in items), 2)
    vat_rate = float(data.get("vat_rate", 20) or 0)
    po = {
        "id": po_id,
        "po_number": f"PO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{po_id[:4].upper()}",
        "organization_id": user.get("organization_id"),
        "user_id": user["id"],
        "quote_id": quote_id,
        "quote_number": quote.get("quote_number", ""),
        "company_id": quote.get("company_id"),
        "company_name": quote.get("company_name", ""),
        "supplier_name": supplier_name,
        "supplier_email": (data.get("supplier_email") or "").strip(),
        "delivery_address": (data.get("delivery_address") or "").strip(),
        "expected_date": data.get("expected_date") or "",
        "items": items,
        "subtotal": subtotal,
        "vat_rate": vat_rate,
        "vat_amount": round(subtotal * vat_rate / 100, 2),
        "total": round(subtotal * (1 + vat_rate / 100), 2),
        "notes": (data.get("notes") or "").strip(),
        "status": "draft",
        "source": "quote",
        "created_by": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.purchase_orders.insert_one(dict(po))
    await _audit(user, quote_id, "po_raised", {"po_number": po["po_number"], "items": len(items)})
    po.pop("_id", None)
    return {"purchase_order": po, **(await _build_view(quote, user))}


@router.post("/{quote_id}/purchase-orders/{po_id}/status")
async def set_po_status(quote_id: str, po_id: str, data: dict, user=Depends(get_crm_user)):
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can update purchase orders")
    status = (data.get("status") or "").lower()
    if status not in ("draft", "ordered", "cancelled"):
        raise HTTPException(422, "status must be draft, ordered or cancelled")
    res = await db.purchase_orders.update_one(
        {"id": po_id, "quote_id": quote_id, **_of(user)},
        {"$set": {"status": status, "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Purchase order not found")
    quote = await _get_quote(quote_id, user)
    return await _build_view(quote, user)


# ── Receive goods (GRN) → auto-create equipment ────────────────────


@router.post("/{quote_id}/purchase-orders/{po_id}/receive")
async def receive_goods(quote_id: str, po_id: str, data: dict, user=Depends(get_crm_user)):
    """Goods-received note. Body:
    {site_id?, items: [{line_id, received_qty, serials?: [..]}]}.
    Creates one equipment register record per received unit of an
    equipment line (using serials where supplied)."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can receive goods")
    quote = await _get_quote(quote_id, user)
    po = await db.purchase_orders.find_one({"id": po_id, "quote_id": quote_id, **_of(user)}, {"_id": 0})
    if not po:
        raise HTTPException(404, "Purchase order not found")

    site_id = (data.get("site_id") or "").strip() or None
    receipts = {r.get("line_id"): r for r in (data.get("items") or [])}
    items = po.get("items", [])
    valid_ids = {it.get("line_id") for it in items}
    unknown = [lid for lid in receipts if lid not in valid_ids]
    if unknown:
        raise HTTPException(422, f"Unknown PO line(s): {', '.join(map(str, unknown))}")
    if not any(int(float(r.get("received_qty", 0) or 0)) > 0 for r in receipts.values()):
        raise HTTPException(422, "Enter a received quantity of at least 1 on one or more lines")
    created_equipment = []

    for item in items:
        r = receipts.get(item.get("line_id"))
        if not r:
            continue
        req = int(float(r.get("received_qty", 0) or 0))
        if req <= 0:
            continue
        outstanding = int(item.get("quantity", 0)) - int(item.get("received_qty", 0))
        if req > outstanding:
            raise HTTPException(422, f"Cannot receive {req} of '{item.get('name')}' — only {outstanding} outstanding")
        serials = r.get("serials") or []
        if item.get("is_equipment"):
            for n in range(req):
                eq_id = _id()
                serial = serials[n] if n < len(serials) else None
                _wtier = get_tier(item.get("warranty_tier"))
                _wstart = _today()
                eq = {
                    "id": eq_id,
                    "user_id": user["id"],
                    "organization_id": user.get("organization_id"),
                    "name": item.get("name") or "Equipment",
                    "equipment_type": "gym_equipment",
                    "manufacturer": item.get("manufacturer") or "",
                    "model": item.get("model") or "",
                    "serial_number": (serial or "").strip() or None,
                    "purchase_date": _wstart,
                    "purchase_cost": float(item.get("sell_price", 0) or 0),
                    "supplier": po.get("supplier_name", ""),
                    "status": "active",
                    "site_id": site_id,
                    "manuals": [],
                    # Warranty sold on the deal.
                    "warranty_tier": _wtier["code"],
                    "warranty_months": _wtier["months"],
                    "warranty_start": _wstart,
                    "warranty_expiry": compute_expiry(_wstart, _wtier["months"]),
                    # Deal traceability.
                    "source": "deal_grn",
                    "quote_id": quote_id,
                    "quote_number": quote.get("quote_number", ""),
                    "po_id": po_id,
                    "po_number": po.get("po_number", ""),
                    "company_id": quote.get("company_id"),
                    "company_name": quote.get("company_name", ""),
                    "created_at": _now(),
                    "updated_at": _now(),
                }
                await db.equipment.insert_one(dict(eq))
                created_equipment.append({"id": eq_id, "name": eq["name"], "serial_number": eq["serial_number"]})
        item["received_qty"] = int(item.get("received_qty", 0)) + req

    # PO status roll-up.
    total_qty = sum(int(i.get("quantity", 0)) for i in items)
    recv_qty = sum(int(i.get("received_qty", 0)) for i in items)
    po_status = "received" if recv_qty >= total_qty and total_qty > 0 else ("part_received" if recv_qty > 0 else po.get("status", "draft"))
    await db.purchase_orders.update_one(
        {"id": po_id, **_of(user)},
        {"$set": {"items": items, "status": po_status, "updated_at": _now(),
                  "last_grn_at": _now()}},
    )
    await _audit(user, quote_id, "goods_received", {"po_number": po.get("po_number"), "created": len(created_equipment)})
    return {"created_equipment": created_equipment, "po_status": po_status, **(await _build_view(quote, user))}
