"""Route member payments to the gym's connected Stripe Express account.

When a gym has completed Stripe Connect onboarding (`charges_enabled`), member
payments are created as **destination charges** on the platform account with a
``transfer_data.destination`` pointing at the gym's connected account plus a
platform application fee. The platform stays merchant of record, so the existing
platform webhooks (``checkout.session.completed`` / ``invoice.paid``) keep
working unchanged.

When the gym isn't connected (or KYC isn't finished), these helpers return
empty / None so the caller falls back to charging the platform account — exactly
the previous behaviour, with no disruption.
"""
from __future__ import annotations

import logging
import os

import stripe

from utils.database import db

logger = logging.getLogger("stripe_connect_routing")

# Platform fee on member transactions — the documented "1% on every member
# transaction". Override per-deploy via env (e.g. set to 0 to take no fee).
MEMBERSHIP_PLATFORM_FEE_PCT = float(os.getenv("MEMBERSHIP_PLATFORM_FEE_PCT", "1.0"))


async def resolve_org_connect_routing(org: dict | None) -> dict | None:
    """Return ``{'destination', 'fee_pct'}`` when the org's connected Express
    account can take charges, else ``None`` (→ charge the platform account)."""
    if not org:
        return None
    acct_id = org.get("stripe_account_id")
    if not acct_id:
        return None
    enabled = None
    try:
        acct = stripe.Account.retrieve(acct_id)
        caps = getattr(acct, "capabilities", None) or {}
        # Destination charges require the `transfers` capability to be *active*.
        # On Express accounts charges + transfers activate together on KYC, but
        # gating on transfers specifically prevents an `insufficient_capabilities
        # _for_transfer` error from ever breaking member checkout.
        enabled = bool(getattr(acct, "charges_enabled", False)) and caps.get("transfers") == "active"
        # Cache the flag so a later Stripe outage still routes correctly.
        if org.get("stripe_charges_enabled") != enabled and org.get("id"):
            await db.organizations.update_one(
                {"id": org["id"]}, {"$set": {"stripe_charges_enabled": enabled}},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("connect routing: account retrieve failed (%s) — using cached flag", exc)
        enabled = bool(org.get("stripe_charges_enabled"))
    if not enabled:
        return None
    return {"destination": acct_id, "fee_pct": MEMBERSHIP_PLATFORM_FEE_PCT}


def payment_intent_connect_kwargs(routing: dict | None, amount_cents: int) -> dict:
    """``payment_intent_data`` fragment for a one-time (mode=payment) charge."""
    if not routing:
        return {}
    fragment: dict = {"transfer_data": {"destination": routing["destination"]}}
    fee = int(round(amount_cents * float(routing.get("fee_pct") or 0) / 100))
    # Stripe rejects a fee >= the charge — cap defensively.
    fee = max(0, min(fee, amount_cents - 1)) if amount_cents > 0 else 0
    if fee > 0:
        fragment["application_fee_amount"] = fee
    return fragment


def subscription_connect_kwargs(routing: dict | None) -> dict:
    """``subscription_data`` fragment for a mode=subscription charge."""
    if not routing:
        return {}
    fragment: dict = {"transfer_data": {"destination": routing["destination"]}}
    pct = float(routing.get("fee_pct") or 0)
    if pct > 0:
        fragment["application_fee_percent"] = pct
    return fragment
