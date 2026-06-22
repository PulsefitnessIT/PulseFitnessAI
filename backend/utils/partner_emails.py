"""Iter 216h281 — Partner Engineer transactional emails.

Closes Gap 1 from the audit: applicants never heard back from the
system. This module owns the three lifecycle emails (received,
approved, rejected) plus the two compliance reminders (insurance /
qualification expiring soon, expired).

All emails go through ``utils.email.send_email`` so they pick up:
* Resend (real provider) with the env-defined sender domain
* the Pulse Fitness co-branded shell wrapper (header + footer)
* the email-rate-limiter (Resend's 5 req/s cap)
* the persisted email-event ledger for retries

No org branding is applied — partner engineers are *not* tied to one
tenant, so emails go out under the platform's master Pulse Fitness brand.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from utils.email import send_email as _send_email


async def send_email(*args, **kwargs):
    """Partner/engineer account comms default to the `support` sending domain.

    Iter 220y — every email in this module is recruitment / trial / account
    lifecycle, so route them all from support.pulsefitness.ai unless a caller
    overrides `category` explicitly.
    """
    kwargs.setdefault("category", "support")
    return await _send_email(*args, **kwargs)

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


# Iter 270 — localize the approval email to the engineer's market. Mirrors the
# apply-form `PARTNER_PRICING` (GBP unchanged; USD/EUR 39.99→19.99; CAD/AUD same
# figures in local symbol) and the per-market compliance doc set.
_PARTNER_PRICING = {
    "GB": {"base": "£30", "discount": "£15", "site": "£3"},
    "US": {"base": "$39.99", "discount": "$19.99", "site": "$3"},
    "IE": {"base": "€39.99", "discount": "€19.99", "site": "€3"},
    "CA": {"base": "C$39.99", "discount": "C$19.99", "site": "C$3"},
    "AU": {"base": "A$39.99", "discount": "A$19.99", "site": "A$3"},
}
_COMPLIANCE_DOCS = {
    "GB": "Insurance, DBS, Right-to-Work",
    "US": "Insurance, I-9 work authorization, background check",
    "IE": "Insurance, proof of right to work, Garda vetting",
    "CA": "Insurance, work eligibility, background check",
    "AU": "Insurance, work rights, police check",
}


def _partner_pricing(country_code: str | None) -> dict:
    return _PARTNER_PRICING.get((country_code or "GB").strip().upper(), _PARTNER_PRICING["GB"])


def _compliance_docs(country_code: str | None) -> str:
    return _COMPLIANCE_DOCS.get((country_code or "GB").strip().upper(), _COMPLIANCE_DOCS["GB"])


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
        f"You're receiving this because you applied to the Pulse Fitness Engineer Partner Network. "
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
        f"<p>Thanks for applying to the Pulse Fitness Engineer Partner Network. "
        f"We've received your application and the team is reviewing it now — "
        f"you'll hear back within <strong>2 working days</strong>.</p>"
        f"<p>While you wait:</p>"
        f"<ul>"
        f"<li>Make sure your public liability insurance is current (we'll ask).</li>"
        f"<li>Have any scanned certifications (PAT, IOSH, CSCS, 18th Edition) ready in case we need them.</li>"
        f"<li>Read the <a href=\"https://pulsefitness.ai/partners/engineers\">commission &amp; pricing detail</a> "
        f"so you're ready to start once approved.</li>"
        f"</ul>"
        f'<p style="margin-top:18px;color:#475569;font-size:12px;">Application ref: <span style="font-family:monospace;">{application_id}</span></p>'
    )
    return await send_email(
        to=email,
        subject="Pulse Fitness Engineer Partner — application received",
        html=_wrap("We've got your application.", body),
    )


# ── 2. Application approved ────────────────────────────────────────


async def send_application_approved(
    email: str,
    full_name: str,
    referral_code: str | None,
    activation_token: str | None = None,
    country_code: str | None = None,
) -> bool:
    """Iter 219f / 270 — single welcome email that funnels the engineer
    straight to a "Set up your sign-in" page (1-minute password
    form) which then auto-redirects to Stripe Checkout for the
    Partner Plan. Pricing + compliance docs are localized to the
    engineer's market (``country_code``).

    Stripe Connect Express (for *receiving* customer invoice
    payouts) is step 3 in the body — it's wired into the activation
    checklist on the dashboard so progression is visible there too.
    """
    first = (full_name or "").split(" ")[0] or "there"
    price = _partner_pricing(country_code)
    docs = _compliance_docs(country_code)
    ref_block = ""
    if referral_code:
        ref_block = (
            f'<p style="background:#F1F5F9;border-left:3px solid #0055FF;padding:14px 16px;border-radius:6px;margin-top:16px;">'
            f'<strong>Your referral code:</strong> '
            f'<span style="font-family:monospace;font-size:16px;font-weight:700;letter-spacing:0.03em;">{referral_code}</span><br/>'
            f'<span style="font-size:12px;color:#475569;">Share this with any gym owner — every gym that signs up under your code earns you a one-off reward + {price["site"]}/site/mo recurring (released after 3 months on the platform).</span>'
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
            f"Stripe to start your {price['base']}/mo Partner Plan.</p>"
        )
    else:
        cta_url = _partner_subscribe_url()
        cta_label = f"Start Partner Plan with Stripe ({price['base']}/mo)"
        sign_in_line = (
            f"<p><strong>Next step — set up your {price['base']}/month Partner Plan with Stripe.</strong> "
            "Click below to go to Stripe Checkout (you'll be asked to sign in or register "
            "with this email first).</p>"
        )

    body = (
        f"<p>Hi {first},</p>"
        f"<p>You're in. Welcome to the Pulse Fitness Engineer Partner Network.</p>"
        f"{sign_in_line}"
        f"<p style=\"font-size:13px;color:#475569;margin-top:18px;\">After that, we'll guide you through:</p>"
        f"<ol style=\"font-size:13px;color:#1f2937;\">"
        f"<li><strong>Pay your {price['base']}/mo Partner Plan</strong> (drops automatically as you refer gyms — free at 10).</li>"
        f"<li><strong>Connect Stripe Express</strong> so customers can pay your invoices by card — typically 3 minutes.</li>"
        f"<li><strong>Upload your compliance documents</strong> ({docs}).</li>"
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
        else f"You're approved — start your {price['base']}/mo Partner Plan with Stripe"
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
        f"<p>Thanks for applying to the Pulse Fitness Engineer Partner Network. After review, we're not able to approve your application at this time.</p>"
        f"{reason_html}"
        f"<p>This isn't always permanent — if your circumstances change (additional certifications, insurance in place, more gym-side experience), you're welcome to re-apply. We keep no permanent block.</p>"
    )
    return await send_email(
        to=email,
        subject="Pulse Fitness Engineer Partner — application update",
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
        name = alt.get("full_name") or "Pulse Fitness Engineer"
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


# ── 7. Welcome-back digest (iter 220r) ─────────────────────────────


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _welcome_back_subject(open_cases: int) -> str:
    """Iter 220r — subject line varies with workload so the digest
    doesn't look like a generic mass-send. An engineer with a queue
    of waiting jobs needs a louder cue than a quiet inbox."""
    if open_cases <= 0:
        return "Welcome back — your Pulse Fitness queue is clear"
    return f"Welcome back — {_plural(open_cases, 'job')} waiting"


def _while_away_block(activity: list[dict] | None) -> str:
    """Iter 220r-2 — "While you were away" recap with per-gym
    one-click thanks CTAs. Each activity row carries:
      {gym_name, opened_during_leave, resolved_during_leave,
       thanks_url}
    Rows with both counts at 0 are filtered upstream so we never
    render a quiet gym here.
    """
    if not activity:
        return ""
    rows: list[str] = []
    for row in activity[:6]:  # cap to keep the email short
        name = row.get("gym_name") or "A referred gym"
        opened = int(row.get("opened_during_leave", 0) or 0)
        resolved = int(row.get("resolved_during_leave", 0) or 0)
        bits = []
        if opened:
            bits.append(f"{_plural(opened, 'new fault')}")
        if resolved:
            bits.append(f"{_plural(resolved, 'fault')} resolved")
        line = " · ".join(bits) if bits else "kept things ticking over"
        thanks_url = row.get("thanks_url") or ""
        thanks_btn = (
            f'<a href="{thanks_url}" style="color:#2563EB;font-weight:700;'
            f'text-decoration:none;font-size:12px;">Send thanks →</a>'
            if thanks_url else ""
        )
        rows.append(
            f'<li style="margin:8px 0;">'
            f'<strong>{name}</strong> — '
            f'<span style="color:#475569;">{line}</span>'
            f'{f"<br/>{thanks_btn}" if thanks_btn else ""}'
            f"</li>"
        )
    return (
        f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
        f'border-radius:8px;padding:14px 16px;margin-top:16px;">'
        f'<p style="margin:0 0 8px;font-size:13px;font-weight:700;'
        f'letter-spacing:0.02em;text-transform:uppercase;color:#0F172A;">'
        f"While you were away"
        f"</p>"
        f'<ul style="margin:0;padding-left:18px;font-size:13px;color:#0F172A;">'
        f'{"".join(rows)}'
        f"</ul>"
        f'<p style="margin:10px 0 0;font-size:11px;color:#94a3b8;">'
        f"One-click thanks goes to the gym's primary contact. "
        f"We keep your name on it — no surprises."
        f"</p>"
        f"</div>"
    )


async def send_welcome_back_digest(
    *,
    email: str,
    full_name: str,
    leave_note: str | None,
    days_away: int | None,
    my_gyms_open_count: int,
    my_gyms_overdue_count: int,
    compliance_warnings: list[str] | None,
    recent_activity: list[dict] | None = None,
    dashboard_url: str | None = None,
) -> bool:
    """Iter 220r — fired once when an engineer's `resumes_on` date
    arrives. Sends a single welcome-back digest with:

    * a friendly hello (no marketing fluff)
    * how many open fault cases are waiting in their referred-gym
      queue (sourced from `db.supplier_cases`, iter 220p semantics)
    * how many of those are already overdue
    * any compliance items that expired / expire soon
    * iter 220r-2: a "While you were away" recap of each referred
      gym's activity during the leave window, with one-click
      "Send thanks" CTAs per gym
    * a single CTA → partner-engineer dashboard

    All inputs are pre-validated by the caller. Failures are caught
    upstream so this never blocks the sweep.
    """
    if not email:
        return False
    first = (full_name or "").strip().split(" ")[0] or "there"
    away_phrase = (
        f"You've been away for <strong>{days_away} days</strong> — "
        if days_away and days_away >= 1
        else "You're back — "
    )
    if my_gyms_open_count <= 0:
        workload_block = (
            f"<p>{away_phrase}your Pulse Fitness queue is clear right now. "
            f"Nothing urgent waiting from your referred gyms — a clean slate.</p>"
        )
    else:
        overdue_phrase = (
            f' (<span style="color:#B91C1C;font-weight:700;">'
            f"{_plural(my_gyms_overdue_count, 'overdue')}</span>)"
            if my_gyms_overdue_count > 0 else ""
        )
        workload_block = (
            f"<p>{away_phrase}while you were out, "
            f"<strong>{_plural(my_gyms_open_count, 'job')}</strong> "
            f"queued up from your referred gyms{overdue_phrase}.</p>"
        )

    compliance_block = ""
    if compliance_warnings:
        items = "".join(
            f'<li style="margin:4px 0;">{line}</li>' for line in compliance_warnings
        )
        compliance_block = (
            f'<p style="background:#FEF3C7;border-left:3px solid #F59E0B;'
            f'padding:12px 14px;border-radius:6px;font-size:13px;color:#78350F;'
            f'margin-top:14px;">'
            f"<strong>Compliance to handle this week:</strong>"
            f'<ul style="margin:6px 0 0;padding-left:18px;">{items}</ul>'
            f"</p>"
        )

    note_block = ""
    if leave_note:
        # Echo the note back so the engineer knows we kept track —
        # tiny detail, real "we noticed" energy.
        note_block = (
            f'<p style="font-size:13px;color:#475569;margin-top:14px;">'
            f'You left a note before going off: <em>"{leave_note}"</em>.</p>'
        )

    activity_block = _while_away_block(recent_activity)

    body = (
        f"<p>Hi {first},</p>"
        f"{workload_block}"
        f"{compliance_block}"
        f"{activity_block}"
        f"{note_block}"
        f'<p style="margin-top:18px;font-size:13px;color:#475569;">'
        f"You're now marked <strong>available</strong> on Pulse Fitness again — "
        f"new contact requests will route to you straight away."
        f"</p>"
    )
    return await send_email(
        to=email,
        subject=_welcome_back_subject(my_gyms_open_count),
        html=_wrap(
            f"Welcome back, {first}.",
            body,
            cta_label="Open your dashboard",
            cta_url=dashboard_url or _partner_dashboard_url(),
        ),
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
        f"{company_suffix} on the Pulse Fitness Engineer Network. {engineer_first_name} {back_phrase} "
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



# ── Engineer 10-day trial lifecycle ───────────────────────────────────


def _trial_feedback_url(token: str) -> str:
    base = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    return f"{base}/partner-engineer/trial-feedback/{token}"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "soon"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%-d %B %Y")
    except Exception:
        return "soon"


async def send_trial_started(email: str, full_name: str, ends_at: str, trial_days: int = 10) -> bool:
    """Sent when an admin (or the campaign auto-enrol) starts the free trial."""
    first = (full_name or "").split(" ")[0] or "there"
    body = (
        f"<p>Hi {first},</p>"
        f"<p>Your <strong>{trial_days}-day free trial</strong> of the Pulse Fitness Engineer App is live. "
        f"You've got full access to take jobs, batch faults, capture photos, fire off branded "
        f"service reports and track your van stock — no card needed.</p>"
        f'<p style="background:#F1F5F9;border-left:3px solid #0055FF;padding:14px 16px;border-radius:6px;">'
        f"Your trial runs until <strong>{_fmt_date(ends_at)}</strong>. We'll email you a short feedback "
        f"form when it ends — if you love it, you can continue on the plan in a couple of taps.</p>"
        f"<p>Get stuck in — the more you put through it, the more useful your feedback will be.</p>"
    )
    return await send_email(
        to=email,
        subject=f"Your {trial_days}-day Pulse Fitness Engineer App trial has started",
        html=_wrap("Your free trial is live.", body, "Open the Engineer App", _partner_dashboard_url()),
    )


async def send_trial_ending_tomorrow(email: str, full_name: str, ends_at: str) -> bool:
    """Day-9 nudge — trial ends tomorrow."""
    first = (full_name or "").split(" ")[0] or "there"
    body = (
        f"<p>Hi {first},</p>"
        f"<p>Quick heads-up — your free trial of the Pulse Fitness Engineer App ends "
        f"<strong>tomorrow ({_fmt_date(ends_at)})</strong>.</p>"
        f"<p>Squeeze in any last jobs you want to test, and keep an eye on your inbox: "
        f"we'll send a 2-minute feedback form right after, with the option to continue on the plan.</p>"
    )
    return await send_email(
        to=email,
        subject="Your Pulse Fitness Engineer App trial ends tomorrow",
        html=_wrap("One day left on your trial.", body, "Open the Engineer App", _partner_dashboard_url()),
    )


async def send_trial_feedback_request(email: str, full_name: str, token: str, trial_days: int = 10) -> bool:
    """Day-10 — trial ended, ask for feedback + continue decision."""
    first = (full_name or "").split(" ")[0] or "there"
    url = _trial_feedback_url(token)
    body = (
        f"<p>Hi {first},</p>"
        f"<p>That's a wrap on your {trial_days}-day Pulse Fitness Engineer App trial — thank you for "
        f"putting it through its paces.</p>"
        f"<p>Could you spare <strong>2 minutes</strong> to tell us how it went? At the end you can "
        f"choose to continue on the plan (£30/mo, automatically dropping to free once you refer "
        f"10 active sites) or step away — no pressure either way.</p>"
        f'<p style="background:#FFF7ED;border-left:3px solid #F59E0B;padding:14px 16px;border-radius:6px;">'
        f"Your access stays on for a few more days while you decide. Tell us your verdict below.</p>"
    )
    return await send_email(
        to=email,
        subject="How was your Pulse Fitness trial? (2 mins) — continue or step away",
        html=_wrap("Tell us how the trial went.", body, "Give feedback & decide", url),
    )


async def send_trial_lastchance(email: str, full_name: str, token: str) -> bool:
    """Final nudge ~2 days after the feedback form if no response yet."""
    first = (full_name or "").split(" ")[0] or "there"
    url = _trial_feedback_url(token)
    body = (
        f"<p>Hi {first},</p>"
        f"<p>Last chance — your Pulse Fitness Engineer App trial access is about to switch off. "
        f"If you'd like to keep going, just complete the quick feedback form and continue on the "
        f"plan. If we don't hear back, your access will pause and any in-flight jobs will be "
        f"returned to the dispatch team.</p>"
    )
    return await send_email(
        to=email,
        subject="Last chance to keep your Pulse Fitness Engineer App access",
        html=_wrap("Your trial access is about to pause.", body, "Continue on the plan", url),
    )
