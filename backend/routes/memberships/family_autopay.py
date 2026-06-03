"""Family Auto-Bill — iter 215aa.

Dance schools, pilates studios, and term-based parents hate logging in
to pay a monthly invoice. With Family Auto-Bill a parent saves a card
once and GymAxis quietly charges their Stripe customer on the 1st of
each month for the PREVIOUS period's class invoice (draft / sent).

Flow
----

1. Member calls ``POST /api/member/billing/auto-pay/setup`` — we create
   a Stripe Checkout session in ``mode=setup`` that saves a card to a
   Stripe Customer. The returned ``checkout_url`` is a normal Stripe
   hosted checkout the parent clicks from their portal.

2. On successful card save, the central Stripe webhook
   (memberships_payments.stripe_webhook) routes to
   ``complete_autopay_setup`` based on
   ``metadata.gymaxis_kind == "autopay_setup"``. We persist the
   customer id + default payment method + card brand/last4 on the
   ``members`` doc and flip ``auto_pay_enabled=true``.

3. The monthly sweeper (``run_family_autopay_cycle``) — plugged into
   the existing ``sicon_poller`` loop — fires on the 1st of every UTC
   month (idempotent per org+member+period) and creates an off-session
   PaymentIntent against the saved customer+pm for the previous
   period's unpaid invoice. Successful charges mark the invoice
   ``paid``; failures flag ``auto_pay_last_error`` on the invoice so
   operators can see it and fall back to a normal pay-link.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from utils.database import db, STRIPE_API_KEY
from utils.email import send_email

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _require_operator_org,
)
from utils.auth import get_current_user
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-family-autopay"])

stripe.api_key = STRIPE_API_KEY


# ═══════════════════════ Member-side endpoints ═══════════════════════


def _frontend() -> str:
    return (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")


class AutoPayStatus(BaseModel):
    enabled: bool
    card_brand: Optional[str] = None
    card_last4: Optional[str] = None
    last_saved_at: Optional[str] = None


@router.get("/member/billing/auto-pay", response_model=AutoPayStatus)
async def get_autopay_status(request: Request):
    """Return the member's current Auto-Bill status."""
    m = await _require_current_member(request)
    return AutoPayStatus(
        enabled=bool(m.get("auto_pay_enabled")),
        card_brand=m.get("auto_pay_card_brand"),
        card_last4=m.get("auto_pay_card_last4"),
        last_saved_at=m.get("auto_pay_saved_at"),
    )


@router.post("/member/billing/auto-pay/setup")
async def start_autopay_setup(request: Request):
    """Kick off a Stripe hosted card-save checkout. Returns a one-shot
    URL the member can open to save a card."""
    if not STRIPE_API_KEY:
        raise HTTPException(503, "Stripe is not configured for this studio.")
    member = await _require_current_member(request)
    # Iter 215af — rate-limit card-save to stop mass Stripe Customer
    # creation from a compromised JWT.
    from utils.security_plus import rate_limit_async
    await rate_limit_async(f"autopay_setup:{member['id']}", max_requests=5, window_seconds=300)
    frontend = _frontend()
    success = f"{frontend}/members?autopay=saved"
    cancel = f"{frontend}/members?autopay=cancelled"

    # Re-use any existing Stripe customer on the member to avoid duplicates.
    customer_id = member.get("auto_pay_customer_id")
    if not customer_id:
        cust = stripe.Customer.create(
            email=member.get("email") or None,
            name=(f"{member.get('first_name') or ''} {member.get('last_name') or ''}").strip() or None,
            metadata={
                "gymaxis_member_id": member["id"],
                "gymaxis_org_id": member.get("organization_id") or "",
            },
        )
        customer_id = cust.id
        await db.members.update_one(
            {"id": member["id"]}, {"$set": {"auto_pay_customer_id": customer_id}},
        )

    session = stripe.checkout.Session.create(
        mode="setup",
        success_url=success,
        cancel_url=cancel,
        customer=customer_id,
        payment_method_types=["card"],
        metadata={
            "gymaxis_kind": "autopay_setup",
            "gymaxis_member_id": member["id"],
            "gymaxis_org_id": member.get("organization_id") or "",
        },
    )
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/member/billing/auto-pay/disable")
async def disable_autopay(request: Request):
    """Turn Auto-Bill off. We keep the Stripe customer reference so the
    parent can re-enable without re-entering a card if they want."""
    member = await _require_current_member(request)
    await db.members.update_one(
        {"id": member["id"]},
        {"$set": {
            "auto_pay_enabled": False,
            "auto_pay_disabled_at": _now_iso(),
        }},
    )
    return {"ok": True, "enabled": False}


# ═══════════════════════ Webhook completion ═══════════════════════


async def complete_autopay_setup(meta: dict, session: dict) -> None:
    """Called by the central Stripe webhook when a setup-mode checkout
    completes. Pulls the saved payment method off the SetupIntent,
    stamps the member doc, and sends a confirmation email."""
    member_id = meta.get("gymaxis_member_id")
    if not member_id:
        logger.warning("[autopay] webhook without gymaxis_member_id")
        return
    si_id = session.get("setup_intent") if isinstance(session, dict) else getattr(session, "setup_intent", None)
    payment_method_id: Optional[str] = None
    card_brand: Optional[str] = None
    card_last4: Optional[str] = None
    if si_id:
        try:
            si = stripe.SetupIntent.retrieve(si_id)
            payment_method_id = si.get("payment_method") if isinstance(si, dict) else getattr(si, "payment_method", None)
            if payment_method_id:
                pm = stripe.PaymentMethod.retrieve(payment_method_id)
                card = (pm.get("card") if isinstance(pm, dict) else getattr(pm, "card", {})) or {}
                card_brand = card.get("brand") if isinstance(card, dict) else getattr(card, "brand", None)
                card_last4 = card.get("last4") if isinstance(card, dict) else getattr(card, "last4", None)
        except Exception:
            logger.exception("[autopay] failed to retrieve SetupIntent/PaymentMethod")

    updates = {
        "auto_pay_enabled": True,
        "auto_pay_saved_at": _now_iso(),
        "auto_pay_card_brand": card_brand,
        "auto_pay_card_last4": card_last4,
    }
    if payment_method_id:
        updates["auto_pay_payment_method_id"] = payment_method_id

    await db.members.update_one({"id": member_id}, {"$set": updates})
    logger.info("[autopay] member=%s saved card ending %s", member_id, card_last4)


# ═══════════════════════ Monthly sweeper (cron) ═══════════════════════


def _period_label(period: str) -> str:
    try:
        y, m = period.split("-")
        return datetime(int(y), int(m), 1).strftime("%B %Y")
    except Exception:
        return period


async def _send_autopay_success_email(
    *, member: dict, invoice: dict, charged_pence: int,
    wallet_applied_pence: int, card_brand: Optional[str], card_last4: Optional[str],
) -> None:
    """Iter 215ac — friendly receipt after a successful Auto-Bill run."""
    email = member.get("email")
    if not email:
        return
    org = await db.organizations.find_one(
        {"id": invoice.get("organization_id")},
        {"_id": 0, "name": 1, "primary_color": 1},
    ) or {}
    color = org.get("primary_color") or "#00B2C7"
    org_name = org.get("name") or "Your studio"
    period_label = _period_label(invoice.get("period") or "")
    total = int(invoice.get("total_pence") or 0)
    first = (member.get("first_name") or "there").strip() or "there"
    card_line = (
        f"{(card_brand or 'Card').upper()} •••• {card_last4}" if card_last4 else "your saved card"
    )
    wallet_row = (
        f"<tr><td style='padding:6px 0;color:#6B7280;font-size:13px'>Wallet applied</td>"
        f"<td style='padding:6px 0;font-size:13px;text-align:right;color:#10B981'>−£{wallet_applied_pence/100:.2f}</td></tr>"
        if wallet_applied_pence > 0 else ""
    )
    html = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:14px;overflow:hidden">
  <div style="background:{color};padding:18px 24px">
    <div style="color:#fff;font-size:11px;letter-spacing:.22em;text-transform:uppercase;opacity:.9">Auto-Bill receipt · {period_label}</div>
    <div style="color:#fff;font-size:22px;font-weight:800;margin-top:4px">{org_name}</div>
  </div>
  <div style="padding:24px">
    <p style="margin:0 0 10px;font-size:15px;color:#111">Hi {first},</p>
    <p style="margin:0 0 20px;font-size:14px;color:#444;line-height:1.55">
      Your {period_label} class invoice was paid automatically. No action needed.
    </p>
    <table style="width:100%;border-collapse:collapse;border-top:1px solid #eee;border-bottom:1px solid #eee;margin-bottom:20px">
      <tr><td style="padding:8px 0;color:#6B7280;font-size:13px">Invoice total</td>
          <td style="padding:8px 0;font-size:13px;text-align:right">£{total/100:.2f}</td></tr>
      {wallet_row}
      <tr><td style="padding:8px 0;font-size:14px;font-weight:800">Charged to {card_line}</td>
          <td style="padding:8px 0;font-size:16px;font-weight:800;text-align:right;color:{color}">£{charged_pence/100:.2f}</td></tr>
    </table>
    <p style="margin:0;font-size:12px;color:#6B7280;line-height:1.55">
      You can turn Auto-Bill off any time from your member portal.
    </p>
  </div>
</div>"""
    try:
        await send_email(email, f"Paid: {period_label} invoice · {org_name}", html, category="billing")
    except Exception:
        logger.exception("[autopay] success email send failed to=%s", email)


async def _send_autopay_decline_email(
    *, member: dict, invoice: dict, error_msg: str,
    card_brand: Optional[str], card_last4: Optional[str],
    tone: str = "firm",
) -> None:
    """Iter 215ac/215ad — nudge when Stripe declines the saved card.

    ``tone`` varies the subject/body copy for dunning-ladder retries:
        * ``"firm"``   — first failure (original decline email)
        * ``"gentle"`` — retry #1 (day +3): "just a reminder"
        * ``"stern"``  — retry #2 (day +7): "card still declining"
        * ``"final"``  — retry #3 (day +14): "pausing access"
    """
    email = member.get("email")
    if not email:
        return
    org = await db.organizations.find_one(
        {"id": invoice.get("organization_id")},
        {"_id": 0, "name": 1, "primary_color": 1},
    ) or {}
    color = org.get("primary_color") or "#00B2C7"
    org_name = org.get("name") or "your studio"
    period_label = _period_label(invoice.get("period") or "")
    first = (member.get("first_name") or "there").strip() or "there"
    card_line = (
        f"{(card_brand or 'Card').upper()} •••• {card_last4}" if card_last4 else "your saved card"
    )
    frontend = _frontend()
    portal = f"{frontend}/members" if frontend else "/members"

    # Tone-specific header + body.
    heading, subj_prefix, body_intro = {
        "firm": (
            "Payment could not be processed",
            "Action needed",
            f"We tried to charge {card_line} for your {period_label} class invoice but it didn't go through.",
        ),
        "gentle": (
            "Quick reminder — invoice still unpaid",
            "Reminder",
            f"Just a gentle nudge: your {period_label} invoice is still outstanding. We'll try {card_line} again in a few days.",
        ),
        "stern": (
            "Your card is still being declined",
            "Important",
            f"We've tried {card_line} twice and the charge keeps failing. Please update your card or top up your wallet so we can settle the {period_label} invoice.",
        ),
        "final": (
            "Final notice — access may be paused",
            "Final notice",
            f"This is our final attempt to collect the {period_label} invoice on {card_line}. If we can't complete payment, your class booking will be paused until the balance is cleared.",
        ),
    }.get(tone, (
        "Payment could not be processed",
        "Action needed",
        f"We tried to charge {card_line} for your {period_label} class invoice but it didn't go through.",
    ))
    header_bg = "#991B1B" if tone == "final" else ("#DC2626" if tone in ("firm", "stern") else "#B45309")

    html = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto;background:#fff;border:1px solid #FECACA;border-radius:14px;overflow:hidden">
  <div style="background:{header_bg};padding:18px 24px">
    <div style="color:#fff;font-size:11px;letter-spacing:.22em;text-transform:uppercase;opacity:.9">{heading}</div>
    <div style="color:#fff;font-size:20px;font-weight:800;margin-top:4px">{org_name} · {period_label}</div>
  </div>
  <div style="padding:24px">
    <p style="margin:0 0 10px;font-size:15px;color:#111">Hi {first},</p>
    <p style="margin:0 0 14px;font-size:14px;color:#444;line-height:1.55">{body_intro}</p>
    <p style="margin:0 0 18px;font-size:13px;color:#DC2626;background:#FEF2F2;border-radius:8px;padding:10px 12px;line-height:1.45">
      <strong>Reason:</strong> {error_msg or 'Your bank declined the charge.'}
    </p>
    <div style="text-align:center;margin:0 0 4px">
      <a href="{portal}" style="display:inline-block;background:{color};color:#0A0C10;padding:12px 22px;border-radius:999px;font-weight:800;text-decoration:none;font-size:14px">
        Open your member portal →
      </a>
    </div>
  </div>
</div>"""
    try:
        await send_email(email, f"{subj_prefix}: {period_label} invoice · {org_name}", html, category="billing")
    except Exception:
        logger.exception("[autopay] decline email send failed to=%s", email)


def _previous_period_iso() -> str:
    now = datetime.now(timezone.utc)
    y, m = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
    return f"{y:04d}-{m:02d}"


# ═══════════════════ Dunning retry ladder (iter 215ad) ═══════════════════

# Each entry: (days_after_last_attempt, email_tone)
_RETRY_LADDER = [
    (3, "gentle"),   # retry #1: day +3 — gentle reminder
    (7, "stern"),    # retry #2: day +7 — card still declining
    (14, "final"),   # retry #3: day +14 — final notice / pause access
]


def _next_retry_tone(attempts: int) -> tuple[Optional[str], str]:
    """Given the number of PAST failed attempts, return (iso_due_at,
    tone_for_the_next_email). ``attempts=0`` after the first failure →
    schedules retry #1 at day +3. Returns ``(None, "")`` once the
    ladder is exhausted."""
    if attempts >= len(_RETRY_LADDER):
        return None, ""
    days, tone = _RETRY_LADDER[attempts]
    due = datetime.now(timezone.utc) + timedelta(days=days)
    return due.isoformat(), tone


async def _schedule_or_exhaust_retry(invoice: dict, attempts: int) -> dict:
    """After a failed charge, advance the retry schedule or mark the
    invoice as ``auto_pay_retry_exhausted=True`` on the last rung.
    Returns ``{exhausted: bool, next_due_at: Optional[str], tone: str}``.
    """
    next_due, tone = _next_retry_tone(attempts)
    if next_due is None:
        await db.membership_class_invoices.update_one(
            {"id": invoice["id"]},
            {"$set": {
                "auto_pay_retry_exhausted": True,
                "auto_pay_retry_exhausted_at": _now_iso(),
                "auto_pay_next_retry_at": None,
            }},
        )
        return {"exhausted": True, "next_due_at": None, "tone": ""}
    await db.membership_class_invoices.update_one(
        {"id": invoice["id"]},
        {"$set": {
            "auto_pay_retry_attempts": attempts + 1,
            "auto_pay_next_retry_at": next_due,
        }},
    )
    return {"exhausted": False, "next_due_at": next_due, "tone": tone}


async def _attempt_autopay_charge(member: dict, invoice: dict) -> dict:
    """Shared charge path — tries wallet first then off-session card.
    Returns ``{outcome: 'paid'|'wallet_only'|'declined'|'skipped', ...}``.

    Does NOT send emails or schedule retries — the caller (either the
    monthly sweep or the dunning-ladder retry) decides which copy to
    send and whether to advance the ladder.
    """
    if int(invoice.get("total_pence") or 0) <= 0:
        return {"outcome": "skipped", "reason": "zero_total"}

    # Wallet first.
    try:
        from routes.memberships.wallet import try_wallet_debit_for_invoice
        wallet_result = await try_wallet_debit_for_invoice(member["id"], invoice)
    except Exception:
        logger.exception("[autopay] wallet debit failed invoice=%s", invoice["id"])
        wallet_result = {
            "applied_pence": 0,
            "remaining_pence": int(invoice["total_pence"]),
            "status": invoice.get("status"),
        }

    if wallet_result.get("status") == "paid":
        return {
            "outcome": "wallet_only",
            "applied_pence": int(wallet_result.get("applied_pence") or 0),
            "charged_pence": 0,
            "wallet_applied_pence": int(wallet_result.get("applied_pence") or 0),
        }

    charge_amount = int(wallet_result.get("remaining_pence") or invoice["total_pence"])
    if charge_amount <= 0:
        return {"outcome": "skipped", "reason": "zero_after_wallet"}

    try:
        pi = stripe.PaymentIntent.create(
            amount=charge_amount,
            currency="gbp",
            customer=member["auto_pay_customer_id"],
            payment_method=member["auto_pay_payment_method_id"],
            off_session=True,
            confirm=True,
            description=f"Auto-Bill · {invoice.get('period')}",
            metadata={
                "gymaxis_kind": "autopay_charge",
                "gymaxis_invoice_id": invoice["id"],
                "gymaxis_member_id": member["id"],
                "gymaxis_org_id": member.get("organization_id") or "",
                "gymaxis_wallet_applied_pence": str(int(wallet_result.get("applied_pence") or 0)),
            },
        )
    except stripe.CardError as e:
        return {
            "outcome": "declined",
            "error_msg": str(getattr(e, "user_message", None) or e),
            "wallet_applied_pence": int(wallet_result.get("applied_pence") or 0),
        }
    except Exception as e:
        logger.exception("[autopay] charge failed invoice=%s", invoice["id"])
        return {
            "outcome": "declined",
            "error_msg": str(e)[:200],
            "wallet_applied_pence": int(wallet_result.get("applied_pence") or 0),
        }

    if pi.status == "succeeded":
        return {
            "outcome": "paid",
            "charged_pence": charge_amount,
            "payment_intent_id": pi.id,
            "wallet_applied_pence": int(wallet_result.get("applied_pence") or 0),
        }
    return {
        "outcome": "declined",
        "error_msg": f"Payment status came back as '{pi.status}'.",
        "wallet_applied_pence": int(wallet_result.get("applied_pence") or 0),
    }


async def run_autopay_retry_ladder() -> dict:
    """Daily cron — walk invoices with ``auto_pay_next_retry_at <= now``,
    re-attempt the charge, and advance/exhaust the retry schedule.

    Safe to run multiple times per day (idempotent via the invoice's
    own ``auto_pay_next_retry_at`` being nulled on success or pushed
    forward on failure).
    """
    if not STRIPE_API_KEY:
        return {"ok": False, "reason": "stripe_not_configured"}

    now_iso = _now_iso()
    stats = {"ok": True, "retried": 0, "paid": 0, "declined": 0, "exhausted": 0}

    cursor = db.membership_class_invoices.find(
        {
            "auto_pay_next_retry_at": {"$ne": None, "$lte": now_iso},
            "status": {"$in": ["draft", "sent"]},
            "auto_pay_retry_exhausted": {"$ne": True},
        },
        {"_id": 0},
    )
    async for invoice in cursor:
        member = await db.members.find_one(
            {"id": invoice.get("member_id")},
            {"_id": 0, "id": 1, "organization_id": 1, "auto_pay_customer_id": 1,
             "auto_pay_payment_method_id": 1, "email": 1,
             "first_name": 1, "last_name": 1,
             "auto_pay_card_brand": 1, "auto_pay_card_last4": 1,
             "auto_pay_enabled": 1},
        )
        if not member or not member.get("auto_pay_enabled") or not member.get("auto_pay_payment_method_id"):
            # Member disabled auto-pay or removed card — halt the ladder.
            await db.membership_class_invoices.update_one(
                {"id": invoice["id"]},
                {"$set": {"auto_pay_next_retry_at": None}},
            )
            continue

        stats["retried"] += 1
        result = await _attempt_autopay_charge(member, invoice)

        if result["outcome"] in ("paid", "wallet_only"):
            # Success — clear retry state, mark paid if not already by wallet.
            updates = {"auto_pay_next_retry_at": None, "auto_pay_retry_exhausted": False}
            if result["outcome"] == "paid":
                updates.update({
                    "status": "paid",
                    "paid_at": _now_iso(),
                    "paid_via": "stripe_autopay_retry",
                    "auto_pay_charged_at": _now_iso(),
                    "auto_pay_payment_intent_id": result.get("payment_intent_id"),
                })
            await db.membership_class_invoices.update_one(
                {"id": invoice["id"]}, {"$set": updates},
            )
            await _send_autopay_success_email(
                member=member, invoice=invoice,
                charged_pence=int(result.get("charged_pence") or 0),
                wallet_applied_pence=int(result.get("wallet_applied_pence") or 0),
                card_brand=member.get("auto_pay_card_brand"),
                card_last4=member.get("auto_pay_card_last4"),
            )
            stats["paid"] += 1
            continue

        # Still failing — advance the ladder.
        attempts_so_far = int(invoice.get("auto_pay_retry_attempts") or 0)
        schedule = await _schedule_or_exhaust_retry(invoice, attempts_so_far)
        await db.membership_class_invoices.update_one(
            {"id": invoice["id"]},
            {"$set": {
                "auto_pay_last_error": result.get("error_msg") or "declined",
                "auto_pay_last_attempt_at": _now_iso(),
            }},
        )
        # Email tone: if we just exhausted the ladder, send "final";
        # otherwise send the tone of the NEXT scheduled retry (so the
        # member gets a preview of escalation).
        tone = "final" if schedule["exhausted"] else (schedule["tone"] or "stern")
        await _send_autopay_decline_email(
            member=member, invoice=invoice,
            error_msg=result.get("error_msg") or "Your bank declined the charge.",
            card_brand=member.get("auto_pay_card_brand"),
            card_last4=member.get("auto_pay_card_last4"),
            tone=tone,
        )
        if schedule["exhausted"]:
            stats["exhausted"] += 1
        else:
            stats["declined"] += 1

    return stats


async def run_family_autopay_cycle() -> dict:
    """Idempotent cron — charge every auto-pay member's outstanding
    invoice for the PREVIOUS period. Runs once-per-UTC-day from the
    sicon_poller loop. Safe to call more than once per day: we skip
    invoices already marked paid OR already charged this period.
    """
    if not STRIPE_API_KEY:
        return {"ok": False, "reason": "stripe_not_configured"}
    now = datetime.now(timezone.utc)
    # Only fire on the 1st-3rd of the month to give a small re-try
    # window if yesterday's run was missed (dyno restart etc).
    if now.day > 3:
        return {"ok": True, "skipped": "not_invoice_window"}

    period = _previous_period_iso()
    stats = {"ok": True, "period": period, "attempted": 0, "charged": 0, "skipped": 0, "failed": 0}

    # Idempotency lock — one sweep doc per UTC day.
    lock_id = f"autopay-sweep-{now.strftime('%Y-%m-%d')}"
    lock = await db.system_jobs.find_one({"id": lock_id}, {"_id": 0})
    if lock and lock.get("status") == "complete":
        return {"ok": True, "deduped": True}
    await db.system_jobs.update_one(
        {"id": lock_id},
        {"$set": {"id": lock_id, "kind": "autopay_sweep", "started_at": _now_iso(), "status": "running"}},
        upsert=True,
    )

    cursor = db.members.find(
        {"auto_pay_enabled": True, "auto_pay_payment_method_id": {"$exists": True}},
        {"_id": 0, "id": 1, "organization_id": 1, "auto_pay_customer_id": 1,
         "auto_pay_payment_method_id": 1, "email": 1,
         "first_name": 1, "last_name": 1,
         "auto_pay_card_brand": 1, "auto_pay_card_last4": 1},
    )
    async for m in cursor:
        invoice = await db.membership_class_invoices.find_one(
            {
                "organization_id": m.get("organization_id"),
                "member_id": m["id"],
                "period": period,
                "status": {"$in": ["draft", "sent"]},
            },
            {"_id": 0},
        )
        if not invoice or int(invoice.get("total_pence") or 0) <= 0:
            stats["skipped"] += 1
            continue
        if invoice.get("auto_pay_charged_at"):
            stats["skipped"] += 1
            continue

        # Iter 215ab — try the wallet FIRST. If it fully covers the
        # invoice we skip the card charge entirely. If it partially
        # covers, we charge the card for the remainder.
        try:
            from routes.memberships.wallet import try_wallet_debit_for_invoice
            wallet_result = await try_wallet_debit_for_invoice(m["id"], invoice)
        except Exception:
            logger.exception("[autopay] wallet debit failed invoice=%s", invoice["id"])
            wallet_result = {"applied_pence": 0, "remaining_pence": int(invoice["total_pence"]), "status": invoice.get("status")}
        if wallet_result.get("status") == "paid":
            stats["charged"] += 1
            stats.setdefault("wallet_only", 0)
            stats["wallet_only"] += 1
            # Receipt email — "paid from wallet, no card charge".
            await _send_autopay_success_email(
                member=m, invoice=invoice,
                charged_pence=0,
                wallet_applied_pence=int(wallet_result.get("applied_pence") or 0),
                card_brand=None, card_last4=None,
            )
            continue
        charge_amount = int(wallet_result.get("remaining_pence") or invoice["total_pence"])
        if charge_amount <= 0:
            stats["skipped"] += 1
            continue

        stats["attempted"] += 1
        try:
            pi = stripe.PaymentIntent.create(
                amount=charge_amount,
                currency="gbp",
                customer=m["auto_pay_customer_id"],
                payment_method=m["auto_pay_payment_method_id"],
                off_session=True,
                confirm=True,
                description=f"Auto-Bill · {invoice.get('period')}",
                metadata={
                    "gymaxis_kind": "autopay_charge",
                    "gymaxis_invoice_id": invoice["id"],
                    "gymaxis_member_id": m["id"],
                    "gymaxis_org_id": m.get("organization_id") or "",
                    "gymaxis_wallet_applied_pence": str(int(wallet_result.get("applied_pence") or 0)),
                },
            )
            if pi.status == "succeeded":
                await db.membership_class_invoices.update_one(
                    {"id": invoice["id"]},
                    {"$set": {
                        "status": "paid",
                        "paid_at": _now_iso(),
                        "paid_via": "stripe_autopay",
                        "auto_pay_charged_at": _now_iso(),
                        "auto_pay_payment_intent_id": pi.id,
                    }},
                )
                stats["charged"] += 1
                await _send_autopay_success_email(
                    member=m, invoice=invoice,
                    charged_pence=charge_amount,
                    wallet_applied_pence=int(wallet_result.get("applied_pence") or 0),
                    card_brand=m.get("auto_pay_card_brand"),
                    card_last4=m.get("auto_pay_card_last4"),
                )
            else:
                await db.membership_class_invoices.update_one(
                    {"id": invoice["id"]},
                    {"$set": {"auto_pay_last_error": f"unexpected status: {pi.status}",
                              "auto_pay_last_attempt_at": _now_iso()}},
                )
                stats["failed"] += 1
                # Iter 215ad — start the retry ladder on first failure.
                await _schedule_or_exhaust_retry(invoice, int(invoice.get("auto_pay_retry_attempts") or 0))
                await _send_autopay_decline_email(
                    member=m, invoice=invoice,
                    error_msg=f"Payment status came back as '{pi.status}'.",
                    card_brand=m.get("auto_pay_card_brand"),
                    card_last4=m.get("auto_pay_card_last4"),
                    tone="firm",
                )
        except stripe.CardError as e:
            msg = str(getattr(e, "user_message", None) or e)
            await db.membership_class_invoices.update_one(
                {"id": invoice["id"]},
                {"$set": {"auto_pay_last_error": msg,
                          "auto_pay_last_attempt_at": _now_iso()}},
            )
            stats["failed"] += 1
            await _schedule_or_exhaust_retry(invoice, int(invoice.get("auto_pay_retry_attempts") or 0))
            await _send_autopay_decline_email(
                member=m, invoice=invoice, error_msg=msg,
                card_brand=m.get("auto_pay_card_brand"),
                card_last4=m.get("auto_pay_card_last4"),
                tone="firm",
            )
        except Exception as e:
            logger.exception("[autopay] charge failed invoice=%s", invoice["id"])
            await db.membership_class_invoices.update_one(
                {"id": invoice["id"]},
                {"$set": {"auto_pay_last_error": str(e)[:200],
                          "auto_pay_last_attempt_at": _now_iso()}},
            )
            stats["failed"] += 1

    await db.system_jobs.update_one(
        {"id": lock_id},
        {"$set": {"status": "complete", "finished_at": _now_iso(), "stats": stats}},
    )
    return stats


# ═══════════════════════ Operator-side helpers ═══════════════════════


@router.get(
    "/memberships/billing/autopay/members",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_autopay_members(user: dict = Depends(get_current_user)):
    """Return all members in this org with Auto-Bill enabled — feeds a
    small badge/filter in the operator InvoicingTab."""
    org_id = await _require_operator_org(user)
    rows = await db.members.find(
        {"organization_id": org_id, "auto_pay_enabled": True},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1,
         "auto_pay_card_brand": 1, "auto_pay_card_last4": 1, "auto_pay_saved_at": 1},
    ).to_list(2000)
    return {"count": len(rows), "members": rows}
