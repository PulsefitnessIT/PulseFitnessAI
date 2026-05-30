"""Iter 216h129 — Engineer-side Quote Builder + PDF + Email.

Phase 1 of the Engineer App overhaul. Adds a fully-featured engineer
quote workflow accessible at `/api/svc/engineer/quotes/*`:

  • POST   /quotes                       — create draft from job/parts/labour
  • GET    /quotes                       — list (with filters)
  • GET    /quotes/{id}                  — single
  • PATCH  /quotes/{id}                  — edit lines / terms / status
  • POST   /quotes/{id}/send             — email branded PDF via Resend
  • GET    /quotes/{id}.pdf              — download branded PDF
  • POST   /quotes/{id}/duplicate        — clone (for "revised" / "follow-up")
  • POST   /quotes/{id}/mark             — set status (accepted | declined | invoiced)
  • POST   /quotes/{id}/convert-to-job   — accepted quote → new svc_case

Data:
  Collection: `db.svc_engineer_quotes`
  Source of truth — distinct from CRM `crm2_quotes` (different audience,
  different lifecycle: engineer→customer vs operator→prospect).

PDF: branded light-mode GymAxis (white + navy + brand blue gradient).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from routes.partners import require_engineer_app_access

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Quotes"],
    dependencies=[Depends(require_engineer_app_access)],
)

QUOTE_STATUSES = ("draft", "sent", "accepted", "declined", "invoiced", "expired")


# ─────────────────────────── helpers ──────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org_id}


def _new_quote_number() -> str:
    """EQ-YYYYMMDD-XXXX (Engineer Quote)."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"EQ-{today}-{uuid.uuid4().hex[:4].upper()}"


def _compute_totals(lines: list[dict], vat_rate: float, discount_pct: float = 0) -> dict:
    """Recompute subtotal / VAT / total. Each line: {description, quantity, unit_price}."""
    subtotal = 0.0
    for ln in lines:
        qty = float(ln.get("quantity", 0) or 0)
        unit = float(ln.get("unit_price", 0) or 0)
        line_total = qty * unit
        ln["line_total"] = round(line_total, 2)
        subtotal += line_total
    discount_amount = round(subtotal * (discount_pct / 100), 2) if discount_pct else 0.0
    subtotal_after_discount = round(subtotal - discount_amount, 2)
    vat_amount = round(subtotal_after_discount * (vat_rate / 100), 2)
    total = round(subtotal_after_discount + vat_amount, 2)
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


async def _case_snapshot(case_id: str | None, user: dict) -> dict:
    if not case_id:
        return {}
    case = await db.svc_cases.find_one(
        {"id": case_id, **_of(user)},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "customer_name": 1,
         "customer_email": 1, "customer_phone": 1, "site_name": 1,
         "asset_name": 1, "asset_id": 1, "asset_serial": 1, "fault_code": 1},
    ) or {}
    return case


# ─────────────────────────── HTTP Models ──────────────────────────


class QuoteLine(BaseModel):
    kind: str = Field(default="labour")  # labour | part | travel | callout | other
    description: str
    quantity: float = 1
    unit_price: float = 0
    notes: str | None = None
    part_id: str | None = None


class QuoteMachine(BaseModel):
    """Iter 220cr — multi-machine attachment on a quote.

    Free-form so the engineer can scribble whatever they need in the
    field; PDFs render this as a bullet list under the asset summary.
    """
    name: str | None = None
    serial: str | None = None
    notes: str | None = None


class QuoteCreate(BaseModel):
    case_id: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    site_name: str | None = None
    site_address: str | None = None
    asset_name: str | None = None
    asset_serial: str | None = None
    machines: list[QuoteMachine] = Field(default_factory=list)
    description_of_work: str | None = None
    lines: list[QuoteLine] = Field(default_factory=list)
    vat_rate: float = 20
    discount_pct: float = 0
    valid_days: int = 30
    terms: str | None = None
    notes: str | None = None
    photo_ids: list[str] = Field(default_factory=list)


class QuoteUpdate(BaseModel):
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    site_name: str | None = None
    site_address: str | None = None
    asset_name: str | None = None
    asset_serial: str | None = None
    machines: list[QuoteMachine] | None = None
    description_of_work: str | None = None
    lines: list[QuoteLine] | None = None
    vat_rate: float | None = None
    discount_pct: float | None = None
    valid_until: str | None = None
    terms: str | None = None
    notes: str | None = None
    photo_ids: list[str] | None = None
    status: str | None = None


class QuoteSend(BaseModel):
    to: str | None = None  # override recipient (defaults to customer_email)
    cc: list[str] = Field(default_factory=list)
    message: str | None = None
    include_photos: bool = False


class StatusMark(BaseModel):
    status: str
    note: str | None = None


# ─────────────────────────── Endpoints ────────────────────────────


@router.post("/quotes", status_code=201)
async def create_quote(body: QuoteCreate, user=Depends(get_current_user)):
    case = await _case_snapshot(body.case_id, user)
    engineer = await _engineer_profile(user)
    lines_dicts = [ln.model_dump() for ln in body.lines]
    totals = _compute_totals(lines_dicts, body.vat_rate or 20, body.discount_pct or 0)
    valid_until = (
        datetime.now(timezone.utc) + timedelta(days=body.valid_days or 30)
    ).date().isoformat()
    quote = {
        "id": str(uuid.uuid4()),
        "quote_number": _new_quote_number(),
        "organization_id": user.get("organization_id"),
        "engineer_id": user.get("id"),
        "engineer_name": engineer.get("full_name"),
        "engineer_email": engineer.get("email"),
        "engineer_mobile": engineer.get("mobile"),
        "case_id": body.case_id or case.get("id"),
        "case_reference": case.get("reference"),
        "asset_id": case.get("asset_id"),
        "customer_name": body.customer_name or case.get("customer_name") or "",
        "customer_email": body.customer_email or case.get("customer_email") or "",
        "customer_phone": body.customer_phone or case.get("customer_phone") or "",
        "site_name": body.site_name or case.get("site_name") or "",
        "site_address": body.site_address or "",
        "asset_name": body.asset_name or case.get("asset_name") or "",
        "asset_serial": body.asset_serial or case.get("asset_serial") or "",
        # Iter 220cr — multi-machine attachment.
        "machines": [m.model_dump() for m in (body.machines or [])],
        "description_of_work": body.description_of_work or "",
        "lines": lines_dicts,
        **totals,
        "valid_until": valid_until,
        "terms": body.terms or (
            "Quote valid for 30 days. Pricing excludes any additional work "
            "discovered on site. Payment terms: 30 days from invoice date."
        ),
        "notes": body.notes or "",
        "photo_ids": body.photo_ids,
        "status": "draft",
        "status_history": [
            {"status": "draft", "at": _now(), "by": user.get("email")},
        ],
        "created_at": _now(), "updated_at": _now(),
        "sent_at": None, "accepted_at": None, "declined_at": None,
        "converted_case_id": None,
    }
    await db.svc_engineer_quotes.insert_one({**quote})
    quote.pop("_id", None)
    # Iter 216h259 — stamp Lite CRM last_job_at on matching customer
    try:
        from routes.svc.engineer_customers import touch_last_job
        await touch_last_job(
            user.get("organization_id"),
            email=quote.get("customer_email"),
            phone=quote.get("customer_phone"),
        )
    except Exception:
        pass
    return quote


@router.get("/quotes")
async def list_quotes(
    status: str | None = None,
    case_id: str | None = None,
    customer_email: str | None = None,
    limit: int = 100,
    user=Depends(get_current_user),
):
    q: dict[str, Any] = {**_of(user), "engineer_id": user.get("id")}
    if status:
        if status not in QUOTE_STATUSES + ("active",):
            raise HTTPException(400, "invalid status")
        if status == "active":
            q["status"] = {"$in": ["draft", "sent"]}
        else:
            q["status"] = status
    if case_id:
        q["case_id"] = case_id
    if customer_email:
        q["customer_email"] = customer_email.lower()
    rows = await db.svc_engineer_quotes.find(
        q, {"_id": 0},
    ).sort("created_at", -1).to_list(max(1, min(500, limit)))
    return {"quotes": rows, "total": len(rows)}


async def _get_quote_or_404(quote_id: str, user: dict) -> dict:
    quote = await db.svc_engineer_quotes.find_one(
        {"id": quote_id, **_of(user)},
        {"_id": 0},
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    # Iter 220az · F-29 / F-33 — return 404 (not 403) on cross-engineer
    # access so the caller can't enumerate quote IDs by status code.
    # Master admins always pass.
    if quote.get("engineer_id") != user.get("id") and not user.get("is_master_admin"):
        raise HTTPException(404, "Quote not found")
    return quote


@router.get("/quotes/{quote_id}.pdf")
async def download_quote_pdf(quote_id: str, user=Depends(get_current_user)):
    quote = await _get_quote_or_404(quote_id, user)
    from utils.engineer_quote_pdf import build_engineer_quote_pdf
    from utils.pdf_footer import is_mod_for_case
    is_mod = await is_mod_for_case(db, quote.get("case_id"))
    pdf_bytes = build_engineer_quote_pdf(quote, is_mod=is_mod)
    filename = f"{quote['quote_number']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/quotes/{quote_id}")
async def get_quote(quote_id: str, user=Depends(get_current_user)):
    return await _get_quote_or_404(quote_id, user)


@router.patch("/quotes/{quote_id}")
async def update_quote(
    quote_id: str, body: QuoteUpdate, user=Depends(get_current_user),
):
    quote = await _get_quote_or_404(quote_id, user)
    if quote["status"] not in ("draft", "sent"):
        raise HTTPException(409, f"Cannot edit quote in {quote['status']} state")
    patch: dict[str, Any] = {"updated_at": _now()}
    payload = body.model_dump(exclude_unset=True)
    if "lines" in payload:
        # Pydantic v2: when explicitly populated, items are QuoteLine objects.
        lines_data = payload["lines"]
        normalised = [
            ln.model_dump() if hasattr(ln, "model_dump") else dict(ln)
            for ln in lines_data
        ] if lines_data is not None else []
        patch["lines"] = normalised
    if "status" in payload and payload["status"]:
        st = payload["status"]
        if st not in QUOTE_STATUSES:
            raise HTTPException(400, "invalid status")
        patch["status"] = st
    # Carry over all simple scalars
    for k in ("customer_name", "customer_email", "customer_phone",
              "site_name", "site_address", "asset_name", "asset_serial",
              "machines",
              "description_of_work", "valid_until", "terms", "notes",
              "photo_ids", "vat_rate", "discount_pct"):
        if k in payload:
            patch[k] = payload[k]
    # Recompute totals when lines/vat/discount changed
    merged = {**quote, **patch}
    if any(k in patch for k in ("lines", "vat_rate", "discount_pct")):
        totals = _compute_totals(
            merged.get("lines") or [],
            float(merged.get("vat_rate") or 20),
            float(merged.get("discount_pct") or 0),
        )
        patch.update(totals)
        patch["lines"] = merged.get("lines") or []
    await db.svc_engineer_quotes.update_one(
        {"id": quote_id},
        {"$set": patch,
         "$push": {"status_history": {"status": patch.get("status", quote["status"]),
                                       "at": _now(), "by": user.get("email")}}}
        if patch.get("status") else {"$set": patch},
    )
    return await _get_quote_or_404(quote_id, user)


@router.post("/quotes/{quote_id}/send")
async def send_quote(
    quote_id: str, body: QuoteSend, user=Depends(get_current_user),
):
    """Email the branded quote PDF to the customer via Resend."""
    quote = await _get_quote_or_404(quote_id, user)
    to_addr = (body.to or quote.get("customer_email") or "").strip().lower()
    if not to_addr or "@" not in to_addr:
        raise HTTPException(400, "Recipient email required (customer_email empty)")
    # Ensure a public accept shortcode exists — generate on first send.
    shortcode = quote.get("public_shortcode")
    if not shortcode:
        from routes.public_quote import generate_shortcode
        shortcode = generate_shortcode()
        await db.svc_engineer_quotes.update_one(
            {"id": quote_id},
            {"$set": {"public_shortcode": shortcode}},
        )
        quote["public_shortcode"] = shortcode
    from utils.engineer_quote_pdf import build_engineer_quote_pdf
    from utils.pdf_footer import is_mod_for_case
    is_mod = await is_mod_for_case(db, quote.get("case_id"))
    pdf_bytes = build_engineer_quote_pdf(quote, is_mod=is_mod)
    import base64
    attachment = {
        "filename": f"{quote['quote_number']}.pdf",
        "content": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    custom = (body.message or "").strip()
    html = _email_html(quote, custom)
    subject = f"Quote {quote['quote_number']} from {quote.get('engineer_name') or 'your engineer'}"
    ok = await send_email(
        to=to_addr, subject=subject, html=html,
        attachments=[attachment],
        organization_id=user.get("organization_id"),
    )
    if not ok:
        raise HTTPException(502, "Email send failed (check Resend configuration)")
    update = {
        "status": "sent",
        "sent_at": _now(),
        "last_sent_to": to_addr,
        "updated_at": _now(),
    }
    await db.svc_engineer_quotes.update_one(
        {"id": quote_id},
        {"$set": update,
         "$push": {
             "status_history": {
                 "status": "sent", "at": _now(), "by": user.get("email"),
                 "to": to_addr,
             },
             "email_log": {
                 "at": _now(), "to": to_addr, "subject": subject,
                 "message": custom, "cc": body.cc or [],
             },
         }},
    )
    return {"success": True, "sent_to": to_addr, "quote_id": quote_id}


@router.post("/quotes/{quote_id}/duplicate")
async def duplicate_quote(quote_id: str, user=Depends(get_current_user)):
    original = await _get_quote_or_404(quote_id, user)
    clone = {**original}
    clone.pop("_id", None)
    clone["id"] = str(uuid.uuid4())
    clone["quote_number"] = _new_quote_number()
    clone["status"] = "draft"
    clone["status_history"] = [{"status": "draft", "at": _now(),
                                  "by": user.get("email"),
                                  "note": f"Duplicated from {original['quote_number']}"}]
    clone["sent_at"] = None
    clone["accepted_at"] = None
    clone["declined_at"] = None
    clone["converted_case_id"] = None
    clone["created_at"] = _now()
    clone["updated_at"] = _now()
    clone["email_log"] = []
    await db.svc_engineer_quotes.insert_one({**clone})
    clone.pop("_id", None)
    return clone


@router.post("/quotes/{quote_id}/mark")
async def mark_quote(
    quote_id: str, body: StatusMark, user=Depends(get_current_user),
):
    await _get_quote_or_404(quote_id, user)
    if body.status not in QUOTE_STATUSES:
        raise HTTPException(400, "invalid status")
    set_payload: dict[str, Any] = {"status": body.status, "updated_at": _now()}
    if body.status == "accepted":
        set_payload["accepted_at"] = _now()
    elif body.status == "declined":
        set_payload["declined_at"] = _now()
    await db.svc_engineer_quotes.update_one(
        {"id": quote_id},
        {"$set": set_payload,
         "$push": {"status_history": {"status": body.status, "at": _now(),
                                       "by": user.get("email"),
                                       "note": body.note}}},
    )
    return await _get_quote_or_404(quote_id, user)


@router.post("/quotes/{quote_id}/convert-to-job")
async def convert_to_job(quote_id: str, user=Depends(get_current_user)):
    """Accepted quote → new svc_case (follow-up work)."""
    quote = await _get_quote_or_404(quote_id, user)
    if quote["status"] != "accepted":
        raise HTTPException(409, "Only accepted quotes can be converted to a job")
    if quote.get("converted_case_id"):
        raise HTTPException(409, f"Already converted to {quote['converted_case_id']}")
    case_id = str(uuid.uuid4())
    reference = f"SC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    case = {
        "id": case_id, "reference": reference,
        "organization_id": user.get("organization_id"),
        "title": (quote.get("description_of_work") or "Follow-up from quote")[:120],
        "status": "assigned",
        "priority": "p3",
        "assigned_engineer_id": user.get("id"),
        "customer_name": quote.get("customer_name"),
        "customer_email": quote.get("customer_email"),
        "customer_phone": quote.get("customer_phone"),
        "site_name": quote.get("site_name"),
        "asset_name": quote.get("asset_name"),
        "asset_id": quote.get("asset_id"),
        "asset_serial": quote.get("asset_serial"),
        "fault_code": "QUOTE_FOLLOW_UP",
        "fault_description": quote.get("description_of_work"),
        "scheduled_at": None,
        "chargeable": True,
        "linked_quote_id": quote_id,
        "linked_quote_number": quote["quote_number"],
        "estimated_value": quote.get("total"),
        "created_at": _now(), "updated_at": _now(),
        "source": "engineer_quote",
    }
    await db.svc_cases.insert_one({**case})
    await db.svc_engineer_quotes.update_one(
        {"id": quote_id},
        {"$set": {"converted_case_id": case_id,
                  "converted_case_reference": reference,
                  "updated_at": _now()},
         "$push": {"status_history": {"status": "converted",
                                       "to_case_id": case_id,
                                       "to_case_reference": reference,
                                       "at": _now(), "by": user.get("email")}}},
    )
    case.pop("_id", None)
    return {"success": True, "case_id": case_id, "case_reference": reference}


# ────────────────────── Engineer Home v2 KPIs ─────────────────────


@router.get("/dashboard")
async def engineer_dashboard(user=Depends(get_current_user)):
    """Rich Engineer Home v2 dashboard payload.

    Returns counts/KPIs + small lists for the home control centre:
      • today / upcoming / overdue jobs
      • pending quotes (draft + sent)
      • unpaid invoices (from svc_invoices_outbox / quotes marked invoiced)
      • parts required (cases with status waiting_parts or pending_parts)
      • job-awaiting-customer-response count
      • earnings this month (sum of accepted/invoiced quote totals)
      • notifications (unread count from svc_case_events.kind == notification)
    """
    of = _of(user)
    user_id = user.get("id")
    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()
    tomorrow_iso = (now + timedelta(days=1)).date().isoformat()
    month_start = now.replace(day=1, hour=0, minute=0,
                              second=0, microsecond=0).isoformat()
    # ── Jobs by window ────────────────────────────────────────────
    base_q = {**of, "assigned_engineer_id": user_id,
              "status": {"$in": ["assigned", "en_route", "on_site",
                                 "in_progress", "awaiting_parts",
                                 "quote_required"]}}
    today_jobs = await db.svc_cases.count_documents(
        {**base_q, "scheduled_at": {"$regex": f"^{today_iso}"}},
    )
    upcoming_jobs = await db.svc_cases.count_documents(
        {**base_q, "scheduled_at": {"$gte": tomorrow_iso}},
    )
    overdue_jobs = await db.svc_cases.count_documents(
        {**base_q, "scheduled_at": {"$lt": today_iso, "$ne": None}},
    )
    awaiting_parts = await db.svc_cases.count_documents(
        {**of, "assigned_engineer_id": user_id, "status": "awaiting_parts"},
    )
    awaiting_customer = await db.svc_cases.count_documents(
        {**of, "assigned_engineer_id": user_id,
         "status": {"$in": ["awaiting_sign_off", "quote_required"]}},
    )

    # ── Quotes ────────────────────────────────────────────────────
    eng_quote_q = {**of, "engineer_id": user_id}
    quote_pending = await db.svc_engineer_quotes.count_documents(
        {**eng_quote_q, "status": {"$in": ["draft", "sent"]}},
    )
    quote_accepted = await db.svc_engineer_quotes.count_documents(
        {**eng_quote_q, "status": "accepted"},
    )
    quote_invoiced = await db.svc_engineer_quotes.count_documents(
        {**eng_quote_q, "status": "invoiced"},
    )

    # ── Earnings this month — sum totals of quotes accepted/invoiced ──
    pipeline = [
        {"$match": {**eng_quote_q,
                    "status": {"$in": ["accepted", "invoiced"]},
                    "updated_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    rows = await db.svc_engineer_quotes.aggregate(pipeline).to_list(1)
    earnings_month = round(rows[0]["total"], 2) if rows else 0.0

    # ── Notifications (unread svc_notifications) — iter 216h142 ──
    notif_count = await db.svc_notifications.count_documents(
        {**of, "user_id": user_id, "read_at": None},
    )

    # ── Top 5 lists ───────────────────────────────────────────────
    today_list = await db.svc_cases.find(
        {**base_q, "scheduled_at": {"$regex": f"^{today_iso}"}},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "site_name": 1,
         "asset_name": 1, "priority": 1, "scheduled_at": 1,
         "sla_resolve_at": 1, "status": 1},
    ).sort("scheduled_at", 1).to_list(5)
    pending_quote_list = await db.svc_engineer_quotes.find(
        {**eng_quote_q, "status": {"$in": ["draft", "sent"]}},
        {"_id": 0, "id": 1, "quote_number": 1, "customer_name": 1,
         "total": 1, "status": 1, "valid_until": 1, "updated_at": 1},
    ).sort("updated_at", -1).to_list(5)

    return {
        "kpis": {
            "today_jobs": today_jobs,
            "upcoming_jobs": upcoming_jobs,
            "overdue_jobs": overdue_jobs,
            "awaiting_parts": awaiting_parts,
            "awaiting_customer": awaiting_customer,
            "quote_pending": quote_pending,
            "quote_accepted": quote_accepted,
            "quote_invoiced": quote_invoiced,
            "earnings_this_month": earnings_month,
            "notifications_unread": notif_count,
        },
        "today_jobs": today_list,
        "pending_quotes": pending_quote_list,
    }


# ─────────────────────────── Analytics ────────────────────────────
# Iter 216h257 — Engineer Analytics surface. Same shape as the
# dashboard KPIs but parameterised by a date window so the engineer
# can break down a 7-day / 30-day / 90-day / YTD slice. Returns the
# headline KPIs + status breakdown for the period.

_ANALYTICS_RANGES = {
    "7d":  timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "ytd": None,   # special-case → Jan 1 of current year
    "all": None,   # no filter
}


@router.get("/analytics")
async def engineer_analytics(
    range: str = "30d",  # noqa: A002 — public API name; harmless shadowing
    user=Depends(get_current_user),
):
    """Filtered KPI breakdown for the engineer over the supplied range.

    Accepts ``range ∈ {7d, 30d, 90d, ytd, all}``. Returns counts of
    jobs/quotes/invoices and the period earnings.
    """
    of = _of(user)
    user_id = user.get("id")
    now = datetime.now(timezone.utc)

    if range not in _ANALYTICS_RANGES:
        raise HTTPException(400, f"invalid range; must be one of {sorted(_ANALYTICS_RANGES)}")

    if range == "ytd":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    elif range == "all":
        start = None
    else:
        start = (now - _ANALYTICS_RANGES[range]).isoformat()

    case_match = {**of, "assigned_engineer_id": user_id}
    quote_match = {**of, "engineer_id": user_id}
    if start:
        case_match["created_at"] = {"$gte": start}
        quote_match["created_at"] = {"$gte": start}

    # Status breakdown for cases.
    case_pipeline = [
        {"$match": case_match},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    case_rows = await db.svc_cases.aggregate(case_pipeline).to_list(40)
    case_by_status = {(r["_id"] or "unknown"): r["n"] for r in case_rows}
    cases_total = sum(case_by_status.values())

    # Status breakdown for engineer quotes + earnings sum.
    quote_pipeline = [
        {"$match": quote_match},
        {"$group": {
            "_id": "$status",
            "n":     {"$sum": 1},
            "total": {"$sum": "$total"},
        }},
    ]
    quote_rows = await db.svc_engineer_quotes.aggregate(quote_pipeline).to_list(40)
    quote_by_status = {(r["_id"] or "unknown"): r["n"] for r in quote_rows}
    quotes_total = sum(quote_by_status.values())
    # Earnings: only count accepted + invoiced.
    earnings = round(sum(
        r["total"] for r in quote_rows if r["_id"] in ("accepted", "invoiced")
    ), 2)

    # Jobs completed in window (status closed | invoiced | repaired).
    completed_match = {**case_match, "status": {"$in": ["closed", "invoiced", "repaired"]}}
    jobs_completed = await db.svc_cases.count_documents(completed_match)

    # Average value of accepted quotes in window.
    accepted_pipeline = [
        {"$match": {**quote_match, "status": {"$in": ["accepted", "invoiced"]}}},
        {"$group": {"_id": None, "avg": {"$avg": "$total"}}},
    ]
    avg_rows = await db.svc_engineer_quotes.aggregate(accepted_pipeline).to_list(1)
    avg_quote_value = round(avg_rows[0]["avg"], 2) if avg_rows and avg_rows[0].get("avg") else 0.0

    return {
        "range": range,
        "range_start": start,
        "cases": {
            "total": cases_total,
            "completed": jobs_completed,
            "by_status": case_by_status,
        },
        "quotes": {
            "total": quotes_total,
            "by_status": quote_by_status,
            "average_value": avg_quote_value,
            "earnings": earnings,
        },
    }


# ─────────────────────────── Convert to invoice ────────────────────────────
# Iter 216h257 — Implemented via the existing
# POST /api/svc/engineer/invoices/from-quote/{quote_id} endpoint in
# engineer_invoices.py. We no longer ship a parallel route here.


# ─────────────────────────── Email body ───────────────────────────


def _email_html(quote: dict, custom_message: str = "") -> str:
    primary = "#1d4ed8"
    accent = "#6366f1"
    customer = quote.get("customer_name") or "there"
    engineer = quote.get("engineer_name") or "Your engineer"
    qno = quote.get("quote_number")
    total = quote.get("total") or 0
    valid_until = quote.get("valid_until") or ""
    description = quote.get("description_of_work") or ""
    shortcode = quote.get("public_shortcode")
    import os
    accept_origin = (os.environ.get("PUBLIC_ORIGIN") or
                      os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    accept_url = f"{accept_origin}/q/{shortcode}" if shortcode and accept_origin else None
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
    accept_block = ""
    if accept_url:
        accept_block = (
            f'<div style="text-align:center;margin:24px 0;">'
            f'<a href="{accept_url}" '
            f'style="display:inline-block;padding:14px 28px;background:linear-gradient(135deg,{primary} 0%,{accent} 100%);'
            f'color:white;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;'
            f'box-shadow:0 6px 14px rgba(99,102,241,0.35);">'
            f'Review &amp; Accept Quote →</a>'
            f'<p style="margin:10px 0 0;font-size:11px;color:#94a3b8;">'
            f'Or copy this link: <span style="color:#475569;">{accept_url}</span></p></div>'
        )
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:600px;margin:0 auto;padding:24px;">
      <div style="background:linear-gradient(135deg,{primary} 0%,{accent} 100%);
                  padding:24px;border-radius:12px;color:white;margin-bottom:24px;">
        <p style="margin:0;font-size:12px;letter-spacing:.2em;text-transform:uppercase;opacity:.85;">GymAxis · Quotation</p>
        <h1 style="margin:6px 0 0;font-size:24px;font-weight:700;">{qno}</h1>
      </div>
      <p style="font-size:16px;line-height:1.6;">Hi {customer},</p>
      <p style="font-size:14px;line-height:1.6;color:#334155;">
        Please find attached quotation <strong>{qno}</strong> for the work described below.
      </p>
      {custom_block}
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:18px 0;">
        <p style="margin:0;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.08em;">Work</p>
        <p style="margin:6px 0 0;font-size:14px;color:#0f172a;line-height:1.5;">{description or '—'}</p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:14px 0;">
        <table style="width:100%;font-size:13px;color:#334155;">
          <tr><td>Total (incl. VAT)</td><td style="text-align:right;font-weight:700;color:{primary};">£{total:,.2f}</td></tr>
          <tr><td>Valid until</td><td style="text-align:right;">{valid_until}</td></tr>
        </table>
      </div>
      {accept_block}
      <p style="font-size:13px;line-height:1.6;color:#64748b;">
        Prefer to reply by email or phone? Reply to this email or contact the engineer directly.
      </p>
      <p style="font-size:14px;margin-top:24px;">Thanks,<br/><strong>{engineer}</strong></p>
      <p style="font-size:11px;color:#94a3b8;margin-top:30px;">
        Powered by GymAxis · Field Service for Fitness Equipment
      </p>
    </div>
    """


__all__ = ["router"]
