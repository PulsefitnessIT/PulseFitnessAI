"""CRM · Staged invoicing for CPQ v2 quotes (Equipment Sales Phase 2).

Extends the EXISTING quote process (``crm2_quotes``) — no new module — so a
complex equipment deal can take a **deposit**, one or more **interim**
payments and a **final balance**, with a live **running balance** and
**credit notes**. Actual invoice / credit-note records live in
``crm2_invoices`` (natural extension of the crm2_* domain).

Data:
  • quote.invoice_schedule = {"stages": [ {stage} ], "updated_at": iso}
      stage = {id, label, kind: deposit|interim|final,
               basis: percent|amount, percent, amount,
               due_date, status: pending|invoiced|part_paid|paid|credited,
               invoice_id, invoice_number, invoiced_at,
               paid_amount, paid_at, credited_amount, credit_note_ids[]}
  • crm2_invoices doc = {id, organization_id, quote_id, quote_number,
      company_id/name, contact_id/name, stage_id, doc_type: invoice|credit_note,
      number, amount, currency, status, due_date, issued_at,
      paid_amount, paid_at, reason, parent_invoice_id, created_by, created_at}
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user

router = APIRouter(prefix="/crm/v2/quotes", tags=["CRM Quote Invoicing"])

INVOICES = "crm2_invoices"
QUOTES = "crm2_quotes"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        await log_audit(user, "quote_invoice", quote_id, action, meta or {})
    except Exception:
        pass


async def _get_quote(quote_id: str, user: dict) -> dict:
    quote = await db[QUOTES].find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "Quote not found")
    return quote


def _stage_amount(stage: dict, quote_total: float) -> float:
    """Live amount for a stage. Percent stages track the current quote total."""
    if (stage.get("basis") or "percent") == "percent":
        return round(quote_total * float(stage.get("percent", 0) or 0) / 100, 2)
    return round(float(stage.get("amount", 0) or 0), 2)


def _round(v: float) -> float:
    return round(float(v or 0), 2)


async def _build_view(quote: dict, user: dict) -> dict:
    """Return the schedule (with live amounts) + invoices + running balance."""
    total = _round(quote.get("total", 0))
    currency = quote.get("currency", "GBP")
    sched = (quote.get("invoice_schedule") or {}).get("stages", []) or []

    invoices = await db[INVOICES].find(
        {"quote_id": quote["id"], **_of(user)}, {"_id": 0},
    ).sort("created_at", 1).to_list(200)

    stages_out = []
    scheduled = 0.0
    for st in sched:
        amt = _stage_amount(st, total)
        scheduled += amt
        stages_out.append({
            **st,
            "amount": amt,
            "paid_amount": _round(st.get("paid_amount", 0)),
            "credited_amount": _round(st.get("credited_amount", 0)),
            "outstanding": _round(amt - _round(st.get("paid_amount", 0)) - _round(st.get("credited_amount", 0))),
        })

    invoiced_gross = _round(sum(i["amount"] for i in invoices if i.get("doc_type") == "invoice"))
    credited = _round(sum(i["amount"] for i in invoices if i.get("doc_type") == "credit_note"))
    paid = _round(sum(_round(i.get("paid_amount", 0)) for i in invoices if i.get("doc_type") == "invoice"))
    invoiced_net = _round(invoiced_gross - credited)
    outstanding = _round(invoiced_net - paid)          # issued but not yet paid
    balance = _round(total - paid - credited)          # what the customer still owes overall
    remaining_to_invoice = _round(total - invoiced_gross)

    return {
        "quote_id": quote["id"],
        "quote_number": quote.get("quote_number", ""),
        "currency": currency,
        "stages": stages_out,
        "invoices": invoices,
        "summary": {
            "total": total,
            "scheduled": _round(scheduled),
            "unscheduled": _round(total - scheduled),
            "invoiced": invoiced_net,
            "invoiced_gross": invoiced_gross,
            "credited": credited,
            "paid": paid,
            "outstanding": outstanding,
            "remaining_to_invoice": remaining_to_invoice,
            "balance": balance,
            "fully_invoiced": remaining_to_invoice <= 0.01,
            "fully_paid": balance <= 0.01 and invoiced_gross > 0,
        },
    }


# ── Read ───────────────────────────────────────────────────────────


@router.get("/{quote_id}/invoicing")
async def get_invoicing(quote_id: str, user=Depends(get_crm_user)):
    quote = await _get_quote(quote_id, user)
    return await _build_view(quote, user)


# ── Schedule ───────────────────────────────────────────────────────


def _normalize_stage(raw: dict, existing: dict | None = None) -> dict:
    kind = (raw.get("kind") or "interim").lower()
    if kind not in ("deposit", "interim", "final"):
        kind = "interim"
    basis = (raw.get("basis") or "percent").lower()
    if basis not in ("percent", "amount"):
        basis = "percent"
    percent = max(0.0, min(100.0, _round(raw.get("percent", 0))))
    amount = max(0.0, _round(raw.get("amount", 0)))
    stage = {
        "id": (existing or {}).get("id") or raw.get("id") or _id(),
        "label": (raw.get("label") or {"deposit": "Deposit", "interim": "Interim payment", "final": "Final balance"}[kind]).strip(),
        "kind": kind,
        "basis": basis,
        "percent": percent,
        "amount": amount,
        "due_date": raw.get("due_date") or "",
        # Preserve lifecycle state if the stage already existed.
        "status": (existing or {}).get("status", "pending"),
        "invoice_id": (existing or {}).get("invoice_id"),
        "invoice_number": (existing or {}).get("invoice_number"),
        "invoiced_at": (existing or {}).get("invoiced_at"),
        "paid_amount": _round((existing or {}).get("paid_amount", 0)),
        "paid_at": (existing or {}).get("paid_at"),
        "credited_amount": _round((existing or {}).get("credited_amount", 0)),
        "credit_note_ids": (existing or {}).get("credit_note_ids", []) or [],
    }
    return stage


@router.put("/{quote_id}/schedule")
async def set_schedule(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Replace the invoice schedule. Stages that already exist (matched by id)
    keep their invoiced/paid lifecycle state; new stages start pending."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can edit the invoice schedule")
    quote = await _get_quote(quote_id, user)
    existing_by_id = {s.get("id"): s for s in (quote.get("invoice_schedule") or {}).get("stages", [])}
    incoming = data.get("stages", []) or []
    stages = [_normalize_stage(s, existing_by_id.get(s.get("id"))) for s in incoming]

    # Guard: don't let a re-schedule drop a stage that's already been invoiced.
    incoming_ids = {s["id"] for s in stages}
    for sid, st in existing_by_id.items():
        if st.get("status") in ("invoiced", "part_paid", "paid", "credited") and sid not in incoming_ids:
            raise HTTPException(400, f"Cannot remove stage '{st.get('label')}' — it has already been invoiced.")

    # Guard: the schedule cannot bill more than the deal is worth.
    total = _round(quote.get("total", 0))
    scheduled = _round(sum(_stage_amount(s, total) for s in stages))
    if scheduled > total + 0.01:
        raise HTTPException(422, f"Scheduled amount ({scheduled}) exceeds the deal total ({total}). Reduce the stages so they total {total} or less.")

    await db[QUOTES].update_one(
        {"id": quote_id, **_of(user)},
        {"$set": {"invoice_schedule": {"stages": stages, "updated_at": _now()}, "updated_at": _now()}},
    )
    await _audit(user, quote_id, "schedule_set", {"stage_count": len(stages)})
    quote["invoice_schedule"] = {"stages": stages}
    return await _build_view(quote, user)


@router.post("/{quote_id}/schedule/auto")
async def auto_schedule(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Convenience: generate a deposit / interim / final split from a preset.
    Body: {deposit_percent?, interim_percent?, final_percent?} (default 25/0/75)."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can edit the invoice schedule")
    quote = await _get_quote(quote_id, user)
    dep = _round(data.get("deposit_percent", 25))
    interim = _round(data.get("interim_percent", 0))
    final = _round(data.get("final_percent", 100 - dep - interim))
    if _round(dep + interim + final) != 100.0:
        raise HTTPException(422, "Deposit + interim + final percentages must total 100")
    stages = []
    if dep > 0:
        stages.append(_normalize_stage({"kind": "deposit", "basis": "percent", "percent": dep}))
    if interim > 0:
        stages.append(_normalize_stage({"kind": "interim", "basis": "percent", "percent": interim}))
    if final > 0:
        stages.append(_normalize_stage({"kind": "final", "basis": "percent", "percent": final}))
    await db[QUOTES].update_one(
        {"id": quote_id, **_of(user)},
        {"$set": {"invoice_schedule": {"stages": stages, "updated_at": _now()}, "updated_at": _now()}},
    )
    await _audit(user, quote_id, "schedule_auto", {"deposit": dep, "interim": interim, "final": final})
    quote["invoice_schedule"] = {"stages": stages}
    return await _build_view(quote, user)


# ── Invoice / pay / credit ─────────────────────────────────────────


def _find_stage(quote: dict, stage_id: str) -> tuple[list, int]:
    stages = (quote.get("invoice_schedule") or {}).get("stages", []) or []
    for idx, st in enumerate(stages):
        if st.get("id") == stage_id:
            return stages, idx
    raise HTTPException(404, "Schedule stage not found")


async def _save_stages(quote_id: str, user: dict, stages: list) -> None:
    await db[QUOTES].update_one(
        {"id": quote_id, **_of(user)},
        {"$set": {"invoice_schedule.stages": stages, "invoice_schedule.updated_at": _now(), "updated_at": _now()}},
    )


@router.post("/{quote_id}/stages/{stage_id}/invoice")
async def invoice_stage(quote_id: str, stage_id: str, data: dict = None, user=Depends(get_crm_user)):
    """Issue an invoice for a schedule stage → creates a crm2_invoices doc."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can raise invoices")
    data = data or {}
    quote = await _get_quote(quote_id, user)
    stages, idx = _find_stage(quote, stage_id)
    stage = stages[idx]
    if stage.get("status") in ("invoiced", "part_paid", "paid", "credited"):
        raise HTTPException(400, "This stage has already been invoiced")
    amount = _stage_amount(stage, _round(quote.get("total", 0)))
    if amount <= 0:
        raise HTTPException(400, "Stage amount must be greater than zero to invoice")

    # Guard: never invoice beyond the deal total.
    total = _round(quote.get("total", 0))
    already_invoiced = _round(sum(
        i.get("amount", 0) for i in await db[INVOICES].find(
            {"quote_id": quote_id, "doc_type": "invoice", **_of(user)}, {"_id": 0, "amount": 1},
        ).to_list(500)
    ))
    if already_invoiced + amount > total + 0.01:
        raise HTTPException(400, f"Invoicing this stage ({amount}) would exceed the deal total ({total}); already invoiced {already_invoiced}.")

    inv_id = _id()
    number = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{inv_id[:4].upper()}"
    due_date = data.get("due_date") or stage.get("due_date") or ""
    invoice = {
        "id": inv_id,
        "organization_id": user.get("organization_id"),
        "quote_id": quote_id,
        "quote_number": quote.get("quote_number", ""),
        "company_id": quote.get("company_id"),
        "company_name": quote.get("company_name", ""),
        "contact_id": quote.get("contact_id"),
        "contact_name": quote.get("contact_name", ""),
        "stage_id": stage_id,
        "stage_label": stage.get("label"),
        "doc_type": "invoice",
        "number": number,
        "amount": amount,
        "currency": quote.get("currency", "GBP"),
        "status": "issued",
        "due_date": due_date,
        "due_at": (due_date + "T00:00:00+00:00") if due_date else None,
        "issued_at": _now(),
        "paid_amount": 0.0,
        "paid_at": None,
        "created_by": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[INVOICES].insert_one(dict(invoice))
    stage.update({
        "status": "invoiced",
        "invoice_id": inv_id,
        "invoice_number": number,
        "invoiced_at": _now(),
    })
    stages[idx] = stage
    await _save_stages(quote_id, user, stages)
    await _audit(user, quote_id, "stage_invoiced", {"stage_id": stage_id, "amount": amount, "number": number})
    quote["invoice_schedule"]["stages"] = stages
    invoice.pop("_id", None)
    return {"invoice": invoice, **(await _build_view(quote, user))}


@router.post("/{quote_id}/stages/{stage_id}/pay")
async def pay_stage(quote_id: str, stage_id: str, data: dict = None, user=Depends(get_crm_user)):
    """Record a payment against an invoiced stage. Body: {amount?} (defaults to
    the full remaining balance of the stage)."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can record payments")
    data = data or {}
    quote = await _get_quote(quote_id, user)
    stages, idx = _find_stage(quote, stage_id)
    stage = stages[idx]
    if not stage.get("invoice_id"):
        raise HTTPException(400, "Raise the invoice before recording a payment")
    amount = _stage_amount(stage, _round(quote.get("total", 0)))
    already = _round(stage.get("paid_amount", 0))
    credited = _round(stage.get("credited_amount", 0))
    remaining = _round(amount - already - credited)
    pay = _round(data.get("amount", remaining))
    if pay <= 0:
        raise HTTPException(422, "Payment amount must be greater than zero")
    if pay > remaining + 0.01:
        raise HTTPException(422, f"Payment {pay} exceeds the {remaining} outstanding on this stage")
    new_paid = _round(already + pay)
    fully = new_paid + credited >= amount - 0.01
    stage["paid_amount"] = new_paid
    stage["paid_at"] = _now() if fully else stage.get("paid_at")
    stage["status"] = "paid" if fully else "part_paid"
    stages[idx] = stage
    await _save_stages(quote_id, user, stages)
    await db[INVOICES].update_one(
        {"id": stage["invoice_id"], **_of(user)},
        {"$set": {"paid_amount": new_paid, "status": "paid" if fully else "part_paid",
                  "paid_at": stage["paid_at"], "updated_at": _now()}},
    )
    await _audit(user, quote_id, "stage_paid", {"stage_id": stage_id, "amount": pay, "fully": fully})
    quote["invoice_schedule"]["stages"] = stages
    return await _build_view(quote, user)


@router.post("/{quote_id}/stages/{stage_id}/credit-note")
async def credit_note_stage(quote_id: str, stage_id: str, data: dict, user=Depends(get_crm_user)):
    """Raise a credit note against an invoiced stage. Body: {amount, reason}.
    Reduces the amount the customer owes for that stage."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can raise credit notes")
    quote = await _get_quote(quote_id, user)
    stages, idx = _find_stage(quote, stage_id)
    stage = stages[idx]
    if not stage.get("invoice_id"):
        raise HTTPException(400, "You can only credit a stage that has been invoiced")
    amount = _stage_amount(stage, _round(quote.get("total", 0)))
    credited = _round(stage.get("credited_amount", 0))
    max_credit = _round(amount - credited)
    cn_amount = _round(data.get("amount", max_credit))
    if cn_amount <= 0:
        raise HTTPException(422, "Credit note amount must be greater than zero")
    if cn_amount > max_credit + 0.01:
        raise HTTPException(422, f"Credit note {cn_amount} exceeds the {max_credit} still invoiced on this stage")
    reason = (data.get("reason") or "").strip()

    cn_id = _id()
    number = f"CN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{cn_id[:4].upper()}"
    cn = {
        "id": cn_id,
        "organization_id": user.get("organization_id"),
        "quote_id": quote_id,
        "quote_number": quote.get("quote_number", ""),
        "company_id": quote.get("company_id"),
        "company_name": quote.get("company_name", ""),
        "contact_id": quote.get("contact_id"),
        "contact_name": quote.get("contact_name", ""),
        "stage_id": stage_id,
        "stage_label": stage.get("label"),
        "doc_type": "credit_note",
        "number": number,
        "amount": cn_amount,
        "currency": quote.get("currency", "GBP"),
        "status": "issued",
        "reason": reason,
        "parent_invoice_id": stage.get("invoice_id"),
        "parent_invoice_number": stage.get("invoice_number"),
        "issued_at": _now(),
        "created_by": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[INVOICES].insert_one(dict(cn))
    new_credited = _round(credited + cn_amount)
    stage["credited_amount"] = new_credited
    stage["credit_note_ids"] = (stage.get("credit_note_ids") or []) + [cn_id]
    # If everything is now credited (and/or paid), mark the stage credited/paid.
    paid = _round(stage.get("paid_amount", 0))
    if new_credited >= amount - 0.01:
        stage["status"] = "credited"
    elif paid + new_credited >= amount - 0.01:
        stage["status"] = "paid"
    stages[idx] = stage
    await _save_stages(quote_id, user, stages)
    await _audit(user, quote_id, "stage_credited", {"stage_id": stage_id, "amount": cn_amount, "number": number})
    quote["invoice_schedule"]["stages"] = stages
    cn.pop("_id", None)
    return {"credit_note": cn, **(await _build_view(quote, user))}
