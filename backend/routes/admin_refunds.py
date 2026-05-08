"""Refund management (iter 215c9).

Master-admin endpoints to issue Stripe refunds and log them in a
searchable `refund_events` collection. Customer-facing refund requests
still arrive via the Intercom-style support inbox — this module lets
admins act on them without leaving the platform.

Why we log to `refund_events`:
    • Accounting reconciliation (we ship CSVs to Xero / Sage quarterly).
    • Customer lifecycle analytics (refund-rate by plan, by tenure).
    • Audit trail — every refund carries actor + reason + IP.

Why partial refunds are allowed:
    • Pro-rata refunds when operators cancel mid-cycle after a support
      escalation. Full refunds would over-compensate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db, STRIPE_API_KEY

logger = logging.getLogger(__name__)
stripe.api_key = STRIPE_API_KEY

router = APIRouter(prefix="/admin/refunds", tags=["admin-refunds"])


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def list_refunds(
    days: int = 90,
    organization_id: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """List refunds issued in the window (default 90d). Master admin only."""
    _require_master_admin(user)
    days = max(1, min(int(days or 90), 365))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q: dict = {"created_at": {"$gte": since}}
    if organization_id:
        q["organization_id"] = organization_id
    rows = await db.refund_events.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

    # Back-fill `organization_name` for rows that pre-date 215d0 (only
    # have an org_id). One batched lookup across all distinct ids.
    missing_ids = {r["organization_id"] for r in rows if r.get("organization_id") and not r.get("organization_name")}
    if missing_ids:
        org_docs = await db.organizations.find(
            {"id": {"$in": list(missing_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(missing_ids) + 1)
        id_to_name = {d["id"]: d.get("name") for d in org_docs}
        for r in rows:
            if r.get("organization_id") and not r.get("organization_name"):
                r["organization_name"] = id_to_name.get(r["organization_id"])

    total_refunded_pence = sum(int(r.get("amount_pence", 0)) for r in rows if r.get("status") == "succeeded")
    return {
        "window_days": days,
        "count": len(rows),
        "total_refunded_pence": total_refunded_pence,
        "total_refunded": round(total_refunded_pence / 100, 2),
        "items": rows,
    }


@router.post("")
async def issue_refund(
    payload: dict,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Issue a refund against an existing Stripe charge.

    Body:
        charge_id       (required) — `ch_xxx` or `pi_xxx` (PaymentIntent).
        amount_pence    (optional) — partial-refund amount. Omit for full refund.
        reason          (required) — `requested_by_customer | duplicate | fraudulent | other`.
        notes           (optional) — internal admin notes, logged with event.
        organization_id (optional) — tag the refund to an org for analytics.
    """
    _require_master_admin(user)

    charge_id = (payload.get("charge_id") or "").strip()
    if not charge_id:
        raise HTTPException(status_code=400, detail="charge_id is required")

    reason = (payload.get("reason") or "").strip().lower()
    if reason not in ("requested_by_customer", "duplicate", "fraudulent", "other"):
        raise HTTPException(status_code=400, detail="reason must be one of requested_by_customer|duplicate|fraudulent|other")

    amount_pence = payload.get("amount_pence")
    if amount_pence is not None:
        try:
            amount_pence = int(amount_pence)
            if amount_pence <= 0:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="amount_pence must be a positive integer") from exc

    notes = (payload.get("notes") or "").strip()[:1000]
    organization_id = payload.get("organization_id")

    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    # Call Stripe — other=...refund-reason is rewritten to `other` which
    # Stripe refuses; we only pass a reason when it's in Stripe's enum.
    stripe_kwargs: dict = {}
    if charge_id.startswith("pi_"):
        stripe_kwargs["payment_intent"] = charge_id
    else:
        stripe_kwargs["charge"] = charge_id
    if amount_pence is not None:
        stripe_kwargs["amount"] = amount_pence
    if reason in ("requested_by_customer", "duplicate", "fraudulent"):
        stripe_kwargs["reason"] = reason

    try:
        refund = stripe.Refund.create(**stripe_kwargs)
    except stripe.InvalidRequestError as exc:
        logger.warning("[refunds] Stripe rejected refund: %s", exc)
        raise HTTPException(status_code=400, detail=f"Stripe: {exc.user_message or str(exc)}") from exc
    except Exception as exc:
        logger.exception("[refunds] unexpected error issuing refund")
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    # Iter 215d0 — if no organization_id was supplied, try to resolve it
    # from the charge's linked customer. Two heuristics, both cheap:
    #   1) match by `stripe_customer_id` on the organization doc
    #   2) fall back to the charge's billing email → primary_contact_email
    # Either way this is best-effort; failure is silent.
    resolved_org_id = organization_id
    resolved_org_name = None
    try:
        charge_obj = None
        if charge_id.startswith("pi_"):
            pi = stripe.PaymentIntent.retrieve(charge_id, expand=["charges.data"])
            items = getattr(pi, "charges", None)
            charge_obj = items.data[0] if items and items.data else None
        else:
            charge_obj = stripe.Charge.retrieve(charge_id)
        cust_id = getattr(charge_obj, "customer", None) if charge_obj else None
        email = charge_obj.billing_details.email if charge_obj and charge_obj.billing_details else None
        if not resolved_org_id and cust_id:
            org = await db.organizations.find_one(
                {"stripe_customer_id": cust_id},
                {"_id": 0, "id": 1, "name": 1},
            )
            if org:
                resolved_org_id = org["id"]
                resolved_org_name = org.get("name")
        if not resolved_org_id and email:
            org = await db.organizations.find_one(
                {"primary_contact_email": email.lower()},
                {"_id": 0, "id": 1, "name": 1},
            )
            if org:
                resolved_org_id = org["id"]
                resolved_org_name = org.get("name")
        if resolved_org_id and not resolved_org_name:
            org = await db.organizations.find_one(
                {"id": resolved_org_id}, {"_id": 0, "name": 1},
            )
            if org:
                resolved_org_name = org.get("name")
    except Exception:
        logger.debug("[refunds] could not resolve linked org (non-fatal)", exc_info=True)

    event = {
        "id": refund.id,
        "charge_id": refund.charge if hasattr(refund, "charge") else charge_id,
        "payment_intent": getattr(refund, "payment_intent", None),
        "status": refund.status,
        "amount_pence": int(refund.amount or 0),
        "currency": (refund.currency or "gbp").lower(),
        "reason": reason,
        "internal_notes": notes,
        "organization_id": resolved_org_id,
        "organization_name": resolved_org_name,
        "issued_by_user_id": user["id"],
        "issued_by_email": user.get("email"),
        "created_at": _now(),
    }
    await db.refund_events.insert_one(dict(event))

    ip = request.client.host if request.client else ""
    await audit_log(
        "refund_issued", user["id"], user.get("email", ""),
        "refund", refund.id,
        f"{refund.amount/100:.2f} {refund.currency.upper()} on {charge_id} · reason={reason}",
        ip,
    )

    # Return the sanitized event, not the Stripe object (which contains
    # data we don't want in browser bundles).
    return {"ok": True, "refund": event}


@router.get("/lookup")
async def lookup_charge(
    query: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Convenience endpoint: find a charge by customer email or last-4.

    Query can be an email, `ch_xxx`, `pi_xxx`, or last-4 card digits.
    Used by the admin refund UI to resolve a payment before refund.
    """
    _require_master_admin(user)
    query = (query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    # Direct-lookup shortcuts.
    try:
        if query.startswith("ch_"):
            ch = stripe.Charge.retrieve(query)
            return {"matches": [_charge_to_dict(ch)]}
        if query.startswith("pi_"):
            pi = stripe.PaymentIntent.retrieve(query, expand=["charges.data"])
            items = getattr(pi, "charges", None)
            ch = (items.data[0] if items and items.data else None)
            return {"matches": [_charge_to_dict(ch)] if ch else []}
    except stripe.InvalidRequestError:
        return {"matches": []}

    # Email-based lookup via customers.
    if "@" in query:
        customers = stripe.Customer.list(email=query, limit=3)
        all_charges = []
        for cust in customers.data:
            charges = stripe.Charge.list(customer=cust.id, limit=10)
            all_charges.extend(_charge_to_dict(c) for c in charges.data)
        return {"matches": all_charges}

    return {"matches": []}


def _charge_to_dict(charge) -> dict:
    if charge is None:
        return {}
    pm = getattr(charge, "payment_method_details", None) or {}
    card = getattr(pm, "card", None) or {}
    return {
        "id": charge.id,
        "amount_pence": int(charge.amount or 0),
        "currency": (charge.currency or "gbp").lower(),
        "status": charge.status,
        "refunded": bool(charge.refunded),
        "amount_refunded_pence": int(charge.amount_refunded or 0),
        "customer_email": charge.billing_details.email if charge.billing_details else None,
        "customer_name": charge.billing_details.name if charge.billing_details else None,
        "last4": card.get("last4") if isinstance(card, dict) else getattr(card, "last4", None),
        "created_at": datetime.fromtimestamp(charge.created, tz=timezone.utc).isoformat() if charge.created else None,
        "description": charge.description,
    }
