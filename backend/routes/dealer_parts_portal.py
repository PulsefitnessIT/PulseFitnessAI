"""Dealer Parts — Phase 5.

AI helpers (invoice parsing → machine lines + allowance, dealer summaries),
CSV report exports, and the Dealer Portal (dealer-scoped read views +
replenishment requests). Reuses Phase 1-4 collections — no duplication.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from utils.database import db
from utils.auth import get_current_user
from utils.dealer_parts_ai import parse_invoice_text, dealer_summary

from routes.dealer_parts import _of, _now, _audit, _dealer_or_404, _get_settings

router = APIRouter(prefix="/dealer-parts", tags=["Dealer Warranty Parts"])

DEALERS = "dealer_parts_dealers"
ORDERS = "dealer_parts_orders"
ALLOCATIONS = "dealer_parts_allocations"
STORES = "dealer_remote_stores"
STORE_STOCK = "dealer_remote_store_stock"
MOVEMENTS = "dealer_stock_movements"
USAGE = "dealer_parts_usage_logs"
REPLEN_REQ = "dealer_parts_replenishment_requests"


# ─────────────────────────────────────────────────────────────────
# AI
# ─────────────────────────────────────────────────────────────────

@router.post("/ai/parse-invoice")
async def ai_parse_invoice(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    s = await _get_settings(org)
    if not s.get("ai_recommendations_enabled", True):
        raise HTTPException(400, "AI is disabled in settings")
    text = (data.get("text") or "").strip()
    if len(text) < 20:
        raise HTTPException(400, "Provide the invoice/order text (at least 20 chars)")
    result = await parse_invoice_text(text)
    await _audit(org, user, "ai_invoice_parsed", available=result.get("available", False))
    return result


@router.post("/ai/dealer-summary")
async def ai_dealer_summary(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    s = await _get_settings(org)
    if not s.get("ai_recommendations_enabled", True):
        raise HTTPException(400, "AI is disabled in settings")
    dealer_id = data.get("dealer_id")
    dealer = await _dealer_or_404(org, dealer_id)
    orders = await db[ORDERS].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).to_list(500)
    allocs = await db[ALLOCATIONS].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).to_list(500)
    stock = await db[STORE_STOCK].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).to_list(2000)
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    usage = await db[USAGE].find({"organization_id": org, "dealer_id": dealer_id, "at": {"$gte": since}}, {"_id": 0}).to_list(2000)
    context = {
        "dealer": {"name": dealer["name"], "country": dealer.get("country"), "region": dealer.get("region")},
        "allowance_total": round(sum(o.get("allowance") or 0 for o in orders), 2),
        "approved_value": round(sum(a.get("approved_value") or 0 for a in allocs if a.get("status") not in ("draft", "cancelled")), 2),
        "stock_value": round(sum((x.get("qty_on_hand") or 0) * (x.get("unit_value") or 0) for x in stock), 2),
        "stock_lines": len(stock),
        "usage_90d": [{"part": u.get("part_sku"), "qty": u.get("quantity"), "failure": u.get("failure_reason"), "warranty": u.get("warranty")} for u in usage[:60]],
        "orders_count": len(orders),
    }
    result = await dealer_summary(context)
    await _audit(org, user, "ai_dealer_summary", dealer_id=dealer_id, available=result.get("available", False))
    return {"dealer_name": dealer["name"], **result}


# ─────────────────────────────────────────────────────────────────
# CSV Reports
# ─────────────────────────────────────────────────────────────────

def _csv(headers: list, rows: list, filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/{report}.csv")
async def report_csv(report: str, dealer_id: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    base: dict = {"organization_id": org}
    if dealer_id:
        base["dealer_id"] = dealer_id

    if report == "allocations":
        rows = await db[ALLOCATIONS].find(base, {"_id": 0}).to_list(5000)
        return _csv(
            ["Dealer", "Order Ref", "Status", "Parts", "Recommended £", "Approved £", "Allowance £", "Over allowance"],
            [[a.get("dealer_name"), a.get("order_reference"), a.get("status"), len(a.get("items", [])),
              a.get("recommended_value"), a.get("approved_value"), a.get("allowance"), a.get("over_allowance")] for a in rows],
            "dealer_allocations.csv",
        )
    if report == "stock":
        rows = await db[STORE_STOCK].find(base, {"_id": 0}).to_list(10000)
        return _csv(
            ["Dealer ID", "Store", "Part SKU", "Part", "On hand", "In transit", "Unit £", "Value £"],
            [[s.get("dealer_id"), s.get("store_name"), s.get("part_sku"), s.get("part_name"),
              s.get("qty_on_hand"), s.get("qty_in_transit", 0), s.get("unit_value"),
              round((s.get("qty_on_hand") or 0) * (s.get("unit_value") or 0), 2)] for s in rows],
            "dealer_stock.csv",
        )
    if report == "usage":
        rows = await db[USAGE].find(base, {"_id": 0}).sort([("at", -1)]).to_list(10000)
        return _csv(
            ["Date", "Dealer", "Part SKU", "Part", "Qty", "Machine", "Serial", "Failure reason", "Warranty", "Country"],
            [[u.get("at", "")[:10], u.get("dealer_name"), u.get("part_sku"), u.get("part_name"), u.get("quantity"),
              u.get("machine_model"), u.get("serial_number"), u.get("failure_reason"), u.get("warranty"), u.get("country")] for u in rows],
            "dealer_usage.csv",
        )
    if report == "failures":
        since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        rows = await db[USAGE].find({**base, "at": {"$gte": since}}, {"_id": 0}).to_list(10000)
        agg: dict = {}
        for u in rows:
            if not (u.get("warranty") or (u.get("failure_reason") or "unknown") != "unknown"):
                continue
            k = (u.get("part_sku"), u.get("country") or "Unknown")
            agg[k] = agg.get(k, 0) + 1
        return _csv(
            ["Part SKU", "Country", "Failures (90d)"],
            [[k[0], k[1], v] for k, v in sorted(agg.items(), key=lambda x: -x[1])],
            "dealer_failures.csv",
        )
    raise HTTPException(404, "Unknown report")


# ─────────────────────────────────────────────────────────────────
# Dealer Portal (dealer-scoped views)
# ─────────────────────────────────────────────────────────────────

@router.get("/portal/{dealer_id}/overview")
async def portal_overview(dealer_id: str, user=Depends(get_current_user)):
    org = _of(user)
    dealer = await _dealer_or_404(org, dealer_id)
    stock = await db[STORE_STOCK].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).to_list(2000)
    incoming = await db[ALLOCATIONS].find(
        {"organization_id": org, "dealer_id": dealer_id, "status": {"$in": ["dispatched", "partially_received"]}}, {"_id": 0}
    ).to_list(200)
    usage = await db[USAGE].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).sort([("at", -1)]).limit(15).to_list(15)
    requests = await db[REPLEN_REQ].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}).sort([("created_at", -1)]).to_list(100)
    for s in stock:
        on_hand = s.get("qty_on_hand") or 0
        mn = s.get("min_stock") or 0
        s["stock_status"] = "out_of_stock" if on_hand <= 0 else ("low_stock" if mn and on_hand <= mn else "in_stock")
    return {
        "dealer": {"id": dealer["id"], "name": dealer["name"], "country": dealer.get("country"), "region": dealer.get("region")},
        "stock": stock,
        "stock_value": round(sum((s.get("qty_on_hand") or 0) * (s.get("unit_value") or 0) for s in stock), 2),
        "incoming": incoming,
        "recent_usage": usage,
        "requests": requests,
    }


@router.post("/portal/{dealer_id}/request-replenishment")
async def request_replenishment(dealer_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    dealer = await _dealer_or_404(org, dealer_id)
    sku = (data.get("part_sku") or "").strip().upper()
    if not sku:
        raise HTTPException(400, "part_sku required")
    req = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "dealer_id": dealer_id,
        "dealer_name": dealer["name"],
        "part_sku": sku,
        "part_name": (data.get("part_name") or sku).strip(),
        "quantity": float(data.get("quantity") or 1),
        "note": (data.get("note") or "").strip(),
        "status": "requested",
        "requested_by": user.get("full_name") or user.get("email"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[REPLEN_REQ].insert_one(dict(req))
    await _audit(org, user, "replenishment_requested", dealer_id=dealer_id, part_sku=sku, quantity=req["quantity"])
    req.pop("_id", None)
    return req


@router.get("/replenishment-requests")
async def list_replenishment_requests(status: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    q: dict = {"organization_id": org}
    if status:
        q["status"] = status
    rows = await db[REPLEN_REQ].find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
    return {"requests": rows, "count": len(rows)}


@router.patch("/replenishment-requests/{req_id}")
async def update_replenishment_request(req_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    existing = await db[REPLEN_REQ].find_one({"organization_id": org, "id": req_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Request not found")
    status = (data.get("status") or "").strip()
    if status not in ("requested", "under_review", "approved", "rejected", "fulfilled"):
        raise HTTPException(400, "Invalid status")
    await db[REPLEN_REQ].update_one({"organization_id": org, "id": req_id}, {"$set": {"status": status, "updated_at": _now()}})
    await _audit(org, user, "replenishment_request_updated", req_id=req_id, status=status)
    return await db[REPLEN_REQ].find_one({"organization_id": org, "id": req_id}, {"_id": 0})
