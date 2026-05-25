"""Iter 216h284 — Partner Engineer first-7-days activation checklist.

Closes Gap 5 from the BA audit: newly approved engineers had no
guided "do this next" path. The plan's value lands at the 5- and
10-referral milestones, but most engineers don't get there because
their first session is "where do I start?".

The checklist has 6 milestones. Most auto-resolve from existing
fields on the partner record so the engineer's just doing the
underlying action, not maintaining a TODO list:

1. **Approved**                 — implicit (they wouldn't see this card otherwise)
2. **Subscribe to Partner Plan** — `subscription.stripe_subscription_id` set
3. **Add your DBS / RTW docs**   — at least one `compliance_docs.*.file`
4. **Copy your referral link**   — ack flag `checklist.referral_link_copied_at`
5. **Get your first referral**   — `referrals_count > 0`
6. **Set service area**          — `service_postcode` AND `travel_radius_km`

The two manual-ack steps (4 + 6 if not set during apply) are persisted
under `partner.checklist.<key>_at`. Server-side computation means a
fresh dashboard load always sees the latest truth — no client cache
to invalidate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

CHECKLIST_KEYS = (
    "approved",
    "subscribed",
    "stripe_connect_ready",
    "compliance_uploaded",
    "referral_link_copied",
    "first_referral",
    "service_area_set",
)

# Steps the user can manually mark as done (the rest auto-resolve).
ACKABLE_KEYS = {"referral_link_copied"}


def _step(key: str, label: str, hint: str, done: bool, completed_at: Optional[datetime] = None) -> dict:
    return {
        "key": key,
        "label": label,
        "hint": hint,
        "done": bool(done),
        "completed_at": completed_at.isoformat() if isinstance(completed_at, datetime) else None,
    }


def build_checklist(partner: dict, referrals_count: int) -> dict:
    """Pure function — given a partner doc + the count of referrals,
    return the full checklist payload the dashboard renders."""
    cl_acks = partner.get("checklist") or {}
    sub = partner.get("subscription") or {}
    compliance = partner.get("compliance_docs") or {}
    any_compliance_uploaded = any(
        isinstance(blob, dict) and blob.get("file") for blob in compliance.values()
    )
    has_service_area = bool(partner.get("service_postcode")) and bool(partner.get("travel_radius_km"))
    # Iter 219e — Stripe Connect Express readiness. The Engineer App's
    # invoice / payouts flow needs `payout.stripe_connect.charges_enabled`
    # to be true before the engineer can take card payments. We use the
    # same field the `/api/svc/engineer/stripe/connect/status` route
    # reads, so any onboarding callback that flips it green also flips
    # this checklist step green on next dashboard load.
    payout = partner.get("payout") or {}
    stripe_connect = payout.get("stripe_connect") or {}
    stripe_connect_ready = bool(stripe_connect.get("charges_enabled"))

    steps = [
        _step("approved", "Approved as a Partner",
              "You're in the network. Welcome.",
              done=True, completed_at=partner.get("approved_at")),
        _step("subscribed", "Start your Partner Plan",
              "£30/mo · drops automatically as you refer gyms — free at 10. Powers the engineer features.",
              done=bool(sub.get("stripe_subscription_id"))),
        _step("stripe_connect_ready", "Connect Stripe Express for payouts",
              "Takes about 3 minutes — required to take card payments from customers on your invoices.",
              done=stripe_connect_ready),
        _step("compliance_uploaded", "Upload your first compliance doc",
              "DBS, Right-to-Work, Safeguarding or Public Liability. Any one of the four counts here.",
              done=any_compliance_uploaded),
        _step("referral_link_copied", "Copy your referral link",
              "Share it with a gym contact this week. The link is at the top of this page.",
              done=bool(cl_acks.get("referral_link_copied_at")),
              completed_at=cl_acks.get("referral_link_copied_at")),
        _step("first_referral", "Land your first referral",
              "When a gym signs up under your code your dashboard updates and we email you.",
              done=referrals_count > 0),
        _step("service_area_set", "Set your service area",
              "Postcode + travel radius so we route the right jobs to you.",
              done=has_service_area),
    ]
    done_count = sum(1 for s in steps if s["done"])
    return {
        "steps": steps,
        "total": len(steps),
        "done": done_count,
        "complete": done_count == len(steps),
        "ackable_keys": sorted(ACKABLE_KEYS),
    }


def is_ackable(key: str) -> bool:
    return key in ACKABLE_KEYS


def ack_field_name(key: str) -> str:
    """Mongo path under `partner.checklist.<key>_at` — keeps each ack
    timestamped so future iterations can show "completed on …"."""
    return f"checklist.{key}_at"
