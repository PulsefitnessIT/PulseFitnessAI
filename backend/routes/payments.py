from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime, timezone
import stripe
import uuid
import logging
import os

from utils.database import (
    db, STRIPE_API_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_STARTER, STRIPE_PRICE_PRO, STRIPE_PRICE_ENTERPRISE,
    STRIPE_PRICE_GYMAXIS_PRO, STRIPE_PRICE_SITE_ADDON,
    STRIPE_PRICE_MEMBERSHIPS, STRIPE_PRICE_CRM,
    STRIPE_PRICE_MARKETING, STRIPE_PRICE_OPERATIONS,
    RESEND_API_KEY,
)
from utils.auth import get_current_user
from utils.stripe_catalog import resolve_price_id, pricing_summary, SUPPORTED_CURRENCIES, get_catalog

logger = logging.getLogger(__name__)
router = APIRouter()

stripe.api_key = STRIPE_API_KEY
RESEND_OK = bool(RESEND_API_KEY)

# ── Iter 215be (Phase 6) — flexible pricing model ────────────────────
# Bundle (£150/mo) includes 1 site. Per-site add-on (£50/mo) is shipped
# as a quantity-based subscription line item so Stripe handles proration
# automatically when sites are added/removed mid-cycle. Individual
# modules are flat monthly subscriptions (£29/£49/£49/£59).
#
# Iter 215c2 — annual billing option. Annual price = monthly × 10
# (~17% discount = 2 months free). Industry-standard SaaS framing.
ANNUAL_DISCOUNT_MONTHS = 10  # pay for 10, get 12 → 2 months free
PRICING_CATALOG = {
    "bundle": {
        "id": "gymaxis_pro",
        "name": "Pulse Fitness Pro",
        "monthly": 150.0,
        "annual": 150.0 * ANNUAL_DISCOUNT_MONTHS,        # £1,500/yr (vs £1,800)
        "per_site": 50.0,
        "per_site_annual": 50.0 * ANNUAL_DISCOUNT_MONTHS,  # £500/site/yr
        "stripe_price_id": STRIPE_PRICE_GYMAXIS_PRO,
        "stripe_price_id_annual": os.environ.get("STRIPE_PRICE_GYMAXIS_PRO_ANNUAL"),
        "site_addon_stripe_price_id": STRIPE_PRICE_SITE_ADDON,
        "site_addon_stripe_price_id_annual": os.environ.get("STRIPE_PRICE_SITE_ADDON_ANNUAL"),
        "modules": ["operations", "memberships", "marketing", "crm"],
    },
    "modules": [
        {"id": "memberships", "name": "Memberships", "monthly": 29.0, "annual": 290.0,
         "stripe_price_id": STRIPE_PRICE_MEMBERSHIPS,
         "stripe_price_id_annual": os.environ.get("STRIPE_PRICE_MEMBERSHIPS_ANNUAL")},
        {"id": "crm", "name": "CRM", "monthly": 49.0, "annual": 490.0,
         "stripe_price_id": STRIPE_PRICE_CRM,
         "stripe_price_id_annual": os.environ.get("STRIPE_PRICE_CRM_ANNUAL")},
        {"id": "marketing", "name": "Marketing", "monthly": 49.0, "annual": 490.0,
         "stripe_price_id": STRIPE_PRICE_MARKETING,
         "stripe_price_id_annual": os.environ.get("STRIPE_PRICE_MARKETING_ANNUAL")},
        {"id": "operations", "name": "Operations", "monthly": 69.0, "annual": 690.0,
         "stripe_price_id": STRIPE_PRICE_OPERATIONS,
         "stripe_price_id_annual": os.environ.get("STRIPE_PRICE_OPERATIONS_ANNUAL")},
    ],
    "trial_days": 3,
    "annual_discount_pct": round((1 - ANNUAL_DISCOUNT_MONTHS / 12) * 100, 1),  # 16.7
}


PACKAGES = {
    "starter": {"name": "Pulse Fitness Starter", "amount": 29.0, "price_id": STRIPE_PRICE_STARTER},
    "pro": {"name": "Pulse Fitness Professional", "amount": 79.0, "price_id": STRIPE_PRICE_PRO},
    "enterprise": {"name": "Pulse Fitness Enterprise", "amount": 149.0, "price_id": STRIPE_PRICE_ENTERPRISE},
}


@router.get("/payments/config")
async def get_stripe_config() -> dict:
    return {"publishable_key": STRIPE_PUBLISHABLE_KEY}


@router.get("/payments/pricing")
async def get_pricing_catalog() -> dict:
    """Iter 215be — public endpoint that returns the Pulse Fitness pricing model.

    The pricing page reads from this so the canonical source of truth for
    bundle/module prices lives in one place. Adds a `stripe_configured`
    flag so the front-end knows whether to show "Get Started → Stripe
    checkout" or fall back to the trial signup modal.
    """
    bundle = dict(PRICING_CATALOG["bundle"])
    modules = [dict(m) for m in PRICING_CATALOG["modules"]]
    # Strip the price IDs from the public response — the FE doesn't need
    # them and we don't want Stripe Price IDs in browser bundles.
    for k in ("stripe_price_id", "stripe_price_id_annual",
              "site_addon_stripe_price_id", "site_addon_stripe_price_id_annual"):
        bundle.pop(k, None)
    for m in modules:
        m.pop("stripe_price_id", None)
        m.pop("stripe_price_id_annual", None)
    return {
        "bundle": bundle,
        "modules": modules,
        "trial_days": PRICING_CATALOG["trial_days"],
        "annual_discount_pct": PRICING_CATALOG["annual_discount_pct"],
        "stripe_configured": bool(
            PRICING_CATALOG["bundle"]["stripe_price_id"]
            and PRICING_CATALOG["bundle"]["site_addon_stripe_price_id"]
        ),
    }


# Eurozone / EU-EEA countries -> price in EUR. US -> USD. Everything else -> GBP.
_EUR_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES",
    "SE", "IS", "LI", "NO",
}


def detect_currency(request: Request) -> str:
    """Best-effort currency from the request's region (edge country header,
    else Accept-Language). Falls back to GBP."""
    country = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-vercel-ip-country")
        or request.headers.get("x-ipcountry")
        or ""
    ).upper()
    if not country or country in ("XX", "T1"):
        import re
        m = re.search(r"[a-zA-Z]{2}-([A-Z]{2})", request.headers.get("accept-language", "") or "")
        country = m.group(1).upper() if m else ""
    if country == "US":
        return "usd"
    if country in _EUR_COUNTRIES:
        return "eur"
    return "gbp"


@router.get("/payments/pricing/live")
async def get_live_pricing(request: Request, currency: str | None = None) -> dict:
    """Public: per-currency module pricing pulled live from Stripe + the
    visitor's auto-detected currency (overridable via ?currency=)."""
    detected = (currency or detect_currency(request)).lower()
    if detected not in SUPPORTED_CURRENCIES:
        detected = "gbp"
    return {
        "detected_currency": detected,
        "currencies": list(SUPPORTED_CURRENCIES),
        "pricing": pricing_summary(),
        "annual_discount_pct": PRICING_CATALOG["annual_discount_pct"],
    }


def _validate_checkout_request(body: dict) -> tuple[dict, str]:
    """Validate the incoming request body; return (package, origin_url) or raise."""
    package_id = body.get("package_id", "")
    origin_url = body.get("origin_url", "")
    if package_id not in PACKAGES:
        raise HTTPException(status_code=400, detail=f"Invalid package: {package_id}")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url is required")
    return PACKAGES[package_id], origin_url


async def _resolve_trial_metadata(user: dict) -> dict:
    """If the user's org is on a trial, return metadata Stripe will tag the session with."""
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0, "is_trial": 1}
    )
    if not (org and org.get("is_trial")):
        return {}
    return {"trial_org_id": user["organization_id"], "trial_convert": "true"}


def _create_stripe_session(package: dict, package_id: str, user: dict,
                           origin_url: str, trial_meta: dict):
    """Wrap the Stripe Checkout Session creation call."""
    trial_query = f"&trial_convert={user['organization_id']}" if trial_meta else ""
    success_url = f"{origin_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}{trial_query}"
    metadata = {
        "user_id": user["id"], "user_email": user["email"],
        "package_id": package_id, "package_name": package["name"],
        **({**trial_meta, "tier": package_id} if trial_meta else {}),
    }
    try:
        return stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": package["price_id"], "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=f"{origin_url}/pricing",
            customer_email=user["email"],
            metadata=metadata,
            idempotency_key=str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"checkout:{user['id']}:{package['price_id']}:{int(datetime.now(timezone.utc).timestamp() // 600)}",
            )),
        )
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _record_pending_payment(session, user: dict, package_id: str, package: dict) -> None:
    """Log the pending transaction for reconciliation by the webhook later."""
    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "user_id": user["id"],
        "user_email": user["email"],
        "package_id": package_id,
        "package_name": package["name"],
        "amount": package["amount"],
        "currency": "gbp",
        "payment_status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/payments/checkout")
async def create_checkout(body: dict, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Create a Stripe Checkout Session for a subscription."""
    package, origin_url = _validate_checkout_request(body)
    package_id = body["package_id"]
    trial_meta = await _resolve_trial_metadata(user)
    session = _create_stripe_session(package, package_id, user, origin_url, trial_meta)
    await _record_pending_payment(session, user, package_id, package)
    return {"url": session.url, "session_id": session.id}


@router.post("/payments/checkout/flex")
async def create_flex_checkout(body: dict, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Iter 215be — flexible checkout for the new pricing model.

    Body:
      - plan: "bundle" (Pulse Fitness Pro) | "module"
      - site_count: int (bundle only, defaults to 1)
      - module_id: str (module plan only, one of memberships/crm/marketing/operations)
      - origin_url: str

    Bundle path: posts a Stripe Checkout Session with two line items —
    the £150/mo base subscription (qty 1) and the £50/mo per-site add-on
    (qty = site_count - 1). Stripe handles proration for site changes
    via the existing subscription.modify flow on the resulting subscription.

    Module path: posts a single line item for the chosen module's price.

    If the relevant Stripe Price IDs are not configured (.env), returns
    501 with a helpful message so the frontend falls back to the trial
    signup flow.
    """
    origin_url = body.get("origin_url", "").rstrip("/")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url is required")
    currency = (body.get("currency") or "gbp").lower()
    if currency not in SUPPORTED_CURRENCIES:
        currency = "gbp"
    billing_cycle = "annual" if str(body.get("billing_cycle", "monthly")).lower() in ("annual", "year", "yearly") else "monthly"
    is_annual = billing_cycle == "annual"
    plan = body.get("plan")
    line_items: list[dict] = []
    package_name = ""
    total_amount = 0.0
    if plan == "bundle":
        bundle = PRICING_CATALOG["bundle"]
        if not bundle["stripe_price_id"] or not bundle["site_addon_stripe_price_id"]:
            raise HTTPException(status_code=501, detail="Stripe bundle Price IDs not configured")
        try:
            site_count = max(1, min(50, int(body.get("site_count", 1))))
        except (TypeError, ValueError):
            site_count = 1
        line_items.append({"price": bundle["stripe_price_id"], "quantity": 1})
        if site_count > 1:
            line_items.append({"price": bundle["site_addon_stripe_price_id"], "quantity": site_count - 1})
        package_name = f"{bundle['name']} ({site_count} site{'s' if site_count != 1 else ''})"
        total_amount = bundle["monthly"] + (site_count - 1) * bundle["per_site"]
    elif plan == "module":
        module_id = (body.get("module_id") or "").lower()
        mod = next((m for m in PRICING_CATALOG["modules"] if m["id"] == module_id), None)
        if not mod:
            raise HTTPException(status_code=400, detail=f"Unknown module: {module_id}")
        price_id, resolved_ccy = resolve_price_id(module_id, currency, billing_cycle)
        if not price_id:
            raise HTTPException(status_code=501, detail=f"Stripe Price for {module_id} ({currency}/{billing_cycle}) not configured")
        currency = resolved_ccy or currency
        line_items.append({"price": price_id, "quantity": 1})
        package_name = f"Pulse Fitness · {mod['name']}"
        _node = get_catalog().get(module_id, {}).get(currency, {}).get("year" if is_annual else "month", {})
        total_amount = (_node.get("unit_amount") or 0) / 100 or (mod["annual"] if is_annual else mod["monthly"])
    else:
        raise HTTPException(status_code=400, detail="plan must be 'bundle' or 'module'")

    trial_meta = await _resolve_trial_metadata(user)
    metadata = {
        "user_id": user["id"], "user_email": user["email"],
        "plan_kind": plan, "package_name": package_name,
        "currency": currency, "billing_cycle": billing_cycle,
        **({**trial_meta, "tier": plan} if trial_meta else {}),
        **({"site_count": str(body.get("site_count", 1))} if plan == "bundle" else {}),
        **({"module_id": body.get("module_id", "")} if plan == "module" else {}),
    }
    success_url = f"{origin_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="subscription",
            success_url=success_url,
            cancel_url=f"{origin_url}/pricing",
            customer_email=user["email"],
            metadata=metadata,
            idempotency_key=str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"checkout-flex:{user['id']}:{plan}:{currency}:{int(datetime.now(timezone.utc).timestamp() // 600)}",
            )),
        )
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "user_id": user["id"],
        "user_email": user["email"],
        "plan_kind": plan,
        "package_name": package_name,
        "amount": total_amount,
        "currency": currency,
        "payment_status": "pending",
        "metadata": metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"url": session.url, "session_id": session.id, "amount": total_amount}


@router.get("/payments/status/{session_id}")
async def check_payment_status(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    payment = await db.payment_transactions.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment["payment_status"] == "paid":
        return payment

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid" and payment["payment_status"] != "paid":
            await _activate_subscription(user["id"], payment["package_id"], session_id, user["email"], payment["package_name"], payment["amount"])
            payment["payment_status"] = "paid"
        elif session.status == "expired":
            await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"payment_status": "expired"}})
            payment["payment_status"] = "expired"
    except stripe.StripeError:
        pass

    return payment


async def _handle_checkout_completed(data: dict) -> None:
    """Handle checkout.session.completed webhook event."""
    session_id = data.get("id")
    metadata = data.get("metadata", {})

    # Trial conversion path — ONLY when Stripe confirms the payment as paid.
    # Previously this fired on every `checkout.session.completed` regardless
    # of payment_status, which let prospects exit Checkout uncharged yet keep
    # full bundle access (iter202 bug — caught when reviewing Bob Knockers).
    trial_org_id = metadata.get("trial_org_id")
    payment_paid = data.get("payment_status") == "paid"
    if trial_org_id and metadata.get("trial_convert") == "true" and payment_paid:
        await db.organizations.update_one(
            {"id": trial_org_id},
            {"$set": {
                "is_trial": False,
                "trial_status": "converted",
                "status": "active",
                "converted_at": datetime.now(timezone.utc).isoformat(),
                "stripe_session_id": session_id,
                "subscription_tier": metadata.get("tier", "pro"),
            }}
        )
        logger.info(f"[Trial] Org {trial_org_id} converted via Stripe session {session_id}")
        return
    if trial_org_id and metadata.get("trial_convert") == "true" and not payment_paid:
        # Stripe fired completion before the payment cleared (or it never will).
        # Leave the trial flag untouched so the org keeps the proper trial state.
        logger.info(f"[Trial] Skipped premature conversion for org {trial_org_id} (payment_status={data.get('payment_status')})")
        return

    user_id = metadata.get("user_id")
    package_id = metadata.get("package_id")
    if not (user_id and package_id and data.get("payment_status") == "paid"):
        # Iter 216h76 — Partner Engineer Plan checkout. Non-package
        # subscription kinds (no package_id) flow through here, so we
        # give the partners module a chance to bind the new sub.
        try:
            from routes.partners import handle_partner_checkout_completed
            await handle_partner_checkout_completed(data)
        except Exception:
            logger.exception("[partners] partner checkout binding failed")
        return
    existing = await db.payment_transactions.find_one({"session_id": session_id, "payment_status": "paid"})
    if existing:
        return
    package = PACKAGES.get(package_id, {})
    await _activate_subscription(user_id, package_id, session_id, metadata.get("user_email", ""), package.get("name", ""), package.get("amount", 0))


async def _handle_subscription_deleted(data: dict) -> None:
    """Handle customer.subscription.deleted webhook event."""
    customer_email = data.get("customer_email") or ""
    if customer_email:
        await db.users.update_one(
            {"email": customer_email},
            {"$set": {"subscription_active": False, "subscription_cancelled_at": datetime.now(timezone.utc).isoformat()}},
        )
    # Iter 216h76 — Partner Engineer Plan subscription sync.
    try:
        from routes.partners import handle_partner_subscription_event
        await handle_partner_subscription_event(data)
    except Exception:
        logger.exception("[partners] partner subscription-deleted sync failed")


async def _handle_subscription_updated(data: dict) -> None:
    """Handle customer.subscription.updated — keeps the partner profile
    in sync with Stripe (status, price ID, cancel-at-period-end)."""
    try:
        from routes.partners import handle_partner_subscription_event
        await handle_partner_subscription_event(data)
    except Exception:
        logger.exception("[partners] partner subscription-updated sync failed")


async def _handle_invoice_payment_failed(data: dict) -> None:
    """Iter 215c0 — Stripe dunning workflow.

    On `invoice.payment_failed`, we:
      1. Increment a per-customer failure counter (`stripe_dunning_state`).
      2. Email the billing contact with retry instructions.
      3. After 3 consecutive failures, suspend the subscription on the
         org doc (`status=past_due`) so the dashboard renders a banner
         and write-paths can soft-block.

    No hard delete — Stripe's smart-retry continues, and a successful
    payment resets the counter via `invoice.paid`.
    """
    from utils.email import send_email

    customer_id = data.get("customer") or ""
    customer_email = data.get("customer_email") or ""
    subscription_id = data.get("subscription") or ""
    amount_due_pence = int(data.get("amount_due") or 0)
    attempt_count = int(data.get("attempt_count") or 1)
    next_attempt = data.get("next_payment_attempt")
    hosted_invoice_url = data.get("hosted_invoice_url") or ""
    now = datetime.now(timezone.utc).isoformat()

    # Resolve target org/user.
    org = None
    user = None
    if customer_id:
        org = await db.organizations.find_one(
            {"stripe_customer_id": customer_id}, {"_id": 0, "id": 1, "name": 1, "primary_contact_email": 1},
        )
    if customer_email and not user:
        user = await db.users.find_one({"email": customer_email}, {"_id": 0, "id": 1, "email": 1, "organization_id": 1})

    org_id = (org or {}).get("id") or (user or {}).get("organization_id")
    target_email = customer_email or (org or {}).get("primary_contact_email") or (user or {}).get("email") or ""

    # Idempotency / counter.
    state = await db.stripe_dunning_state.find_one(
        {"customer_id": customer_id, "subscription_id": subscription_id}, {"_id": 0},
    ) or {}
    fail_count = int(state.get("fail_count", 0)) + 1
    await db.stripe_dunning_state.update_one(
        {"customer_id": customer_id, "subscription_id": subscription_id},
        {"$set": {
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "organization_id": org_id,
            "fail_count": fail_count,
            "last_failed_at": now,
            "last_amount_pence": amount_due_pence,
            "last_invoice_url": hosted_invoice_url,
            "next_attempt": next_attempt,
        }},
        upsert=True,
    )

    # Suspend org after 3 failures.
    if org_id and fail_count >= 3:
        await db.organizations.update_one(
            {"id": org_id},
            {"$set": {
                "billing_status": "past_due",
                "suspended_for_billing_at": now,
            }},
        )
        logger.warning(f"[stripe-dunning] Org {org_id} suspended after {fail_count} failed payments")

    # Email the billing contact.
    if target_email and RESEND_OK:
        amount_str = f"£{amount_due_pence/100:.2f}" if amount_due_pence else "your subscription"
        attempt_str = f"{attempt_count}{'st' if attempt_count == 1 else 'nd' if attempt_count == 2 else 'rd' if attempt_count == 3 else 'th'} attempt"
        cta = f'<a href="{hosted_invoice_url}" style="display:inline-block;padding:12px 22px;background:#2563EB;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">Update payment method</a>' if hosted_invoice_url else ""
        suspended_note = (
            "<p style='color:#dc2626;'><strong>Your account has been temporarily suspended.</strong> Update your payment method to restore access.</p>"
            if fail_count >= 3 else ""
        )
        html = f"""
        <div style="font-family:system-ui,-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#0f172a;">
            <h2 style="color:#0f172a;">Payment for Pulse Fitness failed ({attempt_str})</h2>
            <p>We were unable to charge {amount_str} for your subscription.</p>
            {suspended_note}
            <p>Please update your card details to avoid interruption.</p>
            <p>{cta}</p>
            <p style="color:#6b7280;font-size:12px;margin-top:32px;">
                Need help? Reply to this email and our team will assist.
            </p>
        </div>
        """
        try:
            await send_email(target_email, "Action required: payment for Pulse Fitness failed", html, category="billing")
        except Exception:
            logger.exception("[stripe-dunning] Failed to send dunning email")


async def _handle_invoice_paid(data: dict) -> None:
    """Reset dunning counter and clear suspension when payment succeeds."""
    customer_id = data.get("customer") or ""
    subscription_id = data.get("subscription") or ""
    if not (customer_id or subscription_id):
        return
    await db.stripe_dunning_state.update_one(
        {"customer_id": customer_id, "subscription_id": subscription_id},
        {"$set": {"fail_count": 0, "last_paid_at": datetime.now(timezone.utc).isoformat()}},
    )
    org = await db.organizations.find_one({"stripe_customer_id": customer_id}, {"_id": 0, "id": 1})
    if org:
        await db.organizations.update_one(
            {"id": org["id"]},
            {"$set": {"billing_status": "active"}, "$unset": {"suspended_for_billing_at": ""}},
        )

    # Iter 216h75 — Partner Engineer Network commission accrual. Idempotent
    # by Stripe invoice id, scoped to Operations module charges only. Never
    # block the original webhook flow on a partner failure.
    try:
        from routes.partners import accrue_commission_on_invoice_paid
        await accrue_commission_on_invoice_paid(data)
    except Exception:
        logger.exception("[partners] commission accrual failed")


WEBHOOK_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "customer.subscription.updated": _handle_subscription_updated,
    "invoice.payment_failed": _handle_invoice_payment_failed,
    "invoice.paid": _handle_invoice_paid,
}


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> dict:
    """Handle Stripe webhook events."""
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(body, signature, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info(f"Stripe webhook: {event_type}")

    # Idempotency — dedupe by stripe event id
    event_id = event.get("id")
    if event_id and await db.stripe_webhook_events.find_one({"event_id": event_id}, {"_id": 1}):
        return {"status": "deduped", "event": event_type}
    if event_id:
        await db.stripe_webhook_events.insert_one({
            "event_id": event_id,
            "event_type": event_type,
            "received_at": datetime.now(timezone.utc).isoformat(),
        })

    handler = WEBHOOK_HANDLERS.get(event_type)
    if handler:
        try:
            await handler(data)
        except Exception:
            logger.exception(f"[stripe-webhook] handler failed for {event_type}")
            # Return 200 anyway so Stripe doesn't hammer us; we have the event logged.

    return {"status": "success", "event": event_type}


@router.get("/payments/history")
async def get_payment_history(user: dict = Depends(get_current_user)) -> dict:
    payments = await db.payment_transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"payments": payments}


async def _activate_subscription(user_id: str, package_id: str, session_id: str, email: str, package_name: str, amount: float) -> None:
    """Activate a user's subscription after successful payment."""
    now = datetime.now(timezone.utc).isoformat()
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"payment_status": "paid", "paid_at": now}},
    )
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"subscription_tier": package_id, "subscription_active": True, "subscription_started_at": now}},
    )
    from utils.audit import audit_log
    await audit_log("subscription_payment", user_id, email, "payment", session_id, f"Subscribed to {package_name} (£{amount}/mo)")
