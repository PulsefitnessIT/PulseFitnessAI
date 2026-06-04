"""CRM · Quote intelligence + Sage 200 export prep (Iter 220 P1).

Adds catalogue-aware intelligence to the live quote builder
(`crm2_quotes`, `/crm/v2/quotes`) and a Sage-200 export pipeline:
validate → status → Sage-ready CSV + logged export history.

No live Sage credentials are required for prep/CSV. Actual posting to
Sage 200 activates once the Sage integration is connected (currently
blocked on live OAuth creds).
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from utils.database import db
from routes.crm_auth import get_crm_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/v2/quotes", tags=["CRM Quote · Sage"])

# Sage UK VAT codes (user-confirmed default scheme).
VAT_CODE_MAP = {20: "T1", 0: "T0", 5: "T5"}
OBSOLETE_STATUSES = {"obsolete", "discontinued", "inactive", "archived"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def vat_code(rate) -> str:
    if rate is None or rate == "":
        return "T2"
    try:
        return VAT_CODE_MAP.get(int(round(float(rate))), "T2")
    except (TypeError, ValueError):
        return "T2"


def _margin_pct(cost: float, unit_price: float) -> float:
    if unit_price <= 0:
        return 0.0
    return round((unit_price - cost) / unit_price * 100, 1)


async def _min_margin_threshold(user: dict) -> float:
    s = await db.crm_settings.find_one(
        {"organization_id": user.get("organization_id"), "key": "quote_approval"},
        {"_id": 0, "value": 1},
    )
    if not s:
        return 0.0
    try:
        return float((s.get("value") or {}).get("min_margin_percent", 0))
    except (TypeError, ValueError):
        return 0.0


async def _live_version_id(user: dict) -> str | None:
    v = await db.crm_price_list_versions.find_one({**_of(user), "status": "live"}, {"_id": 0, "id": 1})
    return v["id"] if v else None


# ── Line hydration (called by crm_v2 on create/revise) ─────────────


async def hydrate_quote_lines(lines: list[dict], user: dict) -> list[dict]:
    """Snapshot catalogue facts (Sage code, SKU, cost, status, price-list
    version + the catalogue sell price at quote time) onto each line that
    references a product. Quoted prices the rep set are preserved."""
    live_vid = await _live_version_id(user)
    for line in lines or []:
        pid = line.get("product_id")
        if not pid:
            continue
        prod = await db.crm_products.find_one({"id": pid, **_of(user)}, {"_id": 0})
        if not prod:
            continue
        line.setdefault("description", prod.get("name", ""))
        line.setdefault("unit_price", prod.get("sell_price", 0))
        line.setdefault("cost_price", prod.get("cost_price", 0))
        line.setdefault("tax_rate", prod.get("tax_rate", 20))
        # Catalogue facts always refreshed (not rep-editable).
        line["sku"] = prod.get("sku")
        line["sage_code"] = prod.get("sage_code", "")
        line["product_status"] = prod.get("status", "") or ("inactive" if prod.get("active") is False else "active")
        line["catalogue_sell_at_quote"] = prod.get("sell_price", 0)
        line["price_list_version_id"] = prod.get("version_id") or live_vid
    return lines


# ── Intelligence ───────────────────────────────────────────────────


@router.post("/intelligence")
async def quote_intelligence(body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    """Per-line flags + suggestions for the current quote builder state.
    Body: { lines: [...], contact_id?, company_id? }."""
    lines = body.get("lines") or []
    threshold = await _min_margin_threshold(user)
    out_lines = []
    suggestions = []
    seen_pids = {ln.get("product_id") for ln in lines if ln.get("product_id")}
    totals = {"missing_sage": 0, "obsolete": 0, "low_margin": 0, "price_changed": 0}

    for i, ln in enumerate(lines):
        flags = []
        pid = ln.get("product_id")
        unit = float(ln.get("unit_price", 0) or 0)
        cost = float(ln.get("cost_price", 0) or 0)
        prod = None
        if pid:
            prod = await db.crm_products.find_one({"id": pid, **_of(user)}, {"_id": 0})
        if prod:
            cost = cost or float(prod.get("cost_price", 0) or 0)
            sage = prod.get("sage_code", "")
            status = (prod.get("status") or "").lower()
            if not sage:
                flags.append({"level": "error", "code": "missing_sage", "msg": "No Sage item code — required for export"})
                totals["missing_sage"] += 1
            if status in OBSOLETE_STATUSES or prod.get("active") is False:
                flags.append({"level": "warning", "code": "obsolete", "msg": f"Product is {status or 'inactive'}"})
                totals["obsolete"] += 1
            cur_sell = float(prod.get("sell_price", 0) or 0)
            if unit and cur_sell and round(unit, 2) != round(cur_sell, 2):
                flags.append({"level": "info", "code": "price_changed",
                              "msg": f"Quoted £{unit:.2f} vs catalogue £{cur_sell:.2f}"})
                totals["price_changed"] += 1
        if not (ln.get("description") or "").strip():
            flags.append({"level": "error", "code": "missing_description", "msg": "Missing description"})
        margin = _margin_pct(cost, unit)
        if unit > 0 and threshold and margin < threshold:
            flags.append({"level": "warning", "code": "low_margin", "msg": f"Margin {margin}% below floor {threshold}%"})
            totals["low_margin"] += 1
        out_lines.append({"index": i, "product_id": pid, "sku": ln.get("sku"),
                          "margin_percent": margin, "flags": flags})

        # Suggestions: bundle accessories + related-by-category (with Sage codes).
        if prod:
            acc_ids = [b.get("product_id") for b in (prod.get("bundle_items") or []) if b.get("product_id") and b.get("product_id") not in seen_pids]
            accessories = []
            if acc_ids:
                cur = db.crm_products.find({"id": {"$in": acc_ids}, **_of(user), "active": True}, {"_id": 0, "id": 1, "name": 1, "sku": 1, "sell_price": 1})
                accessories = await cur.to_list(10)
            related = []
            if prod.get("category"):
                cur = db.crm_products.find(
                    {**_of(user), "active": True, "category": prod["category"], "id": {"$nin": list(seen_pids)}},
                    {"_id": 0, "id": 1, "name": 1, "sku": 1, "sell_price": 1},
                ).limit(4)
                related = await cur.to_list(4)
            if accessories or related:
                suggestions.append({
                    "for_product_id": pid, "for_sku": prod.get("sku"), "for_name": prod.get("name"),
                    "accessories": accessories, "related": related,
                })

    ready = totals["missing_sage"] == 0 and all(not any(f["code"] == "missing_description" for f in ol["flags"]) for ol in out_lines)
    return {
        "lines": out_lines, "suggestions": suggestions, "totals": totals,
        "margin_threshold": threshold, "sage_ready": ready,
    }


# ── Sage export prep ───────────────────────────────────────────────


async def _resolve_account_ref(quote: dict, user: dict) -> str:
    if quote.get("sage_account_ref"):
        return quote["sage_account_ref"]
    cid = quote.get("company_id")
    if cid:
        co = await db.crm2_companies.find_one({"id": cid, **_of(user)}, {"_id": 0})
        if co:
            return co.get("sage_account_ref") or co.get("sage_reference") or ""
    return ""


def _build_sage_lines(quote: dict, default_nominal: str) -> list[dict]:
    out = []
    qvat = quote.get("vat_rate", 20)
    for ln in quote.get("lines", []):
        qty = float(ln.get("quantity", 0) or 0)
        unit = float(ln.get("unit_price", 0) or 0)
        disc = float(ln.get("discount", 0) or 0)
        net = round(qty * unit * (1 - disc / 100), 2)
        out.append({
            "product_code": ln.get("sku") or "",
            "sage_item_code": ln.get("sage_code") or "",
            "description": (ln.get("description") or ln.get("product_name") or "").strip(),
            "quantity": qty,
            "unit_price": unit,
            "discount_percent": disc,
            "net_amount": net,
            "vat_code": vat_code(ln.get("tax_rate", qvat)),
            "nominal_code": ln.get("nominal_code") or default_nominal or "",
        })
    return out


async def _validate(quote: dict, user: dict) -> dict:
    threshold = await _min_margin_threshold(user)
    account_ref = await _resolve_account_ref(quote, user)
    errors, warnings, line_reports = [], [], []
    if not account_ref:
        errors.append("Missing customer Sage account reference")
    lines = quote.get("lines", [])
    if not lines:
        errors.append("Quote has no line items")
    ack_obsolete = bool(quote.get("sage_ack_obsolete"))
    net_total = 0.0
    for i, ln in enumerate(lines):
        issues = []
        qty = float(ln.get("quantity", 0) or 0)
        unit = float(ln.get("unit_price", 0) or 0)
        cost = float(ln.get("cost_price", 0) or 0)
        disc = float(ln.get("discount", 0) or 0)
        net_total += round(qty * unit * (1 - disc / 100), 2)
        if not (ln.get("sage_code") or "").strip():
            issues.append("missing Sage item code")
        if not (ln.get("description") or ln.get("product_name") or "").strip():
            issues.append("missing description")
        if qty <= 0:
            issues.append("quantity must be > 0")
        if unit < 0:
            issues.append("negative price")
        status = (ln.get("product_status") or "").lower()
        if status in OBSOLETE_STATUSES:
            (warnings if ack_obsolete else errors).append(f"Line {i + 1} ({ln.get('sku')}): product is {status}{' (acknowledged)' if ack_obsolete else ' — acknowledge to export'}")
        margin = _margin_pct(cost, unit)
        if unit > 0 and threshold and margin < threshold:
            warnings.append(f"Line {i + 1} ({ln.get('sku')}): margin {margin}% below floor {threshold}%")
        if issues:
            errors.append(f"Line {i + 1} ({ln.get('sku') or 'no code'}): " + ", ".join(issues))
        line_reports.append({"index": i, "sku": ln.get("sku"), "sage_code": ln.get("sage_code"), "issues": issues})
    # totals reconcile
    stored = float(quote.get("subtotal", 0) or 0)
    if stored and abs(stored - round(net_total, 2)) > 0.05:
        warnings.append(f"Subtotal mismatch: stored £{stored:.2f} vs recomputed £{net_total:.2f}")
    return {
        "ready": len(errors) == 0,
        "errors": errors, "warnings": warnings,
        "account_ref": account_ref, "lines": line_reports,
        "net_total": round(net_total, 2),
    }


async def _get_quote(quote_id: str, user: dict) -> dict:
    q = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Quote not found")
    return q


@router.put("/{quote_id}/sage/meta")
async def set_sage_meta(quote_id: str, body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    """Set the Sage account ref / default nominal / acknowledge obsolete."""
    await _get_quote(quote_id, user)
    upd = {}
    for k in ("sage_account_ref", "sage_default_nominal"):
        if k in body:
            upd[k] = str(body[k] or "").strip()
    if "sage_ack_obsolete" in body:
        upd["sage_ack_obsolete"] = bool(body["sage_ack_obsolete"])
    if upd:
        upd["updated_at"] = _now()
        await db.crm2_quotes.update_one({"id": quote_id, **_of(user)}, {"$set": upd})
    return {"updated": True, **upd}


@router.post("/{quote_id}/sage/validate")
async def validate_sage(quote_id: str, user=Depends(get_crm_user)) -> dict:
    quote = await _get_quote(quote_id, user)
    report = await _validate(quote, user)
    status = "ready_for_sage" if report["ready"] else "validation_failed"
    await db.crm2_quotes.update_one({"id": quote_id, **_of(user)}, {"$set": {"sage_status": status, "sage_validated_at": _now()}})
    return {"report": report, "sage_status": status}


@router.post("/{quote_id}/sage/export")
async def export_sage(quote_id: str, user=Depends(get_crm_user)) -> dict:
    quote = await _get_quote(quote_id, user)
    report = await _validate(quote, user)
    if not report["ready"]:
        await db.crm2_quotes.update_one({"id": quote_id, **_of(user)}, {"$set": {"sage_status": "validation_failed"}})
        raise HTTPException(422, {"message": "Quote failed Sage validation", "errors": report["errors"]})

    default_nominal = quote.get("sage_default_nominal", "")
    sage_lines = _build_sage_lines(quote, default_nominal)
    net = sum(sl["net_amount"] for sl in sage_lines)
    vat = round(net * float(quote.get("vat_rate", 20)) / 100, 2)

    # Build Sage-ready CSV.
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["QuoteNumber", "AccountRef", "ProductCode", "SageItemCode", "Description",
                "Quantity", "UnitPrice", "DiscountPercent", "NetAmount", "VATCode", "NominalCode"])
    for sl in sage_lines:
        w.writerow([quote.get("quote_number", ""), report["account_ref"], sl["product_code"],
                    sl["sage_item_code"], sl["description"], sl["quantity"], sl["unit_price"],
                    sl["discount_percent"], sl["net_amount"], sl["vat_code"], sl["nominal_code"]])
    csv_text = buf.getvalue()

    # Is live Sage connected? (posting blocked on creds — record intent.)
    sage_cfg = await db.crm_integrations.find_one({"type": "sage200"}, {"_id": 0, "access_token": 1})
    connected = bool(sage_cfg and sage_cfg.get("access_token"))

    export_id = str(uuid.uuid4())
    record = {
        "id": export_id, "organization_id": user.get("organization_id"),
        "quote_id": quote_id, "quote_number": quote.get("quote_number", ""),
        "account_ref": report["account_ref"],
        "status": "exported", "pushed_to_sage": False,
        "sage_reference": None,
        "line_count": len(sage_lines), "net_total": round(net, 2),
        "vat_total": vat, "gross_total": round(net + vat, 2),
        "vat_code_default": vat_code(quote.get("vat_rate", 20)),
        "warnings": report["warnings"],
        "csv": csv_text, "sage_payload": sage_lines,
        "sage_connected_at_export": connected,
        "created_at": _now(), "created_by": user.get("full_name", ""),
        "note": "Sage-ready file generated. Live posting activates once Sage 200 is connected." if not connected else "Sage connected — ready to push.",
    }
    await db.crm_sage_exports.insert_one(dict(record))
    await db.crm2_quotes.update_one({"id": quote_id, **_of(user)}, {"$set": {
        "sage_status": "exported", "sage_exported_at": _now(), "sage_export_id": export_id,
    }})
    record.pop("_id", None)
    record.pop("csv", None)  # fetched via the download endpoint
    return {"export": record}


@router.get("/{quote_id}/sage/export.csv")
async def download_sage_csv(quote_id: str, user=Depends(get_crm_user)):
    await _get_quote(quote_id, user)
    rec = await db.crm_sage_exports.find_one({"quote_id": quote_id, **_of(user)}, {"_id": 0}, sort=[("created_at", -1)])
    if not rec:
        raise HTTPException(404, "No export found — generate one first")
    return Response(content=rec.get("csv", ""), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sage_{rec.get("quote_number", quote_id)}.csv"'})


@router.get("/{quote_id}/sage/exports")
async def list_sage_exports(quote_id: str, user=Depends(get_crm_user)) -> dict:
    await _get_quote(quote_id, user)
    cur = db.crm_sage_exports.find({"quote_id": quote_id, **_of(user)}, {"_id": 0, "csv": 0, "sage_payload": 0}).sort("created_at", -1).limit(20)
    return {"exports": await cur.to_list(20)}


async def ensure_quote_sage_indexes() -> None:
    try:
        await db.crm_sage_exports.create_index([("organization_id", 1), ("quote_id", 1), ("created_at", -1)])
    except Exception:
        logger.exception("ensure_quote_sage_indexes failed (non-fatal)")
