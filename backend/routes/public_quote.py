"""Iter 216h130 — Public Quote Accept (no-login customer signature).

Customer clicks an "Accept this quote" button in their email →
lands on a public page rendered by the React app at `/q/:shortcode`
which calls these no-auth endpoints to view the summary, sign, and
accept the quote. Engineer gets a push notification.

The shortcode is a 10-char URL-safe token generated when the quote
is sent. Stored on `svc_engineer_quotes.public_shortcode`. Single
use — once accepted, future POSTs return 410.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from utils.database import db

router = APIRouter(prefix="/public", tags=["Public · Quote Accept"])

MAX_SIGNATURE_LEN = 250_000  # ~250 KB data-url cap


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_shortcode_index_safe() -> None:
    """Hint: collection indexed via existing mongo init; nothing to do."""
    return None


def generate_shortcode() -> str:
    """URL-safe 10-char token. Collision odds at scale: negligible."""
    return secrets.token_urlsafe(8)[:10]


def _public_quote_view(q: dict) -> dict:
    """Strip sensitive fields before returning to a no-auth caller."""
    return {
        "quote_number": q.get("quote_number"),
        "status": q.get("status"),
        "valid_until": q.get("valid_until"),
        "customer_name": q.get("customer_name"),
        "site_name": q.get("site_name"),
        "site_address": q.get("site_address"),
        "asset_name": q.get("asset_name"),
        "asset_serial": q.get("asset_serial"),
        "description_of_work": q.get("description_of_work"),
        "lines": [
            {k: ln.get(k) for k in ("kind", "description", "quantity",
                                     "unit_price", "line_total")}
            for ln in (q.get("lines") or [])
        ],
        "subtotal": q.get("subtotal"),
        "discount_pct": q.get("discount_pct"),
        "discount_amount": q.get("discount_amount"),
        "vat_rate": q.get("vat_rate"),
        "vat_amount": q.get("vat_amount"),
        "total": q.get("total"),
        "terms": q.get("terms"),
        "notes": q.get("notes"),
        "engineer_name": q.get("engineer_name"),
        "accepted_at": q.get("accepted_at"),
        "accepted_by_name": q.get("accepted_by_name"),
        "declined_at": q.get("declined_at"),
    }


class QuoteAcceptBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    signature_data_url: str | None = Field(default=None, max_length=MAX_SIGNATURE_LEN)
    note: str | None = Field(default=None, max_length=500)


class QuoteDeclineBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


@router.get("/quote/{shortcode}")
async def get_public_quote(shortcode: str):
    """Return a redacted view of the quote for the accept landing page."""
    q = await db.svc_engineer_quotes.find_one(
        {"public_shortcode": shortcode}, {"_id": 0},
    )
    if not q:
        raise HTTPException(404, "Quote not found or no longer available")
    return _public_quote_view(q)


@router.post("/quote/{shortcode}/accept")
async def accept_public_quote(shortcode: str, body: QuoteAcceptBody):
    q = await db.svc_engineer_quotes.find_one(
        {"public_shortcode": shortcode}, {"_id": 0},
    )
    if not q:
        raise HTTPException(404, "Quote not found")
    if q["status"] in ("accepted", "invoiced"):
        raise HTTPException(410, "This quote has already been accepted.")
    if q["status"] in ("declined", "expired"):
        raise HTTPException(410, f"This quote is {q['status']} and can't be accepted.")
    set_payload: dict[str, Any] = {
        "status": "accepted",
        "accepted_at": _now(),
        "accepted_by_name": body.name.strip(),
        "accepted_by_note": (body.note or "").strip(),
        "accepted_via": "public_link",
        "updated_at": _now(),
    }
    if body.signature_data_url:
        set_payload["customer_signature_data_url"] = body.signature_data_url
    await db.svc_engineer_quotes.update_one(
        {"id": q["id"]},
        {"$set": set_payload,
         "$push": {"status_history": {
             "status": "accepted", "at": _now(),
             "via": "public_link", "by": body.name.strip(),
             "note": body.note,
         }}},
    )
    # Notify the engineer (best-effort — failures don't break the flow)
    try:
        await db.svc_case_events.insert_one({
            "id": secrets.token_urlsafe(8),
            "organization_id": q.get("organization_id"),
            "actor_id": q.get("engineer_id"),
            "kind": "notification",
            "subject": f"Quote {q['quote_number']} accepted",
            "body": f"{body.name.strip()} accepted your quote — £{q.get('total', 0):,.2f}.",
            "ref_kind": "engineer_quote",
            "ref_id": q["id"],
            "created_at": _now(),
            "read_at": None,
        })
    except Exception:
        pass
    return {"ok": True, "quote_number": q["quote_number"]}


@router.post("/quote/{shortcode}/decline")
async def decline_public_quote(shortcode: str, body: QuoteDeclineBody):
    q = await db.svc_engineer_quotes.find_one(
        {"public_shortcode": shortcode}, {"_id": 0},
    )
    if not q:
        raise HTTPException(404, "Quote not found")
    if q["status"] in ("accepted", "invoiced"):
        raise HTTPException(410, "This quote has already been accepted.")
    if q["status"] == "declined":
        raise HTTPException(410, "This quote has already been declined.")
    await db.svc_engineer_quotes.update_one(
        {"id": q["id"]},
        {"$set": {"status": "declined", "declined_at": _now(),
                  "declined_by_name": body.name.strip(),
                  "declined_reason": (body.reason or "").strip(),
                  "declined_via": "public_link",
                  "updated_at": _now()},
         "$push": {"status_history": {
             "status": "declined", "at": _now(),
             "via": "public_link", "by": body.name.strip(),
             "reason": body.reason,
         }}},
    )
    try:
        await db.svc_case_events.insert_one({
            "id": secrets.token_urlsafe(8),
            "organization_id": q.get("organization_id"),
            "actor_id": q.get("engineer_id"),
            "kind": "notification",
            "subject": f"Quote {q['quote_number']} declined",
            "body": f"{body.name.strip()} declined your quote.",
            "ref_kind": "engineer_quote",
            "ref_id": q["id"],
            "created_at": _now(),
            "read_at": None,
        })
    except Exception:
        pass
    return {"ok": True, "quote_number": q["quote_number"]}


__all__ = ["router", "generate_shortcode"]
