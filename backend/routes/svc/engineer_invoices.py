"""Iter 216h130 — Phase 2: Engineer Invoice Builder + PDF + Email.

Mirrors the engineer quote workflow but with invoice semantics:
  • due_date, payment_terms, payment_method, bank details
  • status: draft → sent → paid | overdue | void
  • created standalone OR from a completed job OR from an accepted quote
  • marks the source quote as `invoiced` when generated from it

Endpoints (all under /api/svc/engineer):
  POST  /invoices                            — create draft
  POST  /invoices/from-quote/{quote_id}      — derive from accepted quote
  GET   /invoices                            — list (status, customer_email, case_id)
  GET   /invoices/{id}                       — single
  GET   /invoices/{id}.pdf                   — branded PDF
  PATCH /invoices/{id}                       — edit (locks once paid/void)
  POST  /invoices/{id}/send                  — email branded PDF via Resend
  POST  /invoices/{id}/mark                  — set status (paid|sent|overdue|void)
  POST  /invoices/{id}/duplicate
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Invoices"],
    dependencies=[Depends(require_engineer_app_access)],
)

INVOICE_STATUSES = ("draft", "sent", "paid", "overdue", "void")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org_id}


def _new_invoice_number() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"EI-{today}-{uuid.uuid4().hex[:4].upper()}"


async def _engineer_vat_settings(user: dict) -> dict:
    """Iter 220l — fetch the engineer's VAT settings from the partner
    record. Defaults to `{vat_registered: True, vat_number: None}` so
    existing behaviour is preserved for unflagged partners.
    """
    partner = await db.partner_engineers.find_one(
        {"user_id": user["id"]},
        {"_id": 0, "vat_registered": 1, "vat_number": 1},
    )
    if not partner:
        return {"vat_registered": True, "vat_number": None}
    return {
        "vat_registered": partner.get("vat_registered", True),
        "vat_number": partner.get("vat_number"),
    }


def _compute_totals(lines: list[dict], vat_rate: float, discount_pct: float = 0) -> dict:
    subtotal = 0.0
    for ln in lines:
        qty = float(ln.get("quantity", 0) or 0)
        unit = float(ln.get("unit_price", 0) or 0)
        line_total = qty * unit
        ln["line_total"] = round(line_total, 2)
        subtotal += line_total
    discount_amount = round(subtotal * (discount_pct / 100), 2) if discount_pct else 0.0
    sub_after = round(subtotal - discount_amount, 2)
    vat_amount = round(sub_after * (vat_rate / 100), 2)
    total = round(sub_after + vat_amount, 2)
    return {
        "subtotal": round(subtotal, 2),
        "discount_pct": float(discount_pct or 0),
        "discount_amount": discount_amount,
        "vat_rate": float(vat_rate or 0),
        "vat_amount": vat_amount,
        "total": total,
    }


async def _engineer_profile(user: dict) -> dict:
    org_id = user.get("organization_id")
    eng = await db.svc_engineers.find_one(
        {"organization_id": org_id, "id": user["id"]}, {"_id": 0},
    )
    return eng or {
        "id": user["id"], "full_name": user.get("full_name") or user.get("email"),
        "email": user.get("email"), "mobile": user.get("phone"),
    }


# ─────────────────────────── Models ────────────────────────────


class InvoiceLine(BaseModel):
    kind: str = Field(default="labour")
    description: str
    quantity: float = 1
    unit_price: float = 0
    notes: str | None = None
    part_id: str | None = None


class InvoiceCreate(BaseModel):
    case_id: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    site_name: str | None = None
    site_address: str | None = None
    asset_name: str | None = None
    asset_serial: str | None = None
    description_of_work: str | None = None
    lines: list[InvoiceLine] = Field(default_factory=list)
    vat_rate: float = 20
    discount_pct: float = 0
    payment_terms_days: int = 14
    payment_method: str | None = None  # "BACS" | "Card" | "Cheque" | etc.
    payment_instructions: str | None = None
    bank_name: str | None = None
    bank_account_name: str | None = None
    bank_sort_code: str | None = None
    bank_account_number: str | None = None
    notes: str | None = None
    terms: str | None = None


class InvoiceUpdate(BaseModel):
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    site_name: str | None = None
    site_address: str | None = None
    asset_name: str | None = None
    asset_serial: str | None = None
    description_of_work: str | None = None
    lines: list[InvoiceLine] | None = None
    vat_rate: float | None = None
    discount_pct: float | None = None
    payment_terms_days: int | None = None
    due_date: str | None = None
    payment_method: str | None = None
    payment_instructions: str | None = None
    notes: str | None = None
    terms: str | None = None
    status: str | None = None


class InvoiceSend(BaseModel):
    to: str | None = None
    cc: list[str] = Field(default_factory=list)
    message: str | None = None


class StatusMark(BaseModel):
    status: str
    note: str | None = None


# ─────────────────────────── Helpers ───────────────────────────


async def _get_invoice_or_404(invoice_id: str, user: dict) -> dict:
    inv = await db.svc_engineer_invoices.find_one(
        {"id": invoice_id, **_of(user)}, {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    # Iter 220az · F-29 / F-33 — 404 (not 403) on cross-engineer access
    # so an attacker can't enumerate invoice IDs by status code.
    if inv.get("engineer_id") != user.get("id") and not user.get("is_master_admin"):
        raise HTTPException(404, "Invoice not found")
    return inv


def _build_invoice_payload(
    *, user: dict, engineer: dict,
    issue_date: datetime, payment_terms_days: int,
    body: dict, case_snapshot: dict | None = None,
    vat_settings: dict | None = None,
) -> dict:
    case = case_snapshot or {}
    due_date = (issue_date + timedelta(days=payment_terms_days)).date().isoformat()
    lines_dicts = [
        ln if isinstance(ln, dict) else ln.model_dump()
        for ln in (body.get("lines") or [])
    ]
    # Iter 220l — honour the engineer's VAT-registered flag. If they
    # ticked "Not VAT registered", force vat_rate=0 on the invoice so
    # they can't accidentally charge VAT they aren't entitled to.
    vat = vat_settings or {"vat_registered": True, "vat_number": None}
    requested_rate = body.get("vat_rate", 20) or 20
    effective_rate = 0 if not vat.get("vat_registered") else requested_rate
    totals = _compute_totals(lines_dicts, effective_rate,
                              body.get("discount_pct", 0) or 0)
    return {
        "id": str(uuid.uuid4()),
        "invoice_number": _new_invoice_number(),
        "organization_id": user.get("organization_id"),
        "engineer_id": user.get("id"),
        "engineer_name": engineer.get("full_name"),
        "engineer_email": engineer.get("email"),
        "engineer_mobile": engineer.get("mobile"),
        "case_id": body.get("case_id") or case.get("id"),
        "case_reference": case.get("reference"),
        "asset_id": case.get("asset_id"),
        "linked_quote_id": body.get("linked_quote_id"),
        "linked_quote_number": body.get("linked_quote_number"),
        "customer_name": body.get("customer_name") or case.get("customer_name") or "",
        "customer_email": body.get("customer_email") or case.get("customer_email") or "",
        "customer_phone": body.get("customer_phone") or case.get("customer_phone") or "",
        "site_name": body.get("site_name") or case.get("site_name") or "",
        "site_address": body.get("site_address") or "",
        "asset_name": body.get("asset_name") or case.get("asset_name") or "",
        "asset_serial": body.get("asset_serial") or case.get("asset_serial") or "",
        "description_of_work": body.get("description_of_work") or "",
        "lines": lines_dicts,
        **totals,
        # Iter 220l — VAT exemption snapshot (frozen at issue time so
        # later toggles don't retroactively rewrite history).
        "vat_exempt": not vat.get("vat_registered"),
        "vat_number": vat.get("vat_number"),
        "issue_date": issue_date.date().isoformat(),
        "payment_terms_days": payment_terms_days,
        "due_date": due_date,
        "payment_method": body.get("payment_method") or "BACS",
        "payment_instructions": body.get("payment_instructions") or "",
        "bank_name": body.get("bank_name") or "",
        "bank_account_name": body.get("bank_account_name") or "",
        "bank_sort_code": body.get("bank_sort_code") or "",
        "bank_account_number": body.get("bank_account_number") or "",
        "notes": body.get("notes") or "",
        "terms": body.get("terms") or (
            f"Payment due within {payment_terms_days} days. Late payment may "
            "incur interest under the Late Payment of Commercial Debts Act 1998."
        ),
        "status": "draft",
        "status_history": [{"status": "draft", "at": _now(), "by": user.get("email")}],
        "created_at": _now(), "updated_at": _now(),
        "sent_at": None, "paid_at": None,
    }


# ─────────────────────────── Endpoints ─────────────────────────


# Iter 220ct — Invoice prefill from a completed case.
# Pulls labour hours (svc_time_entries.duration_minutes / 60 × hourly
# rate), mileage (svc_mileage_entries × per-mile rate), and parts
# (svc_cases.allocated_parts) into a ready-to-edit invoice body so
# the engineer doesn't have to re-key anything at close-out.
@router.get("/jobs/{case_id}/invoice-prefill")
async def invoice_prefill_from_case(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of},
        {"_id": 0},
    )
    if not case:
        raise HTTPException(404, "Job not found")
    # Engineers only see their own jobs.
    if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != user["id"] \
            and not user.get("is_master_admin"):
        raise HTTPException(404, "Job not found")

    # Engineer pricing defaults — partner.rates set in Account Settings.
    partner = None
    try:
        from routes.partners import _get_partner_by_user  # noqa: WPS433
        partner = await _get_partner_by_user(user["id"])
    except Exception:  # noqa: BLE001
        partner = None
    rates = (partner or {}).get("rates") or {}
    hourly = float(rates.get("labour_rate_per_hour") or 0)
    mileage_rate = float(rates.get("mileage_rate") or 0)
    callout_fee = float(rates.get("callout_fee") or 0)

    # Labour — sum on_site (and admin if engineer wants to bill it).
    time_q = {**of, "case_id": case_id, "engineer_id": user["id"]}
    minutes_by_cat: dict[str, int] = {}
    async for e in db.svc_time_entries.find(time_q, {"_id": 0, "category": 1, "duration_minutes": 1}):
        cat = e.get("category") or "on_site"
        minutes_by_cat[cat] = minutes_by_cat.get(cat, 0) + int(e.get("duration_minutes") or 0)
    on_site_mins = minutes_by_cat.get("on_site", 0)
    on_site_hours = round(on_site_mins / 60.0, 2)

    # Mileage — sum miles from svc_mileage_entries (already keyed by case).
    total_miles = 0.0
    try:
        async for m in db.svc_mileage_entries.find(
            {**of, "case_id": case_id, "engineer_id": user["id"]},
            {"_id": 0, "miles": 1},
        ):
            total_miles += float(m.get("miles") or 0)
    except Exception:  # noqa: BLE001 — degrade gracefully if collection missing
        total_miles = 0.0

    # Parts — svc_cases.allocated_parts (filled when admin approves a
    # parts request and pushes it onto the case).
    parts: list[dict] = list(case.get("allocated_parts") or [])

    lines: list[dict] = []
    # Callout (if rate set and engineer attended on-site).
    if callout_fee > 0 and on_site_mins > 0:
        lines.append({
            "kind": "callout", "description": "Callout fee",
            "quantity": 1, "unit_price": callout_fee,
            "notes": None,
        })
    # Labour.
    if on_site_hours > 0:
        lines.append({
            "kind": "labour",
            "description": f"Labour — on-site ({on_site_hours} h)",
            "quantity": on_site_hours,
            "unit_price": hourly if hourly > 0 else 0,
            "notes": None,
        })
    # Travel / mileage.
    if total_miles > 0:
        lines.append({
            "kind": "travel",
            "description": f"Mileage — {round(total_miles, 1)} mi",
            "quantity": round(total_miles, 1),
            "unit_price": mileage_rate if mileage_rate > 0 else 0,
            "notes": None,
        })
    # Parts — one line per allocated part.
    for p in parts:
        qty = int(p.get("qty") or p.get("quantity") or 1)
        unit = float(p.get("unit_price") or p.get("list_price_gbp") or 0)
        desc = (p.get("name") or p.get("part_name")
                or p.get("sku") or p.get("part_sku") or "Part").strip()
        sku  = (p.get("sku") or p.get("part_sku") or "").strip()
        machine = (p.get("machine_name") or "").strip()
        notes_bits = []
        if sku:
            notes_bits.append(f"SKU {sku}")
        if machine:
            notes_bits.append(machine)
        lines.append({
            "kind": "part",
            "description": desc,
            "quantity": qty,
            "unit_price": unit,
            "notes": " · ".join(notes_bits) or None,
        })

    if not lines:
        # No time, mileage, or parts yet — give the engineer a single
        # default labour line so the form isn't empty.
        lines.append({
            "kind": "labour", "description": "Labour",
            "quantity": 1, "unit_price": hourly if hourly > 0 else 0,
            "notes": None,
        })

    return {
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "customer_name": case.get("customer_name") or "",
        "customer_email": case.get("customer_email") or "",
        "customer_phone": case.get("customer_phone") or "",
        "site_name": case.get("site_name") or "",
        "site_address": case.get("site_address") or "",
        "asset_name": case.get("asset_name") or "",
        "asset_serial": case.get("asset_serial") or "",
        "description_of_work": (
            case.get("resolution_notes")
            or case.get("description")
            or case.get("fault_summary")
            or ""
        ),
        "lines": lines,
        "totals_meta": {
            "on_site_minutes": on_site_mins,
            "on_site_hours":   on_site_hours,
            "miles":           round(total_miles, 1),
            "parts_count":     len(parts),
            "callout_fee":     callout_fee,
            "hourly_rate":     hourly,
            "mileage_rate":    mileage_rate,
        },
    }


@router.post("/invoices", status_code=201)
async def create_invoice(body: InvoiceCreate, user=Depends(get_current_user)):
    case = await db.svc_cases.find_one(
        {"id": body.case_id, **_of(user)},
        {"_id": 0, "id": 1, "reference": 1, "customer_name": 1, "customer_email": 1,
         "customer_phone": 1, "site_name": 1, "asset_name": 1, "asset_id": 1,
         "asset_serial": 1},
    ) if body.case_id else {}
    engineer = await _engineer_profile(user)
    vat_settings = await _engineer_vat_settings(user)
    issue_date = datetime.now(timezone.utc)
    inv = _build_invoice_payload(
        user=user, engineer=engineer,
        issue_date=issue_date,
        payment_terms_days=body.payment_terms_days or 14,
        body=body.model_dump(),
        case_snapshot=case or {},
        vat_settings=vat_settings,
    )
    await db.svc_engineer_invoices.insert_one({**inv})
    inv.pop("_id", None)
    # Iter 216h259 — stamp Lite CRM last_job_at
    try:
        from routes.svc.engineer_customers import touch_last_job
        await touch_last_job(
            user.get("organization_id"),
            email=inv.get("customer_email"),
            phone=inv.get("customer_phone"),
        )
    except Exception:
        pass
    return inv


@router.post("/invoices/from-quote/{quote_id}", status_code=201)
async def create_invoice_from_quote(quote_id: str, user=Depends(get_current_user)):
    """Generate an invoice from an *accepted* engineer quote.

    Marks the source quote as `invoiced` and links both rows.
    """
    quote = await db.svc_engineer_quotes.find_one(
        {"id": quote_id, **_of(user)}, {"_id": 0},
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    # Iter 220az · F-29 / F-33 — 404 (not 403) on cross-engineer access.
    if quote.get("engineer_id") != user.get("id") and not user.get("is_master_admin"):
        raise HTTPException(404, "Quote not found")
    if quote["status"] not in ("accepted", "sent"):
        raise HTTPException(409, "Only accepted (or sent) quotes can be invoiced")
    engineer = await _engineer_profile(user)
    vat_settings = await _engineer_vat_settings(user)
    issue_date = datetime.now(timezone.utc)
    body = {
        "case_id": quote.get("case_id"),
        "customer_name": quote.get("customer_name"),
        "customer_email": quote.get("customer_email"),
        "customer_phone": quote.get("customer_phone"),
        "site_name": quote.get("site_name"),
        "site_address": quote.get("site_address"),
        "asset_name": quote.get("asset_name"),
        "asset_serial": quote.get("asset_serial"),
        "description_of_work": quote.get("description_of_work"),
        "lines": [dict(ln) for ln in (quote.get("lines") or [])],
        "vat_rate": quote.get("vat_rate", 20),
        "discount_pct": quote.get("discount_pct", 0),
        "linked_quote_id": quote_id,
        "linked_quote_number": quote.get("quote_number"),
    }
    case_snapshot = {"id": quote.get("case_id"),
                      "reference": quote.get("case_reference"),
                      "asset_id": quote.get("asset_id")}
    inv = _build_invoice_payload(
        user=user, engineer=engineer,
        issue_date=issue_date, payment_terms_days=14,
        body=body, case_snapshot=case_snapshot,
        vat_settings=vat_settings,
    )
    await db.svc_engineer_invoices.insert_one({**inv})
    # Mark quote as invoiced
    await db.svc_engineer_quotes.update_one(
        {"id": quote_id},
        {"$set": {"status": "invoiced", "updated_at": _now(),
                  "linked_invoice_id": inv["id"],
                  "linked_invoice_number": inv["invoice_number"]},
         "$push": {"status_history": {"status": "invoiced", "at": _now(),
                                       "by": user.get("email"),
                                       "invoice_id": inv["id"]}}},
    )
    inv.pop("_id", None)
    return inv


@router.get("/invoices")
async def list_invoices(
    status: str | None = None,
    case_id: str | None = None,
    customer_email: str | None = None,
    limit: int = 100,
    user=Depends(get_current_user),
):
    q: dict[str, Any] = {**_of(user), "engineer_id": user.get("id")}
    if status:
        if status not in INVOICE_STATUSES + ("unpaid",):
            raise HTTPException(400, "invalid status")
        if status == "unpaid":
            q["status"] = {"$in": ["draft", "sent", "overdue"]}
        else:
            q["status"] = status
    if case_id:
        q["case_id"] = case_id
    if customer_email:
        q["customer_email"] = customer_email.lower()
    rows = await db.svc_engineer_invoices.find(
        q, {"_id": 0},
    ).sort("created_at", -1).to_list(max(1, min(500, limit)))
    return {"invoices": rows, "total": len(rows)}


@router.get("/invoices/{invoice_id}.pdf")
async def download_invoice_pdf(invoice_id: str, user=Depends(get_current_user)):
    inv = await _get_invoice_or_404(invoice_id, user)
    from utils.engineer_invoice_pdf import build_engineer_invoice_pdf
    from utils.pdf_footer import is_mod_for_case
    is_mod = await is_mod_for_case(db, inv.get("case_id"))
    pdf_bytes = build_engineer_invoice_pdf(inv, is_mod=is_mod)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv["invoice_number"]}.pdf"'},
    )


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user=Depends(get_current_user)):
    return await _get_invoice_or_404(invoice_id, user)


@router.patch("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, body: InvoiceUpdate, user=Depends(get_current_user)):
    inv = await _get_invoice_or_404(invoice_id, user)
    if inv["status"] in ("paid", "void"):
        raise HTTPException(409, f"Cannot edit invoice in {inv['status']} state")
    payload = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {"updated_at": _now()}
    if "lines" in payload:
        lines_data = payload["lines"] or []
        patch["lines"] = [
            ln.model_dump() if hasattr(ln, "model_dump") else dict(ln)
            for ln in lines_data
        ]
    if "status" in payload and payload["status"]:
        if payload["status"] not in INVOICE_STATUSES:
            raise HTTPException(400, "invalid status")
        patch["status"] = payload["status"]
    for k in ("customer_name", "customer_email", "customer_phone", "site_name",
              "site_address", "asset_name", "asset_serial", "description_of_work",
              "vat_rate", "discount_pct", "payment_terms_days", "due_date",
              "payment_method", "payment_instructions", "notes", "terms"):
        if k in payload:
            patch[k] = payload[k]
    merged = {**inv, **patch}
    if any(k in patch for k in ("lines", "vat_rate", "discount_pct")):
        # Iter 220l — respect the snapshot vat_exempt flag on the invoice
        # so a PATCH from the engineer can't suddenly re-add VAT to a
        # zero-rated invoice.
        effective_rate = 0 if merged.get("vat_exempt") else float(merged.get("vat_rate") or 20)
        totals = _compute_totals(
            merged.get("lines") or [],
            effective_rate,
            float(merged.get("discount_pct") or 0),
        )
        patch.update(totals)
        patch["lines"] = merged.get("lines") or []
    # If only payment_terms_days changed, re-derive due_date relative to issue
    if "payment_terms_days" in patch and inv.get("issue_date"):
        try:
            issue = datetime.fromisoformat(inv["issue_date"]).date()
            patch["due_date"] = (issue + timedelta(days=int(patch["payment_terms_days"]))).isoformat()
        except Exception:  # pragma: no cover
            pass
    update: dict[str, Any] = {"$set": patch}
    if patch.get("status"):
        update["$push"] = {"status_history": {
            "status": patch["status"], "at": _now(), "by": user.get("email"),
        }}
    await db.svc_engineer_invoices.update_one({"id": invoice_id}, update)
    return await _get_invoice_or_404(invoice_id, user)


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: str, body: InvoiceSend, user=Depends(get_current_user)):
    inv = await _get_invoice_or_404(invoice_id, user)
    to_addr = (body.to or inv.get("customer_email") or "").strip().lower()
    if not to_addr or "@" not in to_addr:
        raise HTTPException(400, "Recipient email required (customer_email empty)")
    # Auto-generate a Stripe Payment Link before sending (best-effort —
    # if Stripe isn't configured we just skip the CTA in the email).
    payment_url = inv.get("stripe_payment_url")
    if not payment_url and inv.get("status") != "paid":
        try:
            from routes.svc.engineer_invoice_payments import _ensure_payment_link
            link = await _ensure_payment_link(inv)
            payment_url = link["url"]
            # Refresh local copy with the new URL
            inv["stripe_payment_url"] = payment_url
            inv["public_shortcode"] = link["shortcode"]
        except HTTPException as exc:
            logger.info("[invoice_send] payment link skipped: %s", exc.detail)
    from utils.engineer_invoice_pdf import build_engineer_invoice_pdf
    from utils.pdf_footer import is_mod_for_case
    is_mod = await is_mod_for_case(db, inv.get("case_id"))
    pdf_bytes = build_engineer_invoice_pdf(inv, is_mod=is_mod)
    attachment = {
        "filename": f"{inv['invoice_number']}.pdf",
        "content": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    html = _email_html(inv, (body.message or "").strip())
    subject = f"Invoice {inv['invoice_number']} from {inv.get('engineer_name') or 'your engineer'}"
    ok = await send_email(
        to=to_addr, subject=subject, html=html,
        attachments=[attachment],
        organization_id=user.get("organization_id"),
    )
    if not ok:
        raise HTTPException(502, "Email send failed (check Resend configuration)")
    new_status = "sent" if inv["status"] == "draft" else inv["status"]
    update = {"$set": {"status": new_status, "sent_at": _now(),
                       "last_sent_to": to_addr, "updated_at": _now()},
              "$push": {
                  "status_history": {"status": new_status, "at": _now(),
                                      "by": user.get("email"), "to": to_addr},
                  "email_log": {"at": _now(), "to": to_addr, "subject": subject,
                                 "message": body.message, "cc": body.cc or []},
              }}
    await db.svc_engineer_invoices.update_one({"id": invoice_id}, update)
    return {"success": True, "sent_to": to_addr, "invoice_id": invoice_id}


@router.post("/invoices/{invoice_id}/mark")
async def mark_invoice(invoice_id: str, body: StatusMark, user=Depends(get_current_user)):
    await _get_invoice_or_404(invoice_id, user)
    if body.status not in INVOICE_STATUSES:
        raise HTTPException(400, "invalid status")
    set_payload: dict[str, Any] = {"status": body.status, "updated_at": _now()}
    if body.status == "paid":
        set_payload["paid_at"] = _now()
        set_payload["paid_recorded_by"] = user.get("email")
    await db.svc_engineer_invoices.update_one(
        {"id": invoice_id},
        {"$set": set_payload,
         "$push": {"status_history": {"status": body.status, "at": _now(),
                                       "by": user.get("email"), "note": body.note}}},
    )
    return await _get_invoice_or_404(invoice_id, user)


@router.post("/invoices/{invoice_id}/duplicate")
async def duplicate_invoice(invoice_id: str, user=Depends(get_current_user)):
    original = await _get_invoice_or_404(invoice_id, user)
    clone = {**original}
    clone.pop("_id", None)
    clone["id"] = str(uuid.uuid4())
    clone["invoice_number"] = _new_invoice_number()
    clone["status"] = "draft"
    clone["status_history"] = [{"status": "draft", "at": _now(),
                                  "by": user.get("email"),
                                  "note": f"Duplicated from {original['invoice_number']}"}]
    clone["sent_at"] = None
    clone["paid_at"] = None
    clone["created_at"] = _now()
    clone["updated_at"] = _now()
    clone["email_log"] = []
    today = datetime.now(timezone.utc)
    clone["issue_date"] = today.date().isoformat()
    clone["due_date"] = (today + timedelta(days=clone.get("payment_terms_days") or 14)).date().isoformat()
    await db.svc_engineer_invoices.insert_one({**clone})
    clone.pop("_id", None)
    return clone


# ─────────────────────────── Email body ───────────────────────────


def _email_html(invoice: dict, custom_message: str = "") -> str:
    primary = "#1d4ed8"
    accent = "#6366f1"
    customer = invoice.get("customer_name") or "there"
    engineer = invoice.get("engineer_name") or "Your engineer"
    ino = invoice.get("invoice_number")
    total = invoice.get("total") or 0
    due_date = invoice.get("due_date") or ""
    description = invoice.get("description_of_work") or ""
    pay_url = invoice.get("stripe_payment_url")
    custom_block = ""
    if custom_message:
        safe = (
            custom_message.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\n", "<br/>")
        )
        custom_block = (
            f'<div style="background:#f8fafc;border-left:4px solid {primary};'
            f'padding:12px 16px;margin:20px 0;font-size:14px;line-height:1.6;'
            f'color:#1e293b;">{safe}</div>'
        )
    pay_block = ""
    if pay_url:
        pay_block = (
            f'<div style="text-align:center;margin:24px 0;">'
            f'<a href="{pay_url}" '
            f'style="display:inline-block;padding:14px 28px;background:linear-gradient(135deg,{primary} 0%,{accent} 100%);'
            f'color:white;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;'
            f'box-shadow:0 6px 14px rgba(99,102,241,0.35);">'
            f'Pay £{total:,.2f} now by card →</a>'
            f'<p style="margin:10px 0 0;font-size:11px;color:#94a3b8;">'
            f'Secured by Stripe. Card payment marks this invoice paid automatically.</p></div>'
        )
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:600px;margin:0 auto;padding:24px;">
      <div style="background:linear-gradient(135deg,{primary} 0%,{accent} 100%);
                  padding:24px;border-radius:12px;color:white;margin-bottom:24px;">
        <p style="margin:0;font-size:12px;letter-spacing:.2em;text-transform:uppercase;opacity:.85;">GymAxis · Invoice</p>
        <h1 style="margin:6px 0 0;font-size:24px;font-weight:700;">{ino}</h1>
      </div>
      <p style="font-size:16px;line-height:1.6;">Hi {customer},</p>
      <p style="font-size:14px;line-height:1.6;color:#334155;">
        Please find attached invoice <strong>{ino}</strong> for the work below.
      </p>
      {custom_block}
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:18px 0;">
        <p style="margin:0;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.08em;">Work</p>
        <p style="margin:6px 0 0;font-size:14px;color:#0f172a;line-height:1.5;">{description or '—'}</p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:14px 0;">
        <table style="width:100%;font-size:13px;color:#334155;">
          <tr><td>{"Total due" if invoice.get('vat_exempt') else "Total due (incl. VAT)"}</td><td style="text-align:right;font-weight:700;color:{primary};">£{total:,.2f}</td></tr>
          <tr><td>Due by</td><td style="text-align:right;">{due_date}</td></tr>
        </table>
      </div>
      {pay_block}
      <p style="font-size:13px;line-height:1.6;color:#64748b;">
        Prefer BACS? Payment instructions are on the attached PDF.
      </p>
      <p style="font-size:14px;margin-top:24px;">Thanks,<br/><strong>{engineer}</strong></p>
      <p style="font-size:11px;color:#94a3b8;margin-top:30px;">
        Powered by GymAxis · Field Service for Fitness Equipment
      </p>
    </div>
    """


__all__ = ["router"]
