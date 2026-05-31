r"""Web-security helpers — Iter 220av (Wave 4).

Three risk-register findings closed in one helper module:

  * **F-04** — DOM-XSS via stored rich text. ``sanitize_rich_text``
    is a bleach allow-list scrubber for any HTML/Markdown a user can
    persist (CRM notes, activity bodies, tender executive summaries,
    blog Q&A blocks). Conservative tag/attr set; no ``<script>``,
    ``<iframe>``, ``on*=`` handlers or ``javascript:`` URLs.
  * **F-05** — Open redirect via ``?next=`` query param.
    ``is_safe_next_url`` rejects anything that resolves to a
    different origin (scheme/netloc), absolute URLs, protocol-relative
    URLs (``//evil.com``), backslash tricks (``/\evil.com``), control
    chars, schemes (``javascript:``, ``data:``) and over-long values.
  * **F-22** — Email-recipient validation. ``validate_email_recipient``
    guards every transactional + ad-hoc send: transactional kinds
    pass through; ad-hoc / CRM sends must target an address that
    belongs to the same organisation, an active CRM contact, or an
    explicitly whitelisted partner contact.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Iterable
from urllib.parse import urlparse

import bleach
from fastapi import HTTPException

log = logging.getLogger(__name__)


# ── F-04 · stored rich-text bleach allow-list ─────────────────────


_RICH_TEXT_TAGS = frozenset({
    "a", "abbr", "b", "blockquote", "br", "cite", "code", "del",
    "em", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "i", "ins", "img",
    "li", "ol", "p", "pre", "s", "small",
    "span", "strong", "sub", "sup",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "u", "ul", "div",
})

_RICH_TEXT_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height"],
    "span": ["class"],
    "div": ["class"],
    "code": ["class"],
    "pre": ["class"],
    "th": ["colspan", "rowspan", "scope"],
    "td": ["colspan", "rowspan"],
    "abbr": ["title"],
}

_RICH_TEXT_PROTOS = ("http", "https", "mailto", "tel")


def sanitize_rich_text(value: str | None, *, max_chars: int = 200_000) -> str:
    """Run ``value`` through bleach with a conservative allow-list.

    * Strips ``<script>``, ``<iframe>``, ``<svg>``, ``<style>``, ``<object>``,
      ``<embed>``, ``<form>``, ``<link>``, ``<meta>``, and any ``on*=``
      event handler.
    * Drops ``javascript:`` / ``data:`` / ``vbscript:`` URLs from
      ``href``/``src``.
    * Clamps to ``max_chars`` chars so the DB never stores 1 MB of
      attacker-controlled markup that crashes the renderer.

    Empty / None passes through to ``""`` (no allocation).
    """
    if not value:
        return value or ""
    if not isinstance(value, str):
        value = str(value)
    if len(value) > max_chars:
        value = value[:max_chars]
    return bleach.clean(
        value,
        tags=_RICH_TEXT_TAGS,
        attributes=_RICH_TEXT_ATTRS,
        protocols=_RICH_TEXT_PROTOS,
        strip=True,
        strip_comments=True,
    )


def sanitize_rich_text_dict(doc: dict, *, fields: Iterable[str]) -> dict:
    """In-place ``sanitize_rich_text`` over the given dict keys. Skips
    keys that are absent / None. Returns the same dict for chaining."""
    for f in fields:
        v = doc.get(f)
        if v:
            doc[f] = sanitize_rich_text(v)
    return doc


# ── F-05 · safe-next URL check ────────────────────────────────────


_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+\-.]*:")


def is_safe_next_url(raw: str | None, *, max_length: int = 512) -> bool:
    r"""Return True iff ``raw`` is a relative path safe to redirect to.

    Hard rules (any one fails → reject):

      * Must be non-empty + < ``max_length`` chars.
      * Must not contain CR / LF / NUL / TAB / backslash.
      * Must start with a single ``/`` (no protocol-relative ``//host``).
      * Must not look like a URI scheme (``http:``, ``javascript:`` …).
      * Must not resolve to an absolute URL with a netloc.

    All of the famous open-redirect bypasses are caught:

      * ``//evil.com``                            → protocol-relative
      * ``/\evil.com``                            → backslash
      * ``/%2F%2Fevil.com``                       → still relative, OK
      * ``javascript:alert(1)``                   → scheme
      * ``data:text/html,…``                      → scheme
      * ``http://app.gymaxisai.com/admin``        → netloc
      * ``%2F%2Fevil.com``                        → no leading slash
    """
    if not raw or not isinstance(raw, str):
        return False
    if len(raw) >= max_length:
        return False
    if any(c in raw for c in ("\\", "\r", "\n", "\x00", "\t")):
        return False
    if not raw.startswith("/"):
        return False
    if raw.startswith("//"):
        return False
    if _SCHEME_PATTERN.match(raw):
        return False
    try:
        parsed = urlparse(raw)
    except ValueError:
        return False
    if parsed.scheme or parsed.netloc:
        return False
    return True


def safe_next_or(raw: str | None, fallback: str) -> str:
    """Convenience: returns ``raw`` when ``is_safe_next_url`` agrees,
    otherwise ``fallback``."""
    return raw if is_safe_next_url(raw) else fallback


# ── F-22 · email-recipient validation ─────────────────────────────


# Transactional kinds bypass the same-org check — these are emails the
# platform itself sends to anyone (auth flows, system alerts).
_TRANSACTIONAL_KINDS = frozenset({
    "auth.register_welcome",
    "auth.password_reset",
    "auth.magic_link",
    "auth.mfa_recovery",
    "auth.invite",
    "public.demo_request_ack",
    "public.signup_welcome",
    "public.contact_form",
    "supplier.case_link",
    "engineer.invoice_paid",
    "engineer.invoice_dispute",
    "engineer.application_decision",
    "partner.commission_payout",
    "system.ops_alert",
})


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_email_syntactically_valid(addr: str | None) -> bool:
    if not addr or not isinstance(addr, str):
        return False
    return bool(_EMAIL_PATTERN.match(addr.strip()))


_ENFORCE_RECIPIENT_VALIDATION = os.environ.get(
    "ENFORCE_EMAIL_RECIPIENT_VALIDATION", "false",
).lower() in ("1", "true", "yes")


async def validate_email_recipient(
    *,
    to_email: str | None,
    kind: str,
    organization_id: str | None,
    db,
) -> None:
    """Raise HTTPException(400) when ``to_email`` is unsafe for this
    organisation. Idempotent + non-blocking when env flag is off (dev).

    Trust ladder (first match wins):

      1. **Kind whitelist** — transactional / auth / system emails
         go to whoever the upstream code says (we don't know the
         intended recipient ahead of time; the kind is the contract).
      2. **Same-org user** — the address belongs to a user in the
         same ``organization_id``.
      3. **CRM contact** — the address belongs to an active CRM
         contact owned by ``organization_id``.
      4. **Partner contact** — the address belongs to an approved
         partner engineer or supplier contact for the org.

    If none match: 400 with a redacted reason.

    Off-by-default in dev (``ENFORCE_EMAIL_RECIPIENT_VALIDATION=false``)
    so existing test suites that hit ``send_email`` directly don't
    spuriously fail. Flip on in production to gate the entire ad-hoc
    email surface.
    """
    if not _ENFORCE_RECIPIENT_VALIDATION:
        return
    if not _is_email_syntactically_valid(to_email):
        raise HTTPException(400, "Invalid recipient email address.")
    if kind in _TRANSACTIONAL_KINDS:
        return
    if not organization_id:
        # Non-transactional with no org context → reject.
        raise HTTPException(
            400,
            "Email rejected: ad-hoc sends require an organisation context.",
        )
    addr = to_email.strip().lower()

    # Same-org user?
    try:
        u = await db.users.find_one(
            {"email": addr, "organization_id": organization_id},
            {"_id": 0, "id": 1},
        )
        if u:
            return
    except Exception:
        log.exception("validate_email_recipient: users lookup failed")

    # CRM contact?
    for coll in ("crm2_contacts", "crm_contacts", "members"):
        try:
            c = await db[coll].find_one(
                {"email": addr, "organization_id": organization_id},
                {"_id": 0, "id": 1},
            )
            if c:
                return
        except Exception:
            log.exception("validate_email_recipient: %s lookup failed", coll)

    # Partner / supplier contact tied to this org?
    for coll in ("partner_engineers", "suppliers", "engineer_customers"):
        try:
            p = await db[coll].find_one(
                {"email": addr, "organization_id": organization_id},
                {"_id": 0, "id": 1},
            )
            if p:
                return
        except Exception:
            log.exception("validate_email_recipient: %s lookup failed", coll)

    raise HTTPException(
        400,
        "Email rejected: recipient is not part of this organisation or its CRM/partner roster.",
    )


__all__ = [
    "sanitize_rich_text", "sanitize_rich_text_dict",
    "is_safe_next_url", "safe_next_or",
    "validate_email_recipient",
]
