"""
Pulse Stripe Connect — Phase 2.

Adds the runtime side of Stripe Connect Standard once an account is linked:

  • POST /api/stripe-connect/webhook                — Stripe → us. Signed
    (`STRIPE_CONNECT_WEBHOOK_SECRET`) when configured. Handles
    `account.updated`, `charge.succeeded`, `charge.refunded`, and
    `application_fee.created` — anything else is ack-and-ignored so Stripe
    stops retrying.
  • POST /api/stripe-connect/charges                — issue a destination/
    application-fee charge on the connected account from the platform side.
    Always uses the dynamic platform fee from `platform_config`.
  • GET  /api/stripe-connect/analytics              — profit-per-customer
    aggregates (revenue − fees − refunds) for the connected account.
  • POST /api/stripe-connect/dev/seed-events        — DEV ONLY. Seeds a small
    set of fake charges/refunds so the analytics dashboard has something to
    show before live Stripe events arrive. No-op if real charges already
    exist for this account.

Storage:
  • db.stripe_charges          — one row per charge (cents, fees, refunds, customer)
  • db.stripe_connect_events   — raw signed events (ledger / debugging)

The actual charge call uses the standard Stripe REST API via httpx — we don't
need the official SDK because the surface we touch is small and we already use
httpx for the OAuth handshake.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user
from utils.database import db

# Re-use the gates and constants we already defined in phase 1.
from routes.pulse_master_admin import (
    _require_pulse_or_master,
    _connect_account_doc_filter,
    _get_pricing_config,
)

logger = logging.getLogger(__name__)
router = APIRouter()

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_CONNECT_WEBHOOK_SECRET = os.environ.get("STRIPE_CONNECT_WEBHOOK_SECRET", "")


# ── Helpers ───────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _connected_account_for_event(account_id: Optional[str]) -> Optional[dict]:
    if not account_id:
        return None
    return await db.stripe_connect_accounts.find_one({"stripe_account_id": account_id}, {"_id": 0})


def _verify_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """Stripe signing scheme v1 — `t=<ts>,v1=<sig>`. We accept timestamps
    within a 5-minute window to mitigate replay."""
    if not signature_header or not secret:
        return False
    try:
        parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
        ts = parts.get("t")
        sig = parts.get("v1")
        if not ts or not sig:
            return False
        if abs(int(time.time()) - int(ts)) > 300:
            return False
        signed_payload = f"{ts}.".encode() + payload
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False


# ── Webhook handlers ──────────────────────────────────────────────────────


@router.post("/stripe-connect/webhook")
async def stripe_connect_webhook(request: Request):
    """Receive Stripe Connect events.

    Note: the body must be the *raw* unparsed bytes for signature verification.
    Stripe will hammer this endpoint with retries for 3 days if we 5xx, so we
    swallow handler exceptions and ack 200 once the signature is valid (the
    error is logged for follow-up).
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    # When the webhook secret is set, refuse anything that doesn't sign cleanly.
    # When it isn't (dev / pre-prod), we still log everything but skip auth so
    # the operator can wire integration tests without a Stripe webhook in front.
    # Fail closed: require a valid signature. The only way to skip verification
    # is an explicit dev override (STRIPE_CONNECT_WEBHOOK_ALLOW_UNSIGNED=true),
    # so a missing/empty secret in production rejects forged Connect events.
    allow_unsigned = (os.environ.get("STRIPE_CONNECT_WEBHOOK_ALLOW_UNSIGNED", "") or "").lower() == "true"
    if STRIPE_CONNECT_WEBHOOK_SECRET:
        if not _verify_signature(payload, sig, STRIPE_CONNECT_WEBHOOK_SECRET):
            raise HTTPException(status_code=400, detail="Invalid signature")
    elif not allow_unsigned:
        raise HTTPException(status_code=400, detail="Webhook signature verification not configured")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON")

    event_id = event.get("id")
    event_type = event.get("type")
    account_id = event.get("account")  # Stripe attaches this on Connect events
    data_object = (event.get("data") or {}).get("object") or {}

    # Idempotency — Stripe can deliver the same event twice. We check before
    # processing rather than relying on a unique index because a duplicate
    # insert on a missing/poorly-named index would silently duplicate work.
    if event_id:
        existing = await db.stripe_connect_events.find_one({"id": event_id}, {"_id": 0, "id": 1})
        if existing:
            logger.info("connect webhook duplicate %s — skipping", event_id)
            return {"received": True, "duplicate": True, "type": event_type}

    await db.stripe_connect_events.insert_one({
        "id": event_id or str(uuid.uuid4()),
        "type": event_type,
        "account_id": account_id,
        "received_at": _now_iso(),
        "raw": event,
    })

    handler = _EVENT_HANDLERS.get(event_type)
    if handler:
        try:
            await handler(event, data_object, account_id)
        except Exception as exc:  # pragma: no cover — non-blocking
            logger.exception("connect webhook handler %s failed: %s", event_type, exc)
    return {"received": True, "type": event_type}


async def _handle_account_updated(event: dict, obj: dict, account_id: Optional[str]):
    """Sync `charges_enabled` / `payouts_enabled` flags onto our local record.
    Useful right after onboarding when Stripe finishes verification."""
    if not account_id:
        return
    await db.stripe_connect_accounts.update_one(
        {"stripe_account_id": account_id},
        {"$set": {
            "charges_enabled": obj.get("charges_enabled"),
            "payouts_enabled": obj.get("payouts_enabled"),
            "country": obj.get("country"),
            "default_currency": obj.get("default_currency"),
            "details_submitted": obj.get("details_submitted"),
            "updated_at": _now_iso(),
        }},
    )


async def _upsert_charge_row(charge: dict, account_id: Optional[str]):
    """Idempotent upsert into `db.stripe_charges` so analytics aggregates stay
    accurate whether the data came from the create-charge endpoint, a Stripe
    webhook, or our dev seeder."""
    charge_id = charge.get("id") or charge.get("stripe_charge_id")
    if not charge_id:
        return
    customer_email = charge.get("billing_details", {}).get("email") if isinstance(charge.get("billing_details"), dict) else None
    customer_email = (
        customer_email
        or charge.get("receipt_email")
        or charge.get("customer_email")
        or "unknown@unknown"
    )
    customer_name = charge.get("customer_name") or charge.get("billing_details", {}).get("name") if isinstance(charge.get("billing_details"), dict) else None
    customer_name = customer_name or charge.get("customer_name") or ""

    doc = {
        "id": charge_id,  # Stripe id is the natural primary key
        "stripe_account_id": account_id,
        "amount": int(charge.get("amount") or 0),  # cents
        "currency": (charge.get("currency") or "gbp").lower(),
        "application_fee_amount": int(charge.get("application_fee_amount") or 0),
        "amount_refunded": int(charge.get("amount_refunded") or 0),
        "customer_email": (customer_email or "").lower(),
        "customer_name": customer_name,
        "status": charge.get("status", "succeeded"),
        "created_at": charge.get("created_at") or datetime.fromtimestamp(charge.get("created") or time.time(), tz=timezone.utc).isoformat(),
        "metadata": charge.get("metadata") or {},
        "updated_at": _now_iso(),
    }
    await db.stripe_charges.update_one({"id": charge_id}, {"$set": doc}, upsert=True)


async def _handle_charge_succeeded(event: dict, obj: dict, account_id: Optional[str]):
    await _upsert_charge_row(obj, account_id)


async def _handle_charge_refunded(event: dict, obj: dict, account_id: Optional[str]):
    # `obj` is the charge after refund — `amount_refunded` is the cumulative refund total.
    await _upsert_charge_row(obj, account_id)


async def _handle_application_fee_created(event: dict, obj: dict, account_id: Optional[str]):
    """Stripe creates a separate application-fee object after the charge.
    We project the fee amount onto the matching charge row so analytics
    don't have to join across collections."""
    charge_id = obj.get("charge")
    if not charge_id:
        return
    await db.stripe_charges.update_one(
        {"id": charge_id},
        {"$set": {
            "application_fee_amount": int(obj.get("amount") or 0),
            "application_fee_currency": (obj.get("currency") or "gbp").lower(),
            "application_fee_id": obj.get("id"),
            "updated_at": _now_iso(),
        }},
        upsert=False,
    )


_EVENT_HANDLERS = {
    "account.updated": _handle_account_updated,
    "charge.succeeded": _handle_charge_succeeded,
    "charge.refunded": _handle_charge_refunded,
    "application_fee.created": _handle_application_fee_created,
}


# ── Charge creation ───────────────────────────────────────────────────────


class ChargeCreate(BaseModel):
    """Request payload for issuing a charge on the connected account.

    `amount` is the gross charge amount in the major currency unit (e.g.
    ``99.0`` for £99). The platform fee is always computed server-side from
    `platform_config` so the frontend cannot manipulate it.
    """
    amount: float = Field(gt=0, le=100000)
    currency: Optional[str] = None  # defaults to pricing config currency
    customer_email: EmailStr
    customer_name: Optional[str] = None
    description: Optional[str] = None
    # Required for live Stripe charges (e.g. "pm_card_visa"). Optional for
    # dev-fake-account simulated charges where we bypass Stripe entirely.
    payment_method: Optional[str] = None
    metadata: Optional[dict] = None


def _calc_application_fee(amount_cents: int, pricing: dict) -> int:
    flat = int(round(float(pricing.get("platform_fee_per_customer") or 0) * 100))
    pct = float(pricing.get("platform_fee_pct") or 0)
    pct_amount = int(round(amount_cents * pct / 100))
    fee = flat + pct_amount
    # Stripe rejects fees larger than the charge — cap defensively.
    return max(0, min(fee, amount_cents - 1)) if amount_cents > 0 else 0


@router.post("/stripe-connect/charges")
async def create_charge(body: ChargeCreate, user: dict = Depends(get_current_user)) -> dict:
    """Create a destination charge on the connected account with the dynamic
    platform fee. The charge is recorded locally before we hit Stripe so a
    network blip after Stripe accepts can be reconciled via the webhook."""
    _require_pulse_or_master(user)
    account = await db.stripe_connect_accounts.find_one(_connect_account_doc_filter(user), {"_id": 0})
    if not account or not account.get("stripe_account_id"):
        raise HTTPException(status_code=400, detail="Stripe is not connected yet")
    if not account.get("charges_enabled"):
        raise HTTPException(
            status_code=400,
            detail="Stripe still verifying the connected account — charges are disabled",
        )
    pricing = await _get_pricing_config()
    currency = (body.currency or pricing.get("currency") or "gbp").lower()
    amount_cents = int(round(body.amount * 100))
    application_fee = _calc_application_fee(amount_cents, pricing)

    # Dev-fake-account short-circuit: when the connected account is one we
    # provisioned via /dev/fake-connection, skip the live Stripe call and
    # record a simulated charge directly. Lets the platform admin smoke-test
    # the fee maths and analytics without standing up real Stripe creds.
    if account.get("_dev_fake"):
        sim_charge_id = f"dev_ch_{uuid.uuid4().hex[:14]}"
        await _upsert_charge_row({
            "id": sim_charge_id,
            "amount": amount_cents,
            "currency": currency,
            "application_fee_amount": application_fee,
            "amount_refunded": 0,
            "billing_details": {"email": body.customer_email, "name": body.customer_name or ""},
            "customer_name": body.customer_name or "",
            "status": "succeeded",
            "created": int(time.time()),
            "metadata": {**(body.metadata or {}), "source": "dev_test_charge"},
        }, account["stripe_account_id"])
        return {
            "ok": True,
            "charge_id": sim_charge_id,
            "amount": amount_cents,
            "currency": currency,
            "application_fee_amount": application_fee,
            "status": "succeeded",
            "simulated": True,
        }

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured on server")

    if not body.payment_method:
        raise HTTPException(
            status_code=400,
            detail="payment_method is required for live Stripe charges (e.g. 'pm_card_visa').",
        )

    payload = {
        "amount": str(amount_cents),
        "currency": currency,
        "payment_method": body.payment_method,
        "confirm": "true",
        "off_session": "true",
        "application_fee_amount": str(application_fee),
        "transfer_data[destination]": account["stripe_account_id"],
        "description": body.description or f"Pulse Fitness platform charge for {body.customer_email}",
        "receipt_email": body.customer_email,
        "metadata[customer_email]": body.customer_email,
        "metadata[customer_name]": body.customer_name or "",
        "metadata[platform_fee_flat]": str(pricing.get("platform_fee_per_customer", 0)),
        "metadata[platform_fee_pct]": str(pricing.get("platform_fee_pct", 0)),
    }
    if body.metadata:
        for k, v in body.metadata.items():
            payload[f"metadata[{k}]"] = str(v)

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.stripe.com/v1/payment_intents",
            data=payload,
            auth=(STRIPE_SECRET_KEY, ""),
        )
    if r.status_code != 200:
        logger.warning("Stripe charge create failed: %s %s", r.status_code, r.text[:400])
        try:
            err = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            err = r.text[:200]
        raise HTTPException(status_code=502, detail=f"Stripe error: {err}")

    intent = r.json()
    # PaymentIntent → primary Charge id is in latest_charge or charges.data[0].
    charge_id = intent.get("latest_charge") or (((intent.get("charges") or {}).get("data") or [{}])[0]).get("id")
    if not charge_id:
        # Still ack — Stripe will fire charge.succeeded shortly.
        charge_id = intent.get("id")

    # Record locally. The webhook will overwrite with canonical data when it arrives.
    await _upsert_charge_row({
        "id": charge_id,
        "amount": amount_cents,
        "currency": currency,
        "application_fee_amount": application_fee,
        "amount_refunded": 0,
        "billing_details": {"email": body.customer_email, "name": body.customer_name or ""},
        "customer_name": body.customer_name or "",
        "status": intent.get("status", "succeeded"),
        "created": int(time.time()),
        "metadata": dict(body.metadata or {}),
    }, account["stripe_account_id"])

    return {
        "ok": True,
        "charge_id": charge_id,
        "amount": amount_cents,
        "currency": currency,
        "application_fee_amount": application_fee,
        "status": intent.get("status"),
    }


# ── Analytics ─────────────────────────────────────────────────────────────


@router.get("/stripe-connect/analytics")
async def stripe_connect_analytics(user: dict = Depends(get_current_user)) -> dict:
    """Profit-per-customer aggregates for the calling pulse admin's connected
    account. Numbers are in major currency units (e.g. pounds, not pence)."""
    _require_pulse_or_master(user)
    account = await db.stripe_connect_accounts.find_one(_connect_account_doc_filter(user), {"_id": 0})
    if not account:
        return {"connected": False, "totals": {}, "customers": []}

    account_id = account["stripe_account_id"]
    pipeline = [
        {"$match": {"stripe_account_id": account_id}},
        {"$group": {
            "_id": "$customer_email",
            "customer_email": {"$first": "$customer_email"},
            "customer_name": {"$first": "$customer_name"},
            "currency": {"$first": "$currency"},
            "charges_count": {"$sum": 1},
            "gross_revenue_cents": {"$sum": "$amount"},
            "platform_fees_cents": {"$sum": "$application_fee_amount"},
            "refunded_cents": {"$sum": "$amount_refunded"},
            "first_charge": {"$min": "$created_at"},
            "last_charge": {"$max": "$created_at"},
        }},
        {"$project": {
            "_id": 0,
            "customer_email": 1, "customer_name": 1, "currency": 1,
            "charges_count": 1,
            "gross_revenue": {"$divide": ["$gross_revenue_cents", 100]},
            "platform_fees": {"$divide": ["$platform_fees_cents", 100]},
            "refunded": {"$divide": ["$refunded_cents", 100]},
            "platform_profit": {"$divide": [
                {"$subtract": ["$platform_fees_cents", "$refunded_cents"]}, 100,
            ]},
            "first_charge": 1, "last_charge": 1,
        }},
        {"$sort": {"platform_profit": -1}},
    ]
    customers = await db.stripe_charges.aggregate(pipeline).to_list(1000)

    # Roll-up totals so the frontend can show headline numbers without
    # re-summing on the client.
    total_gross = sum(c.get("gross_revenue", 0) for c in customers)
    total_fees = sum(c.get("platform_fees", 0) for c in customers)
    total_refunded = sum(c.get("refunded", 0) for c in customers)
    return {
        "connected": True,
        "currency": account.get("default_currency") or "gbp",
        "totals": {
            "customers": len(customers),
            "charges": sum(c.get("charges_count", 0) for c in customers),
            "gross_revenue": round(total_gross, 2),
            "platform_fees": round(total_fees, 2),
            "refunded": round(total_refunded, 2),
            "platform_profit": round(total_fees - total_refunded, 2),
            "pulse_take_home": round(total_gross - total_fees - total_refunded, 2),
        },
        "customers": customers,
    }


# ── Dev-mode seeder ───────────────────────────────────────────────────────


@router.post("/stripe-connect/dev/seed-events")
async def dev_seed_events(user: dict = Depends(get_current_user)) -> dict:
    """Seed a small set of fake charges/refunds against the calling pulse
    admin's connected account so the analytics dashboard has data to show
    before live Stripe events arrive.

    Refuses to run if real charges already exist for the account so we never
    pollute live data.
    """
    _require_pulse_or_master(user)
    account = await db.stripe_connect_accounts.find_one(_connect_account_doc_filter(user), {"_id": 0})
    if not account:
        raise HTTPException(status_code=400, detail="Connect a Stripe account first (dev seed needs an account_id to attach to)")

    account_id = account["stripe_account_id"]
    existing = await db.stripe_charges.count_documents({"stripe_account_id": account_id})
    if existing > 0:
        raise HTTPException(status_code=409, detail=f"{existing} charges already exist for this account — refusing to seed")

    pricing = await _get_pricing_config()
    currency = (pricing.get("currency") or "gbp").lower()

    # 6 fake customers with varied charge counts & one refund so the analytics
    # roll-up has interesting shapes to render.
    SAMPLE = [
        {"email": "leeds-fitness@example.com",      "name": "Leeds Fitness",      "charges": [99.0, 99.0, 99.0]},
        {"email": "manchester-gym@example.com",     "name": "Manchester Gym",     "charges": [149.0, 149.0]},
        {"email": "brighton-leisure@example.com",   "name": "Brighton Leisure",   "charges": [49.0, 49.0, 49.0, 49.0, 49.0]},
        {"email": "edinburgh-club@example.com",     "name": "Edinburgh Club",     "charges": [199.0]},
        {"email": "cardiff-strength@example.com",   "name": "Cardiff Strength",   "charges": [89.0, 89.0], "refund": 89.0},
        {"email": "newcastle-pulse@example.com",    "name": "Newcastle Pulse",    "charges": [129.0, 129.0, 129.0]},
    ]
    seeded = 0
    now_ts = int(time.time())
    for cust in SAMPLE:
        for i, amount in enumerate(cust["charges"]):
            amount_cents = int(round(amount * 100))
            fee = _calc_application_fee(amount_cents, pricing)
            refund_cents = int(round(cust.get("refund", 0) * 100)) if i == len(cust["charges"]) - 1 else 0
            await _upsert_charge_row({
                "id": f"dev_ch_{uuid.uuid4().hex[:14]}",
                "amount": amount_cents,
                "currency": currency,
                "application_fee_amount": fee,
                "amount_refunded": refund_cents,
                "billing_details": {"email": cust["email"], "name": cust["name"]},
                "customer_name": cust["name"],
                "status": "succeeded",
                "created": now_ts - (seeded + 1) * 86400,  # back-date so first_charge/last_charge differ
                "metadata": {"source": "dev_seed"},
            }, account_id)
            seeded += 1
    return {"ok": True, "seeded": seeded, "account_id": account_id}


@router.post("/stripe-connect/dev/fake-connection")
async def dev_fake_connection(user: dict = Depends(get_current_user)) -> dict:
    """DEV ONLY. Insert a fake `stripe_connect_accounts` row so the analytics
    seeder has something to attach to before the real OAuth flow is wired.

    Refuses to overwrite a real (non-dev) connection so we can't accidentally
    nuke a production account record.
    """
    _require_pulse_or_master(user)
    flt = _connect_account_doc_filter(user)
    existing = await db.stripe_connect_accounts.find_one(flt, {"_id": 0})
    if existing and not existing.get("stripe_account_id", "").startswith("acct_dev_"):
        raise HTTPException(
            status_code=409,
            detail="A real Stripe connection already exists — refusing to replace it with a dev fake.",
        )
    fake_id = f"acct_dev_{uuid.uuid4().hex[:14]}"
    now = _now_iso()
    await db.stripe_connect_accounts.update_one(
        flt,
        {"$set": {
            "owner_user_id": user["id"],
            "context": "pulse_fitness",
            "stripe_account_id": fake_id,
            "livemode": False,
            "scope": "read_write",
            "country": "GB",
            "default_currency": "gbp",
            "charges_enabled": True,
            "payouts_enabled": True,
            "connected_at": now,
            "updated_at": now,
            "_dev_fake": True,
        }},
        upsert=True,
    )
    return {"ok": True, "account_id": fake_id}


__all__ = ["router"]
