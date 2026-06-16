import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException

from utils.database import RESEND_API_KEY, SENDER_EMAIL, db

logger = logging.getLogger(__name__)

# Iter 216h64 — co-branded email wrapper. Every outbound email is wrapped
# in a header showing Pulse Fitness (the platform) + the operator's logo, plus
# a matching footer. Pulse Pro tenants get the Pulse Fitness mark in the
# co-brand slot. Logos resolve to absolute URLs against the platform's
# public domain so the <img> tags survive Gmail/Outlook caching.

PUBLIC_BASE_URL = (
    os.environ.get("EMAIL_PUBLIC_BASE_URL")
    or os.environ.get("FRONTEND_URL")
    or os.environ.get("REACT_APP_BACKEND_URL")
    or ""
).rstrip("/")

# Iter 220i — the previous external `customer-assets.emergentagent.com`
# mark started 403-ing in late 2026, breaking the logo on every
# customer-facing email (service reports, lifecycle, etc). Pull the
# mark from our own /brand/ path which is served by the frontend
# (mounted at the same origin as the API ingress). Fallback to the
# absolute public URL so dev / offline previews still resolve.
_DEFAULT_GYMAXIS_MARK = "/brand/gymaxis-mark-tight.png"


def _resolve_gymaxis_mark() -> str:
    explicit = os.environ.get("EMAIL_GYMAXIS_LOGO_URL", "").strip()
    if explicit:
        return explicit
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}{_DEFAULT_GYMAXIS_MARK}"
    return _DEFAULT_GYMAXIS_MARK


GYMAXIS_LOGO_MARK = _resolve_gymaxis_mark()
PULSE_FITNESS_LOGO = (
    "https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/"
    "iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg"
)


def _abs_url(maybe_relative: str | None) -> str:
    """Convert /api/account/logo/{id} or /api/public/files/{id} into a
    fully-qualified URL for the email image. data: URIs and absolute
    URLs pass through unchanged. Empty / None returns ""."""
    if not maybe_relative:
        return ""
    if maybe_relative.startswith("http://") or maybe_relative.startswith("https://"):
        return maybe_relative
    if maybe_relative.startswith("data:"):
        return maybe_relative
    if not PUBLIC_BASE_URL:
        return maybe_relative  # best-effort relative
    return f"{PUBLIC_BASE_URL}{maybe_relative}"


async def _resolve_co_brand(organization_id: str | None) -> dict:
    """Return logos + names for the co-brand header.

    Result keys: gym_logo, gym_name, partner_logo, partner_name.
    `partner_logo` defaults to the Pulse Fitness mark; Pulse Pro accounts use
    the Pulse Fitness lockup. Operator logos that aren't yet uploaded
    fall back to an initial-circle inside the header.
    """
    gym_logo = ""
    gym_name = "Pulse Fitness"
    partner_logo = GYMAXIS_LOGO_MARK
    partner_name = "Pulse Fitness AI"
    if not organization_id:
        return {"gym_logo": "", "gym_name": "", "partner_logo": partner_logo, "partner_name": partner_name}
    try:
        org = await db.organizations.find_one(
            {"id": organization_id},
            {"_id": 0, "name": 1, "logo_url": 1, "logo_path": 1, "account_type": 1},
        )
    except Exception:
        org = None
    if not org:
        return {"gym_logo": "", "gym_name": "", "partner_logo": partner_logo, "partner_name": partner_name}
    gym_name = (org.get("name") or "").strip() or gym_name
    gym_logo = _abs_url(org.get("logo_url") or "")
    # Pulse Pro tenants get the Pulse Fitness lockup as the platform mark.
    if (org.get("account_type") or "").lower() in ("pulse_pro", "lite"):
        partner_logo = PULSE_FITNESS_LOGO
        partner_name = "Pulse Fitness · powered by Pulse Fitness"
    return {
        "gym_logo": gym_logo, "gym_name": gym_name,
        "partner_logo": partner_logo, "partner_name": partner_name,
    }


def _header_html(brand: dict, accent: str = "#0055FF") -> str:
    """Render the dual-logo header. Operator logo on the LEFT, platform
    mark on the RIGHT. Empty operator logo falls back to a circle with
    the operator's name initial. The single visible separator keeps
    the header readable in both light + dark email clients."""
    gym_logo = brand.get("gym_logo") or ""
    gym_name = brand.get("gym_name") or ""
    partner_logo = brand.get("partner_logo") or GYMAXIS_LOGO_MARK
    partner_name = brand.get("partner_name") or "Pulse Fitness"
    if gym_logo:
        left_block = (
            f'<img src="{gym_logo}" alt="{gym_name}" style="max-height:42px;max-width:160px;'
            f'vertical-align:middle;border:0;" />'
        )
    elif gym_name:
        initial = gym_name[:1].upper() or "G"
        left_block = (
            f'<div style="display:inline-block;width:38px;height:38px;border-radius:8px;'
            f'background:{accent};color:#fff;line-height:38px;text-align:center;font-weight:800;'
            f'font-size:18px;font-family:Arial,sans-serif;vertical-align:middle;">{initial}</div>'
            f'<span style="margin-left:10px;color:#1a1a1a;font-weight:700;font-size:15px;'
            f'font-family:Arial,sans-serif;vertical-align:middle;">{gym_name}</span>'
        )
    else:
        left_block = ""
    right_block = (
        f'<img src="{partner_logo}" alt="{partner_name}" style="max-height:30px;max-width:140px;'
        f'vertical-align:middle;border:0;" />'
    )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;background:#ffffff;border-bottom:1px solid #e5e7eb;">'
        '  <tr>'
        f'    <td style="padding:18px 30px;text-align:left;vertical-align:middle;width:50%;">{left_block}</td>'
        f'    <td style="padding:18px 30px;text-align:right;vertical-align:middle;width:50%;">{right_block}</td>'
        '  </tr>'
        '</table>'
    )


def _footer_html(brand: dict) -> str:
    """Co-branded footer with both logos as small marks."""
    gym_name = brand.get("gym_name") or ""
    partner_name = brand.get("partner_name") or "Pulse Fitness AI"
    bits = []
    if gym_name:
        bits.append(f'<strong>{gym_name}</strong>')
    bits.append(partner_name)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;background:#f5f5f5;">'
        '  <tr><td style="padding:18px 30px;text-align:center;color:#888;font-size:11px;'
        'font-family:Arial,sans-serif;">'
        + ' · '.join(bits) +
        '<br/><span style="color:#aaa;font-size:10px;">'
        'You\'re receiving this because of your account with the operator above. '
        'Manage email preferences in your dashboard.</span>'
        '  </td></tr>'
        '</table>'
    )


def _looks_branded(html: str) -> bool:
    """Heuristic — body already contains a co-brand header (e.g. it was
    pre-wrapped by an upstream builder). Avoid double-wrapping."""
    if not html:
        return True
    needle = "gymaxis-email-cobrand-wrap"
    return needle in html


async def wrap_branded(html: str, organization_id: str | None = None) -> str:
    """Wrap raw HTML in the co-branded shell. Idempotent — wrapping an
    already-wrapped body is a no-op.

    Iter 216h64 — even without an organization_id we still wrap so
    platform-only emails (welcome, password reset, trial signup) get
    the Pulse Fitness mark in the header for consistency.
    """
    if _looks_branded(html):
        return html
    brand = await _resolve_co_brand(organization_id)
    # When there's no operator logo OR name, suppress the empty left
    # block so the header just shows the platform mark centred.
    if not brand.get("gym_logo") and not brand.get("gym_name"):
        brand["gym_name"] = ""
    header = _header_html(brand)
    footer = _footer_html(brand)
    return (
        '<div class="gymaxis-email-cobrand-wrap" '
        'style="background:#f9fafb;padding:24px 0;font-family:Arial,sans-serif;">'
        '<div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;'
        'overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);">'
        f'{header}'
        f'<div style="padding:0;">{html}</div>'
        f'{footer}'
        '</div></div>'
    )

try:
    import resend
    if RESEND_API_KEY:
        resend.api_key = RESEND_API_KEY
except ImportError:
    resend = None


# ── Per-category sending domains ──────────────────────────────────────
# The platform owns four verified Resend domains. Each outbound email is
# sent from the domain that matches its purpose (better deliverability +
# clear brand separation). Each is env-overridable; defaults use the
# verified www.pulsefitness.ai sending subdomains. `support`/default fall back
# to the configured root SENDER_EMAIL.
_CATEGORY_SENDER_ENV = {
    "billing": "SENDER_EMAIL_BILLING",
    "support": "SENDER_EMAIL_SUPPORT",
    "service": "SENDER_EMAIL_SERVICE",
}
_CATEGORY_SENDER_DEFAULT = {
    "billing": "Pulse Fitness Billing <billing@billing.www.pulsefitness.ai>",
    "support": "Pulse Fitness Support <support@support.www.pulsefitness.ai>",
    "service": "Pulse Fitness Service <service@service.www.pulsefitness.ai>",
}


def _bare_addr(sender: str) -> str:
    """Return the bare address from 'Name <addr@dom>' (or the string as-is)."""
    if sender and "<" in sender and ">" in sender:
        return sender[sender.index("<") + 1: sender.index(">")].strip()
    return (sender or "").strip()


def _category_sender(category: str | None) -> str:
    """Resolve the From address for a category, falling back to the root
    SENDER_EMAIL when the category is unknown / unset."""
    if category in _CATEGORY_SENDER_ENV:
        configured = (os.environ.get(_CATEGORY_SENDER_ENV[category]) or "").strip()
        sender = configured or _CATEGORY_SENDER_DEFAULT[category]
        # Lowercase the domain segment (Resend rejects mixed-case domains).
        bare = _bare_addr(sender)
        local, _, domain = bare.partition("@")
        if domain:
            fixed = f"{local}@{domain.lower()}"
            sender = sender.replace(bare, fixed)
        return sender
    return SENDER_EMAIL


# Per-category Reply-To. The operator org's own `email_sender_reply_to`
# always wins (so customer replies reach the gym); these are the canonical
# fallback inboxes for platform-originated mail. Env-overridable; defaults
# consolidate replies onto the root-domain mailboxes.
_CATEGORY_REPLY_ENV = {
    "billing": "REPLY_TO_BILLING",
    "support": "REPLY_TO_SUPPORT",
    "service": "REPLY_TO_SERVICE",
}
_CATEGORY_REPLY_DEFAULT = {
    "billing": "billing@pulsefitness.ai",
    "support": "support@pulsefitness.ai",
    "service": "service@pulsefitness.ai",
}


def _category_reply_to(category: str | None) -> str | None:
    """Canonical Reply-To for a category (env-overridable), else None."""
    if category in _CATEGORY_REPLY_ENV:
        return (os.environ.get(_CATEGORY_REPLY_ENV[category]) or "").strip() or _CATEGORY_REPLY_DEFAULT[category]
    return None


def _category_for_kind(kind: str | None) -> str | None:
    """Best-effort kind → category mapping for call sites that pass a
    ``kind`` but not an explicit ``category``."""
    if not kind:
        return None
    k = kind.lower()
    # Billing first so `engineer.invoice*` routes to billing, not service.
    if k.startswith((
        "billing", "invoice", "payment", "engineer.invoice",
        "partner.commission", "membership.invoice", "membership.payment",
        "autopay", "dunning", "receipt", "sales_pack",
    )):
        return "billing"
    if k.startswith(("service", "svc", "engineer.", "supplier.case", "job", "case.")):
        return "service"
    if k.startswith(("auth", "account", "support", "public", "system")):
        return "support"
    return None



async def _record_email_event(
    *,
    to: str,
    subject: str,
    status: str,
    error: str | None,
    payload: dict | None = None,
) -> str | None:
    """Best-effort write to the ``email_send_events`` audit collection.

    Powers the Master Admin "email health" pill and the Outbound emails
    panel. Capped to recent history via a TTL index created in
    :mod:`server` startup.

    Iter 216h222 — when ``status != "sent"`` and ``payload`` is supplied
    the full Resend params (from/to/subject/html/reply_to/attachments)
    + branding context are persisted on the row so a master admin can
    one-click retry the failed send from the Outbound emails panel.
    Successful rows never carry the payload (saves space + avoids
    leaking customer-bound HTML in the audit log longer than needed).

    Returns the event id so the caller can correlate retries.
    """
    import uuid
    event_id = str(uuid.uuid4())
    doc: dict = {
        "id": event_id,
        "to": to,
        "subject": subject,
        "sender": SENDER_EMAIL or "",
        "status": status,            # "sent" | "failed" | "no_api_key" | "bad_sender"
        "error": (error or "")[:500],
        "created_at": datetime.now(timezone.utc),
    }
    # Stash the full payload on failed sends so they're retryable.
    if status != "sent" and payload:
        doc["payload"] = payload
    try:
        await db.email_send_events.insert_one(doc)
    except Exception:
        # Telemetry failures must never block real email sends.
        return None
    return event_id


async def send_email(
    to: str,
    subject: str,
    html: str,
    attachments: list[dict] | None = None,
    *,
    cc: list[str] | str | None = None,
    organization_id: str | None = None,
    kind: str | None = None,
    category: str | None = None,
):
    """Send an email via Resend.

    Iter 216bc — when ``organization_id`` is provided, look up that
    org's ``email_sender_friendly_name`` / ``email_sender_reply_to``
    and use them. This keeps the actual From-address on the verified
    Pulse Fitness sender domain (so SPF/DKIM/DMARC keep passing) while
    showing the operator's brand to their customers and routing replies
    back to the operator.

    Iter 220av · F-22 — when the env flag
    ``ENFORCE_EMAIL_RECIPIENT_VALIDATION=true`` is set, every send is
    validated by ``utils.web_security.validate_email_recipient``.
    Transactional kinds (auth flows, system alerts) pass through
    unconditionally; ad-hoc / CRM sends must target an address that
    belongs to the same organisation, a CRM contact, or a partner /
    supplier contact for the org. Pass ``kind=`` to identify the
    transactional family (see ``web_security._TRANSACTIONAL_KINDS``).
    """
    # Iter 220av · F-22 — recipient validation gate (no-op when env flag off).
    try:
        from utils.web_security import validate_email_recipient
        await validate_email_recipient(
            to_email=to, kind=kind or "adhoc",
            organization_id=organization_id, db=db,
        )
    except HTTPException:
        # Re-raise so the caller learns the recipient was rejected.
        raise
    except Exception:
        logger.exception("validate_email_recipient failed (non-fatal)")
    if not RESEND_API_KEY:
        logger.warning(f"Email NOT sent (RESEND_API_KEY missing in env): to={to}, subject={subject!r}")
        await _record_email_event(to=to, subject=subject, status="no_api_key", error="RESEND_API_KEY missing")
        return False
    if not SENDER_EMAIL or "@" not in SENDER_EMAIL:
        logger.warning(f"Email NOT sent (SENDER_EMAIL invalid in env: {SENDER_EMAIL!r}): to={to}")
        await _record_email_event(to=to, subject=subject, status="bad_sender", error=f"SENDER_EMAIL={SENDER_EMAIL!r}")
        return False

    # Resolve per-org branding
    # Iter 220y — pick the sending domain by category (billing / service /
    # support), falling back to the configured root SENDER_EMAIL. An
    # explicit `category` wins; otherwise we infer it from `kind`.
    resolved_category = category or _category_for_kind(kind)
    base_sender = _category_sender(resolved_category)
    from_addr = base_sender
    reply_to: str | None = None
    if organization_id:
        try:
            org = await db.organizations.find_one(
                {"id": organization_id},
                {"_id": 0, "email_sender_friendly_name": 1, "email_sender_reply_to": 1, "name": 1},
            )
            if org:
                friendly = (org.get("email_sender_friendly_name") or org.get("name") or "").strip()
                reply_to = (org.get("email_sender_reply_to") or "").strip() or None
                if friendly:
                    # Keep the verified category address; swap the display name.
                    safe = friendly.replace('"', '').replace('<', '').replace('>', '')
                    from_addr = f"{safe} <{_bare_addr(base_sender)}>"
        except Exception:
            # Branding lookup failure must never block real email sends.
            pass

    # Operator's own reply-to wins; otherwise route replies to the canonical
    # per-category inbox so billing/support/service responses aren't lost.
    if not reply_to:
        reply_to = _category_reply_to(resolved_category)

    try:
        # Iter 216h64 — auto-wrap in the co-branded shell (operator
        # logo + Pulse Fitness/Pulse Fitness mark) when an organization_id is
        # supplied. Idempotent: already-wrapped HTML passes through.
        branded_html = await wrap_branded(html, organization_id)
        params = {
            "from": from_addr,
            "to": [to],
            "subject": subject,
            "html": branded_html,
        }
        if reply_to:
            params["reply_to"] = reply_to
        if cc:
            params["cc"] = cc if isinstance(cc, list) else [cc]
        if attachments:
            params["attachments"] = attachments
        # Iter 216h100 — gate the actual Resend HTTP call through the
        # process-wide rate limiter so signup-journey + lifecycle email
        # bursts can't overrun Resend's 5 req/s cap.
        from utils.email_rate_limiter import acquire as _rl_acquire
        await _rl_acquire()
        # Iter 232 — bound the provider call. A hung Resend API must never
        # block the calling API route (partner approve, quote send, …)
        # beyond this ceiling; timeouts fall into the retry-payload path
        # below like any other send failure.
        _send_timeout = float(os.environ.get("EMAIL_SEND_TIMEOUT_SECONDS", "10"))
        result = await asyncio.wait_for(
            asyncio.to_thread(resend.Emails.send, params), timeout=_send_timeout,
        )
        logger.info(f"Email sent to {to} (subject={subject!r}, resend_id={result.get('id') if isinstance(result, dict) else result})")
        await _record_email_event(to=to, subject=subject, status="sent", error=None)
        return True
    except Exception as e:
        logger.error(f"Email send FAILED via Resend: to={to}, subject={subject!r}, sender={from_addr!r}, error={e!r}")
        # Iter 216h222 — persist the full Resend payload so master
        # admins can one-click retry the send once the underlying
        # issue (e.g. domain not verified) is fixed.
        retry_payload = {
            "from": from_addr,
            "to": [to],
            "subject": subject,
            "html": branded_html,
            "reply_to": reply_to,
            "attachments": attachments or [],
            "organization_id": organization_id,
        }
        await _record_email_event(
            to=to, subject=subject, status="failed", error=repr(e),
            payload=retry_payload,
        )
        return False


async def send_welcome_email(email: str, name: str):
    html = f"""<div style="font-family: Arial; max-width: 600px; margin: 0 auto;">
    <div style="background: #0055FF; padding: 30px; text-align: center;">
        <h1 style="color: white; margin: 0;">Welcome to Pulse Fitness AI</h1>
    </div>
    <div style="padding: 30px; background: #f9f9f9;">
        <h2>Hi {name},</h2>
        <p>Welcome to Pulse Fitness AI - the complete gym maintenance platform.</p>
        <p>Here's what you can do:</p>
        <ul>
            <li><strong>AI Fault Diagnosis</strong> - Get instant repair guidance</li>
            <li><strong>Risk Assessments</strong> - Generate professional reports</li>
            <li><strong>Issue Tracking</strong> - Log and manage equipment faults</li>
            <li><strong>Maintenance Checklists</strong> - Keep your gym safe and compliant</li>
        </ul>
        <p>Get started by logging into your dashboard.</p>
        <a href="#" style="display: inline-block; background: #0055FF; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Go to Dashboard</a>
    </div>
    </div>"""
    await send_email(email, "Welcome to Pulse Fitness AI", html, category="support")


async def send_report_notification(email: str, name: str, report_type: str, report_id: str):
    html = f"""<div style="font-family: Arial; max-width: 600px; margin: 0 auto;">
    <div style="background: #0055FF; padding: 20px; text-align: center;">
        <h2 style="color: white; margin: 0;">Pulse Fitness AI - Report Ready</h2>
    </div>
    <div style="padding: 30px; background: #f9f9f9;">
        <p>Hi {name},</p>
        <p>Your <strong>{report_type}</strong> has been generated and is ready to view.</p>
        <p>Log into your dashboard to view, print, or download the report.</p>
    </div>
    </div>"""
    # Route through test recipient in test mode
    test_mode = 'resend.dev' in (os.environ.get('SENDER_EMAIL', '') or '')
    test_recipient = os.environ.get('TEST_RECIPIENT_EMAIL', '')
    recipient = (test_recipient or email) if test_mode else email
    await send_email(recipient, f"Pulse Fitness AI - {report_type} Ready", html, category="service")


async def send_password_reset_email(email: str, name: str, reset_url: str):
    html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff;">
    <div style="background: #0055FF; padding: 30px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 22px;">Pulse Fitness AI</h1>
    </div>
    <div style="padding: 40px 30px;">
        <h2 style="color: #1a1a1a; margin: 0 0 12px;">Password Reset Request</h2>
        <p style="color: #555; line-height: 1.6;">Hi {name},</p>
        <p style="color: #555; line-height: 1.6;">We received a request to reset your password. Click the button below to set a new password:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="display: inline-block; background: #0055FF; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 15px;">Reset Password</a>
        </div>
        <p style="color: #888; font-size: 13px; line-height: 1.6;">This link will expire in 1 hour. If you didn't request this, you can safely ignore this email.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
        <p style="color: #aaa; font-size: 12px;">If the button doesn't work, copy and paste this URL into your browser:<br/><a href="{reset_url}" style="color: #0055FF; word-break: break-all;">{reset_url}</a></p>
    </div>
    <div style="background: #f5f5f5; padding: 16px 30px; text-align: center;">
        <p style="color: #aaa; font-size: 11px; margin: 0;">Pulse Fitness AI · Gym Equipment Maintenance Platform</p>
    </div>
    </div>"""
    return await send_email(email, "Reset Your Password — Pulse Fitness AI", html, category="support")



async def send_onboarding_invite_email(email: str, recipient_name: str, customer_name: str,
                                        share_url: str, sender_name: str, deadline_days: int = 14) -> bool:
    """Send a branded onboarding invite to a prospective customer's primary contact."""
    greeting = f"Hi {recipient_name}," if recipient_name else "Hello,"
    html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff;">
    <div style="background: linear-gradient(135deg, #0055FF 0%, #0033AA 100%); padding: 36px 30px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px; letter-spacing: -0.5px;">Welcome to Pulse Fitness AI</h1>
        <p style="color: #cfe0ff; margin: 8px 0 0; font-size: 13px;">Your equipment management platform is ready</p>
    </div>
    <div style="padding: 40px 32px;">
        <h2 style="color: #1a1a1a; margin: 0 0 16px; font-size: 20px;">Let's get {customer_name or 'you'} set up</h2>
        <p style="color: #444; line-height: 1.7; margin: 0 0 16px;">{greeting}</p>
        <p style="color: #444; line-height: 1.7; margin: 0 0 20px;">
            {sender_name} has prepared a secure onboarding form so we can configure Pulse Fitness for your sites, staff,
            and equipment in one go. It takes around <strong>10–15 minutes</strong> and auto-saves as you go —
            you can complete it in multiple sessions.
        </p>
        <div style="background: #f0f7ff; border-left: 4px solid #0055FF; padding: 18px 20px; margin: 24px 0; border-radius: 4px;">
            <p style="margin: 0 0 6px; color: #0033AA; font-weight: 600; font-size: 13px;">What you'll need</p>
            <ul style="margin: 0; padding-left: 18px; color: #444; line-height: 1.7; font-size: 14px;">
                <li>Your legal entity name and billing address</li>
                <li>Details of each site you operate</li>
                <li>Staff members who need access (we'll email them to set passwords)</li>
                <li>Your equipment list — you can paste rows from Excel</li>
            </ul>
        </div>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{share_url}" style="display: inline-block; background: #0055FF; color: white; padding: 16px 36px;
               text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 15px; letter-spacing: 0.3px;">
               Open Onboarding Form →
            </a>
        </div>
        <p style="color: #888; font-size: 13px; line-height: 1.6; text-align: center;">
            This secure link expires in {deadline_days} days. Please complete it before then.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 28px 0;" />
        <p style="color: #aaa; font-size: 12px; line-height: 1.6;">
            If the button doesn't work, copy and paste this URL into your browser:<br/>
            <a href="{share_url}" style="color: #0055FF; word-break: break-all;">{share_url}</a>
        </p>
    </div>
    <div style="background: #f5f5f5; padding: 18px 30px; text-align: center;">
        <p style="color: #888; font-size: 12px; margin: 0;">Pulse Fitness AI · Gym Equipment Maintenance Platform</p>
        <p style="color: #aaa; font-size: 11px; margin: 4px 0 0;">Sent by {sender_name}</p>
    </div>
    </div>"""
    return await send_email(email, f"Onboarding invitation for {customer_name or 'your organisation'}", html, category="support")



async def send_trial_signup_notification(trial: dict):
    """Notify the platform owner(s) that a new trial user has signed up.

    Recipient(s) controlled by env var TRIAL_SIGNUP_NOTIFY_EMAIL
    (defaults to Lee@pulsefitness.ai). Comma-separated list supported.
    """
    recipients_raw = os.environ.get("TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@pulsefitness.ai")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        return False

    name = trial.get("full_name") or "New user"
    email = trial.get("email") or ""
    company = trial.get("company_name") or ""
    phone = trial.get("phone") or "—"
    days = trial.get("trial_duration_days") or 14
    org_id = trial.get("organization_id") or ""
    frontend = os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    admin_link = f"{frontend}/master-admin" if frontend else "/master-admin"

    html = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#05070A 0%,#0d1117 100%);padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.3);">
    <div style="color:#19CDFF;font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px;">New Trial Signup</div>
    <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{name} just started a {days}-day free trial</h1>
  </div>
  <div style="padding:28px 32px;background:#0A0B10;">
    <table style="width:100%;border-collapse:collapse;color:#e5e7eb;font-size:14px;">
      <tr><td style="padding:8px 0;color:#9ca3af;width:130px;">Full name</td><td style="padding:8px 0;font-weight:600;">{name}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Work email</td><td style="padding:8px 0;"><a href="mailto:{email}" style="color:#19CDFF;text-decoration:none;">{email}</a></td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Company / Gym</td><td style="padding:8px 0;font-weight:600;">{company}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Phone</td><td style="padding:8px 0;">{phone}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Trial length</td><td style="padding:8px 0;">{days} days</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Org ID</td><td style="padding:8px 0;font-family:monospace;font-size:12px;color:#9ca3af;">{org_id}</td></tr>
    </table>
    <div style="margin-top:24px;">
      <a href="{admin_link}" style="display:inline-block;background:#19CDFF;color:#05070A;padding:12px 24px;text-decoration:none;border-radius:999px;font-weight:700;font-size:13px;letter-spacing:0.05em;text-transform:uppercase;">Open Master Admin →</a>
    </div>
  </div>
  <div style="background:#05070A;padding:16px 32px;border-top:1px solid rgba(255,255,255,0.05);">
    <p style="color:#6b7280;font-size:11px;margin:0;">Sent by the Pulse Fitness trial funnel · landing-page signup</p>
  </div>
</div>"""

    subject = f"[Trial] {name} — {company or email}"
    ok = True
    for rcpt in recipients:
        if not await send_email(rcpt, subject, html):
            ok = False
    return ok
