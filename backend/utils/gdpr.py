"""GDPR opt-out helpers for CRM contacts.

UK GDPR Article 21 — right to object to processing for direct
marketing. We store explicit per-channel booleans on each contact
so the marketing engine can hard-skip opted-out recipients without
ambiguity.

Channels:
    email, sms, phone, post, marketing (catch-all)

Usage::

    from utils.gdpr import is_contact_opted_out

    if await is_contact_opted_out(contact_id, "email"):
        # Skip — the contact has opted out of email marketing.
        return

    # ... otherwise proceed.

Or, if you have the contact dict already in hand::

    if is_dict_opted_out(contact, "email"):
        return
"""
from __future__ import annotations

from typing import Iterable

from utils.database import db


CHANNELS = ("email", "sms", "phone", "post", "marketing")


def is_dict_opted_out(contact: dict, channel: str) -> bool:
    """Inspect a contact dict (already loaded). Cheap, no DB hit."""
    if not contact:
        return True  # safer default — no contact = no marketing
    if contact.get("opt_out_marketing"):
        return True
    return bool(contact.get(f"opt_out_{channel}"))


async def is_contact_opted_out(contact_id: str, channel: str) -> bool:
    """Resolve opt-out by contact id. Returns ``True`` if the contact
    has opted out of *channel* OR the marketing catch-all."""
    if not contact_id or channel not in CHANNELS:
        return True
    contact = await db.crm2_contacts.find_one(
        {"id": contact_id},
        {"_id": 0, "opt_out_email": 1, "opt_out_sms": 1, "opt_out_phone": 1,
         "opt_out_post": 1, "opt_out_marketing": 1},
    )
    return is_dict_opted_out(contact or {}, channel)


async def filter_marketing_eligible(
    contact_ids: Iterable[str], channel: str,
) -> list[str]:
    """Filter a batch of contact ids down to those eligible for
    *channel* marketing (i.e. NOT opted out)."""
    ids = [c for c in contact_ids if c]
    if not ids:
        return []
    if channel not in CHANNELS:
        return []
    cursor = db.crm2_contacts.find(
        {
            "id": {"$in": ids},
            "opt_out_marketing": {"$ne": True},
            f"opt_out_{channel}": {"$ne": True},
        },
        {"_id": 0, "id": 1},
    )
    eligible = await cursor.to_list(length=len(ids))
    return [c["id"] for c in eligible]
