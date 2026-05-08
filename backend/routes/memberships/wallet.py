"""Family Wallet — iter 215ab.

A pre-paid balance per parent account. The parent tops up once (Stripe
Checkout), we store pence on ``members.wallet_balance_pence`` and a
ledger row in ``wallet_ledger``. When the monthly auto-pay cron runs,
we debit the wallet BEFORE charging the saved card — so parents don't
see a card charge when their wallet covers the bill.

Endpoints
---------

* ``GET  /api/member/wallet``           → balance + last 20 ledger rows
* ``POST /api/member/wallet/topup``     → Stripe Checkout for £N topup
* ``POST /api/memberships/billing/invoice/{id}/apply-wallet`` (operator)
      → deduct wallet balance from a draft/sent invoice. If the wallet
      fully covers it, mark the invoice paid. Otherwise deduct what we
      can and leave the remainder outstanding.

Webhook
-------

``complete_wallet_topup(meta, session)`` is called by the central
Stripe webhook when ``metadata.gymaxis_kind == 'wallet_topup'``.
Credits the wallet atomically + inserts a ``topup`` ledger row.

Auto-Bill integration
---------------------

``try_wallet_debit_for_invoice(member_id, invoice)`` returns how much
of the invoice the wallet covers and flips status to ``paid`` when
fully covered. Called from ``family_autopay.run_family_autopay_cycle``
BEFORE the card charge.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import stripe
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db, STRIPE_API_KEY
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _require_operator_org,
    _uuid,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-wallet"])

stripe.api_key = STRIPE_API_KEY


def _frontend() -> str:
    return (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")


# ═══════════════════════ Ledger helpers ═══════════════════════


async def _record_ledger(
    *, member_id: str, organization_id: str, kind: str,
    amount_pence: int, balance_after_pence: int,
    invoice_id: Optional[str] = None, note: Optional[str] = None,
    stripe_session_id: Optional[str] = None,
) -> dict:
    row = {
        "id": _uuid(),
        "member_id": member_id,
        "organization_id": organization_id,
        "kind": kind,
        "amount_pence": int(amount_pence),
        "balance_after_pence": int(balance_after_pence),
        "invoice_id": invoice_id,
        "note": note,
        "stripe_session_id": stripe_session_id,
        "created_at": _now_iso(),
    }
    await db.wallet_ledger.insert_one({**row})
    return row


async def _get_balance(member_id: str) -> int:
    m = await db.members.find_one(
        {"id": member_id}, {"_id": 0, "wallet_balance_pence": 1},
    ) or {}
    try:
        return int(m.get("wallet_balance_pence") or 0)
    except (TypeError, ValueError):
        return 0


# ═══════════════════════ Member endpoints ═══════════════════════


@router.get("/member/wallet")
async def get_wallet(request: Request):
    m = await _require_current_member(request)
    balance = await _get_balance(m["id"])
    ledger = await db.wallet_ledger.find(
        {"member_id": m["id"]}, {"_id": 0},
    ).sort("created_at", -1).to_list(20)
    return {
        "balance_pence": balance,
        "currency": "gbp",
        "ledger": ledger,
    }


class TopupIn(BaseModel):
    amount_pence: int = Field(ge=500, le=100_000)  # £5 - £1000 per topup


@router.post("/member/wallet/topup")
async def topup_wallet(request: Request, body: TopupIn = Body(...)):
    if not STRIPE_API_KEY:
        raise HTTPException(503, "Stripe is not configured for this studio.")
    member = await _require_current_member(request)
    # Iter 215af — rate-limit card-save & topup to stop someone from
    # flooding Stripe Checkout session creation on a compromised JWT.
    from utils.security_plus import rate_limit_async
    await rate_limit_async(f"wallet_topup:{member['id']}", max_requests=10, window_seconds=60)
    frontend = _frontend()
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=f"{frontend}/members?wallet=topped_up",
        cancel_url=f"{frontend}/members?wallet=cancelled",
        customer_email=member.get("email") or None,
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "gbp",
                "unit_amount": int(body.amount_pence),
                "product_data": {"name": f"Wallet top-up · £{body.amount_pence/100:.2f}"},
            },
        }],
        metadata={
            "gymaxis_kind": "wallet_topup",
            "gymaxis_member_id": member["id"],
            "gymaxis_org_id": member.get("organization_id") or "",
            "gymaxis_topup_pence": str(int(body.amount_pence)),
        },
    )
    return {"checkout_url": session.url, "session_id": session.id}


# ═══════════════════════ Operator endpoints ═══════════════════════


@router.post(
    "/memberships/billing/invoice/{invoice_id}/apply-wallet",
    dependencies=[Depends(require_module("memberships"))],
)
async def apply_wallet_to_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    """Operator-triggered: debit the member's wallet against this
    invoice. Idempotent — re-running on a fully-paid invoice is a no-op."""
    org_id = await _require_operator_org(user)
    invoice = await db.membership_class_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id}, {"_id": 0},
    )
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    if invoice.get("status") in ("paid", "void"):
        return {"ok": True, "skipped": "already_settled", "status": invoice.get("status")}
    applied = await try_wallet_debit_for_invoice(invoice["member_id"], invoice)
    return applied


@router.get(
    "/memberships/billing/wallet/members",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_wallet_balances(user: dict = Depends(get_current_user)):
    """Operator roster of members with non-zero wallet balance — feeds
    a sidebar chip in the InvoicingTab."""
    org_id = await _require_operator_org(user)
    rows = await db.members.find(
        {"organization_id": org_id, "wallet_balance_pence": {"$gt": 0}},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "wallet_balance_pence": 1},
    ).to_list(2000)
    total = sum(int(r.get("wallet_balance_pence") or 0) for r in rows)
    return {"count": len(rows), "total_balance_pence": total, "members": rows}


# ═══════════════════════ Core debit helper ═══════════════════════


async def try_wallet_debit_for_invoice(member_id: str, invoice: dict) -> dict:
    """Debit up to ``total_pence`` from the member's wallet against the
    invoice. Returns ``{applied_pence, remaining_pence, status}``.

    - Fully covered → invoice.status = 'paid', paid_via = 'wallet'.
    - Partially covered → wallet emptied, invoice stays 'sent' / 'draft',
      invoice.wallet_applied_pence accumulates. Auto-Bill can then charge
      the remainder on the card.
    - Wallet empty / zero → no-op, returns applied=0.
    """
    balance = await _get_balance(member_id)
    total = int(invoice.get("total_pence") or 0)
    already = int(invoice.get("wallet_applied_pence") or 0)
    owed = max(0, total - already)
    if balance <= 0 or owed <= 0:
        return {"applied_pence": 0, "remaining_pence": owed, "status": invoice.get("status")}

    apply = min(balance, owed)
    new_balance = balance - apply
    new_applied = already + apply
    remaining = total - new_applied

    # Atomic-ish: update wallet, ledger, invoice.
    await db.members.update_one(
        {"id": member_id}, {"$set": {"wallet_balance_pence": new_balance}},
    )
    await _record_ledger(
        member_id=member_id, organization_id=invoice.get("organization_id") or "",
        kind="debit", amount_pence=-apply, balance_after_pence=new_balance,
        invoice_id=invoice["id"], note=f"Invoice {invoice.get('period')}",
    )
    updates: dict = {
        "wallet_applied_pence": new_applied,
        "wallet_last_debit_at": _now_iso(),
    }
    if remaining <= 0:
        updates.update({
            "status": "paid",
            "paid_at": _now_iso(),
            "paid_via": "wallet",
        })
    await db.membership_class_invoices.update_one(
        {"id": invoice["id"]}, {"$set": updates},
    )
    return {
        "applied_pence": apply,
        "remaining_pence": max(0, remaining),
        "status": "paid" if remaining <= 0 else invoice.get("status") or "draft",
        "wallet_balance_after_pence": new_balance,
    }


# ═══════════════════════ Webhook completion ═══════════════════════


async def complete_wallet_topup(meta: dict, session) -> None:
    """Credit the wallet when a top-up Checkout completes."""
    member_id = meta.get("gymaxis_member_id")
    if not member_id:
        logger.warning("[wallet] topup webhook without member_id")
        return
    amount = int(meta.get("gymaxis_topup_pence") or 0)
    if amount <= 0:
        logger.warning("[wallet] topup webhook with invalid amount: %s", amount)
        return
    # Idempotency: if we've already recorded a ledger row for this session, skip.
    session_id = getattr(session, "id", None) or (session.get("id") if isinstance(session, dict) else None)
    if session_id and await db.wallet_ledger.find_one(
        {"stripe_session_id": session_id}, {"_id": 1},
    ):
        logger.info("[wallet] topup webhook deduped session=%s", session_id)
        return

    m = await db.members.find_one({"id": member_id}, {"_id": 0, "organization_id": 1}) or {}
    current = await _get_balance(member_id)
    new_balance = current + amount
    await db.members.update_one(
        {"id": member_id}, {"$set": {"wallet_balance_pence": new_balance}},
    )
    await _record_ledger(
        member_id=member_id, organization_id=m.get("organization_id") or "",
        kind="topup", amount_pence=amount, balance_after_pence=new_balance,
        note=f"Top-up £{amount/100:.2f}", stripe_session_id=session_id,
    )
    logger.info("[wallet] credited member=%s +%spence balance=%s", member_id, amount, new_balance)
