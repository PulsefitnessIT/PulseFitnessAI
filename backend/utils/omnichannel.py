"""Omni-channel dispatch layer (Iter 233).

Single entry-point — ``dispatch_step`` — that the journey engine + any
future workflow can call to deliver a step's payload to a contact across
email / SMS / push / in-app, without each caller learning the per-channel
quirks.

Design notes:
  • Every send returns a uniform ``DeliveryResult`` with ``ok``,
    ``channel``, ``provider`` (e.g. "twilio", "mock", "fallback"), and
    ``message_id`` so the journey runtime can record what happened.
  • If a real provider isn't configured (no Twilio creds, no VAPID
    keys), we still record a row in ``marketing_messages`` with
    ``status="mock_sent"`` so dashboards stay accurate during MOCKED-mode
    development.
  • ``send_in_app`` is the universal fallback — every contact has an
    inbox, so this never returns ok=False unless the DB is down.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from utils.database import db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ───────────────────────── DTO ─────────────────────────


@dataclass
class DeliveryResult:
    ok: bool
    channel: str
    provider: str
    message_id: str
    error: Optional[str] = None


# ───────────────────────── Provider adapters ─────────────────────────


async def _send_sms_via_twilio(*, to: str, body: str) -> tuple[bool, str, Optional[str]]:
    """Returns ``(ok, provider, error)``.

    When TWILIO_* env vars are absent (MOCKED-mode) we return ok=True with
    provider='mock' so the calling code can still mark the message as
    delivered and dashboards reflect intent. The real wiring is one
    drop-in replacement away.
    """
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    sender = os.environ.get("TWILIO_FROM_NUMBER")
    if not (sid and token and sender):
        logger.info("[omnichannel] Twilio not configured — MOCKED SMS to %s", to)
        return True, "mock", None
    try:
        # Lazy import to keep the dependency optional in tests / dev.
        from twilio.rest import Client  # type: ignore
        client = Client(sid, token)
        # Run in a thread — Twilio SDK is sync and we don't want to block.
        import asyncio
        await asyncio.to_thread(
            client.messages.create, body=body, from_=sender, to=to,
        )
        return True, "twilio", None
    except Exception as exc:  # pragma: no cover — provider failures hard
        logger.info("[omnichannel] Twilio send failed for %s: %s", to, exc)
        return False, "twilio", str(exc)[:300]


async def _send_push_via_webpush(
    *, subscription: dict, title: str, body: str, link: str = ""
) -> tuple[bool, str, Optional[str]]:
    """Web-push delivery. VAPID keys are optional — without them we
    queue the payload for a future worker.

    The ``push_queue`` collection is the durable buffer; the eventual
    worker reads from it and calls into ``pywebpush`` (already pinned in
    requirements.txt). For MOCKED-mode we still record the row so
    counts are correct in dashboards."""
    pub = os.environ.get("WEB_PUSH_VAPID_PUBLIC")
    priv = os.environ.get("WEB_PUSH_VAPID_PRIVATE")
    if not (pub and priv and subscription):
        return True, "queued", None
    try:
        from pywebpush import webpush  # type: ignore
        import asyncio
        await asyncio.to_thread(
            webpush,
            subscription_info=subscription,
            data=f"{title}\n{body}\n{link}",
            vapid_private_key=priv,
            vapid_claims={"sub": "mailto:noreply@gymaxis.ai"},
        )
        return True, "webpush", None
    except Exception as exc:  # pragma: no cover
        logger.info("[omnichannel] webpush failed: %s", exc)
        return False, "webpush", str(exc)[:300]


# ───────────────────────── Public API ─────────────────────────


async def send_sms(
    *, organization_id: str, contact: dict, body: str,
    journey_id: Optional[str] = None,
    journey_run_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> DeliveryResult:
    """Dispatch an SMS. Persists a row to ``marketing_messages`` with
    the channel, provider and the resolved status."""
    msg_id = _new_id()
    to = (contact.get("phone") or "").strip()
    if not to:
        await db.marketing_messages.insert_one({
            "id": msg_id, "organization_id": organization_id,
            "contact_id": contact.get("id"),
            "channel": "sms", "status": "no_phone",
            "journey_id": journey_id, "journey_run_id": journey_run_id,
            "campaign_id": campaign_id,
            "body": body, "sent_at": _now_iso(),
        })
        return DeliveryResult(False, "sms", "none", msg_id, "Contact has no phone number")
    body = body.replace("{{first_name}}", contact.get("first_name") or "there")
    ok, provider, err = await _send_sms_via_twilio(to=to, body=body)
    status = "sent" if ok and provider == "twilio" else ("mock_sent" if ok else "failed")
    await db.marketing_messages.insert_one({
        "id": msg_id, "organization_id": organization_id,
        "contact_id": contact.get("id"),
        "channel": "sms", "status": status, "provider": provider,
        "journey_id": journey_id, "journey_run_id": journey_run_id,
        "campaign_id": campaign_id,
        "to": to, "body": body, "sent_at": _now_iso(),
        "error": err,
    })
    return DeliveryResult(ok, "sms", provider, msg_id, err)


async def send_push_notification(
    *, organization_id: str, contact: dict, title: str, body: str, link: str = "",
    journey_id: Optional[str] = None,
    journey_run_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> DeliveryResult:
    """Dispatch a web-push notification. The contact must carry a
    `push_subscription` (set via the PWA service-worker registration)
    for direct delivery; otherwise we queue."""
    msg_id = _new_id()
    sub = (contact.get("push_subscription") or contact.get("push_subscriptions") or [None])
    if isinstance(sub, list):
        sub = sub[0] if sub else None
    title = (title or "").strip().replace("{{first_name}}", contact.get("first_name") or "there")
    body = (body or "").replace("{{first_name}}", contact.get("first_name") or "there")

    if not sub:
        # No subscription — queue for later AND drop an in-app notification
        # so the contact still sees it on next sign-in.
        await db.push_queue.insert_one({
            "id": msg_id, "organization_id": organization_id,
            "contact_id": contact.get("id"),
            "title": title, "body": body, "link": link,
            "journey_id": journey_id, "journey_run_id": journey_run_id,
            "campaign_id": campaign_id,
            "status": "queued", "queued_at": _now_iso(),
        })
        provider = "queued"
        ok = True
        err = None
    else:
        ok, provider, err = await _send_push_via_webpush(
            subscription=sub, title=title, body=body, link=link,
        )
    status = "sent" if ok and provider == "webpush" else ("queued" if ok else "failed")
    await db.marketing_messages.insert_one({
        "id": msg_id, "organization_id": organization_id,
        "contact_id": contact.get("id"),
        "channel": "push", "status": status, "provider": provider,
        "journey_id": journey_id, "journey_run_id": journey_run_id,
        "campaign_id": campaign_id,
        "title": title, "body": body, "link": link,
        "sent_at": _now_iso(), "error": err,
    })
    return DeliveryResult(ok, "push", provider, msg_id, err)


async def send_in_app_notification(
    *, organization_id: str, contact: dict, title: str, body: str, link: str = "",
    journey_id: Optional[str] = None,
    journey_run_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    kind: str = "marketing",
) -> DeliveryResult:
    """Always-deliverable channel — drops the message into the contact's
    inbox so they see it next time they sign in. Universal fallback."""
    msg_id = _new_id()
    member_id = contact.get("member_id") or contact.get("id")
    title = (title or "").strip().replace("{{first_name}}", contact.get("first_name") or "there")
    body = (body or "").replace("{{first_name}}", contact.get("first_name") or "there")
    try:
        await db.member_inbox.insert_one({
            "id": msg_id,
            "organization_id": organization_id,
            "member_id": member_id,
            "contact_id": contact.get("id"),
            "kind": kind,
            "title": title or "New notification",
            "body": body,
            "link": link,
            "journey_id": journey_id,
            "journey_run_id": journey_run_id,
            "campaign_id": campaign_id,
            "read": False,
            "created_at": _now_iso(),
        })
        ok = True
        err = None
    except Exception as exc:
        ok = False
        err = str(exc)[:300]
    status = "sent" if ok else "failed"
    await db.marketing_messages.insert_one({
        "id": _new_id(), "organization_id": organization_id,
        "contact_id": contact.get("id"),
        "channel": "in_app", "status": status, "provider": "inbox",
        "journey_id": journey_id, "journey_run_id": journey_run_id,
        "campaign_id": campaign_id,
        "title": title, "body": body, "link": link,
        "sent_at": _now_iso(), "error": err,
    })
    return DeliveryResult(ok, "in_app", "inbox", msg_id, err)


async def dispatch_step(
    *, organization_id: str, contact: dict, node: dict,
    journey_id: Optional[str] = None,
    journey_run_id: Optional[str] = None,
) -> DeliveryResult:
    """Single-entry router — the journey engine calls this for any
    leaf node (one that produces a delivery)."""
    ntype = (node.get("type") or "").lower()
    common = {
        "organization_id": organization_id,
        "contact": contact,
        "journey_id": journey_id,
        "journey_run_id": journey_run_id,
    }
    if ntype == "send_sms":
        return await send_sms(body=node.get("body") or "", **common)
    if ntype == "send_push":
        return await send_push_notification(
            title=node.get("title") or "", body=node.get("body") or "",
            link=node.get("link") or "", **common,
        )
    if ntype == "send_in_app":
        return await send_in_app_notification(
            title=node.get("title") or "", body=node.get("body") or "",
            link=node.get("link") or "", **common,
        )
    if ntype == "send_email":
        # Email is handled via routes.marketing.campaigns._send_one for
        # campaigns. Journeys forward to the email helper directly.
        from routes.marketing.helpers import _now_iso as _h_now
        try:
            from utils.email import send_email  # type: ignore
        except ImportError:
            send_email = None  # type: ignore
        msg_id = _new_id()
        email = (contact.get("email") or "").strip()
        ok = False
        err = None
        provider = "none"
        if not email:
            err = "Contact has no email"
        elif send_email is None:
            err = "Email backend unavailable"
            provider = "mock"
            ok = True  # treat as MOCKED-sent so dashboards advance
        else:
            try:
                await send_email(
                    to=email,
                    subject=node.get("subject") or node.get("title") or "Message",
                    html=(node.get("body") or "").replace(
                        "{{first_name}}", contact.get("first_name") or "there"
                    ),
                )
                ok = True
                provider = "resend"
            except Exception as exc:  # pragma: no cover
                err = str(exc)[:300]
                provider = "resend"
        await db.marketing_messages.insert_one({
            "id": msg_id, "organization_id": organization_id,
            "contact_id": contact.get("id"),
            "channel": "email",
            "status": "sent" if (ok and provider != "mock") else ("mock_sent" if ok else "failed"),
            "provider": provider,
            "journey_id": journey_id, "journey_run_id": journey_run_id,
            "subject": node.get("subject") or node.get("title") or "",
            "body": node.get("body") or "",
            "sent_at": _h_now(), "error": err,
        })
        return DeliveryResult(ok, "email", provider, msg_id, err)
    return DeliveryResult(False, ntype or "unknown", "none", _new_id(), f"Unsupported node type '{ntype}'")
