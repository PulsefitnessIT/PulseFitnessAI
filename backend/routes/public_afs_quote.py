"""Public (no-login) Aftersales maintenance-quote acceptance.

Commercial customers click a link → land on /aq/:shortcode in the React app,
review the maintenance quote + PDF, then accept (with signature) or decline.
Acceptance auto-prepares a DRAFT agreement for the coordinator (feeds straight
into agreement prep). MOD keeps its existing SOR portal flow — not this one.

Single-use: once accepted/declined, future POSTs return 410.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from utils.database import db

router = APIRouter(prefix="/public/afs", tags=["Public · Aftersales Quote"])

MAX_SIGNATURE_LEN = 250_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(q: dict) -> bool:
    vu = q.get("valid_until")
    if not vu:
        return False
    try:
        return datetime.fromisoformat(vu.replace("Z", "+00:00")) < datetime.now(timezone.utc)
    except (ValueError, AttributeError):
        return False


def _public_view(q: dict) -> dict:
    summary = q.get("summary", {}) or {}
    return {
        "quote_number": q.get("quote_number"),
        "company_name": q.get("company_name"),
        "contract_type": q.get("contract_type"),
        "term_years": summary.get("term_years", q.get("term_years", 1)),
        "grouped_lines": [
            {k: g.get(k) for k in ("model", "console_type", "description", "qty",
                                    "annual_unit", "annual_total")}
            for g in (q.get("grouped_lines") or [])
        ],
        "summary": {k: summary.get(k) for k in (
            "final_annual", "monthly", "term_total", "term_years",
            "vat_pct", "vat_amount", "final_annual_inc_vat", "quote_discount_pct")},
        "valid_until": q.get("valid_until"),
        "expired": _is_expired(q),
        "portal_status": q.get("portal_status"),
        "accepted_at": q.get("accepted_at"),
        "accepted_by_name": q.get("accepted_by_name"),
        "declined_at": q.get("declined_at"),
    }


async def _find(shortcode: str) -> dict:
    q = await db.crm2_afs_quotes.find_one({"public_shortcode": shortcode}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Quote not found or no longer available")
    return q


class AcceptBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    signature_data_url: str | None = Field(default=None, max_length=MAX_SIGNATURE_LEN)
    note: str | None = Field(default=None, max_length=500)


class DeclineBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


@router.get("/quote/{shortcode}")
async def get_public_afs_quote(shortcode: str):
    return _public_view(await _find(shortcode))


@router.get("/quote/{shortcode}/pdf")
async def public_afs_quote_pdf(shortcode: str):
    q = await _find(shortcode)
    from utils.afs_quote_pdf import render_afs_quote_pdf
    pdf = await render_afs_quote_pdf(q, organization_id=q.get("organization_id"))
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{q.get("quote_number", "quote")}.pdf"'})


@router.post("/quote/{shortcode}/accept")
async def accept_public_afs_quote(shortcode: str, body: AcceptBody):
    q = await _find(shortcode)
    if q.get("portal_status") == "accepted":
        raise HTTPException(410, "This quote has already been accepted.")
    if q.get("portal_status") == "declined":
        raise HTTPException(410, "This quote has already been declined.")
    if _is_expired(q):
        raise HTTPException(410, "This quote has expired. Please contact Pulse Fitness for a fresh quote.")
    set_payload = {
        "portal_status": "accepted", "accepted_at": _now(),
        "accepted_by_name": body.name.strip(),
        "accepted_by_note": (body.note or "").strip(),
        "accepted_via": "public_link", "updated_at": _now(),
    }
    if body.signature_data_url:
        set_payload["customer_signature_data_url"] = body.signature_data_url
    await db.crm2_afs_quotes.update_one({"id": q["id"]}, {"$set": set_payload})

    # Feed straight into agreement prep — auto-create a DRAFT agreement.
    agreement_number = None
    try:
        from routes.crm_aftersales import _insert_agreement_from_quote
        q2 = await db.crm2_afs_quotes.find_one({"id": q["id"]}, {"_id": 0})
        ag = await _insert_agreement_from_quote(
            q["organization_id"], q2, f"portal:{body.name.strip()}",
            timeline_note=f"Customer {body.name.strip()} accepted quote {q.get('quote_number')} via portal")
        agreement_number = ag.get("agreement_number")
    except Exception:
        agreement_number = None
    return {"ok": True, "quote_number": q.get("quote_number"), "agreement_number": agreement_number}


@router.post("/quote/{shortcode}/decline")
async def decline_public_afs_quote(shortcode: str, body: DeclineBody):
    q = await _find(shortcode)
    if q.get("portal_status") == "accepted":
        raise HTTPException(410, "This quote has already been accepted.")
    if q.get("portal_status") == "declined":
        raise HTTPException(410, "This quote has already been declined.")
    await db.crm2_afs_quotes.update_one({"id": q["id"]}, {"$set": {
        "portal_status": "declined", "declined_at": _now(),
        "declined_by_name": body.name.strip(),
        "declined_reason": (body.reason or "").strip(),
        "declined_via": "public_link", "updated_at": _now()}})
    return {"ok": True, "quote_number": q.get("quote_number")}


__all__ = ["router"]
