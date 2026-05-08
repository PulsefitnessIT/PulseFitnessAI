"""
Microsoft Teams outbound channel (P4, Feb 2026).

Sends an Adaptive Card v1.4 to a customer-supplied Teams incoming webhook /
Power Automate workflow URL. Same payload shape used by the email digest so
the two channels stay visually aligned.

Teams URL formats we accept:
  - New Workflows (recommended by Microsoft): https://prod-XX.<region>.logic.azure.com:443/workflows/.../invoke?...
  - Legacy Office 365 Connectors (deprecated but still works): https://<tenant>.webhook.office.com/webhookb2/...

Both accept POSTs of the same JSON body. The Adaptive Card wrapping differs
slightly — we auto-detect from the host.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Hosts where the webhook expects the legacy MessageCard wrapping. Everything
# else we treat as a modern Workflows URL (attachments wrapper).
_LEGACY_HOSTS = ("webhook.office.com", "outlook.office365.com", "outlook.office.com")


def _is_legacy_webhook(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except (ValueError, AttributeError):
        return False
    return any(host.endswith(h) for h in _LEGACY_HOSTS)


def validate_webhook_url(url: str) -> None:
    """Basic safety check: must be HTTPS, must be a Microsoft endpoint."""
    if not url:
        raise HTTPException(status_code=400, detail="Webhook URL is empty")
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid URL") from exc
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS")
    host = (parsed.hostname or "").lower()
    allowed_suffixes = _LEGACY_HOSTS + (".logic.azure.com",)
    if not any(host.endswith(s.lstrip(".")) for s in allowed_suffixes):
        raise HTTPException(
            status_code=400,
            detail="Only Microsoft Teams webhook URLs are accepted",
        )


def render_adaptive_card(user: dict, payload: dict, freq_label: str) -> dict:
    """Build an Adaptive Card v1.4 body mirroring the email digest."""
    first_name = (user.get("full_name") or user.get("email", "").split("@")[0]).split(" ")[0]
    items_blocks: list[dict[str, Any]] = []
    for item in payload["items"]:
        tone = {"high": "Attention", "med": "Warning", "low": "Good"}.get(
            item.get("severity"), "Default",
        )
        title = _humanise_type(item.get("type"))
        body = item.get("customer_safe_message") or item.get("summary") or ""
        items_blocks.append({
            "type": "Container",
            "style": tone,
            "bleed": True,
            "items": [
                {"type": "TextBlock", "weight": "Bolder", "text": title, "wrap": True},
                {"type": "TextBlock", "text": body, "wrap": True, "spacing": "Small"},
            ],
            "spacing": "Medium",
        })

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "size": "Small", "color": "Accent",
             "text": f"Your {freq_label} digest"},
            {"type": "TextBlock", "size": "Large", "weight": "Bolder",
             "text": f"Hi {first_name},", "wrap": True},
            {"type": "TextBlock", "text": payload["summary"] + ".",
             "wrap": True, "spacing": "Small"},
            *items_blocks,
        ],
        "actions": [{
            "type": "Action.OpenUrl",
            "title": "Open dashboard",
            "url": _app_url() + "/dashboard",
        }],
    }
    return card


def _humanise_type(t: str) -> str:
    return {
        "nudge.warranty_expiring": "Warranty expiring",
        "nudge.ppm_overdue": "Planned maintenance overdue",
        "nudge.supplier_sla_drift": "Supplier performance drift",
        "nudge.password_rotation": "Password rotation due",
    }.get(t or "", (t or "Nudge").replace("nudge.", "").replace("_", " ").title())


def _app_url() -> str:
    import os
    return (os.environ.get("FRONTEND_URL", "") or "https://app.gymaxis.ai").rstrip("/")


def wrap_for_transport(card: dict, webhook_url: str) -> dict:
    """Wrap the Adaptive Card in whichever envelope the destination expects."""
    if _is_legacy_webhook(webhook_url):
        # Classic Office 365 Connector — accepts raw card with attachments wrapper.
        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }
    # Power Automate Workflows — same wrapping works.
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }


async def post_to_teams(webhook_url: str, card: dict) -> bool:
    """POST an Adaptive Card. Returns True on 2xx, False otherwise. Never raises."""
    if not webhook_url:
        return False
    body = wrap_for_transport(card, webhook_url)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                content=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            if 200 <= resp.status_code < 300:
                return True
            logger.warning(
                f"[teams] webhook returned {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.HTTPError as exc:
        logger.warning(f"[teams] webhook error: {exc}")
    return False
