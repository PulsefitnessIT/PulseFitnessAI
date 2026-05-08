"""Master Admin — per-organisation billing ledger.

Bridges the gap between Stripe and "the customer paid us via BACS / cheque
/ wire transfer". Master admin can:

  • View every invoice + payment for an org (chronological ledger).
  • Generate a fresh invoice for the current period from active modules.
  • Record a manual payment (BACS / cheque / wire / other).
  • Activate or update the org's subscription manually — useful when
    money landed in our bank but never touched Stripe.
  • Download a stored invoice as a PDF (uses ReportLab — already in deps).

Bill-to-date math
-----------------
``balance = sum(invoices.total) - sum(payments.amount)`` — positive
means the org owes us, negative means credit. The endpoint exposes both
the running balance and the recent activity so the master-admin UI can
render a clean ledger.

Schema
------

`org_billing_invoices` — one row per generated invoice::

    {
        "id":              uuid,
        "organization_id": str,
        "brand":           "gymaxis" | "pulse",
        "number":          "INV-2026-04-0001",   # human-readable
        "currency":        "GBP",
        "billing_cycle":   "monthly" | "annual",
        "period_start":    iso,
        "period_end":      iso,
        "line_items": [
            {"plan_id": uuid, "module_id": str, "name": str,
             "sites": int, "discount_pct": float,
             "net_amount": int, "vat_amount": int, "total_amount": int}
        ],
        "subtotal":        int,    # sum of line_items.net_amount
        "vat_total":       int,    # sum of line_items.vat_amount
        "total":           int,    # sum of line_items.total_amount
        "status":          "draft" | "issued" | "paid" | "void",
        "due_at":          iso,
        "issued_at":       iso,
        "paid_at":         iso | null,
        "created_by":      user_id,
        "created_at":      iso
    }

`org_billing_payments` — one row per payment received::

    {
        "id":              uuid,
        "organization_id": str,
        "invoice_id":      uuid | null,    # null = "on account"
        "amount":          int,
        "currency":        str,
        "method":          "bacs" | "cheque" | "wire" | "stripe" | "other",
        "reference":       str,
        "paid_at":         iso,
        "notes":           str,
        "recorded_by":     user_id,
        "recorded_at":     iso
    }

`organizations.subscription` — added/updated by ``activate``::

    {
        "active_modules":   ["operations", "memberships", …],
        "billing_currency": "GBP",
        "billing_cycle":    "monthly" | "annual",
        "sites":            int,
        "next_renewal_at":  iso,
        "manual_billing":   bool,    # true → bypass Stripe entirely
        "status":           "active" | "past_due" | "cancelled" | "trial"
    }
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from utils.auth import get_current_user
from utils.database import db

from routes.master_admin_pricing import (
    SUPPORTED_CURRENCIES, MODULE_IDS, BUNDLE_ID, calculate_quote,
)


router = APIRouter()
logger = logging.getLogger(__name__)


CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$"}


# ── Helpers ─────────────────────────────────────────────────────────


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


async def _get_org(org_id: str) -> dict:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    return org


async def _next_invoice_number() -> str:
    """Sequential invoice number — `INV-YYYY-MM-####`."""
    now = _now()
    prefix = f"INV-{now.year:04d}-{now.month:02d}-"
    last = await db.org_billing_invoices.find_one(
        {"number": {"$regex": f"^{prefix}"}}, {"_id": 0, "number": 1}, sort=[("number", -1)]
    )
    seq = 1
    if last and last.get("number"):
        try:
            seq = int(last["number"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:04d}"


async def _ledger_balance(org_id: str, currency: str) -> dict[str, int]:
    """Return {invoiced, paid, balance} in minor units for a currency."""
    inv_pipeline = [
        {"$match": {"organization_id": org_id, "currency": currency, "status": {"$ne": "void"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    pay_pipeline = [
        {"$match": {"organization_id": org_id, "currency": currency}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    inv_agg = await db.org_billing_invoices.aggregate(inv_pipeline).to_list(length=1)
    pay_agg = await db.org_billing_payments.aggregate(pay_pipeline).to_list(length=1)
    invoiced = int(inv_agg[0]["total"]) if inv_agg else 0
    paid = int(pay_agg[0]["total"]) if pay_agg else 0
    return {"invoiced": invoiced, "paid": paid, "balance": invoiced - paid}


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/master-admin/orgs/{org_id}/billing")
async def get_org_billing(
    org_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return org subscription + ledger summary + recent invoices/payments."""
    _require_master(user)
    org = await _get_org(org_id)
    sub = org.get("subscription") or {}
    currency = (sub.get("billing_currency") or "GBP").upper()
    ledger = await _ledger_balance(org_id, currency)

    invoices = await db.org_billing_invoices.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(length=50)

    payments = await db.org_billing_payments.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("paid_at", -1).limit(50).to_list(length=50)

    return {
        "organization": {
            "id": org.get("id"),
            "name": org.get("name") or org.get("company_name"),
            "brand": _brand_for_org(org),
            "subscription": sub,
            "currency": currency,
        },
        "ledger": ledger,
        "invoices": invoices,
        "payments": payments,
        "supported_currencies": list(SUPPORTED_CURRENCIES),
        "available_modules": list(MODULE_IDS) + [BUNDLE_ID],
    }


@router.post("/master-admin/orgs/{org_id}/billing/activate")
async def activate_subscription(
    org_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Activate or update an org's subscription manually.

    Body::

        {
            "active_modules": ["operations", "memberships"],   # or ["bundle_all"]
            "billing_cycle":  "monthly",                       # or "annual"
            "billing_currency": "GBP",
            "sites":          3,
            "manual_billing": true,
            "status":         "active"
        }
    """
    _require_master(user)
    await _get_org(org_id)  # validate exists

    modules = payload.get("active_modules") or []
    if not isinstance(modules, list) or not modules:
        raise HTTPException(400, "active_modules must be a non-empty list")
    valid = set(MODULE_IDS) | {BUNDLE_ID}
    for m in modules:
        if m not in valid:
            raise HTTPException(400, f"unknown module: {m}")

    cycle = payload.get("billing_cycle", "monthly")
    if cycle not in ("monthly", "annual"):
        raise HTTPException(400, "billing_cycle must be monthly|annual")
    currency = (payload.get("billing_currency") or "GBP").upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(400, f"currency must be one of {SUPPORTED_CURRENCIES}")
    try:
        sites = max(1, int(payload.get("sites", 1)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "sites must be an integer") from exc

    status = payload.get("status", "active")
    if status not in ("active", "past_due", "cancelled", "trial"):
        raise HTTPException(400, "status must be active|past_due|cancelled|trial")

    period_days = 30 if cycle == "monthly" else 365
    next_renewal = _now() + timedelta(days=period_days)

    sub = {
        "active_modules": list(modules),
        "billing_cycle": cycle,
        "billing_currency": currency,
        "sites": sites,
        "manual_billing": bool(payload.get("manual_billing", True)),
        "status": status,
        "next_renewal_at": _iso(next_renewal),
        "activated_at": _iso(_now()),
        "activated_by": user.get("id"),
    }
    await db.organizations.update_one({"id": org_id}, {"$set": {"subscription": sub}})

    return {"subscription": sub}


@router.post("/master-admin/orgs/{org_id}/billing/invoice")
async def generate_invoice(
    org_id: str,
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Generate an invoice for the current billing period from the
    org's active modules. Body may override ``period_start`` /
    ``period_end`` / ``due_at`` for back-dating.
    """
    _require_master(user)
    org = await _get_org(org_id)
    sub = org.get("subscription") or {}
    if not sub.get("active_modules"):
        raise HTTPException(400, "Org has no active subscription — activate first")

    brand = _brand_for_org(org)
    cycle = sub.get("billing_cycle", "monthly")
    currency = (sub.get("billing_currency") or "GBP").upper()
    sites = int(sub.get("sites") or 1)

    period_days = 30 if cycle == "monthly" else 365
    now = _now()
    period_start = _parse_iso(payload.get("period_start")) or now
    period_end = _parse_iso(payload.get("period_end")) or (period_start + timedelta(days=period_days))
    due_at = _parse_iso(payload.get("due_at")) or (now + timedelta(days=14))

    # Look up plans for the org's brand once.
    plans = await db.pricing_plans.find(
        {"brand": brand, "module_id": {"$in": list(sub["active_modules"])}}, {"_id": 0}
    ).to_list(length=20)
    plans_by_module = {p["module_id"]: p for p in plans}
    missing = [m for m in sub["active_modules"] if m not in plans_by_module]
    if missing:
        raise HTTPException(400, f"Pricing not configured for: {missing}. Seed defaults or create plans.")

    line_items = []
    subtotal = 0
    vat_total = 0
    grand = 0
    for module_id in sub["active_modules"]:
        plan = plans_by_module[module_id]
        q = calculate_quote(plan, currency=currency, billing_cycle=cycle, sites=sites)
        line_items.append({
            "plan_id": plan["id"],
            "module_id": module_id,
            "name": plan.get("name") or module_id.title(),
            "sites": sites,
            "discount_pct": q["discount_pct"],
            "net_amount": q["net_amount"],
            "vat_amount": q["vat_amount"],
            "total_amount": q["total_amount"],
        })
        subtotal += q["net_amount"]
        vat_total += q["vat_amount"]
        grand += q["total_amount"]

    invoice = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "brand": brand,
        "number": await _next_invoice_number(),
        "currency": currency,
        "billing_cycle": cycle,
        "period_start": _iso(period_start),
        "period_end": _iso(period_end),
        "line_items": line_items,
        "subtotal": subtotal,
        "vat_total": vat_total,
        "total": grand,
        "status": payload.get("status", "issued"),
        "due_at": _iso(due_at),
        "issued_at": _iso(now),
        "paid_at": None,
        "created_by": user.get("id"),
        "created_at": _iso(now),
    }
    await db.org_billing_invoices.insert_one(dict(invoice))
    # Activation event — first invoice for the org. Idempotent per org.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            org_id, "first_invoice_generated",
            trigger_user_id=user.get("id"),
            payload={"invoice_id": invoice["id"], "total": invoice["total"]},
        )
    except Exception:
        pass
    saved = await db.org_billing_invoices.find_one({"id": invoice["id"]}, {"_id": 0})
    return {"invoice": saved}


# ── Auto-invoicing batch ────────────────────────────────────────────


@router.post("/master-admin/billing/run-renewals")
async def run_renewals(user: dict = Depends(get_current_user)) -> dict:
    """Find every active manual-billing org whose ``next_renewal_at`` has
    passed, auto-generate the next invoice, and roll the renewal date
    forward by one period. Designed to be safe to re-run — orgs that
    already have an invoice for the current period are skipped.

    The endpoint is idempotent and runs in O(active orgs); for now it's
    callable from the Master Admin UI as a "Run renewals now" button.
    Hook to a daily cron (e.g. APScheduler / k8s CronJob) when ready.
    """
    _require_master(user)
    cutoff = _iso(_now())
    cursor = db.organizations.find(
        {
            "subscription.status": "active",
            "subscription.manual_billing": True,
            "subscription.next_renewal_at": {"$lte": cutoff},
        },
        {"_id": 0},
    )
    orgs = await cursor.to_list(length=500)

    results = {"processed": 0, "invoices_created": 0, "skipped": 0, "errors": []}
    for org in orgs:
        try:
            outcome = await _renew_one_org(org, user.get("id"))
            results["processed"] += 1
            if outcome == "invoiced":
                results["invoices_created"] += 1
            else:
                results["skipped"] += 1
        except Exception as exc:  # pragma: no cover — surface in response
            logger.exception("renewal failed for org %s", org.get("id"))
            results["errors"].append({"org_id": org.get("id"), "error": str(exc)})
    return results


async def _renew_one_org(org: dict, actor_id: str | None) -> str:
    """Generate the next invoice for ``org`` and bump ``next_renewal_at``.

    Returns ``"invoiced"`` on success, ``"skipped"`` if an invoice for the
    current period already exists (e.g. operator generated it manually).
    """
    sub = org.get("subscription") or {}
    cycle = sub.get("billing_cycle", "monthly")
    currency = (sub.get("billing_currency") or "GBP").upper()
    sites = int(sub.get("sites") or 1)
    brand = _brand_for_org(org)
    period_days = 30 if cycle == "monthly" else 365
    now = _now()

    # Skip if there's already an issued invoice for this period — protects
    # against double-billing if an operator generated one manually that day.
    existing = await db.org_billing_invoices.find_one(
        {
            "organization_id": org["id"],
            "status": {"$in": ["issued", "paid"]},
            "period_start": {"$gte": _iso(now - timedelta(days=2))},
        },
        {"_id": 0, "id": 1},
    )
    if existing:
        # Even if we skip the invoice, advance the renewal date so we don't
        # re-attempt every batch run.
        await db.organizations.update_one(
            {"id": org["id"]},
            {"$set": {"subscription.next_renewal_at": _iso(now + timedelta(days=period_days))}},
        )
        return "skipped"

    plans = await db.pricing_plans.find(
        {"brand": brand, "module_id": {"$in": list(sub.get("active_modules") or [])}},
        {"_id": 0},
    ).to_list(length=20)
    plans_by_module = {p["module_id"]: p for p in plans}

    line_items, subtotal, vat_total, grand = [], 0, 0, 0
    for module_id in sub.get("active_modules") or []:
        plan = plans_by_module.get(module_id)
        if not plan:
            continue
        q = calculate_quote(plan, currency=currency, billing_cycle=cycle, sites=sites)
        line_items.append({
            "plan_id": plan["id"], "module_id": module_id,
            "name": plan.get("name") or module_id.title(), "sites": sites,
            "discount_pct": q["discount_pct"], "net_amount": q["net_amount"],
            "vat_amount": q["vat_amount"], "total_amount": q["total_amount"],
        })
        subtotal += q["net_amount"]
        vat_total += q["vat_amount"]
        grand += q["total_amount"]

    if not line_items:
        return "skipped"

    invoice = {
        "id": str(uuid.uuid4()),
        "organization_id": org["id"],
        "brand": brand,
        "number": await _next_invoice_number(),
        "currency": currency,
        "billing_cycle": cycle,
        "period_start": _iso(now),
        "period_end": _iso(now + timedelta(days=period_days)),
        "line_items": line_items,
        "subtotal": subtotal, "vat_total": vat_total, "total": grand,
        "status": "issued",
        "due_at": _iso(now + timedelta(days=14)),
        "issued_at": _iso(now),
        "paid_at": None,
        "created_by": actor_id,
        "created_at": _iso(now),
        "auto_generated": True,
    }
    await db.org_billing_invoices.insert_one(dict(invoice))
    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {"subscription.next_renewal_at": _iso(now + timedelta(days=period_days))}},
    )
    return "invoiced"


@router.post("/master-admin/orgs/{org_id}/billing/payment")
async def record_payment(
    org_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Record a manual payment. If `invoice_id` is supplied and this
    payment closes out the invoice's balance, the invoice is auto-
    marked ``paid``."""
    _require_master(user)
    await _get_org(org_id)  # validate org exists; raises 404 if not

    try:
        amount = int(payload.get("amount", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "amount must be int (minor units)") from exc
    if amount <= 0:
        raise HTTPException(400, "amount must be > 0")

    method = payload.get("method", "bacs")
    if method not in ("bacs", "cheque", "wire", "stripe", "other"):
        raise HTTPException(400, "method must be bacs|cheque|wire|stripe|other")

    currency = (payload.get("currency") or "GBP").upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(400, f"currency must be one of {SUPPORTED_CURRENCIES}")

    invoice_id = payload.get("invoice_id")
    paid_at = _parse_iso(payload.get("paid_at")) or _now()

    rec = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "invoice_id": invoice_id,
        "amount": amount,
        "currency": currency,
        "method": method,
        "reference": (payload.get("reference") or "")[:120],
        "notes": (payload.get("notes") or "")[:500],
        "paid_at": _iso(paid_at),
        "recorded_by": user.get("id"),
        "recorded_at": _iso(_now()),
    }
    await db.org_billing_payments.insert_one(dict(rec))

    # Auto-mark invoice paid if balanced.
    if invoice_id:
        inv = await db.org_billing_invoices.find_one({"id": invoice_id}, {"_id": 0})
        if inv:
            payments_for_invoice = await db.org_billing_payments.aggregate([
                {"$match": {"invoice_id": invoice_id}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]).to_list(length=1)
            paid_total = int(payments_for_invoice[0]["total"]) if payments_for_invoice else 0
            if paid_total >= int(inv.get("total", 0)) and inv.get("status") != "paid":
                await db.org_billing_invoices.update_one(
                    {"id": invoice_id},
                    {"$set": {"status": "paid", "paid_at": _iso(_now())}},
                )

    saved = await db.org_billing_payments.find_one({"id": rec["id"]}, {"_id": 0})
    return {"payment": saved}


@router.delete("/master-admin/orgs/{org_id}/billing/payment/{payment_id}")
async def void_payment(
    org_id: str,
    payment_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Void a manual payment (e.g. recorded by mistake). If the linked
    invoice was auto-marked paid, revert it to ``issued``."""
    _require_master(user)
    rec = await db.org_billing_payments.find_one(
        {"id": payment_id, "organization_id": org_id}, {"_id": 0}
    )
    if not rec:
        raise HTTPException(404, "Payment not found")
    await db.org_billing_payments.delete_one({"id": payment_id})
    if rec.get("invoice_id"):
        # Recompute and revert if needed.
        inv = await db.org_billing_invoices.find_one({"id": rec["invoice_id"]}, {"_id": 0})
        if inv and inv.get("status") == "paid":
            remaining = await db.org_billing_payments.aggregate([
                {"$match": {"invoice_id": rec["invoice_id"]}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]).to_list(length=1)
            paid_total = int(remaining[0]["total"]) if remaining else 0
            if paid_total < int(inv.get("total", 0)):
                await db.org_billing_invoices.update_one(
                    {"id": rec["invoice_id"]},
                    {"$set": {"status": "issued", "paid_at": None}},
                )
    return {"deleted": True}


@router.post("/master-admin/orgs/{org_id}/billing/invoice/{invoice_id}/void")
async def void_invoice(
    org_id: str,
    invoice_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_master(user)
    inv = await db.org_billing_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id}, {"_id": 0}
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    await db.org_billing_invoices.update_one(
        {"id": invoice_id}, {"$set": {"status": "void"}}
    )
    return {"voided": True}


@router.get("/master-admin/orgs/{org_id}/billing/invoice/{invoice_id}/pdf")
async def invoice_pdf(
    org_id: str,
    invoice_id: str,
    user: dict = Depends(get_current_user),
) -> Response:
    """Render an invoice as a downloadable PDF using ReportLab."""
    _require_master(user)
    inv = await db.org_billing_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id}, {"_id": 0}
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    org = await _get_org(org_id)
    pdf_bytes = _render_invoice_pdf(inv, org)
    # Auto-capture into the platform documents library — best-effort.
    try:
        from routes.master_admin_documents_lib import record_generated_document
        await record_generated_document(
            title=f"Invoice {inv.get('number','')}",
            category="invoice",
            body=pdf_bytes,
            content_type="application/pdf",
            filename=f"{inv.get('number','invoice')}.pdf",
            organization_id=org_id,
            linked_type="invoice", linked_id=inv["id"],
            tags=[inv.get("currency", ""), inv.get("billing_cycle", "")],
            actor_id=user.get("id"),
        )
    except Exception:
        pass
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv["number"]}.pdf"'},
    )


# ── PDF rendering ───────────────────────────────────────────────────


def _render_invoice_pdf(inv: dict, org: dict) -> bytes:
    """Return the bytes of a clean A4 invoice PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=40, bottomMargin=40, leftMargin=40, rightMargin=40)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=22, spaceAfter=4, textColor=colors.HexColor("#0A0C10"))
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#666"))
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#999"), spaceAfter=2)

    sym = CURRENCY_SYMBOLS.get(inv.get("currency", "GBP"), "")

    def money(minor: int) -> str:
        return f"{sym}{minor / 100:,.2f}"

    brand = inv.get("brand", "gymaxis")
    brand_name = "GymAxis AI" if brand == "gymaxis" else "Pulse Fitness"

    flow = []
    flow.append(Paragraph(f"<b>{brand_name}</b>", h1))
    flow.append(Paragraph("VAT-registered. UK.", small))
    flow.append(Spacer(1, 16))

    flow.append(Paragraph(f"<b>Invoice {inv['number']}</b>", styles["Heading2"]))
    flow.append(Paragraph(f"Issued {inv.get('issued_at','')[:10]} · Due {inv.get('due_at','')[:10]}", small))
    flow.append(Spacer(1, 12))

    bill_to = org.get("name") or org.get("company_name") or "Customer"
    flow.append(Paragraph("Bill to", label))
    flow.append(Paragraph(f"<b>{bill_to}</b>", styles["Normal"]))
    flow.append(Spacer(1, 18))

    rows = [["Module", "Sites", "Discount", "Net", "VAT", "Total"]]
    for li in inv.get("line_items", []):
        rows.append([
            li.get("name", li.get("module_id", "")),
            str(li.get("sites", 1)),
            f"{li.get('discount_pct', 0):.0f}%",
            money(li.get("net_amount", 0)),
            money(li.get("vat_amount", 0)),
            money(li.get("total_amount", 0)),
        ])
    rows.append(["", "", "Subtotal", money(inv.get("subtotal", 0)), money(inv.get("vat_total", 0)), money(inv.get("total", 0))])
    table = Table(rows, colWidths=[160, 50, 70, 80, 70, 80])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A0C10")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#0A0C10")),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#999")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
    ]))
    flow.append(table)
    flow.append(Spacer(1, 18))
    flow.append(Paragraph(
        f"Cycle: <b>{inv.get('billing_cycle','monthly').title()}</b> · "
        f"Period: {inv.get('period_start','')[:10]} → {inv.get('period_end','')[:10]} · "
        f"Status: <b>{inv.get('status','issued').title()}</b>",
        small,
    ))
    flow.append(Spacer(1, 24))
    flow.append(Paragraph(
        "Thank you. For BACS payments use our published account details and quote the invoice number above as the reference.",
        small,
    ))
    doc.build(flow)
    return buf.getvalue()


# ── Internal helpers ────────────────────────────────────────────────


def _parse_iso(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _brand_for_org(org: dict) -> str:
    """Map an org's account_type → brand bucket used by pricing."""
    at = (org.get("account_type") or "").lower()
    if at.startswith("pulse"):
        return "pulse"
    return "gymaxis"


# ── Indexes ─────────────────────────────────────────────────────────


async def ensure_org_billing_indexes() -> None:
    try:
        await db.org_billing_invoices.create_index([("organization_id", 1), ("created_at", -1)])
        await db.org_billing_invoices.create_index([("number", 1)], unique=True)
        await db.org_billing_invoices.create_index([("status", 1)])
        await db.org_billing_payments.create_index([("organization_id", 1), ("paid_at", -1)])
        await db.org_billing_payments.create_index([("invoice_id", 1)])
    except Exception:
        logger.exception("ensure_org_billing_indexes failed (non-fatal)")
