"""Iter 216h131 — Stripe Payment Link on engineer invoices.

Generates a single-use **Stripe Checkout Session** keyed to the
engineer invoice and attaches it to the invoice email. On
successful payment a Stripe webhook fires and the invoice is
auto-marked `paid` + a customer receipt email is sent via Resend.

The Engineer's `earnings_this_month` KPI on the Home dashboard
automatically picks this up because the dashboard query sums all
`accepted+invoiced` quote totals — and the underlying quote (if the
invoice was generated from one) is already marked `invoiced`.

Endpoints (all `/api/svc/engineer` and gated by
`require_engineer_app_access`):
  • POST   /invoices/{id}/payment-link  → ensure a Checkout Session
                                          exists; returns {url, session_id}.
  • POST   /webhooks/stripe/engineer-invoices  → public Stripe webhook.
  • GET    /public/invoice/{shortcode}/receipt → public confirmation
                                                  data after redirect.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from routes.partners import require_engineer_app_access
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get("STRIPE_API_KEY")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET") or os.environ.get(
    "STRIPE_INVOICE_WEBHOOK_SECRET")

router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Invoice Payments"],
    dependencies=[Depends(require_engineer_app_access)],
)
# Webhook + public confirmation router (no auth)
public_router = APIRouter(tags=["Public · Engineer Invoice Payments"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_short() -> str:
    return secrets.token_urlsafe(8)[:10]


async def _get_invoice(invoice_id: str, user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    inv = await db.svc_engineer_invoices.find_one(
        {"id": invoice_id, "organization_id": org}, {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.get("engineer_id") != user.get("id"):
        raise HTTPException(403, "Not your invoice")
    return inv


def _origin() -> str:
    return (os.environ.get("PUBLIC_ORIGIN")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "").rstrip("/")


async def _ensure_payment_link(invoice: dict) -> dict:
    """Return existing payment link or create a fresh Stripe Checkout
    Session and persist it on the invoice."""
    if not stripe.api_key:
        raise HTTPException(500, "Stripe is not configured on this server")
    existing_url = invoice.get("stripe_payment_url")
    if existing_url and invoice.get("status") not in ("paid", "void"):
        return {
            "url": existing_url,
            "session_id": invoice.get("stripe_session_id"),
            "shortcode": invoice.get("public_shortcode"),
        }
    if invoice.get("status") in ("paid", "void"):
        raise HTTPException(409, f"Invoice is {invoice['status']}; cannot pay.")
    total = float(invoice.get("total") or 0)
    if total <= 0:
        raise HTTPException(400, "Invoice total must be > 0 to take card payment.")
    # Public shortcode used by the success page
    shortcode = invoice.get("public_shortcode") or _new_short()
    origin = _origin()
    success_url = f"{origin}/i/{shortcode}/paid" if origin else None
    cancel_url = f"{origin}/i/{shortcode}/cancelled" if origin else None
    customer_email = (invoice.get("customer_email") or "").strip() or None

    metadata = {
        "invoice_id": invoice["id"],
        "invoice_number": invoice.get("invoice_number") or "",
        "engineer_id": invoice.get("engineer_id") or "",
        "organization_id": invoice.get("organization_id") or "",
        "tenant": "engineer_invoice",
    }
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "gbp",
                    "product_data": {
                        "name": f"{invoice.get('invoice_number') or 'Invoice'} · {invoice.get('description_of_work') or 'Engineer invoice'}",
                        "description": (invoice.get("description_of_work") or "")[:300] or None,
                    },
                    "unit_amount": int(round(total * 100)),
                },
                "quantity": 1,
            }],
            customer_email=customer_email,
            success_url=success_url or "https://gymaxis.com/payment-success",
            cancel_url=cancel_url or "https://gymaxis.com/payment-cancelled",
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
        )
    except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
        logger.warning("[engineer_invoice_payment] stripe error: %s", exc)
        raise HTTPException(502, f"Stripe error: {exc.user_message or str(exc)}")

    await db.svc_engineer_invoices.update_one(
        {"id": invoice["id"]},
        {"$set": {
            "stripe_session_id": session.id,
            "stripe_payment_url": session.url,
            "stripe_session_created_at": _now(),
            "public_shortcode": shortcode,
            "updated_at": _now(),
        }},
    )
    return {"url": session.url, "session_id": session.id, "shortcode": shortcode}


@router.post("/invoices/{invoice_id}/payment-link")
async def create_payment_link(invoice_id: str, user=Depends(get_current_user)):
    inv = await _get_invoice(invoice_id, user)
    out = await _ensure_payment_link(inv)
    return {"ok": True, **out}


# ─────────────────────── Public webhook ───────────────────────────


async def _mark_invoice_paid(invoice: dict, *, paid_via: str = "stripe") -> dict:
    paid_at = _now()
    set_payload = {
        "status": "paid",
        "paid_at": paid_at,
        "paid_via": paid_via,
        "updated_at": paid_at,
    }
    await db.svc_engineer_invoices.update_one(
        {"id": invoice["id"]},
        {"$set": set_payload,
         "$push": {"status_history": {"status": "paid", "at": paid_at, "via": paid_via}}},
    )
    # Notify the engineer
    try:
        await db.svc_case_events.insert_one({
            "id": f"inv-paid-{invoice['id']}-{int(datetime.now(timezone.utc).timestamp())}",
            "organization_id": invoice.get("organization_id"),
            "actor_id": invoice.get("engineer_id"),
            "kind": "notification",
            "subject": f"Invoice {invoice.get('invoice_number')} paid",
            "body": f"£{float(invoice.get('total') or 0):,.2f} received from {invoice.get('customer_name') or 'customer'}.",
            "ref_kind": "engineer_invoice",
            "ref_id": invoice["id"],
            "created_at": paid_at,
            "read_at": None,
        })
    except Exception:
        pass
    # Fire receipt email to the customer (best-effort)
    customer_email = (invoice.get("customer_email") or "").strip().lower()
    if customer_email and "@" in customer_email:
        try:
            html = _receipt_html(invoice)
            await send_email(
                to=customer_email,
                subject=f"Receipt · {invoice.get('invoice_number')} · GymAxis",
                html=html,
                organization_id=invoice.get("organization_id"),
            )
        except Exception as exc:
            logger.info("[engineer_invoice_payment] receipt email failed: %s", exc)
    return {**invoice, **set_payload}


def _receipt_html(invoice: dict) -> str:
    primary = "#1d4ed8"; accent = "#6366f1"
    customer = invoice.get("customer_name") or "there"
    engineer = invoice.get("engineer_name") or "Your engineer"
    ino = invoice.get("invoice_number") or ""
    total = float(invoice.get("total") or 0)
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:600px;margin:0 auto;padding:24px;">
      <div style="background:linear-gradient(135deg,{primary} 0%,{accent} 100%);padding:24px;border-radius:12px;color:white;margin-bottom:24px;">
        <p style="margin:0;font-size:12px;letter-spacing:.2em;text-transform:uppercase;opacity:.85;">GymAxis · Payment Received</p>
        <h1 style="margin:6px 0 0;font-size:24px;font-weight:700;">{ino}</h1>
      </div>
      <p style="font-size:16px;">Hi {customer},</p>
      <p style="font-size:14px;line-height:1.6;color:#334155;">
        We've received your card payment of <strong>£{total:,.2f}</strong> for invoice <strong>{ino}</strong>. Thanks!
      </p>
      <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:14px;margin:18px 0;">
        <table style="width:100%;font-size:13px;color:#334155;">
          <tr><td>Amount received</td><td style="text-align:right;font-weight:700;color:{primary};">£{total:,.2f}</td></tr>
          <tr><td>Paid via</td><td style="text-align:right;">Stripe (card)</td></tr>
        </table>
      </div>
      <p style="font-size:14px;">All the best,<br/><strong>{engineer}</strong></p>
      <p style="font-size:11px;color:#94a3b8;margin-top:30px;">Powered by GymAxis · Field Service for Fitness Equipment</p>
    </div>
    """


@public_router.post("/webhooks/stripe/engineer-invoices")
async def stripe_engineer_invoices_webhook(request: Request):
    """Stripe webhook for `checkout.session.completed`.

    Only acts on sessions whose metadata says `tenant=engineer_invoice`.
    Other tenants' webhooks are ignored.
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if WEBHOOK_SECRET and sig:
        try:
            event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:  # type: ignore[attr-defined]
            raise HTTPException(400, "Invalid signature")
    else:
        try:
            event = stripe.Event.construct_from(__import__("json").loads(payload), stripe.api_key)
        except Exception:
            raise HTTPException(400, "Invalid body")
    if event["type"] != "checkout.session.completed":
        return {"ok": True, "ignored": True, "type": event["type"]}
    session = event["data"]["object"]
    meta = session.get("metadata") or {}
    if meta.get("tenant") != "engineer_invoice":
        return {"ok": True, "ignored": True, "tenant": meta.get("tenant")}
    invoice_id = meta.get("invoice_id")
    if not invoice_id:
        return {"ok": False, "reason": "no invoice_id"}
    inv = await db.svc_engineer_invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        return {"ok": False, "reason": "invoice not found"}
    if inv["status"] == "paid":
        return {"ok": True, "already_paid": True}
    await _mark_invoice_paid(inv, paid_via="stripe_checkout")
    return {"ok": True, "invoice_id": invoice_id, "status": "paid"}


# Convenience: bypass for local/test fixtures — never expose this in prod
@router.post("/invoices/{invoice_id}/_test-mark-paid")
async def test_mark_paid(invoice_id: str, user=Depends(get_current_user)):
    """Test-only: simulate the webhook by marking an invoice paid.

    Master admin only — used by E2E tests so we don't have to spin up a
    real Stripe session in CI.
    """
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Admin only")
    inv = await db.svc_engineer_invoices.find_one(
        {"id": invoice_id, "organization_id": user.get("organization_id")},
        {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    await _mark_invoice_paid(inv, paid_via="test_harness")
    fresh = await db.svc_engineer_invoices.find_one({"id": invoice_id}, {"_id": 0})
    return fresh


# ───────────────────── Public confirmation ────────────────────────


@public_router.get("/public/invoice/{shortcode}/receipt")
async def public_invoice_receipt(shortcode: str):
    """Minimal data for the post-redirect confirmation page."""
    inv = await db.svc_engineer_invoices.find_one(
        {"public_shortcode": shortcode}, {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return {
        "invoice_number": inv.get("invoice_number"),
        "customer_name": inv.get("customer_name"),
        "status": inv.get("status"),
        "total": inv.get("total"),
        "paid_at": inv.get("paid_at"),
        "engineer_name": inv.get("engineer_name"),
    }


__all__ = ["router", "public_router", "_ensure_payment_link"]
