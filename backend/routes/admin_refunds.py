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

Iter 216h164 — refactored: the previous `issue_refund` was a single
function with cyclomatic complexity E/36. It's been split into small
helpers (validation, Stripe call, org resolution, event persistence)
that each do one job. Behaviour is unchanged; this is purely an
ergonomics + maintainability fix.
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

_STRIPE_REASONS = ("requested_by_customer", "duplicate", "fraudulent")
_ALL_REASONS = (*_STRIPE_REASONS, "other")


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── List ─────────────────────────────────────────────────────────

async def _backfill_org_names(rows: list[dict]) -> None:
    """Mutate `rows` in place to add `organization_name` for legacy entries.

    Pre-iter 215d0 rows only carry `organization_id`; the UI wants a
    human-readable name. One batched lookup serves the whole window.
    """
    missing = {
        r["organization_id"] for r in rows
        if r.get("organization_id") and not r.get("organization_name")
    }
    if not missing:
        return
    org_docs = await db.organizations.find(
        {"id": {"$in": list(missing)}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(len(missing) + 1)
    id_to_name = {d["id"]: d.get("name") for d in org_docs}
    for r in rows:
        if r.get("organization_id") and not r.get("organization_name"):
            r["organization_name"] = id_to_name.get(r["organization_id"])


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
    await _backfill_org_names(rows)

    total_refunded_pence = sum(
        int(r.get("amount_pence", 0)) for r in rows if r.get("status") == "succeeded"
    )
    return {
        "window_days": days,
        "count": len(rows),
        "total_refunded_pence": total_refunded_pence,
        "total_refunded": round(total_refunded_pence / 100, 2),
        "items": rows,
    }


# ── Issue refund — helpers ───────────────────────────────────────

def _validate_refund_payload(payload: dict) -> dict:
    """Coerce and validate the inbound payload; return a tidy dict.
    Raises HTTPException(400) on every validation failure."""
    charge_id = (payload.get("charge_id") or "").strip()
    if not charge_id:
        raise HTTPException(status_code=400, detail="charge_id is required")

    reason = (payload.get("reason") or "").strip().lower()
    if reason not in _ALL_REASONS:
        raise HTTPException(
            status_code=400,
            detail=f"reason must be one of {'|'.join(_ALL_REASONS)}",
        )

    raw_amount = payload.get("amount_pence")
    amount_pence: int | None = None
    if raw_amount is not None:
        try:
            amount_pence = int(raw_amount)
            if amount_pence <= 0:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400,
                detail="amount_pence must be a positive integer",
            ) from exc

    return {
        "charge_id": charge_id,
        "reason": reason,
        "amount_pence": amount_pence,
        "notes": (payload.get("notes") or "").strip()[:1000],
        "organization_id": payload.get("organization_id"),
    }


def _build_refund_kwargs(charge_id: str, amount_pence: int | None, reason: str) -> dict:
    """Stripe.Refund.create accepts `charge` OR `payment_intent`, not both.
    `reason` is only valid when in Stripe's enum — `other` is ours."""
    kwargs: dict = {}
    if charge_id.startswith("pi_"):
        kwargs["payment_intent"] = charge_id
    else:
        kwargs["charge"] = charge_id
    if amount_pence is not None:
        kwargs["amount"] = amount_pence
    if reason in _STRIPE_REASONS:
        kwargs["reason"] = reason
    return kwargs


def _create_stripe_refund(kwargs: dict):
    """Wrap Stripe.Refund.create — map Stripe failures to clean HTTP errors."""
    try:
        return stripe.Refund.create(**kwargs)
    except stripe.InvalidRequestError as exc:
        logger.warning("[refunds] Stripe rejected refund: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Stripe: {exc.user_message or str(exc)}",
        ) from exc
    except Exception as exc:
        logger.exception("[refunds] unexpected error issuing refund")
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc


def _fetch_charge_object(charge_id: str):
    """Retrieve the underlying Charge for a charge_id OR payment_intent."""
    if charge_id.startswith("pi_"):
        pi = stripe.PaymentIntent.retrieve(charge_id, expand=["charges.data"])
        items = getattr(pi, "charges", None)
        return items.data[0] if items and items.data else None
    return stripe.Charge.retrieve(charge_id)


async def _find_org_by_field(field: str, value: str) -> tuple[str | None, str | None]:
    """Look up an org by a single field and return (id, name) or (None, None)."""
    org = await db.organizations.find_one(
        {field: value}, {"_id": 0, "id": 1, "name": 1},
    )
    if not org:
        return None, None
    return org["id"], org.get("name")


async def _resolve_org_link(
    charge_id: str, organization_id: str | None,
) -> tuple[str | None, str | None]:
    """Best-effort: figure out which org issued this charge.
    Tries stripe_customer_id, then billing email. Never raises."""
    resolved_id, resolved_name = organization_id, None
    try:
        charge_obj = _fetch_charge_object(charge_id)
        cust_id = getattr(charge_obj, "customer", None) if charge_obj else None
        email = (
            charge_obj.billing_details.email
            if charge_obj and charge_obj.billing_details else None
        )

        if not resolved_id and cust_id:
            resolved_id, resolved_name = await _find_org_by_field(
                "stripe_customer_id", cust_id,
            )
        if not resolved_id and email:
            resolved_id, resolved_name = await _find_org_by_field(
                "primary_contact_email", email.lower(),
            )
        if resolved_id and not resolved_name:
            _, resolved_name = await _find_org_by_field("id", resolved_id)
    except Exception:
        logger.debug("[refunds] could not resolve linked org (non-fatal)", exc_info=True)
    return resolved_id, resolved_name


def _build_refund_event(
    refund, *, validated: dict, user: dict,
    org_id: str | None, org_name: str | None,
) -> dict:
    return {
        "id": refund.id,
        "charge_id": refund.charge if hasattr(refund, "charge") else validated["charge_id"],
        "payment_intent": getattr(refund, "payment_intent", None),
        "status": refund.status,
        "amount_pence": int(refund.amount or 0),
        "currency": (refund.currency or "gbp").lower(),
        "reason": validated["reason"],
        "internal_notes": validated["notes"],
        "organization_id": org_id,
        "organization_name": org_name,
        "issued_by_user_id": user["id"],
        "issued_by_email": user.get("email"),
        "created_at": _now(),
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
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    validated = _validate_refund_payload(payload)
    refund = _create_stripe_refund(_build_refund_kwargs(
        validated["charge_id"], validated["amount_pence"], validated["reason"],
    ))
    org_id, org_name = await _resolve_org_link(
        validated["charge_id"], validated["organization_id"],
    )

    event = _build_refund_event(
        refund, validated=validated, user=user,
        org_id=org_id, org_name=org_name,
    )
    await db.refund_events.insert_one(dict(event))

    ip = request.client.host if request.client else ""
    await audit_log(
        "refund_issued", user["id"], user.get("email", ""),
        "refund", refund.id,
        f"{refund.amount/100:.2f} {refund.currency.upper()} on "
        f"{validated['charge_id']} · reason={validated['reason']}",
        ip,
    )

    # Return the sanitized event, not the Stripe object (which contains
    # data we don't want in browser bundles).
    return {"ok": True, "refund": event}


# ── Lookup ───────────────────────────────────────────────────────

def _lookup_by_id(query: str) -> list[dict]:
    """Resolve a `ch_…` or `pi_…` directly."""
    try:
        if query.startswith("ch_"):
            ch = stripe.Charge.retrieve(query)
            return [_charge_to_dict(ch)]
        if query.startswith("pi_"):
            pi = stripe.PaymentIntent.retrieve(query, expand=["charges.data"])
            items = getattr(pi, "charges", None)
            ch = items.data[0] if items and items.data else None
            return [_charge_to_dict(ch)] if ch else []
    except stripe.InvalidRequestError:
        return []
    return []


def _lookup_by_email(email: str) -> list[dict]:
    customers = stripe.Customer.list(email=email, limit=3)
    out: list[dict] = []
    for cust in customers.data:
        charges = stripe.Charge.list(customer=cust.id, limit=10)
        out.extend(_charge_to_dict(c) for c in charges.data)
    return out


@router.get("/lookup")
async def lookup_charge(
    query: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Find a charge by customer email or charge/payment-intent id.

    Used by the admin refund UI to resolve a payment before refund."""
    _require_master_admin(user)
    query = (query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    if query.startswith(("ch_", "pi_")):
        return {"matches": _lookup_by_id(query)}
    if "@" in query:
        return {"matches": _lookup_by_email(query)}
    return {"matches": []}


def _card_last4(charge) -> str | None:
    pm = getattr(charge, "payment_method_details", None) or {}
    card = getattr(pm, "card", None) or {}
    if isinstance(card, dict):
        return card.get("last4")
    return getattr(card, "last4", None)


def _charge_to_dict(charge) -> dict:
    if charge is None:
        return {}
    billing = charge.billing_details
    return {
        "id": charge.id,
        "amount_pence": int(charge.amount or 0),
        "currency": (charge.currency or "gbp").lower(),
        "status": charge.status,
        "refunded": bool(charge.refunded),
        "amount_refunded_pence": int(charge.amount_refunded or 0),
        "customer_email": billing.email if billing else None,
        "customer_name": billing.name if billing else None,
        "last4": _card_last4(charge),
        "created_at": (
            datetime.fromtimestamp(charge.created, tz=timezone.utc).isoformat()
            if charge.created else None
        ),
        "description": charge.description,
    }
