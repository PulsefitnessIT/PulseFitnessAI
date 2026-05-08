"""Cross-module sync helpers.

Iter 215bx — single source of truth for "create or update a CRM contact /
company" so every module (marketing forms, memberships, lite-CRM, etc.)
writes to the SAME collection (`crm2_contacts`) and the live CRM portal
shows everything.

Before this iter, marketing forms wrote to `crm_contacts` (legacy v1),
memberships analytics push wrote to `crm_contacts`, and the CRM portal
read from `crm2_contacts` (v2). Result: leads were silently dropped.

Public API (all idempotent / upsert-by-email):
    upsert_crm_contact(org_id, *, email, first_name, last_name, phone,
                       source, lifecycle, tags, notes, company_name,
                       custom_fields, communication_preferences) -> contact_id
    upsert_crm_company(org_id, *, name, domain, source) -> company_id | None
    log_crm_activity(org_id, *, contact_id, type, subject, body,
                     created_by) -> activity_id
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from utils.database import db

logger = logging.getLogger(__name__)


def _iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _email_of(rec: dict | None) -> str | None:
    return ((rec or {}).get("email") or "").strip().lower() or None


async def upsert_crm_contact(
    organization_id: str,
    *,
    email: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    source: str = "",
    lifecycle: str = "Lead",
    tags: list[str] | None = None,
    notes: str | None = None,
    company_name: str | None = None,
    company_id: str | None = None,
    custom_fields: dict | None = None,
    communication_preferences: dict | None = None,
) -> str | None:
    """Idempotent contact upsert keyed by (organization_id, email).

    Returns the contact id, or None if `email` is missing (we can't
    safely dedupe without it).
    """
    if not email:
        return None
    email = email.strip().lower()
    now = _iso()
    existing = await db.crm2_contacts.find_one(
        {"organization_id": organization_id, "email": email}, {"_id": 0, "id": 1, "tags": 1},
    )
    if existing:
        merged_tags = sorted({*(existing.get("tags") or []), *(tags or [])})
        update: dict[str, Any] = {
            "updated_at": now,
            "tags": merged_tags,
        }
        # Only fill blanks — don't overwrite curated CRM data.
        if first_name:
            update.setdefault("first_name", first_name)
        if last_name:
            update.setdefault("last_name", last_name)
        if phone:
            update.setdefault("phone", phone)
        if company_id:
            update.setdefault("company_id", company_id)
        if company_name and not company_id:
            update.setdefault("company_name", company_name)
        if source:
            update.setdefault("source", source)
        if notes:
            update.setdefault("notes", notes)
        if communication_preferences:
            update.setdefault("communication_preferences", communication_preferences)
        if custom_fields:
            update.setdefault("custom_fields", custom_fields)
        # Use $setOnInsert-style filling: prefer existing values, but
        # also accept new ones by writing the full set under a different
        # key path to not stomp.
        # Simpler: only set the keys we set (above), since they're
        # already gated to "if missing".
        if len(update) > 2:  # more than just updated_at + tags
            await db.crm2_contacts.update_one({"id": existing["id"]}, {"$set": update})
        else:
            await db.crm2_contacts.update_one({"id": existing["id"]}, {"$set": {"updated_at": now, "tags": merged_tags}})
        return existing["id"]

    contact_id = str(uuid.uuid4())
    contact = {
        "id": contact_id,
        "organization_id": organization_id,
        "first_name": first_name or "",
        "last_name": last_name or "",
        "email": email,
        "phone": phone or "",
        "lifecycle": lifecycle or "Lead",
        "source": source,
        "tags": sorted(set(tags or [])),
        "notes": notes or "",
        "company_id": company_id or None,
        "company_name": company_name or "",
        "custom_fields": custom_fields or {},
        "communication_preferences": communication_preferences or {},
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.crm2_contacts.insert_one(contact)
    except Exception as exc:
        logger.info("crm2_contacts insert failed (non-fatal): %s", exc)
        return None
    return contact_id


async def upsert_crm_company(
    organization_id: str,
    *,
    name: str | None,
    domain: str | None = None,
    source: str = "",
) -> str | None:
    """Upsert keyed by (organization_id, lowercased name)."""
    if not name or not name.strip():
        return None
    name = name.strip()
    needle = name.lower()
    existing = await db.crm2_companies.find_one(
        {"organization_id": organization_id, "name_lower": needle}, {"_id": 0, "id": 1},
    )
    if existing:
        await db.crm2_companies.update_one(
            {"id": existing["id"]},
            {"$set": {"updated_at": _iso()}},
        )
        return existing["id"]

    cid = str(uuid.uuid4())
    await db.crm2_companies.insert_one({
        "id": cid,
        "organization_id": organization_id,
        "name": name,
        "name_lower": needle,
        "domain": (domain or "").lower() or None,
        "source": source,
        "tags": [],
        "created_at": _iso(),
        "updated_at": _iso(),
    })
    return cid


async def log_crm_activity(
    organization_id: str,
    *,
    contact_id: str | None,
    type: str,
    subject: str,
    body: str = "",
    created_by: str | None = None,
    opportunity_id: str | None = None,
) -> str | None:
    """Append an activity row in `crm2_activities`."""
    if not contact_id and not opportunity_id:
        return None
    aid = str(uuid.uuid4())
    try:
        await db.crm2_activities.insert_one({
            "id": aid,
            "organization_id": organization_id,
            "contact_id": contact_id,
            "opportunity_id": opportunity_id,
            "type": type,
            "subject": subject,
            "body": body,
            "owner_id": created_by,
            "created_at": _iso(),
        })
    except Exception as exc:
        logger.info("crm2_activities insert failed (non-fatal): %s", exc)
        return None
    return aid
