"""Master Admin → "Send invoice to client".

One-click email of a generated invoice PDF to the customer's billing
contact, with a signed public download link as a backup so the
recipient can re-fetch the document even if the email attachment is
stripped.

Flow
====

1. Master admin clicks "Send" on an invoice row.
2. ``POST /api/master-admin/orgs/{org_id}/billing/invoice/{invoice_id}/send``
   renders the PDF via :mod:`master_admin_billing` (so styling stays in
   one place), persists an ``invoice_share_links`` row containing a
   uuid4 token + expiry, then emails the PDF (Resend) with a public
   download URL.
3. Recipient hits ``GET /api/public/invoice-share/{token}`` — no auth.
   We verify the token is unexpired and return the PDF bytes.

Schema (``invoice_share_links``)
================================

::

    {
        "id":              uuid,
        "token":           uuid,
        "organization_id": str,
        "invoice_id":      str,
        "recipient_email": str,
        "subject":         str,
        "message":         str,
        "expires_at":      iso,
        "used_count":      int,
        "last_used_at":    iso | null,
        "created_by":      user_id,
        "created_at":      iso,
        "revoked":         bool,
    }
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email


router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 30
MAX_TTL_DAYS = 180


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public_base() -> str:
    """Frontend-facing base URL for share links. Falls back to the
    backend public URL so the link still resolves end-to-end."""
    return (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")


def _ccy_symbol(ccy: str) -> str:
    return {"GBP": "£", "EUR": "€", "USD": "$"}.get((ccy or "").upper(), "")


def _format_money(minor: int, ccy: str) -> str:
    return f"{_ccy_symbol(ccy)}{(minor or 0) / 100:,.2f}"


# ── Email body ──────────────────────────────────────────────────────


def _render_invoice_email_html(
    org_name: str,
    invoice: dict,
    download_url: str,
    sender_message: str,
    expires_at: datetime,
) -> str:
    """Branded HTML body — keeps colours close to the rest of the GymAxis
    transactional emails."""
    ccy = invoice.get("currency", "GBP")
    total = _format_money(invoice.get("total", 0), ccy)
    period = ""
    ps = (invoice.get("period_start") or "")[:10]
    pe = (invoice.get("period_end") or "")[:10]
    if ps and pe:
        period = f"{ps} → {pe}"
    expires_str = expires_at.strftime("%-d %b %Y")
    msg_block = ""
    if sender_message:
        # Conservative escaping: emails are sent over Resend HTML.
        safe = (
            sender_message
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        msg_block = (
            f'<div style="background:#f0f7ff;border-left:4px solid #0055FF;'
            f'padding:14px 18px;margin:18px 0;border-radius:4px;color:#1a1a1a;'
            f'line-height:1.6;font-size:14px;">{safe}</div>'
        )
    return f"""<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;background:#fff;">
  <div style="background:#0A0C10;padding:28px 30px;text-align:center;">
    <h1 style="color:#19CDFF;margin:0;font-size:22px;letter-spacing:-0.3px;">Invoice from {org_name or 'GymAxis AI'}</h1>
    <p style="color:#9ca3af;margin:6px 0 0;font-size:13px;">Invoice {invoice.get('number','')}</p>
  </div>
  <div style="padding:32px 30px;color:#1a1a1a;">
    <p style="line-height:1.6;margin:0 0 12px;">Hi,</p>
    <p style="line-height:1.6;margin:0 0 16px;">
      Please find attached invoice <strong>{invoice.get('number','')}</strong>
      {f"covering {period}" if period else ""}.
    </p>
    {msg_block}
    <table style="width:100%;border-collapse:collapse;margin:18px 0;font-size:14px;">
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Total due</td>
        <td style="padding:8px 0;text-align:right;font-weight:700;">{total}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Currency</td>
        <td style="padding:8px 0;text-align:right;">{ccy}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Status</td>
        <td style="padding:8px 0;text-align:right;text-transform:capitalize;">{invoice.get('status','issued')}</td>
      </tr>
    </table>
    <div style="text-align:center;margin:28px 0;">
      <a href="{download_url}" style="display:inline-block;background:#19CDFF;color:#0A0C10;padding:14px 32px;
         text-decoration:none;border-radius:8px;font-weight:700;font-size:14px;letter-spacing:0.3px;">
         Download invoice PDF →
      </a>
    </div>
    <p style="color:#6b7280;font-size:12px;line-height:1.6;text-align:center;">
      This secure link expires on {expires_str}. The PDF is also attached to this email.
    </p>
  </div>
  <div style="background:#f5f5f5;padding:16px 30px;text-align:center;">
    <p style="color:#9ca3af;font-size:11px;margin:0;">Sent from {org_name or 'GymAxis AI'} billing</p>
  </div>
</div>"""


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/master-admin/orgs/{org_id}/billing/invoice/{invoice_id}/send")
async def send_invoice_to_client(
    org_id: str,
    invoice_id: str,
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Email an invoice PDF to the customer's billing contact."""
    _require_master(user)

    inv = await db.org_billing_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id}, {"_id": 0}
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organization not found")

    # Recipient: caller-supplied wins, else org primary contact.
    requested_email = (payload.get("to_email") or "").strip()
    fallback_email = (
        org.get("primary_contact_email")
        or (org.get("primary_contact") or {}).get("email")
        or ""
    ).strip()
    recipient = requested_email or fallback_email
    if "@" not in recipient:
        raise HTTPException(400, "Recipient email is required")

    # TTL — clamp to safe bounds so we don't hand out forever-valid links.
    try:
        ttl_days = int(payload.get("ttl_days") or DEFAULT_TTL_DAYS)
    except (TypeError, ValueError):
        ttl_days = DEFAULT_TTL_DAYS
    ttl_days = max(1, min(ttl_days, MAX_TTL_DAYS))
    expires_at = _now() + timedelta(days=ttl_days)

    sender_message = (payload.get("message") or "").strip()[:2000]

    # Render the PDF using the same renderer the download endpoint uses.
    from routes.master_admin_billing import _render_invoice_pdf
    pdf_bytes = _render_invoice_pdf(inv, org)

    # Persist the share link.
    token = uuid.uuid4().hex
    share = {
        "id": str(uuid.uuid4()),
        "token": token,
        "organization_id": org_id,
        "invoice_id": invoice_id,
        "recipient_email": recipient,
        "subject": f"Invoice {inv.get('number','')} from {org.get('name','GymAxis AI')}",
        "message": sender_message,
        "expires_at": expires_at.isoformat(),
        "used_count": 0,
        "last_used_at": None,
        "created_by": user.get("id"),
        "created_at": _now().isoformat(),
        "revoked": False,
    }
    await db.invoice_share_links.insert_one(dict(share))

    base = _public_base()
    download_url = f"{base}/api/public/invoice-share/{token}" if base else f"/api/public/invoice-share/{token}"

    html = _render_invoice_email_html(
        org_name=org.get("name", ""),
        invoice=inv,
        download_url=download_url,
        sender_message=sender_message,
        expires_at=expires_at,
    )
    attachments = [{
        "filename": f"{inv.get('number','invoice')}.pdf",
        "content": base64.b64encode(pdf_bytes).decode(),
    }]
    sent_ok = await send_email(
        recipient,
        share["subject"],
        html,
        attachments=attachments,
        category="billing",
    )

    # Append a send record on the invoice for the in-app audit trail.
    await db.org_billing_invoices.update_one(
        {"id": invoice_id, "organization_id": org_id},
        {"$push": {"sends": {
            "share_id": share["id"],
            "recipient": recipient,
            "sent_at": share["created_at"],
            "sent_by": user.get("id"),
            "delivered": bool(sent_ok),
        }}},
    )

    return {
        "sent": bool(sent_ok),
        "recipient": recipient,
        "share_id": share["id"],
        "share_url": download_url,
        "expires_at": share["expires_at"],
        "delivered_via_email": bool(sent_ok),
    }


@router.get("/public/invoice-share/{token}")
async def public_invoice_share(token: str) -> Response:
    """Public, no-auth invoice download via signed token."""
    share = await db.invoice_share_links.find_one({"token": token}, {"_id": 0})
    if not share or share.get("revoked"):
        raise HTTPException(404, "Link not found or revoked")
    expires_at = share.get("expires_at") or ""
    try:
        exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(404, "Link malformed")
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    if exp_dt < _now():
        raise HTTPException(410, "Link expired")

    inv = await db.org_billing_invoices.find_one(
        {"id": share["invoice_id"], "organization_id": share["organization_id"]},
        {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice missing")
    org = await db.organizations.find_one({"id": share["organization_id"]}, {"_id": 0}) or {}

    from routes.master_admin_billing import _render_invoice_pdf
    pdf_bytes = _render_invoice_pdf(inv, org)

    # Audit access.
    await db.invoice_share_links.update_one(
        {"id": share["id"]},
        {"$inc": {"used_count": 1}, "$set": {"last_used_at": _now().isoformat()}},
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{inv.get("number","invoice")}.pdf"'},
    )


@router.get("/master-admin/orgs/{org_id}/billing/invoice/{invoice_id}/sends")
async def list_invoice_sends(
    org_id: str,
    invoice_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Send history for one invoice (used by the admin UI tooltip)."""
    _require_master(user)
    inv = await db.org_billing_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id},
        {"_id": 0, "sends": 1, "number": 1},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return {"sends": inv.get("sends") or [], "invoice_number": inv.get("number")}


# ── Indexes ─────────────────────────────────────────────────────────


async def ensure_invoice_share_indexes() -> None:
    try:
        await db.invoice_share_links.create_index("token", unique=True)
        await db.invoice_share_links.create_index([("organization_id", 1), ("created_at", -1)])
        await db.invoice_share_links.create_index([("invoice_id", 1)])
    except Exception:
        logger.exception("ensure_invoice_share_indexes failed (non-fatal)")
