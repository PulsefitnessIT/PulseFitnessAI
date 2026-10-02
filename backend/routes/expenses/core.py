"""Expenses — capture, workflow, receipt OCR & serving (iter 278)."""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db, get_object

from .common import (
    router, org_of, can_review, get_org, ensure_seeded, approval_mode,
    default_country_rule, now_iso, audit, upload_receipt, ocr_receipt,
    receipt_warnings, find_duplicate, scope_filter,
    DRAFT, SUBMITTED, NEEDS_DETAILS, APPROVED, REJECTED, REIMBURSED,
    CANCELLED, EXPORTED, LOCKED_STATUSES,
)


async def _next_reference(org_id: str) -> str:
    n = await db.expenses.count_documents({"organization_id": org_id})
    return f"EXP-{n + 1:05d}"


# ── Receipt OCR (upload → scan → return editable draft, never saved) ─
@router.post("/ocr")
async def scan_receipt(file: UploadFile = File(...), user=Depends(get_current_user)):
    org_id = org_of(user)
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 12MB)")
    ctype = file.content_type or "image/jpeg"
    path = await upload_receipt(data, ctype, org_id, file.filename or "receipt.jpg")

    extracted: dict = {}
    if ctype.startswith("image/"):
        extracted = await ocr_receipt(base64.b64encode(data).decode("ascii"))

    dup = None
    if extracted.get("total_amount") and extracted.get("date"):
        dup = await find_duplicate(org_id, user.get("id"),
                                   extracted.get("merchant_name"),
                                   extracted.get("total_amount"), extracted.get("date"))
    return {
        "receipt_path": path,
        "is_pdf": ctype == "application/pdf",
        "extracted": extracted,
        "duplicate": bool(dup),
        "warnings": receipt_warnings(extracted, bool(dup)),
    }


# ── Create / edit ────────────────────────────────────────────────────
class MileageDetail(BaseModel):
    start_location: Optional[str] = ""
    end_location: Optional[str] = ""
    return_journey: bool = False
    distance: float = 0.0
    unit: str = "mi"
    vehicle_type: str = "personal_car"
    vehicle_id: Optional[str] = ""
    vehicle_reg: Optional[str] = ""
    rate: float = 0.0
    calculated_amount: float = 0.0
    business_reason: Optional[str] = ""


class ExpenseBody(BaseModel):
    expense_type: str = "manual"  # receipt|manual|mileage|out_of_pocket
    country_code: Optional[str] = None
    currency: Optional[str] = None
    category_id: Optional[str] = ""
    category_name: Optional[str] = ""
    merchant: Optional[str] = ""
    merchant_country: Optional[str] = ""
    transaction_date: Optional[str] = ""
    gross_amount: float = 0.0
    tax_amount: float = 0.0
    tax_rate: float = 0.0
    payment_method: Optional[str] = ""
    receipt_number: Optional[str] = ""
    receipt_paths: list[str] = []
    description: Optional[str] = ""
    business_purpose: Optional[str] = ""
    job_id: Optional[str] = ""
    job_reference: Optional[str] = ""
    customer_id: Optional[str] = ""
    customer_name: Optional[str] = ""
    site_id: Optional[str] = ""
    site_name: Optional[str] = ""
    vehicle_id: Optional[str] = ""
    department: Optional[str] = ""
    billable_to_customer: bool = False
    internal_cost: bool = False
    mileage: Optional[MileageDetail] = None
    ocr_confidence: Optional[float] = None
    submit: bool = False  # submit immediately vs save draft


async def _resolve_rule(org_id: str, country_code: Optional[str]) -> dict:
    if country_code:
        r = await db.expense_country_rules.find_one(
            {"organization_id": org_id, "country_code": country_code.upper()}, {"_id": 0})
        if r:
            return r
    return await default_country_rule(org_id)


def _net_from_gross(gross: float, tax: float) -> float:
    return round(max(gross - (tax or 0.0), 0.0), 2)


@router.post("")
async def create_expense(body: ExpenseBody, user=Depends(get_current_user)):
    org_id = org_of(user)
    org = await get_org(org_id)
    await ensure_seeded(org_id, org)
    if body.expense_type not in {"receipt", "manual", "mileage", "out_of_pocket"}:
        raise HTTPException(400, "Invalid expense type")

    rule = await _resolve_rule(org_id, body.country_code)
    currency = body.currency or (rule.get("currency") if rule else None) or org.get("currency") or "GBP"

    gross = round(body.gross_amount or 0.0, 2)
    mileage = body.mileage.model_dump() if body.mileage else None
    if body.expense_type == "mileage" and mileage:
        # Server authoritative: never trust a client-supplied calculated_amount;
        # always recompute from distance × rate (defeats amount tampering).
        mileage["calculated_amount"] = round((mileage.get("distance") or 0.0) * (mileage.get("rate") or 0.0), 2)
        gross = mileage["calculated_amount"]

    dup = await find_duplicate(org_id, user.get("id"), body.merchant, gross, body.transaction_date)

    doc = {
        "id": str(uuid.uuid4()),
        "reference": await _next_reference(org_id),
        "organization_id": org_id,
        "user_id": user.get("id"),
        "user_name": user.get("full_name") or user.get("email") or "",
        "user_role": (user.get("role") or ""),
        "country_code": (body.country_code or (rule.get("country_code") if rule else "") or "").upper(),
        "currency": currency,
        "expense_type": body.expense_type,
        "category_id": body.category_id or "",
        "category_name": body.category_name or "",
        "merchant": (body.merchant or "").strip(),
        "merchant_country": (body.merchant_country or "").upper(),
        "transaction_date": body.transaction_date or "",
        "submitted_date": None,
        "gross_amount": gross,
        "net_amount": _net_from_gross(gross, body.tax_amount),
        "tax_amount": round(body.tax_amount or 0.0, 2),
        "tax_rate": body.tax_rate or 0.0,
        "tax_label": rule.get("tax_label") if rule else "Tax",
        "payment_method": body.payment_method or "",
        "receipt_paths": body.receipt_paths or [],
        "receipt_number": body.receipt_number or "",
        "description": body.description or "",
        "business_purpose": body.business_purpose or "",
        "job_id": body.job_id or "", "job_reference": body.job_reference or "",
        "customer_id": body.customer_id or "", "customer_name": body.customer_name or "",
        "site_id": body.site_id or "", "site_name": body.site_name or "",
        "vehicle_id": body.vehicle_id or "", "department": body.department or "",
        "billable_to_customer": bool(body.billable_to_customer),
        "internal_cost": bool(body.internal_cost),
        "mileage": mileage,
        "status": DRAFT,
        "reviewer_id": None, "reviewer_name": None, "review_note": None, "reviewed_at": None,
        "reimbursement_status": "not_submitted",
        "reimbursed_at": None, "payment_batch": None, "payroll_reference": None,
        "export_status": "not_exported", "exported_at": None, "locked": False,
        "accounting_code": (rule.get("accounting_code_default") if rule else "") or "",
        "payroll_code": (rule.get("payroll_code_default") if rule else "") or "",
        "ocr_confidence": body.ocr_confidence,
        "duplicate_flag": bool(dup),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.expenses.insert_one(doc)
    doc.pop("_id", None)
    await audit(doc, user, "created", new=doc["reference"])

    if body.submit:
        return await _do_submit(doc, user, org)
    return doc


@router.get("")
async def list_expenses(
    status: Optional[str] = None,
    expense_type: Optional[str] = None,
    category_id: Optional[str] = None,
    job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200,
    user=Depends(get_current_user),
):
    q = scope_filter(user)
    if status and status != "all":
        q["status"] = {"$in": status.split(",")}
    if expense_type:
        q["expense_type"] = expense_type
    if category_id:
        q["category_id"] = category_id
    if job_id:
        q["job_id"] = job_id
    if user_id and can_review(user):
        q["user_id"] = user_id
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["transaction_date"] = rng
    rows = await db.expenses.find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 500)).to_list(min(limit, 500))
    return {"expenses": rows, "count": len(rows)}


async def _load(expense_id: str, user: dict) -> dict:
    e = await db.expenses.find_one({"id": expense_id, "organization_id": org_of(user)}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Expense not found")
    if not can_review(user) and e.get("user_id") != user.get("id"):
        raise HTTPException(403, "Not your expense")
    return e


@router.get("/{expense_id}")
async def get_expense(expense_id: str, user=Depends(get_current_user)):
    return await _load(expense_id, user)


@router.put("/{expense_id}")
async def update_expense(expense_id: str, body: ExpenseBody, user=Depends(get_current_user)):
    e = await _load(expense_id, user)
    owner = e.get("user_id") == user.get("id")
    if e.get("status") in LOCKED_STATUSES:
        raise HTTPException(409, "This expense is locked (exported/reimbursed). Use a correction.")
    if owner and e.get("status") not in (DRAFT, NEEDS_DETAILS, SUBMITTED) and not can_review(user):
        raise HTTPException(409, "This expense can no longer be edited")

    gross = round(body.gross_amount or 0.0, 2)
    mileage = body.mileage.model_dump() if body.mileage else e.get("mileage")
    if body.expense_type == "mileage" and mileage:
        # Server authoritative: recompute from distance × rate, never trust the
        # client-supplied calculated_amount.
        mileage["calculated_amount"] = round((mileage.get("distance") or 0.0) * (mileage.get("rate") or 0.0), 2)
        gross = round(mileage["calculated_amount"] or gross, 2)
    update = {
        "category_id": body.category_id or "", "category_name": body.category_name or "",
        "merchant": (body.merchant or "").strip(),
        "merchant_country": (body.merchant_country or "").upper(),
        "transaction_date": body.transaction_date or "",
        "gross_amount": gross, "tax_amount": round(body.tax_amount or 0.0, 2),
        "net_amount": _net_from_gross(gross, body.tax_amount), "tax_rate": body.tax_rate or 0.0,
        "payment_method": body.payment_method or "", "description": body.description or "",
        "business_purpose": body.business_purpose or "",
        "receipt_paths": body.receipt_paths if body.receipt_paths else e.get("receipt_paths", []),
        "job_id": body.job_id or "", "job_reference": body.job_reference or "",
        "customer_id": body.customer_id or "", "customer_name": body.customer_name or "",
        "site_id": body.site_id or "", "site_name": body.site_name or "",
        "vehicle_id": body.vehicle_id or "",
        "billable_to_customer": bool(body.billable_to_customer),
        "internal_cost": bool(body.internal_cost), "mileage": mileage,
        "updated_at": now_iso(),
    }
    await db.expenses.update_one({"id": expense_id, "organization_id": e["organization_id"]}, {"$set": update})
    await audit(e, user, "edited", note="fields updated")
    merged = {**e, **update}
    if body.submit and e.get("status") in (DRAFT, NEEDS_DETAILS):
        return await _do_submit(merged, user, await get_org(e["organization_id"]))
    return merged


# ── Workflow ─────────────────────────────────────────────────────────
async def _notify(user_id: str, org_id: str, title: str, body: str, link: str) -> None:
    try:
        from routes.svc.notifications import create_notification
        await create_notification(user_id=user_id, organization_id=org_id,
                                  kind="expense", title=title, body=body, link=link,
                                  source_type="expense")
    except Exception:  # noqa: BLE001
        pass


async def _notify_reviewers(org_id: str, title: str, body: str) -> None:
    try:
        from routes.svc.notifications import create_notification
        cursor = db.users.find(
            {"organization_id": org_id,
             "$or": [{"role": {"$in": ["owner", "manager", "finance", "admin"]}},
                     {"is_pulse_admin": True}, {"is_service_desk": True}]},
            {"_id": 0, "id": 1}).limit(20)
        async for u in cursor:
            await create_notification(user_id=u["id"], organization_id=org_id,
                                      kind="expense", title=title, body=body,
                                      link="/svc/finance/expenses", source_type="expense")
    except Exception:  # noqa: BLE001
        pass


async def _do_submit(e: dict, user: dict, org: dict) -> dict:
    solo = approval_mode(org) == "off"
    new_status = APPROVED if solo else SUBMITTED
    update = {
        "status": new_status, "submitted_date": now_iso(), "updated_at": now_iso(),
        "reimbursement_status": "approved_for_reimbursement" if solo else "awaiting_approval",
    }
    if solo:
        update["reviewer_name"] = "Auto-approved (solo mode)"
        update["reviewed_at"] = now_iso()
    await db.expenses.update_one({"id": e["id"], "organization_id": e["organization_id"]}, {"$set": update})
    await audit(e, user, "submitted", new=new_status)
    if not solo:
        await _notify_reviewers(e["organization_id"], "Expense submitted",
                                f"{e.get('user_name')} submitted {e.get('reference')} ({e.get('currency')} {e.get('gross_amount')}).")
    return {**e, **update}


@router.post("/{expense_id}/submit")
async def submit_expense(expense_id: str, user=Depends(get_current_user)):
    e = await _load(expense_id, user)
    if e.get("status") not in (DRAFT, NEEDS_DETAILS):
        raise HTTPException(409, f"Cannot submit a {e.get('status')} expense")
    return await _do_submit(e, user, await get_org(e["organization_id"]))


class ReviewBody(BaseModel):
    action: str  # approve|reject|needs_details
    note: Optional[str] = ""
    accounting_code: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None


@router.post("/{expense_id}/review")
async def review_expense(expense_id: str, body: ReviewBody, user=Depends(get_current_user)):
    if not can_review(user):
        raise HTTPException(403, "Reviewer access required")
    e = await _load(expense_id, user)
    if e.get("status") not in (SUBMITTED, NEEDS_DETAILS):
        raise HTTPException(409, f"Cannot review a {e.get('status')} expense")
    # Segregation of duties — a reviewer cannot approve/return their own claim
    # (except solo-operator orgs where there is no second person to approve).
    if e.get("user_id") == user.get("id") and approval_mode(await get_org(e["organization_id"])) != "off":
        raise HTTPException(403, "You can't review your own expense — it needs a second approver.")
    actions = {"approve": APPROVED, "reject": REJECTED, "needs_details": NEEDS_DETAILS}
    if body.action not in actions:
        raise HTTPException(400, "Invalid action")
    new_status = actions[body.action]
    update = {
        "status": new_status, "reviewer_id": user.get("id"),
        "reviewer_name": user.get("full_name") or user.get("email"),
        "review_note": body.note or "", "reviewed_at": now_iso(), "updated_at": now_iso(),
    }
    if body.accounting_code is not None:
        update["accounting_code"] = body.accounting_code
    if body.category_id is not None:
        update["category_id"] = body.category_id
        update["category_name"] = body.category_name or ""
    if new_status == APPROVED:
        update["reimbursement_status"] = "approved_for_reimbursement"
    elif new_status == REJECTED:
        update["reimbursement_status"] = "rejected"
    await db.expenses.update_one({"id": expense_id, "organization_id": e["organization_id"]}, {"$set": update})
    await audit(e, user, f"review_{body.action}", new=new_status, note=body.note)
    titles = {"approve": "Expense approved", "reject": "Expense rejected",
              "needs_details": "More details needed on your expense"}
    await _notify(e["user_id"], e["organization_id"], titles[body.action],
                  f"{e.get('reference')}: {body.note or ''}".strip(),
                  "/svc/engineer/expenses")
    return {**e, **update}


class ReimburseBody(BaseModel):
    payment_batch: Optional[str] = ""
    payroll_reference: Optional[str] = ""


@router.post("/{expense_id}/reimburse")
async def reimburse_expense(expense_id: str, body: ReimburseBody, user=Depends(get_current_user)):
    if not can_review(user):
        raise HTTPException(403, "Finance access required")
    e = await _load(expense_id, user)
    if e.get("status") not in (APPROVED, EXPORTED):
        raise HTTPException(409, "Only approved/exported expenses can be reimbursed")
    # Segregation of duties — you cannot mark your own claim as paid (unless a
    # solo-operator org with no second person).
    if e.get("user_id") == user.get("id") and approval_mode(await get_org(e["organization_id"])) != "off":
        raise HTTPException(403, "You can't reimburse your own expense — it needs a second person.")
    update = {
        "status": REIMBURSED, "reimbursement_status": "paid",
        "reimbursed_at": now_iso(), "payment_batch": body.payment_batch or "",
        "payroll_reference": body.payroll_reference or "", "locked": True,
        "updated_at": now_iso(),
    }
    await db.expenses.update_one({"id": expense_id, "organization_id": e["organization_id"]}, {"$set": update})
    await audit(e, user, "reimbursed", new="paid", note=body.payroll_reference)
    await _notify(e["user_id"], e["organization_id"], "Expense reimbursed",
                  f"{e.get('reference')} has been paid.", "/svc/engineer/expenses")
    return {**e, **update}


@router.post("/{expense_id}/cancel")
async def cancel_expense(expense_id: str, user=Depends(get_current_user)):
    e = await _load(expense_id, user)
    if e.get("status") in LOCKED_STATUSES or e.get("status") == REIMBURSED:
        raise HTTPException(409, "Locked expenses cannot be cancelled")
    await db.expenses.update_one({"id": expense_id, "organization_id": e["organization_id"]},
                                 {"$set": {"status": CANCELLED, "updated_at": now_iso()}})
    await audit(e, user, "cancelled")
    return {"ok": True}


@router.get("/{expense_id}/events")
async def expense_events(expense_id: str, user=Depends(get_current_user)):
    await _load(expense_id, user)
    rows = await db.expense_events.find(
        {"expense_id": expense_id}, {"_id": 0}).sort("at", -1).limit(100).to_list(100)
    return {"events": rows}


# ── Private receipt serving (authed, scope-checked) ──────────────────
@router.get("/{expense_id}/receipt")
async def get_receipt(expense_id: str, i: int = Query(0), user=Depends(get_current_user)):
    e = await _load(expense_id, user)
    paths = e.get("receipt_paths") or []
    if i < 0 or i >= len(paths):
        raise HTTPException(404, "Receipt not found")
    try:
        content, ctype = get_object(paths[i])
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "Receipt unavailable")
    return Response(content=content, media_type=ctype,
                    headers={"Cache-Control": "private, max-age=300"})
