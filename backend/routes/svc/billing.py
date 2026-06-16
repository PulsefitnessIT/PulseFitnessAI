"""
Pulse Fitness Service Operations — Quoting & Billing.

Iter 215dt (Phase 6).

Closes the chargeable workflow:
  case → engineer adds time + parts → operator builds a quote
  → operator approves → invoice draft pushed to svc_sage_invoice_outbox
  with real line values (replaces the placeholder line emitted in Phase 1).

Quotes live in `svc_quotes` (one quote per case for now; revisions are
tracked by `version` integer + `history[]`).

Field mapping (extends SVC_FIELD_MAPPING.md §10):
  Pulse Fitness quote line          ↔ Sage SLInvoiceLine
  ─────────────────────────────────────────────────
  kind=labour                  ↔ NominalCode (4010 chargeable default)
                                + Description "Labour — engineer name (Nh)"
  kind=part                    ↔ NominalCode (parts nominal),
                                StockCode = sage_stock_code or part_sku,
                                Description = part name + qty,
                                UnitNetAmount = unit_amount
  kind=adjustment              ↔ extra line (discount or surcharge)
"""
__integration_fields__ = {
    # svc_quotes (header)
    "quotes.id":              "gymaxis_only: local uuid",
    "quotes.organization_id": "gymaxis_only: tenant scoping",
    "quotes.case_id":         "sicon: ServiceCallID · Pulse Fitness → Sicon · sage: invoice link via case",
    "quotes.case_reference":  "sicon: ServiceCallReference · sage: SLInvoice.Reference · Pulse Fitness → both",
    "quotes.reference":       "sage: SLQuote.Reference (when SLQuote wiring lands) · Pulse Fitness → Sage",
    "quotes.status":          "gymaxis_only: draft|approved|invoiced|void (drives outbox enqueue)",
    "quotes.lines":           "sage: SLInvoiceLine[] (rolled per line) · Pulse Fitness → Sage",
    "quotes.subtotal":        "sage: SLInvoice.NetAmount · Pulse Fitness → Sage",
    "quotes.discount":        "sage: SLInvoice.GlobalDiscountValue · Pulse Fitness → Sage",
    "quotes.net":             "sage: SLInvoice.NetAmount (post-discount) · Pulse Fitness → Sage",
    "quotes.vat":             "sage: SLInvoice.TaxAmount · Pulse Fitness → Sage",
    "quotes.gross":           "sage: SLInvoice.GrossAmount · Pulse Fitness → Sage",
    "quotes.vat_rate":        "sage: TaxRate (default 0.20 / T1) · Pulse Fitness → Sage",
    "quotes.discount_pct":    "sage: GlobalDiscountPercent · Pulse Fitness → Sage",
    "quotes.notes":           "sage: SLInvoice.SecondReference / Notes · Pulse Fitness → Sage",
    "quotes.version":         "gymaxis_only: revision counter for audit trail",
    "quotes.history":         "gymaxis_only: revision diffs",
    "quotes.created_by_id":   "sage: Employee.Reference · Pulse Fitness → Sage (line-level if needed)",
    "quotes.approved_by_id":  "sage: ApprovedBySageUserID · Pulse Fitness → Sage",
    "quotes.approved_at":     "sage: ApprovedAt · Pulse Fitness → Sage",
    "quotes.invoiced_at":     "sage: SLInvoice.PostedAt · Pulse Fitness → Sage",
    # svc_quotes.lines[] (line-item)
    "lines.id":              "gymaxis_only: local uuid (echo on outbox payload for traceability)",
    "lines.kind":            "sage: line type — labour|part|adjustment maps to NominalCode + Description shape",
    "lines.qty":             "sage: SLInvoiceLine.Quantity · Pulse Fitness → Sage",
    "lines.unit_amount":     "sage: SLInvoiceLine.UnitNetAmount · Pulse Fitness → Sage",
    "lines.description":     "sage: SLInvoiceLine.Description · Pulse Fitness → Sage",
    "lines.nominal_code":    "sage: SLInvoiceLine.NominalCode (4010 labour · 4011 parts default) · Pulse Fitness → Sage",
    "lines.tax_code":        "sage: SLInvoiceLine.TaxCode (T1 default) · Pulse Fitness → Sage",
    "lines.part_sku":        "sicon: PartCode · sage: StockCode fallback · Pulse Fitness → both",
    "lines.stock_code":      "sage: SLInvoiceLine.StockCode · Pulse Fitness → Sage",
    "lines.engineer_id":     "sage: Employee.Reference (labour line attribution) · Pulse Fitness → Sage",
    "lines.engineer_name":   "sage: line description fragment · Pulse Fitness → Sage",
    "lines.time_entry_id":   "sicon: TimeEntryID (back-reference) · Pulse Fitness → Sicon (audit only)",
    "lines.movement_id":     "sicon: StockMovementID(s) (back-reference) · Pulse Fitness → Sicon (audit only)",
    "lines.total":           "sage: SLInvoiceLine.LineTotalNetAmount · Pulse Fitness → Sage",
}

from datetime import datetime, timezone
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.audit import audit_log
from routes.svc.integrations import sage_invoice

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/billing", tags=["Service Ops · Billing"])


_VALID_QUOTE_STATES = ("draft", "approved", "invoiced", "void")
_LABOUR_DEFAULT_RATE = 65.0  # £/hr placeholder — finance to confirm
_PARTS_NOMINAL = "4011"      # placeholder until finance signs off (mapping doc §10)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Math + line shaping
# ─────────────────────────────────────────────────────────────────

def _line_total(line: dict) -> float:
    return round(float(line.get("qty") or 0) * float(line.get("unit_amount") or 0), 2)


def _quote_totals(lines: list[dict], *, vat_rate: float = 0.20,
                  discount_pct: float = 0.0) -> dict:
    subtotal = round(sum(_line_total(line) for line in lines), 2)
    discount = round(subtotal * (discount_pct / 100.0), 2)
    net = round(max(0.0, subtotal - discount), 2)
    vat = round(net * vat_rate, 2)
    gross = round(net + vat, 2)
    return {
        "subtotal": subtotal,
        "discount": discount,
        "net": net,
        "vat": vat,
        "gross": gross,
    }


def _normalise_lines(raw_lines: list[dict]) -> list[dict]:
    out: list[dict] = []
    for raw in (raw_lines or []):
        kind = (raw.get("kind") or "labour").lower()
        if kind not in ("labour", "part", "adjustment"):
            continue
        qty = float(raw.get("qty") or 0)
        unit = float(raw.get("unit_amount") or 0)
        if qty == 0 and unit == 0 and kind != "adjustment":
            continue
        line = {
            "id": raw.get("id") or str(uuid.uuid4()),
            "kind": kind,
            "qty": qty,
            "unit_amount": unit,
            "description": (raw.get("description") or "").strip(),
            "nominal_code": (raw.get("nominal_code") or "").strip() or None,
            "tax_code": (raw.get("tax_code") or "T1").strip(),
            "part_sku": (raw.get("part_sku") or "").strip().upper() or None,
            "stock_code": (raw.get("stock_code") or "").strip() or None,
            "engineer_id": raw.get("engineer_id") or "",
            "engineer_name": raw.get("engineer_name") or "",
            "time_entry_id": raw.get("time_entry_id") or "",
            "movement_id": raw.get("movement_id") or "",
            "total": round(qty * unit, 2),
        }
        out.append(line)
    return out


async def _next_quote_reference(org_id: str) -> str:
    res = await db.svc_counters.find_one_and_update(
        {"organization_id": org_id, "key": "quote_seq"},
        {"$inc": {"value": 1}, "$setOnInsert": {"created_at": _now()}},
        upsert=True, return_document=True,
    )
    return f"Q-{(res or {}).get('value', 1):05d}"


# ─────────────────────────────────────────────────────────────────
# List + read
# ─────────────────────────────────────────────────────────────────

@router.get("")
async def billing_queue(
    status: str = Query("", description="ready|quoted|invoiced|all"),
    user=Depends(get_current_user),
):
    """List chargeable cases with their billing state.

    `ready`    — closed/invoiced cases that have NO quote yet.
    `quoted`   — cases with an approved quote not yet finalised to Sage.
    `invoiced` — quote.status='invoiced'.
    """
    of = _of(user)
    cases = await db.svc_cases.find(
        {**of, "cover_type": "chargeable", "status": {"$in": ["closed", "invoiced", "awaiting_sign_off", "repaired"]}},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "status": 1, "customer_name": 1,
         "site_name": 1, "closed_at": 1, "scheduled_at": 1},
    ).sort("closed_at", -1).limit(500).to_list(500)
    if not cases:
        return {"rows": [], "count": 0}
    case_ids = [c["id"] for c in cases]
    quotes = await db.svc_quotes.find(
        {**of, "case_id": {"$in": case_ids}, "status": {"$ne": "void"}}, {"_id": 0},
    ).to_list(len(case_ids))
    by_case = {q["case_id"]: q for q in quotes}
    rows = []
    for c in cases:
        q = by_case.get(c["id"])
        billing_state = "ready"
        if q and q.get("status") == "approved":
            billing_state = "quoted"
        elif q and q.get("status") == "invoiced":
            billing_state = "invoiced"
        if status and status != "all" and status != billing_state:
            continue
        rows.append({**c, "billing_state": billing_state, "quote": q})
    return {"rows": rows, "count": len(rows)}


@router.get("/{case_id}/quote")
async def get_quote(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = _strip(await db.svc_cases.find_one({"id": case_id, **of}))
    if not case:
        raise HTTPException(404, "Case not found")
    quote = _strip(await db.svc_quotes.find_one({**of, "case_id": case_id, "status": {"$ne": "void"}}))
    return {"case": case, "quote": quote}


# ─────────────────────────────────────────────────────────────────
# Auto-fill from time entries + parts movements
# ─────────────────────────────────────────────────────────────────

@router.post("/{case_id}/quote/auto-fill")
async def auto_fill(case_id: str, user=Depends(get_current_user)):
    """Pre-populate a draft quote from chargeable time entries +
    allocated/consumed parts. Operator can then tweak and approve.
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    if (case.get("cover_type") or "").lower() != "chargeable":
        raise HTTPException(409, "Auto-fill is only valid for chargeable cases")

    # --- Labour lines (one per engineer) ----------------------------------
    entries = await db.svc_time_entries.find(
        {**of, "case_id": case_id, "end_at": {"$ne": None}},
        {"_id": 0},
    ).to_list(500)
    by_eng: dict[str, dict] = {}
    for e in entries:
        # Only "on_site" is chargeable by default; travel and admin land
        # on the timesheet but not the invoice unless the operator marks
        # them chargeable explicitly via line edit.
        if (e.get("category") or "").lower() != "on_site":
            continue
        mins = int(e.get("duration_minutes") or 0)
        if mins <= 0:
            continue
        eid = e.get("engineer_id") or "unassigned"
        bucket = by_eng.setdefault(eid, {
            "engineer_id": eid,
            "engineer_name": e.get("engineer_name") or "Engineer",
            "minutes": 0,
            "time_entry_ids": [],
        })
        bucket["minutes"] += mins
        bucket["time_entry_ids"].append(e["id"])

    labour_lines = []
    for b in by_eng.values():
        hours = round(b["minutes"] / 60.0, 2)
        labour_lines.append({
            "kind": "labour",
            "qty": hours,
            "unit_amount": _LABOUR_DEFAULT_RATE,
            "description": f"Labour — {b['engineer_name']} ({hours}h)",
            "engineer_id": b["engineer_id"],
            "engineer_name": b["engineer_name"],
            "tax_code": "T1",
        })

    # --- Parts lines (allocated + consumed movements) ---------------------
    movements = await db.svc_part_movements.find(
        {**of, "case_id": case_id, "movement_type": {"$in": ["allocate", "consume"]}},
        {"_id": 0},
    ).to_list(500)
    by_sku: dict[str, dict] = {}
    for m in movements:
        sku = (m.get("part_sku") or "").upper()
        if not sku:
            continue
        bucket = by_sku.setdefault(sku, {"qty": 0, "movement_ids": []})
        # 'consume' decrements stock — count those; 'allocate' is the
        # reservation, only count if no consume row exists for the same
        # SKU (the engineer hasn't filed the movement yet).
        if m.get("movement_type") == "consume":
            bucket["qty"] += int(m.get("qty") or 0)
            bucket["movement_ids"].append(m["id"])

    # Fall back to the case's allocated_parts when no consume rows yet —
    # operators usually quote at sign-off, before the engineer has
    # backed-flushed van consumption.
    if not by_sku:
        for a in (case.get("allocated_parts") or []):
            sku = (a.get("part_sku") or "").upper()
            if not sku:
                continue
            by_sku.setdefault(sku, {"qty": 0, "movement_ids": []})
            by_sku[sku]["qty"] += int(a.get("qty") or 0)

    # Look up part costs in one round-trip.
    part_lookup: dict[str, dict] = {}
    if by_sku:
        cat = await db.svc_parts.find(
            {**of, "sku": {"$in": list(by_sku.keys())}}, {"_id": 0},
        ).to_list(len(by_sku))
        part_lookup = {p["sku"]: p for p in cat}

    parts_lines = []
    for sku, info in by_sku.items():
        if info["qty"] <= 0:
            continue
        part = part_lookup.get(sku, {})
        # Mark up cost by 30% as default sell price; operator can edit.
        unit_cost = float(part.get("cost") or 0)
        sell = round(unit_cost * 1.30, 2) if unit_cost > 0 else 0
        parts_lines.append({
            "kind": "part",
            "qty": info["qty"],
            "unit_amount": sell,
            "description": f"{sku} — {part.get('name') or 'Part'}",
            "part_sku": sku,
            "stock_code": part.get("sage_stock_code") or sku,
            "nominal_code": _PARTS_NOMINAL,
            "tax_code": "T1",
            "movement_id": ",".join(info["movement_ids"]),
        })

    proposed_lines = _normalise_lines(labour_lines + parts_lines)
    totals = _quote_totals(proposed_lines)

    # Upsert the draft quote, preserving any prior manual edits the
    # operator has made (we don't clobber an existing draft — we return
    # the suggestion alongside).
    existing = await db.svc_quotes.find_one({**of, "case_id": case_id, "status": {"$ne": "void"}}, {"_id": 0})
    return {
        "case_id": case_id,
        "proposed_lines": proposed_lines,
        "proposed_totals": totals,
        "existing_quote": existing,
        "labour_rate": _LABOUR_DEFAULT_RATE,
    }


# ─────────────────────────────────────────────────────────────────
# Upsert + approve + finalise
# ─────────────────────────────────────────────────────────────────

@router.put("/{case_id}/quote")
async def upsert_quote(case_id: str, data: dict, user=Depends(get_current_user)):
    """Create or update a draft quote.

    Body: {lines: [...], notes?, vat_rate?, discount_pct?}
    Approved quotes can't be edited — void it first.
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    existing = await db.svc_quotes.find_one({**of, "case_id": case_id, "status": {"$ne": "void"}})
    if existing and existing.get("status") in ("approved", "invoiced"):
        raise HTTPException(409, f"Cannot edit a {existing['status']} quote — void it first")
    lines = _normalise_lines((data or {}).get("lines") or [])
    vat_rate = float((data or {}).get("vat_rate") if (data or {}).get("vat_rate") is not None else 0.20)
    discount_pct = float((data or {}).get("discount_pct") or 0)
    totals = _quote_totals(lines, vat_rate=vat_rate, discount_pct=discount_pct)

    if existing:
        update = {
            "lines": lines,
            "notes": ((data or {}).get("notes") or "").strip(),
            "vat_rate": vat_rate,
            "discount_pct": discount_pct,
            **totals,
            "total": totals["gross"],
            "version": int(existing.get("version") or 1) + 1,
            "updated_at": _now(),
            "updated_by_id": user["id"],
            "updated_by_name": user.get("full_name") or user.get("email") or "",
        }
        await db.svc_quotes.update_one({"id": existing["id"]}, {"$set": update, "$push": {"history": {
            "version": update["version"], "lines": lines, "totals": totals, "at": _now(), "actor": user.get("email") or "",
        }}})
        return _strip(await db.svc_quotes.find_one({"id": existing["id"]}, {"_id": 0}))

    reference = await _next_quote_reference(of["organization_id"])
    quote = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "reference": reference,
        "status": "draft",
        "lines": lines,
        "notes": ((data or {}).get("notes") or "").strip(),
        "vat_rate": vat_rate,
        "discount_pct": discount_pct,
        **totals,
        "total": totals["gross"],
        "version": 1,
        "history": [{"version": 1, "lines": lines, "totals": totals, "at": _now(), "actor": user.get("email") or ""}],
        "created_by_id": user["id"],
        "created_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
        "updated_at": _now(),
        "approved_at": None,
        "invoiced_at": None,
    }
    await db.svc_quotes.insert_one(quote)
    quote.pop("_id", None)
    return quote


@router.post("/{case_id}/quote/approve")
async def approve_quote(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    quote = await db.svc_quotes.find_one({**of, "case_id": case_id, "status": "draft"}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "No draft quote to approve")
    await db.svc_quotes.update_one(
        {"id": quote["id"]},
        {"$set": {"status": "approved", "approved_at": _now(), "approved_by_id": user["id"],
                  "approved_by_name": user.get("full_name") or "", "updated_at": _now()}},
    )
    return _strip(await db.svc_quotes.find_one({"id": quote["id"]}, {"_id": 0}))


@router.post("/{case_id}/quote/void")
async def void_quote(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    quote = await db.svc_quotes.find_one({**of, "case_id": case_id, "status": {"$in": ["draft", "approved"]}}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "No active quote to void")
    if quote["status"] == "invoiced":
        raise HTTPException(409, "Cannot void an invoiced quote")
    await db.svc_quotes.update_one(
        {"id": quote["id"]},
        {"$set": {"status": "void", "voided_at": _now(), "updated_at": _now()}},
    )
    return {"ok": True, "quote_id": quote["id"]}


@router.post("/{case_id}/invoice/finalise")
async def finalise_invoice(case_id: str, user=Depends(get_current_user)):
    """Push the approved quote to svc_sage_invoice_outbox as `ready` and
    flip the quote to invoiced. Worker (Phase 8) drains the outbox."""
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    quote = await db.svc_quotes.find_one({**of, "case_id": case_id, "status": "approved"}, {"_id": 0})
    if not quote:
        raise HTTPException(409, "No approved quote — approve a quote before finalising")
    # Look up the org's Sage customer id from the CRM company record
    # (best-effort, v2-first via the shared resolver — Iter 220ea·26 G3).
    from utils.svc_crm_sync import resolve_sage_customer_id
    sage_customer_id = await resolve_sage_customer_id(
        of["organization_id"],
        name=case.get("customer_name") or "",
        email=case.get("customer_email") or "",
        company_id=case.get("company_id") or "",
    )
    await sage_invoice.enqueue_invoice_for_case(
        case, sage_customer_id=sage_customer_id, quote=quote, status="ready",
    )
    await db.svc_quotes.update_one(
        {"id": quote["id"]},
        {"$set": {"status": "invoiced", "invoiced_at": _now(), "updated_at": _now()}},
    )
    # Iter 216h152 — emit CRM "service_invoice" activity carrying the
    # net amount so the CRM company timeline and the "Service revenue
    # YTD" tile both pick it up. Best-effort.
    try:
        from utils.svc_crm_sync import emit_invoice_activity
        finalised_quote = await db.svc_quotes.find_one({"id": quote["id"]}, {"_id": 0})
        await emit_invoice_activity(case, finalised_quote or quote, user)
    except Exception as e:
        logger.warning("[svc→crm] emit_invoice_activity failed: %s", e)
    # Iter 216h155 — compliance audit. Invoice finalisation is the
    # money-commit step — the strongest audit signal in the SVC module.
    try:
        await audit_log(
            action="svc.invoice.finalise",
            user_id=user.get("id", ""),
            user_email=user.get("email", ""),
            resource_type="svc_invoice",
            resource_id=quote["id"],
            details=f"case={case.get('reference', '')} · "
                    f"net=£{quote.get('net') or quote.get('subtotal') or 0} · "
                    f"gross=£{quote.get('gross') or quote.get('total') or 0}",
        )
    except Exception as e:
        logger.warning("[audit] invoice.finalise failed: %s", e)
    # Echo the outbox row so the UI can confirm.
    outbox = await db.svc_sage_invoice_outbox.find_one({**of, "case_id": case_id}, {"_id": 0})
    return {"ok": True, "quote": _strip(await db.svc_quotes.find_one({"id": quote["id"]}, {"_id": 0})), "outbox": outbox}


@router.get("/{case_id}/invoice/preview")
async def preview_invoice(case_id: str, user=Depends(get_current_user)):
    """What the Sage payload will look like — pure read."""
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    quote = await db.svc_quotes.find_one({**of, "case_id": case_id, "status": {"$in": ["draft", "approved"]}}, {"_id": 0})
    payload = sage_invoice._to_sage_invoice(case, quote=quote)
    return {"case_id": case_id, "quote": _strip(quote), "payload": payload}


__all__ = ["router"]
