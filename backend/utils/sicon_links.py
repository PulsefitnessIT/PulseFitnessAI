"""
Sicon ↔ Pulse external-identifier mapping layer (spec §7).

A single reusable link table keyed by the immutable Sicon external id so every
sync is idempotent: the same siconEquipmentId / siSMCaseId always resolves to
the same Pulse record and can never create a duplicate.

Collection: db.sicon_external_links
Unique on (integration_source, external_entity_type, external_id).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from utils.database import db

logger = logging.getLogger(__name__)

SOURCE = "sicon"

# Canonical Sicon entity types we link (extend as later phases are proven).
ENTITY_EQUIPMENT = "equipment"
ENTITY_CASE = "case"
ENTITY_CUSTOMER = "customer"
ENTITY_SITE = "site"
ENTITY_CONTACT = "contact"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_link(external_entity_type: str, external_id: str,
                   organization_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the stored link for a Sicon external id, or None."""
    q: Dict[str, Any] = {
        "integration_source": SOURCE,
        "external_entity_type": external_entity_type,
        "external_id": str(external_id),
    }
    if organization_id:
        q["organization_id"] = organization_id
    return await db.sicon_external_links.find_one(q, {"_id": 0})


async def get_pulse_id(external_entity_type: str, external_id: str,
                       organization_id: Optional[str] = None) -> Optional[str]:
    link = await get_link(external_entity_type, external_id, organization_id)
    return link.get("pulse_entity_id") if link else None


async def upsert_link(external_entity_type: str, external_id: str,
                      pulse_entity_type: str, pulse_entity_id: str,
                      organization_id: Optional[str] = None,
                      source_updated_at: Optional[str] = None,
                      sync_status: str = "linked",
                      extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create or update a Sicon→Pulse link. Idempotent."""
    now = _now()
    key = {
        "integration_source": SOURCE,
        "external_entity_type": external_entity_type,
        "external_id": str(external_id),
    }
    doc = {
        **key,
        "organization_id": organization_id,
        "pulse_entity_type": pulse_entity_type,
        "pulse_entity_id": str(pulse_entity_id),
        "last_synced_at": now,
        "sync_status": sync_status,
    }
    if source_updated_at:
        doc["source_updated_at"] = source_updated_at
    if extra:
        doc.update(extra)
    await db.sicon_external_links.update_one(key, {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True)
    return doc


async def set_status(external_entity_type: str, external_id: str, sync_status: str,
                     reason: str = "", organization_id: Optional[str] = None) -> None:
    """Flag a link's state (e.g. 'conflict', 'failed', 'ignored') without linking."""
    now = _now()
    key = {
        "integration_source": SOURCE,
        "external_entity_type": external_entity_type,
        "external_id": str(external_id),
    }
    setdoc: Dict[str, Any] = {**key, "sync_status": sync_status, "last_synced_at": now}
    if organization_id:
        setdoc["organization_id"] = organization_id
    if reason:
        setdoc["status_reason"] = reason[:500]
    await db.sicon_external_links.update_one(key, {"$set": setdoc, "$setOnInsert": {"created_at": now}}, upsert=True)


async def counts_by_status(external_entity_type: str,
                           organization_id: Optional[str] = None) -> Dict[str, int]:
    """Aggregate link counts by sync_status for the admin dashboard."""
    match: Dict[str, Any] = {"integration_source": SOURCE, "external_entity_type": external_entity_type}
    if organization_id:
        match["organization_id"] = organization_id
    pipeline = [{"$match": match}, {"$group": {"_id": "$sync_status", "n": {"$sum": 1}}}]
    out: Dict[str, int] = {}
    async for row in db.sicon_external_links.aggregate(pipeline):
        out[row["_id"] or "unknown"] = row["n"]
    out["total"] = sum(out.values())
    return out
