"""
Pulse Fitness · Engineer Attention digest — iter 220j.

Single read-only endpoint that aggregates "things this engineer needs
to act on" so the Engineer App can render a single pulsing amber dot
on the hamburger menu, plus surface the exact reasons inside the
Account Settings drawer.

Why one endpoint and not derive client-side?
  • It lets us reuse the partner record + compliance docs + checklist
    + Stripe Connect state without making the engineer's home screen
    fire four separate XHRs.
  • The same digest is consumed by future surfaces (a banner on the
    job-detail view, the daily push notification job, etc.). Keeping
    the business rules server-side stops them drifting.

Severity ladder:
    "red"   → action blocks paid work (subscription past_due/canceled,
              compliance expired)
    "amber" → action is non-blocking but time-sensitive (cert expires
              in <14 days, Stripe Connect not finished, application
              pending review more than 3 working days)
    "green" → nothing needs attention.

Endpoint:
    GET /api/svc/engineer/attention
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/svc/engineer", tags=["Service Ops · Engineer attention (iter 220j)"])


_HIGHEST = {"red": 2, "amber": 1, "green": 0}


def _max_severity(items: list[dict]) -> str:
    if not items:
        return "green"
    return max((i.get("severity", "amber") for i in items), key=lambda s: _HIGHEST.get(s, 0))


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


@router.get("/attention")
async def engineer_attention(user=Depends(get_current_user)):
    """Aggregate engineer-attention items.

    Returns a flat list each consumer can format as it pleases. Each
    item carries a stable ``key`` so the frontend can dedupe / route
    on tap.
    """
    items: list[dict] = []
    now = datetime.now(timezone.utc)

    # ── Partner record / subscription / compliance ─────────────────
    partner = await db.partner_engineers.find_one({"user_id": user["id"]}, {"_id": 0})
    if partner:
        status = (partner.get("status") or "").lower()
        if status == "pending":
            items.append({
                "key": "partner_pending",
                "severity": "amber",
                "label": "Application under review",
                "hint": "We aim to respond within 2 working days.",
                "cta_to": "/partner-engineer",
            })
        elif status == "rejected":
            items.append({
                "key": "partner_rejected",
                "severity": "red",
                "label": "Application not approved",
                "hint": "Tap to update your details and resubmit.",
                "cta_to": "/partners/engineers/apply",
            })
        elif status == "suspended":
            items.append({
                "key": "partner_suspended",
                "severity": "red",
                "label": "Partner access suspended",
                "hint": "Contact Pulse Fitness support to discuss next steps.",
                "cta_to": "/partner-engineer",
            })

        sub = partner.get("subscription") or {}
        sub_status = (sub.get("status") or "").lower()
        if sub_status in ("past_due", "unpaid"):
            items.append({
                "key": "subscription_past_due",
                "severity": "red",
                "label": "Partner Plan payment failed",
                "hint": "Update your card to keep the Engineer App unlocked.",
                "cta_to": "/partner-engineer",
            })
        elif sub_status == "canceled":
            items.append({
                "key": "subscription_canceled",
                "severity": "red",
                "label": "Partner Plan cancelled",
                "hint": "Tap to reactivate and keep taking paid jobs.",
                "cta_to": "/partner-engineer",
            })
        elif status == "approved" and not sub.get("stripe_subscription_id"):
            items.append({
                "key": "subscription_inactive",
                "severity": "amber",
                "label": "Activate the Partner Plan",
                "hint": "Start your £30/mo plan to unlock the Engineer App.",
                "cta_to": "/partner-engineer",
            })

        # Compliance docs — flag expired or expiring in <14 days.
        docs = partner.get("compliance_docs") or {}
        for kind, blob in docs.items():
            if not isinstance(blob, dict):
                continue
            exp = _parse_iso(blob.get("expires_at"))
            if not exp:
                continue
            delta_days = (exp - now).days
            label_kind = kind.replace("_", " ").title()
            if delta_days < 0:
                items.append({
                    "key": f"compliance_expired_{kind}",
                    "severity": "red",
                    "label": f"{label_kind} expired",
                    "hint": "Re-upload to keep your verified status.",
                    "cta_to": "/partner-engineer",
                })
            elif delta_days <= 14:
                items.append({
                    "key": f"compliance_expiring_{kind}",
                    "severity": "amber",
                    "label": f"{label_kind} expires in {delta_days}d",
                    "hint": "Re-upload before it expires to avoid a gap.",
                    "cta_to": "/partner-engineer",
                })

        # Compliance-paused flag (set by the nightly job).
        if partner.get("compliance_paused"):
            items.append({
                "key": "compliance_paused",
                "severity": "red",
                "label": "Compliance paused",
                "hint": "Resolve missing docs to resume the verified badge.",
                "cta_to": "/partner-engineer",
            })

        # Stripe Connect (payouts) not finished.
        payout = partner.get("payout") or {}
        connect = payout.get("stripe_connect") or {}
        if not connect.get("charges_enabled"):
            items.append({
                "key": "stripe_connect_pending",
                "severity": "amber",
                "label": "Finish Stripe Connect",
                "hint": "≈3 min — required to take card payments on invoices.",
                "cta_to": "/svc/engineer/payouts",
            })

    # ── Dedupe (just in case) and sort by severity then label ──────
    seen: set[str] = set()
    unique: list[dict] = []
    for it in items:
        k = it["key"]
        if k in seen:
            continue
        seen.add(k)
        unique.append(it)
    unique.sort(key=lambda i: (-_HIGHEST.get(i.get("severity", "amber"), 0), i.get("label", "")))

    return {
        "count": len(unique),
        "severity": _max_severity(unique),
        "items": unique,
    }


__all__ = ["router"]
