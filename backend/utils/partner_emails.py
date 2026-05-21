"""Iter 216h281 — Partner Engineer transactional emails.

Closes Gap 1 from the audit: applicants never heard back from the
system. This module owns the three lifecycle emails (received,
approved, rejected) plus the two compliance reminders (insurance /
qualification expiring soon, expired).

All emails go through ``utils.email.send_email`` so they pick up:
* Resend (real provider) with the env-defined sender domain
* the GymAxis co-branded shell wrapper (header + footer)
* the email-rate-limiter (Resend's 5 req/s cap)
* the persisted email-event ledger for retries

No org branding is applied — partner engineers are *not* tied to one
tenant, so emails go out under the platform's master GymAxis brand.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from utils.email import send_email

logger = logging.getLogger(__name__)


def _partner_dashboard_url() -> str:
    base = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    return f"{base}/partner-engineer"


def _apply_again_url() -> str:
    base = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    return f"{base}/partners/engineers/apply"


# ── Shared layout ───────────────────────────────────────────────────


def _wrap(headline: str, body_html: str, cta_label: str | None = None, cta_url: str | None = None) -> str:
    """Lightweight inner body — the platform-wide co-branded header/
    footer is added automatically by ``wrap_branded`` inside ``send_email``."""
    cta = ""
    if cta_label and cta_url:
        cta = (
            f'<p style="margin:28px 0 8px;">'
            f'<a href="{cta_url}" style="background:#0055FF;color:#fff;text-decoration:none;'
            f'display:inline-block;padding:12px 22px;border-radius:999px;'
            f'font-weight:700;font-family:Arial,sans-serif;font-size:14px;">{cta_label}</a>'
            f"</p>"
        )
    return (
        f'<div style="font-family:Arial,sans-serif;color:#0F172A;line-height:1.55;max-width:560px;margin:0 auto;">'
        f'<h2 style="margin:0 0 12px;font-size:22px;font-weight:800;letter-spacing:-0.01em;">{headline}</h2>'
        f"{body_html}"
        f"{cta}"
        f'<p style="margin-top:28px;color:#475569;font-size:12px;">'
        f"You're receiving this because you applied to the GymAxis Engineer Partner Network. "
        f'If this wasn\'t you, reply and we\'ll remove your record.'
        f"</p>"
        f"</div>"
    )


# ── 1. Application received ────────────────────────────────────────


async def send_application_received(email: str, full_name: str, application_id: str) -> bool:
    """Sent immediately after the public-apply form submits."""
    first = (full_name or "").split(" ")[0] or "there"
    body = (
        f"<p>Hi {first},</p>"
        f"<p>Thanks for applying to the GymAxis Engineer Partner Network. "
        f"We've received your application and the team is reviewing it now — "
        f"you'll hear back within <strong>2 working days</strong>.</p>"
        f"<p>While you wait:</p>"
        f"<ul>"
        f"<li>Make sure your public liability insurance is current (we'll ask).</li>"
        f"<li>Have any scanned certifications (PAT, IOSH, CSCS, 18th Edition) ready in case we need them.</li>"
        f"<li>Read the <a href=\"https://www.gymaxisai.com/partners/engineers\">commission &amp; pricing detail</a> "
        f"so you're ready to start once approved.</li>"
        f"</ul>"
        f'<p style="margin-top:18px;color:#475569;font-size:12px;">Application ref: <span style="font-family:monospace;">{application_id}</span></p>'
    )
    return await send_email(
        to=email,
        subject="GymAxis Engineer Partner — application received",
        html=_wrap("We've got your application.", body),
    )


# ── 2. Application approved ────────────────────────────────────────


async def send_application_approved(email: str, full_name: str, referral_code: str | None) -> bool:
    first = (full_name or "").split(" ")[0] or "there"
    ref_block = ""
    if referral_code:
        ref_block = (
            f'<p style="background:#F1F5F9;border-left:3px solid #0055FF;padding:14px 16px;border-radius:6px;margin-top:16px;">'
            f'<strong>Your referral code:</strong> '
            f'<span style="font-family:monospace;font-size:16px;font-weight:700;letter-spacing:0.03em;">{referral_code}</span><br/>'
            f'<span style="font-size:12px;color:#475569;">Share this with any gym owner — every gym that signs up under your code earns you a one-off reward + £3/site/mo recurring (released after 3 months on the platform).</span>'
            f"</p>"
        )
    body = (
        f"<p>Hi {first},</p>"
        f"<p>You're in. Welcome to the GymAxis Engineer Partner Network.</p>"
        f"<p>Here's what to do next:</p>"
        f"<ol>"
        f"<li><strong>Open your dashboard</strong> — copy your referral link and start sharing.</li>"
        f"<li><strong>Start your Partner Plan subscription</strong> (£30/mo, drops automatically as you refer gyms — free at 10).</li>"
        f"<li><strong>Download the Engineer App</strong> from the same dashboard — mobile-first PWA with offline support.</li>"
        f"</ol>"
        f"{ref_block}"
    )
    return await send_email(
        to=email,
        subject="You're approved — welcome to the GymAxis Engineer Network",
        html=_wrap("You're approved.", body, cta_label="Open your dashboard", cta_url=_partner_dashboard_url()),
    )


# ── 3. Application rejected ────────────────────────────────────────


async def send_application_rejected(email: str, full_name: str, reason: str | None) -> bool:
    first = (full_name or "").split(" ")[0] or "there"
    reason_html = ""
    if reason:
        reason_html = (
            f'<p style="background:#FEF2F2;border-left:3px solid #DC2626;padding:14px 16px;border-radius:6px;margin-top:16px;">'
            f'<strong>Reason given:</strong><br/><em>"{reason}"</em>'
            f"</p>"
        )
    body = (
        f"<p>Hi {first},</p>"
        f"<p>Thanks for applying to the GymAxis Engineer Partner Network. After review, we're not able to approve your application at this time.</p>"
        f"{reason_html}"
        f"<p>This isn't always permanent — if your circumstances change (additional certifications, insurance in place, more gym-side experience), you're welcome to re-apply. We keep no permanent block.</p>"
    )
    return await send_email(
        to=email,
        subject="GymAxis Engineer Partner — application update",
        html=_wrap("An update on your application.", body, cta_label="Update & re-apply", cta_url=_apply_again_url()),
    )


# ── 4. Compliance reminders (insurance / qualifications expiry) ───


async def send_compliance_reminder(
    email: str,
    full_name: str,
    kind: str,            # "insurance" | "qualifications"
    expires_at: datetime,
    days_remaining: int,
) -> bool:
    """One reminder template used by the nightly job for T-30 / T-7 / T-0."""
    first = (full_name or "").split(" ")[0] or "there"
    label = "public liability insurance" if kind == "insurance" else "engineering qualifications / certifications"
    deadline = expires_at.astimezone(timezone.utc).strftime("%d %b %Y")
    if days_remaining > 0:
        headline = f"Your {kind} expires in {days_remaining} days."
        urgency = (
            f"<p>Your {label} on file expires on <strong>{deadline}</strong> "
            f"({days_remaining} day{'s' if days_remaining != 1 else ''} from now).</p>"
            f"<p>Update us before then to keep your Partner status active — once your cover lapses we have to pause "
            f"new jobs being routed to you (gym operators audit this).</p>"
        )
    else:
        headline = f"Your {kind} has expired."
        urgency = (
            f"<p>Your {label} on file expired on <strong>{deadline}</strong>.</p>"
            f"<p>Your Partner status is now <strong>paused</strong> for new jobs. Update your details to resume.</p>"
        )
    body = f"<p>Hi {first},</p>{urgency}"
    return await send_email(
        to=email,
        subject=f"Action needed — your {kind} {'has expired' if days_remaining <= 0 else f'expires in {days_remaining} days'}",
        html=_wrap(headline, body, cta_label="Update your profile", cta_url=_partner_dashboard_url()),
    )
