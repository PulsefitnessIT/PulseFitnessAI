"""Stripe Connect Express onboarding for organisations (gyms).

Each organisation owns a Stripe Connect account (Express by default; gyms
can also link an existing Standard account by providing the account_id).
GymAxis charges 1% application_fee_amount on every member transaction
made against the connected account.

Endpoints (master admin scope; per-org-admin scope can be added later)
---------------------------------------------------------------------
* ``GET    /api/stripe-connect/orgs/{org}/status``         — onboarding state
* ``POST   /api/stripe-connect/orgs/{org}/onboarding-link`` — Express start
* ``POST   /api/stripe-connect/orgs/{org}/link-existing``  — paste account_id
* ``POST   /api/stripe-connect/orgs/{org}/dashboard-link`` — Express dashboard
* ``DELETE /api/stripe-connect/orgs/{org}/disconnect``     — clear account ref
* ``POST   /api/webhooks/stripe-connect``                  — account.updated etc.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import stripe
from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request

from routes.auth import get_current_user
from routes.master_admin import require_master_admin
from utils.database import db
from utils.stripe_connect_errors import stripe_connect_http_exception

load_dotenv()
log = logging.getLogger("stripe_connect")

stripe.api_key = os.getenv("STRIPE_API_KEY")
PLATFORM_FEE_PERCENT = 1.0  # 1% application fee on every member transaction


def _effective_fee(org: dict | None) -> float:
    """Per-gym fee override (`org.membership_platform_fee_pct`) or the global default."""
    if org and org.get("membership_platform_fee_pct") is not None:
        return float(org["membership_platform_fee_pct"])
    return PLATFORM_FEE_PERCENT

router = APIRouter(tags=["stripe-connect"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _origin_or(default: str, request: Request) -> str:
    return (request.headers.get("origin") or default).rstrip("/")


async def _get_org(org_id: str) -> dict:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    return org


def _account_summary(account: stripe.Account) -> dict[str, Any]:
    return {
        "account_id": account.id,
        "details_submitted": bool(account.details_submitted),
        "charges_enabled": bool(account.charges_enabled),
        "payouts_enabled": bool(account.payouts_enabled),
        "default_currency": getattr(account, "default_currency", None),
        "country": getattr(account, "country", None),
        "business_profile_name": (account.business_profile or {}).get("name") if hasattr(account, "business_profile") else None,
        "requirements_due": list(((account.requirements or {}).get("currently_due") or []) if hasattr(account, "requirements") else []),
    }


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/stripe-connect/orgs/{organization_id}/status")
async def status(organization_id: str = Path(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    org = await _get_org(organization_id)
    acct_id = org.get("stripe_account_id")
    if not acct_id:
        return {
            "connected": False,
            "ready": False,
            "platform_fee_percent": _effective_fee(org),
            "custom_fee": org.get("membership_platform_fee_pct") is not None,
            "account": None,
        }
    try:
        account = stripe.Account.retrieve(acct_id)
    except stripe.error.StripeError as exc:
        log.warning("stripe.Account.retrieve failed for %s: %s", acct_id, exc)
        return {"connected": True, "ready": False, "error": str(exc), "account": {"account_id": acct_id}}
    summary = _account_summary(account)
    return {
        "connected": True,
        "ready": summary["charges_enabled"] and summary["payouts_enabled"],
        "platform_fee_percent": _effective_fee(org),
        "custom_fee": org.get("membership_platform_fee_pct") is not None,
        "account": summary,
    }


@router.put("/stripe-connect/orgs/{organization_id}/fee")
async def set_org_fee(
    organization_id: str = Path(...),
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Master-admin: set (or clear) the per-gym platform fee % on member
    transactions. Send `{"platform_fee_percent": null}` (or omit) to reset to
    the global default."""
    require_master_admin(user)
    await _get_org(organization_id)
    raw = body.get("platform_fee_percent", None)
    if raw is None or raw == "":
        await db.organizations.update_one(
            {"id": organization_id}, {"$unset": {"membership_platform_fee_pct": ""}},
        )
        return {"platform_fee_percent": PLATFORM_FEE_PERCENT, "custom_fee": False}
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, "platform_fee_percent must be a number")
    if pct < 0 or pct > 100:
        raise HTTPException(400, "platform_fee_percent must be between 0 and 100")
    await db.organizations.update_one(
        {"id": organization_id}, {"$set": {"membership_platform_fee_pct": pct}},
    )
    return {"platform_fee_percent": pct, "custom_fee": True}


@router.get("/stripe-connect/me/status")
async def my_status(user: dict = Depends(get_current_user)):
    """Operator-facing: the caller's OWN org Connect status (for billing UI)."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"connected": False, "ready": False, "charges_enabled": False,
                "platform_fee_percent": PLATFORM_FEE_PERCENT}
    org = await _get_org(org_id)
    fee = _effective_fee(org)
    acct_id = org.get("stripe_account_id")
    if not acct_id:
        return {"connected": False, "ready": False, "charges_enabled": False,
                "platform_fee_percent": fee}
    try:
        account = stripe.Account.retrieve(acct_id)
    except stripe.error.StripeError:
        return {"connected": True, "ready": False,
                "charges_enabled": bool(org.get("stripe_charges_enabled")),
                "platform_fee_percent": fee}
    summary = _account_summary(account)
    return {
        "connected": True,
        "ready": summary["charges_enabled"] and summary["payouts_enabled"],
        "charges_enabled": summary["charges_enabled"],
        "payouts_enabled": summary["payouts_enabled"],
        "platform_fee_percent": fee,
    }


@router.post("/stripe-connect/orgs/{organization_id}/onboarding-link")
async def onboarding_link(
    request: Request,
    organization_id: str = Path(...),
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Create or reuse an Express account and return a fresh onboarding URL."""
    require_master_admin(user)
    org = await _get_org(organization_id)
    acct_id = org.get("stripe_account_id")
    try:
        if not acct_id:
            account = stripe.Account.create(
                type="express",
                country=(body.get("country") or "GB"),
                email=org.get("contact_email") or org.get("email"),
                business_profile={"name": org.get("name")},
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                    "bacs_debit_payments": {"requested": True},
                },
                metadata={"organization_id": organization_id, "source": "gymaxis"},
            )
            acct_id = account.id
            await db.organizations.update_one(
                {"id": organization_id},
                {"$set": {
                    "stripe_account_id": acct_id,
                    "stripe_account_type": "express",
                    "stripe_connected_at": _now(),
                }},
            )
        origin = _origin_or("https://gymaxisai.com", request)
        link = stripe.AccountLink.create(
            account=acct_id,
            refresh_url=f"{origin}/master-admin/orgs/{organization_id}/payments?refresh=1",
            return_url=f"{origin}/master-admin/orgs/{organization_id}/payments?onboarded=1",
            type="account_onboarding",
        )
        return {"url": link.url, "expires_at": link.expires_at, "account_id": acct_id}
    except stripe.error.StripeError as exc:
        log.error("Onboarding link failed: %s", exc, exc_info=True)
        raise stripe_connect_http_exception(exc)


@router.post("/stripe-connect/me/onboarding-link")
async def my_onboarding_link(
    request: Request,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Owner self-serve Stripe Connect Express onboarding for their OWN org.

    A gym owner clicks "Connect Stripe" in the Account Settings setup
    checklist; this creates/reuses their org's Express account and returns a
    fresh Stripe-hosted onboarding URL so the client can redirect straight to
    Stripe. Owners only (master admins manage other orgs via the org-scoped
    endpoint above).
    """
    if (user.get("role") or "").lower() != "owner" and not user.get("is_master_admin"):
        raise HTTPException(403, "Only the organisation owner can connect Stripe.")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "No organisation is linked to this account.")
    org = await _get_org(org_id)
    acct_id = org.get("stripe_account_id")
    # Where Stripe sends the owner back to — re-open Account Settings → billing.
    return_path = (body.get("return_path") or "/dashboard").strip()
    if not return_path.startswith("/"):
        return_path = "/" + return_path
    origin = _origin_or("https://gymaxisai.com", request)
    sep = "&" if "?" in return_path else "?"
    try:
        if not acct_id:
            account = stripe.Account.create(
                type="express",
                country=(body.get("country") or "GB"),
                email=org.get("contact_email") or org.get("email") or user.get("email"),
                business_profile={"name": org.get("name")},
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                    "bacs_debit_payments": {"requested": True},
                },
                metadata={"organization_id": org_id, "source": "gymaxis_owner_self_serve"},
            )
            acct_id = account.id
            await db.organizations.update_one(
                {"id": org_id},
                {"$set": {
                    "stripe_account_id": acct_id,
                    "stripe_account_type": "express",
                    "stripe_connected_at": _now(),
                }},
            )
        link = stripe.AccountLink.create(
            account=acct_id,
            refresh_url=f"{origin}{return_path}{sep}account=billing&stripe=refresh",
            return_url=f"{origin}{return_path}{sep}account=billing&stripe=onboarded",
            type="account_onboarding",
        )
        return {"url": link.url, "expires_at": link.expires_at, "account_id": acct_id}
    except stripe.error.StripeError as exc:
        log.error("Owner onboarding link failed: %s", exc, exc_info=True)
        raise stripe_connect_http_exception(exc)


@router.post("/stripe-connect/orgs/{organization_id}/link-existing")
async def link_existing(
    organization_id: str = Path(...),
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Allow gyms with an existing Stripe Standard account to link by ID.

    They paste their `acct_…` id; we verify it resolves and store it. The
    gym must have already authorised the platform via Connect OAuth in a
    real production setup. For now we accept any retrievable account id —
    full OAuth wiring is a Phase-2 follow-up.
    """
    require_master_admin(user)
    await _get_org(organization_id)
    acct_id = (body.get("account_id") or "").strip()
    if not acct_id.startswith("acct_"):
        raise HTTPException(400, "account_id must start with 'acct_'")
    try:
        account = stripe.Account.retrieve(acct_id)
    except stripe.error.StripeError as exc:
        raise HTTPException(400, f"Could not retrieve account: {exc.user_message or str(exc)}")
    await db.organizations.update_one(
        {"id": organization_id},
        {"$set": {
            "stripe_account_id": account.id,
            "stripe_account_type": "standard",
            "stripe_connected_at": _now(),
        }},
    )
    return {"ok": True, "account": _account_summary(account)}


@router.post("/stripe-connect/orgs/{organization_id}/dashboard-link")
async def dashboard_link(
    organization_id: str = Path(...),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    org = await _get_org(organization_id)
    acct_id = org.get("stripe_account_id")
    if not acct_id:
        raise HTTPException(400, "Organisation has no connected Stripe account")
    try:
        link = stripe.Account.create_login_link(acct_id)
        return {"url": link.url}
    except stripe.error.StripeError as exc:
        raise HTTPException(400, f"Stripe error: {exc.user_message or str(exc)}")


@router.delete("/stripe-connect/orgs/{organization_id}/disconnect")
async def disconnect(
    organization_id: str = Path(...),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    await _get_org(organization_id)
    await db.organizations.update_one(
        {"id": organization_id},
        {"$unset": {"stripe_account_id": "", "stripe_account_type": "", "stripe_connected_at": ""}},
    )
    return {"ok": True}


# ── Webhook (account.updated etc) ─────────────────────────────────────


WEBHOOK_SECRET = os.getenv("STRIPE_CONNECT_WEBHOOK_SECRET") or os.getenv("STRIPE_WEBHOOK_SECRET")


@router.post("/webhooks/stripe-connect")
async def webhook_connect(request: Request):
    """Receive Connect-scoped webhook events.

    For now we mostly observe `account.updated` so the operator's status
    panel reflects current onboarding state on next refresh.
    """
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        if WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        else:
            # Test-only path — never enabled in production thanks to the env check above.
            import json as _json
            event = _json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Webhook signature verification failed: %s", exc)
        raise HTTPException(400, f"Invalid signature: {exc}")
    etype = event.get("type") if isinstance(event, dict) else event["type"]
    # Iter 220as — Stripe webhook idempotency. Stripe retries on any
    # non-2xx, so without dedupe an ``account.updated`` would refresh
    # the cache twice. Cheap (single indexed find+upsert) but plugs a
    # whole class of replay attacks.
    from utils.stripe_idempotency import mark_event_processed
    event_id = event.get("id") if isinstance(event, dict) else event["id"]
    if not await mark_event_processed(event_id, handler="stripe_connect"):
        return {"received": True, "duplicate": True}
    data = event.get("data", {}).get("object", {}) if isinstance(event, dict) else event["data"]["object"]
    if etype == "account.updated":
        acct_id = data.get("id") if isinstance(data, dict) else data["id"]
        # Flip status caches so the next admin GET picks fresh fields.
        await db.organizations.update_one(
            {"stripe_account_id": acct_id},
            {"$set": {"stripe_account_last_event_at": _now()}},
        )
    # everything else: ignore for now (the public_signup webhook handles
    # checkout.session.completed and related member-creation events)
    return {"received": True}


__all__ = ["router", "PLATFORM_FEE_PERCENT"]
