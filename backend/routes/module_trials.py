"""Module trials + Lite-to-Pro upgrade (Iter 238).

Self-serve endpoints for operators to:
  • Start a 3-day free trial of Memberships / CRM / Marketing (Pulse Pro
    only — Lite must upgrade first).
  • Upgrade their org from Pulse Lite → Pulse Pro.
  • Read which bolt-ons they can still trial vs already used.

Pricing references in `pricing_plans` are the source of truth for the UI;
this module only mutates `organizations.account_type` + `module_trials`
+ records to the existing `account_change_audit` collection.

Auth: org owner or master admin. Operators below owner level get a
clear 403 with `notifyApiError`-friendly detail so the upgrade UI can
explain the next step.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_access import (
    BOLT_ON_MODULES, TRIAL_DURATION_DAYS,
    resolve_module_access, trial_status,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Paid bolt-on subscription plans (Iter — self-serve module purchase) ──
# Source-of-truth prices live SERVER-SIDE only (never trust the frontend).
# Recurring Stripe Price IDs are pre-provisioned in backend/.env; if absent
# we fall back to an inline recurring price so checkout still works in
# dev/test. Pence amounts mirror the ModuleAccessGate marketing copy.
MODULE_PLANS = {
    "memberships": {"name": "Memberships", "amount_pennies": 5900,
                    "price_env": "STRIPE_PRICE_MEMBERSHIPS", "price_env_annual": "STRIPE_PRICE_MEMBERSHIPS_ANNUAL"},
    "crm": {"name": "CRM", "amount_pennies": 4900,
            "price_env": "STRIPE_PRICE_CRM", "price_env_annual": "STRIPE_PRICE_CRM_ANNUAL"},
    "marketing": {"name": "Marketing", "amount_pennies": 3900,
                  "price_env": "STRIPE_PRICE_MARKETING", "price_env_annual": "STRIPE_PRICE_MARKETING_ANNUAL"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def _resolve_org(user: dict) -> dict:
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0},
    )
    if not org:
        # Iter 216h272 — last-resort safety net: master admins must
        # never see the operator-facing module pages crash on a
        # missing org doc. The startup seeder normally self-heals
        # this on boot, but if it failed (e.g. mid-restore) we still
        # synthesise a minimal full-access org so the UI can render.
        if user.get("is_master_admin"):
            return {
                "id": user.get("organization_id") or "master-admin",
                "name": "Pulse Fitness AI Admin",
                "account_type": "full",
                "subscription_tier": "premium",
                "modules": {
                    "memberships": {"enabled": True, "source": "seed"},
                    "crm": {"enabled": True, "source": "seed"},
                    "marketing": {"enabled": True, "source": "seed"},
                },
            }
        raise HTTPException(404, "Organisation not found")
    return org


def _require_owner_or_master(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    role = (user.get("role") or "").lower()
    if role == "owner":
        return
    raise HTTPException(
        403, "Only the organisation owner (or a master admin) can change billing — please ask them to upgrade.",
    )


@router.get("/me/module-trials")
async def get_module_trials(user: dict = Depends(get_current_user)):
    """Operator-facing: what's the upgrade picture for my org?"""
    org = await _resolve_org(user)
    return {
        "account_type": org.get("account_type"),
        "module_access": resolve_module_access(user, org),
        "trials": trial_status(org),
        "trial_duration_days": TRIAL_DURATION_DAYS,
        "bolt_on_modules": list(BOLT_ON_MODULES),
        "is_owner": (user.get("role") or "").lower() == "owner" or bool(user.get("is_master_admin")),
    }


@router.post("/me/module-trials/start")
async def start_module_trial(
    body: dict = Body(...), user: dict = Depends(get_current_user),
):
    _require_owner_or_master(user)
    module = (body.get("module") or "").strip().lower()
    if module not in BOLT_ON_MODULES:
        raise HTTPException(400, f"module must be one of {list(BOLT_ON_MODULES)}")
    org = await _resolve_org(user)
    if (org.get("account_type") or "").lower() == "lite":
        raise HTTPException(
            400,
            "Pulse Lite cannot start bolt-on trials. Upgrade to Pulse Pro first, then start your free trial.",
        )
    statuses = trial_status(org)
    current = statuses.get(module, {})
    if current.get("admin_disabled"):
        raise HTTPException(
            403,
            f"{module.capitalize()} has been disabled by your administrator. "
            "Please contact them to enable it.",
        )
    if current.get("status") == "used":
        raise HTTPException(409, f"The free trial of {module.capitalize()} has already been used.")
    if current.get("status") == "active":
        raise HTTPException(409, f"A trial of {module.capitalize()} is already running.")

    started_at = _now()
    expires_at = started_at + timedelta(days=TRIAL_DURATION_DAYS)
    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            f"module_trials.{module}.started_at": started_at.isoformat(),
            f"module_trials.{module}.expires_at": expires_at.isoformat(),
            f"module_trials.{module}.started_by": user["id"],
            f"modules.{module}.enabled": True,
            f"modules.{module}.source": "trial",
            "updated_at": _now_iso(),
        }},
    )
    await db.account_change_audit.insert_one({
        "id": f"trial-{org['id']}-{module}-{int(started_at.timestamp())}",
        "organization_id": org["id"],
        "actor_id": user["id"],
        "kind": "module_trial_start",
        "module": module,
        "expires_at": expires_at.isoformat(),
        "created_at": _now_iso(),
    })
    return {
        "ok": True,
        "module": module,
        "started_at": started_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "days_remaining": TRIAL_DURATION_DAYS,
    }


@router.post("/me/upgrade-to-pro")
async def upgrade_to_pulse_pro(
    body: dict = Body(default_factory=dict), user: dict = Depends(get_current_user),
):
    """Self-serve Lite → Pro upgrade. Records to the audit trail and
    optionally auto-starts trials for any modules the operator selected
    on the upgrade screen.

    body = {"start_trials": ["memberships", "crm", "marketing"]}
    """
    _require_owner_or_master(user)
    org = await _resolve_org(user)
    current = (org.get("account_type") or "").lower()
    if current == "pulse_pro":
        return {"ok": True, "already_pro": True}
    if current != "lite":
        raise HTTPException(400, f"Cannot upgrade from '{current}' — only Pulse Lite orgs upgrade to Pro.")

    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            "account_type": "pulse_pro",
            "previous_account_type": current,
            "upgraded_at": _now_iso(),
            "upgraded_by": user["id"],
            "updated_at": _now_iso(),
        }},
    )
    await db.account_change_audit.insert_one({
        "id": f"upgrade-{org['id']}-{int(_now().timestamp())}",
        "organization_id": org["id"],
        "actor_id": user["id"],
        "kind": "account_type_upgrade",
        "from": current,
        "to": "pulse_pro",
        "created_at": _now_iso(),
    })

    # Optional bolt-on trials at the same time.
    requested = body.get("start_trials") or []
    started: list[dict] = []
    if isinstance(requested, list):
        for module in requested:
            mod = str(module).strip().lower()
            if mod not in BOLT_ON_MODULES:
                continue
            # Re-fetch org so trial_status sees the previous record.
            fresh = await _resolve_org(user)
            statuses = trial_status(fresh)
            if statuses.get(mod, {}).get("status") == "used":
                continue
            # NOTE: we intentionally do NOT skip `admin_disabled` here. On a
            # Lite org every bolt-on is seeded `enabled:false, source:"admin"`
            # by default — identical to a deliberate master-admin disable — so
            # skipping it meant "Try Pulse Pro free" upgraded the tier but
            # unlocked NOTHING (the reported bug). This branch only runs on an
            # explicit owner-initiated Lite→Pro upgrade, so we always convert
            # the requested bolt-ons into a live 3-day trial (source:"trial").
            started_at = _now()
            expires_at = started_at + timedelta(days=TRIAL_DURATION_DAYS)
            await db.organizations.update_one(
                {"id": org["id"]},
                {"$set": {
                    f"module_trials.{mod}.started_at": started_at.isoformat(),
                    f"module_trials.{mod}.expires_at": expires_at.isoformat(),
                    f"module_trials.{mod}.started_by": user["id"],
                    f"modules.{mod}.enabled": True,
                    f"modules.{mod}.source": "trial",
                }},
            )
            started.append({
                "module": mod,
                "expires_at": expires_at.isoformat(),
                "days_remaining": TRIAL_DURATION_DAYS,
            })

    return {
        "ok": True,
        "account_type": "pulse_pro",
        "trials_started": started,
    }


@router.post("/me/module-purchase/checkout")
async def create_module_checkout(
    body: dict = Body(...), user: dict = Depends(get_current_user),
):
    """Owner → Stripe Checkout (subscription) for a single bolt-on module.

    Mirrors the verified raw-SDK subscription pattern in
    `routes/service_provider_billing.py` (idempotency, payment_transactions
    ledger, polling status endpoint). On `paid`, the status endpoint flips
    `modules.<module>.{enabled:true, source:"paid"}` so the module stays
    unlocked beyond the trial window.
    """
    _require_owner_or_master(user)
    from utils.database import STRIPE_API_KEY
    if not STRIPE_API_KEY:
        raise HTTPException(500, "Stripe is not configured.")

    module = (body.get("module") or "").strip().lower()
    if module not in MODULE_PLANS:
        raise HTTPException(400, f"module must be one of {list(MODULE_PLANS)}")

    org = await _resolve_org(user)
    if (org.get("account_type") or "").lower() == "lite":
        raise HTTPException(400, "Upgrade to Pulse Pro before subscribing to a bolt-on.")
    cfg = (org.get("modules") or {}).get(module) or {}
    if cfg.get("enabled") and cfg.get("source") == "paid":
        raise HTTPException(400, f"{MODULE_PLANS[module]['name']} is already subscribed.")

    interval = "annual" if (body.get("interval") == "annual") else "month"
    origin_url = (body.get("origin_url") or "").rstrip("/")
    if not origin_url:
        raise HTTPException(400, "origin_url required")
    return_path = body.get("return_path") or "/"
    plan = MODULE_PLANS[module]

    import stripe
    stripe.api_key = STRIPE_API_KEY

    metadata = {
        "purpose": "module_subscription",
        "organization_id": org["id"],
        "user_id": user["id"],
        "module": module,
        "interval": interval,
    }
    sep = "&" if "?" in return_path else "?"
    session_kwargs = {
        "payment_method_types": ["card"],
        "mode": "subscription",
        "success_url": f"{origin_url}{return_path}{sep}purchase=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{origin_url}{return_path}{sep}purchase=cancelled",
        "customer_email": user.get("email") or None,
        "metadata": metadata,
    }
    price_id = os.environ.get(plan["price_env_annual"] if interval == "annual" else plan["price_env"])
    if price_id:
        session_kwargs["line_items"] = [{"price": price_id, "quantity": 1}]
    else:
        session_kwargs["line_items"] = [{
            "price_data": {
                "currency": "gbp",
                "product_data": {"name": f"Pulse Pro · {plan['name']}"},
                "unit_amount": plan["amount_pennies"] * (12 if interval == "annual" else 1),
                "recurring": {"interval": "year" if interval == "annual" else "month"},
            },
            "quantity": 1,
        }]

    try:
        from utils.stripe_client_idempotency import stripe_idem_key
        session = stripe.checkout.Session.create(
            **session_kwargs,
            idempotency_key=stripe_idem_key("module_subscription", org["id"], module, interval),
        )
    except Exception as e:
        logger.exception("Stripe module checkout failed")
        raise HTTPException(502, f"Stripe error: {e}")

    await db.payment_transactions.insert_one({
        "session_id": session.id,
        "organization_id": org["id"],
        "user_id": user["id"],
        "purpose": "module_subscription",
        "module": module,
        "interval": interval,
        "amount": plan["amount_pennies"],
        "currency": "gbp",
        "payment_status": "pending",
        "metadata": metadata,
        "created_at": _now_iso(),
    })
    return {"url": session.url, "session_id": session.id}


@router.get("/me/module-purchase/status/{session_id}")
async def module_purchase_status(session_id: str, user: dict = Depends(get_current_user)):
    """Poll Stripe; on `paid`, mark the module paid+enabled. Idempotent."""
    from utils.database import STRIPE_API_KEY
    if not STRIPE_API_KEY:
        raise HTTPException(500, "Stripe is not configured.")
    import stripe
    stripe.api_key = STRIPE_API_KEY

    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your transaction")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(502, f"Stripe error: {e}")

    payment_status = session.get("payment_status", "")
    module = txn.get("module")
    if payment_status == "paid" and txn.get("payment_status") != "paid":
        now = _now_iso()
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "completed_at": now}},
        )
        await db.organizations.update_one(
            {"id": txn["organization_id"]},
            {"$set": {
                f"modules.{module}.enabled": True,
                f"modules.{module}.source": "paid",
                f"modules.{module}.tier": "pro",
                f"module_subscriptions.{module}.stripe_customer_id": session.get("customer"),
                f"module_subscriptions.{module}.stripe_subscription_id": session.get("subscription"),
                f"module_subscriptions.{module}.started_at": now,
                f"module_subscriptions.{module}.interval": txn.get("interval"),
                "updated_at": now,
            }},
        )
        await db.account_change_audit.insert_one({
            "id": f"subscribe-{txn['organization_id']}-{module}-{int(_now().timestamp())}",
            "organization_id": txn["organization_id"],
            "actor_id": user["id"],
            "kind": "module_subscription_paid",
            "module": module,
            "created_at": now,
        })
        logger.info("Module %s subscribed (paid) for org %s session %s", module, txn["organization_id"], session_id)

    return {"status": session.get("status"), "payment_status": payment_status, "module": module}
