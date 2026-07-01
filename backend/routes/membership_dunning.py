"""Membership dunning — recover failed/overdue member charges.

When a member's Stripe subscription charge fails, the memberships webhook
flips ``member_memberships.billing_status='past_due'``. This module lets
the operator recover that revenue: see at-risk members, fire staged
reminder emails, and retry the failed Stripe invoice on demand.

Money safety: a retry only re-attempts an EXISTING open Stripe invoice
(``stripe.Invoice.pay``) for a member who already failed a charge — it
never creates a new charge.

NOTE: B2B charge dunning is stubbed for a future invoicing model; today
the concrete target is membership subscriptions.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email

logger = logging.getLogger("membership_dunning")
router = APIRouter(prefix="/dunning", tags=["dunning"])
stripe.api_key = os.environ.get("STRIPE_API_KEY")

# Staged cadence: (stage, min days past due, headline).
STAGES = [
    (1, 1, "A quick reminder about your membership payment"),
    (2, 7, "Your membership payment is overdue"),
    (3, 14, "Final reminder — your membership is at risk"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


async def _operator_org(user: dict) -> str:
    if not user or user.get("account_type") == "member":
        raise HTTPException(403, "Operators only")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "No organization context")
    return org_id


def _days_past_due(mm: dict) -> int:
    ref = _parse_iso(mm.get("past_due_since")) or _parse_iso(mm.get("next_billing_at")) \
        or _parse_iso(mm.get("updated_at"))
    if not ref:
        return 0
    return max(0, (_now() - ref).days)


def _stage_for(days: int, fired: set[int]) -> int | None:
    elig = [s for s, mind, _ in STAGES if days >= mind and s not in fired]
    return max(elig) if elig else None


async def _at_risk_rows(org_id: str) -> list[dict]:
    mms = await db.member_memberships.find(
        {"organization_id": org_id, "billing_status": "past_due"}, {"_id": 0}).to_list(1000)
    rows = []
    for mm in mms:
        member = await db.members.find_one({"id": mm.get("member_id")}, {"_id": 0}) or {}
        days = _days_past_due(mm)
        reminders = mm.get("dunning", {}).get("reminders", []) if isinstance(mm.get("dunning"), dict) else []
        rows.append({
            "id": mm.get("id"),
            "member_id": mm.get("member_id"),
            "member_name": (f"{member.get('first_name','')} {member.get('last_name','')}").strip() or member.get("email") or "Member",
            "member_email": member.get("email"),
            "plan_name": mm.get("plan_name") or mm.get("plan_id"),
            "amount": float(mm.get("price") or mm.get("amount") or 0),
            "currency": mm.get("currency") or "gbp",
            "days_past_due": days,
            "reminders_sent": len(reminders),
            "last_reminder_at": reminders[-1]["sent_at"] if reminders else None,
            "has_subscription": bool(mm.get("stripe_subscription_id")),
        })
    rows.sort(key=lambda r: r["days_past_due"], reverse=True)
    return rows


def _reminder_html(name: str, plan: str, amount: float, ccy: str, stage: int) -> str:
    sym = {"gbp": "£", "usd": "$", "eur": "€"}.get(str(ccy).lower(), "")
    headline = next((h for s, _, h in STAGES if s == stage), "Reminder about your membership")
    urgency = ("We couldn't take your latest membership payment." if stage == 1
               else "Your membership payment is still outstanding." if stage == 2
               else "This is a final reminder before your membership is paused.")
    return (
        f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#0f172a">'
        f'<h2 style="color:#1d4ed8">{headline}</h2>'
        f'<p>Hi {name or "there"},</p>'
        f'<p>{urgency} Your <strong>{plan or "membership"}</strong> '
        f'({sym}{amount:.2f}) needs attention.</p>'
        f'<p>Please update your payment details or get in touch so we can keep your membership active. '
        f'Thank you!</p></div>'
    )


@router.get("/summary")
async def dunning_summary(user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    rows = await _at_risk_rows(org_id)
    return {
        "at_risk_count": len(rows),
        "at_risk_revenue": round(sum(r["amount"] for r in rows), 2),
        "never_reminded": sum(1 for r in rows if r["reminders_sent"] == 0),
    }


@router.get("/at-risk")
async def dunning_at_risk(user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    return {"members": await _at_risk_rows(org_id)}


async def _fire_reminder(org_id: str, mm: dict, stage: int) -> bool:
    member = await db.members.find_one({"id": mm.get("member_id")}, {"_id": 0}) or {}
    to = member.get("email")
    if not to:
        return False
    name = (f"{member.get('first_name','')} {member.get('last_name','')}").strip()
    html = _reminder_html(name, mm.get("plan_name") or "", float(mm.get("price") or 0),
                          mm.get("currency") or "gbp", stage)
    subject = next((h for s, _, h in STAGES if s == stage), "Membership payment reminder")
    ok = await send_email(to=to, subject=subject, html=html, organization_id=org_id,
                          kind="membership.dunning", category="service")
    if ok:
        await db.member_memberships.update_one(
            {"id": mm["id"], "organization_id": org_id},
            {"$push": {"dunning.reminders": {"stage": stage, "sent_at": _now_iso(),
                                             "days_past_due": _days_past_due(mm)}}})
    return ok


@router.post("/{mm_id}/remind")
async def remind_member(mm_id: str, user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    mm = await db.member_memberships.find_one({"id": mm_id, "organization_id": org_id}, {"_id": 0})
    if not mm:
        raise HTTPException(404, "Membership not found")
    if mm.get("billing_status") != "past_due":
        raise HTTPException(400, "This membership is not past due")
    fired = {r.get("stage") for r in mm.get("dunning", {}).get("reminders", [])} if isinstance(mm.get("dunning"), dict) else set()
    stage = _stage_for(_days_past_due(mm), fired) or (max(fired) if fired else 1)
    ok = await _fire_reminder(org_id, mm, stage)
    if not ok:
        raise HTTPException(502, "Could not send the reminder (no member email or email failed).")
    return {"ok": True, "stage": stage}


@router.post("/{mm_id}/retry")
async def retry_charge(mm_id: str, user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    mm = await db.member_memberships.find_one({"id": mm_id, "organization_id": org_id}, {"_id": 0})
    if not mm:
        raise HTTPException(404, "Membership not found")
    sub_id = mm.get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(409, "No Stripe subscription on file to retry")
    try:
        invs = stripe.Invoice.list(subscription=sub_id, status="open", limit=1)
        if not invs.data:
            raise HTTPException(409, "No open invoice to retry — Stripe may have already recovered it")
        paid = stripe.Invoice.pay(invs.data[0].id)
        if paid.status == "paid":
            await db.member_memberships.update_one(
                {"id": mm_id, "organization_id": org_id},
                {"$set": {"billing_status": "current", "updated_at": _now_iso()}})
        await db.member_memberships.update_one(
            {"id": mm_id, "organization_id": org_id},
            {"$push": {"dunning.retries": {"at": _now_iso(), "invoice": paid.id, "status": paid.status}}})
        return {"ok": True, "invoice_status": paid.status}
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        msg = getattr(e, "user_message", None) or str(e)
        logger.warning("retry charge failed: %s", e)
        raise HTTPException(502, f"Retry failed: {msg}")


@router.post("/run")
async def run_dunning(body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    mms = await db.member_memberships.find(
        {"organization_id": org_id, "billing_status": "past_due"}, {"_id": 0}).to_list(1000)
    sent = skipped = 0
    for mm in mms:
        fired = {r.get("stage") for r in mm.get("dunning", {}).get("reminders", [])} if isinstance(mm.get("dunning"), dict) else set()
        stage = _stage_for(_days_past_due(mm), fired)
        if not stage:
            skipped += 1
            continue
        sent += 1 if await _fire_reminder(org_id, mm, stage) else 0
    return {"reminders_sent": sent, "skipped": skipped, "at_risk": len(mms)}
