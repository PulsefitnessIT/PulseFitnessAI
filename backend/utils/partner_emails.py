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


def _partner_subscribe_url() -> str:
    """Iter 219e — deep-link straight to the Partner Plan Stripe
    Checkout flow. The dashboard reads ``?action=subscribe`` and
    auto-fires the checkout once the engineer is authenticated."""
    base = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    return f"{base}/partner-engineer?action=subscribe"


def _partner_activation_url(token: str) -> str:
    """Iter 219f — single-use activation deep-link. The engineer
    lands on a "Set up your sign-in" page that creates their user
    account, links the partner row, then auto-redirects to Stripe
    Checkout for the £30/mo plan."""
    base = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    return f"{base}/partner-engineer/activate?token={token}"


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


async def send_application_approved(
    email: str,
    full_name: str,
    referral_code: str | None,
    activation_token: str | None = None,
) -> bool:
    """Iter 219f — single welcome email that funnels the engineer
    straight to a "Set up your sign-in" page (1-minute password
    form) which then auto-redirects to Stripe Checkout for the
    £30/mo Partner Plan. The page also creates the user account
    and links it to the partner row so the engineer is signed in
    by the time they land back on the dashboard.

    Stripe Connect Express (for *receiving* customer invoice
    payouts) is step 3 in the body — it's wired into the activation
    checklist on the dashboard so progression is visible there too.
    """
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
    # If we have a single-use activation token, the CTA is a 1-click
    # set-password link. Fallback to the dashboard URL keeps the email
    # useful even when token plumbing is offline (extreme defence in
    # depth — every production approval generates a token).
    if activation_token:
        cta_url = _partner_activation_url(activation_token)
        cta_label = "Set up your sign-in (1 min)"
        sign_in_line = (
            "<p><strong>Step 1 — set up your sign-in.</strong> Click the button below to "
            "choose your password. We'll create your account, then take you straight to "
            "Stripe to start your £30/mo Partner Plan.</p>"
        )
    else:
        cta_url = _partner_subscribe_url()
        cta_label = "Start Partner Plan with Stripe (£30/mo)"
        sign_in_line = (
            "<p><strong>Next step — set up your £30/month Partner Plan with Stripe.</strong> "
            "Click below to go to Stripe Checkout (you'll be asked to sign in or register "
            "with this email first).</p>"
        )

    body = (
        f"<p>Hi {first},</p>"
        f"<p>You're in. Welcome to the GymAxis Engineer Partner Network.</p>"
        f"{sign_in_line}"
        f"<p style=\"font-size:13px;color:#475569;margin-top:18px;\">After that, we'll guide you through:</p>"
        f"<ol style=\"font-size:13px;color:#1f2937;\">"
        f"<li><strong>Pay your £30/mo Partner Plan</strong> (drops automatically as you refer gyms — free at 10).</li>"
        f"<li><strong>Connect Stripe Express</strong> so customers can pay your invoices by card — typically 3 minutes.</li>"
        f"<li><strong>Upload your compliance documents</strong> (Insurance, DBS, Right-to-Work).</li>"
        f"<li><strong>Open the Engineer App</strong> — mobile-first PWA with offline support.</li>"
        f"</ol>"
        f"{ref_block}"
        f"<p style=\"font-size:11px;color:#94a3b8;margin-top:20px;\">"
        f"This activation link is valid for 14 days. If it expires, reply to this email "
        f"and we'll send a fresh one."
        f"</p>"
    )
    subject = (
        "You're approved — set up your sign-in (1 min)"
        if activation_token
        else "You're approved — start your £30/mo Partner Plan with Stripe"
    )
    return await send_email(
        to=email,
        subject=subject,
        html=_wrap(
            "You're approved.",
            body,
            cta_label=cta_label,
            cta_url=cta_url,
        ),
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



# ── 6. Engineer-on-leave autoreply (iter 216h290) ───────────────────


def _format_leave_date(iso: str | None) -> str | None:
    """Render a 'YYYY-MM-DD' as '5 March' for the email body."""
    if not iso:
        return None
    try:
        from datetime import date
        return date.fromisoformat(iso).strftime("%-d %B")
    except Exception:  # noqa: BLE001
        return iso


def _alternatives_block(alternatives: list[dict]) -> str:
    """Render a tiny list of alternative engineers, or empty string
    when there are none — keeps the email lean either way."""
    if not alternatives:
        return ""
    rows: list[str] = []
    for alt in alternatives[:3]:
        name = alt.get("full_name") or "GymAxis Engineer"
        company = alt.get("company_name")
        area = alt.get("service_postcode_area") or ""
        bits = [f"<strong>{name}</strong>"]
        if company:
            bits.append(company)
        if area:
            bits.append(area)
        rows.append(
            f'<li style="margin:4px 0;">{" · ".join(bits)}</li>'
        )
    return (
        '<p style="margin-top:18px;font-size:13px;color:#475569;">In the meantime,'
        " these in-area engineers are accepting work:</p>"
        f'<ul style="padding-left:18px;margin:6px 0;">{"".join(rows)}</ul>'
    )


async def send_engineer_unavailable_autoreply(
    *,
    to_email: str,
    requester_first_name: str | None,
    engineer_first_name: str,
    engineer_company: str | None,
    resumes_on: str | None,
    leave_note: str | None,
    alternatives: list[dict] | None = None,
) -> bool:
    """Iter 216h290 — Gap 10 follow-up: when a customer expresses
    interest in an engineer who's currently on leave, fire a polite
    autoreply so they're not left wondering. Includes a short list of
    in-area alternatives if we have any.

    All inputs are pre-validated by the caller. Failures are caught
    upstream so this never blocks the contact-request flow.
    """
    if not to_email:
        return False
    salutation = (requester_first_name or "").strip().split(" ")[0] or "there"
    company_suffix = f" of {engineer_company}" if engineer_company else ""
    back_phrase = (
        f"is back on <strong>{_format_leave_date(resumes_on)}</strong>"
        if resumes_on else "is currently on leave (no return date set)"
    )
    note_block = (
        f'<p style="background:#FEF3C7;border-left:3px solid #F59E0B;padding:12px 14px;'
        f'border-radius:6px;font-size:13px;color:#78350F;">'
        f"<strong>{engineer_first_name} says:</strong> {leave_note}</p>"
        if leave_note else ""
    )
    body = (
        f"<p>Hi {salutation},</p>"
        f"<p>Thanks for getting in touch about <strong>{engineer_first_name}</strong>"
        f"{company_suffix} on the GymAxis Engineer Network. {engineer_first_name} {back_phrase} "
        f"and will respond as soon as they're back.</p>"
        f"{note_block}"
        f"{_alternatives_block(alternatives or [])}"
        f'<p style="margin-top:20px;font-size:13px;color:#475569;">No further action is needed '
        f'— your enquiry is logged and will be picked up automatically.</p>'
    )
    subject = (
        f"{engineer_first_name} is on leave — we've logged your enquiry"
        if resumes_on
        else f"{engineer_first_name} is currently on leave"
    )
    return await send_email(
        to=to_email,
        subject=subject,
        html=_wrap(f"{engineer_first_name} is on leave", body),
    )
