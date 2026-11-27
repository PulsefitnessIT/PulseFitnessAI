"""
Sicon ↔ Pulse external-identifier mapping layer (spec §7).

A single reusable link table keyed by the immutable Sicon external id so every
sync is idempotent: the same siconEquipmentId / siSMCaseId always resolves to
the same Pulse record and can never create a duplicate.

Collection: db.sicon_external_links
Unique on (integration_source, source_company, external_entity_type, external_id).
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
ENTITY_RESOURCE = "resource"  # Sicon appointment resource ↔ Pulse svc_engineer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


import contextvars

_COMPANY_CACHE: Dict[str, tuple] = {}
_WS_CACHE: Dict[str, tuple] = {}
# The connection that actually retrieved the records being processed (set by each sync run). Links are scoped by
# it — never inferred from the destination customer organisation.
SOURCE_CTX: contextvars.ContextVar = contextvars.ContextVar("sicon_source_connection", default=None)


async def is_pulse_workspace(org_id: Optional[str]) -> bool:
    """Pulse operator company / platform admin org: syncs the estates of many customers."""
    if not org_id:
        return False
    hit = _WS_CACHE.get(org_id)
    if hit and (datetime.now(timezone.utc).timestamp() - hit[1]) < 300:
        return hit[0]
    val = bool(await db.organizations.find_one({"id": org_id, "is_operator_company": True}, {"_id": 1})
               or await db.users.find_one({"organization_id": org_id, "is_master_admin": True}, {"_id": 1}))
    _WS_CACHE[org_id] = (val, datetime.now(timezone.utc).timestamp())
    return val


async def connection_company(organization_id: Optional[str]) -> Optional[str]:
    """The Sicon connection identity (companyId) used by this organisation's sync. Every link is scoped by it so
    identical numeric Sicon ids in different Sage/Sicon companies can never collide."""
    if not organization_id:
        return None
    hit = _COMPANY_CACHE.get(organization_id)
    if hit and (datetime.now(timezone.utc).timestamp() - hit[1]) < 60:
        return hit[0]
    import os
    cfg = await db.sicon_config.find_one({"organization_id": organization_id},
                                         {"_id": 0, "company_id": 1, "enabled": 1, "base_url": 1}) or {}
    cid = cfg.get("company_id") if cfg.get("enabled") else None
    base = cfg.get("base_url") if cid else None
    if not cid:
        from routes.integrations import get_integration_config
        integ = await get_integration_config("sicon") or {}
        creds = integ.get("credentials") if isinstance(integ.get("credentials"), dict) and integ.get("enabled") else {}
        cid = creds.get("company_id") or os.environ.get("SICON_COMPANY_ID")
        base = (integ.get("base_url") or creds.get("base_url")) if creds.get("company_id") else os.environ.get("SICON_BASE_URL")
    from urllib.parse import urlparse
    host = (urlparse(str(base or "")).netloc or "").lower()
    # installation + company: identical companyIds on different Sicon servers never collide
    val = f"{host}#{str(cid).strip()}" if cid not in (None, "", 0, "0") else None
    _COMPANY_CACHE[organization_id] = (val, datetime.now(timezone.utc).timestamp())
    return val


async def sage_company_for(organization_id: Optional[str]) -> Optional[str]:
    """Sage company label (as used for Import Centre uploads) the Sicon connection belongs to; None when not configured."""
    import os
    cfg = await db.sicon_config.find_one({"organization_id": organization_id}, {"_id": 0, "sage_company": 1}) if organization_id else None
    val = (cfg or {}).get("sage_company") or os.environ.get("SICON_SAGE_COMPANY") or ""
    return val.strip().upper() or None


def _base(external_entity_type: str, external_id: str) -> Dict[str, Any]:
    return {"integration_source": SOURCE, "external_entity_type": external_entity_type, "external_id": str(external_id)}


async def _find(external_entity_type: str, external_id: str, organization_id: Optional[str],
                source_company: Optional[str]) -> Optional[Dict[str, Any]]:
    base = _base(external_entity_type, external_id)
    company = source_company or SOURCE_CTX.get() or await connection_company(organization_id) or "unscoped"
    d = await db.sicon_external_links.find_one({**base, "source_company": company}, {"_id": 0})
    if d:
        return d
    # Legacy (pre-scoping) links are only honoured for the organisation that created them, until migrated.
    q = {**base, "source_company": {"$exists": False}}
    if organization_id:
        q["organization_id"] = organization_id
        return await db.sicon_external_links.find_one(q, {"_id": 0})
    rows = await db.sicon_external_links.find(q, {"_id": 0}).to_list(2)
    return rows[0] if len(rows) == 1 else None


async def get_link(external_entity_type: str, external_id: str,
                   organization_id: Optional[str] = None, source_company: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the stored link for a Sicon external id (scoped by connection company), or None."""
    d = await _find(external_entity_type, external_id, organization_id, source_company)
    if d and organization_id and d.get("organization_id") not in (None, organization_id) \
            and not await is_pulse_workspace(organization_id):
        return None  # a customer never resolves another org's record; the Pulse workspace may (it services them)
    return d


async def get_pulse_id(external_entity_type: str, external_id: str,
                       organization_id: Optional[str] = None, source_company: Optional[str] = None) -> Optional[str]:
    link = await get_link(external_entity_type, external_id, organization_id, source_company)
    return link.get("pulse_entity_id") if link else None


async def _key_for_write(external_entity_type: str, external_id: str, organization_id: Optional[str],
                         source_company: Optional[str]) -> Dict[str, Any]:
    base = _base(external_entity_type, external_id)
    company = source_company or SOURCE_CTX.get() or await connection_company(organization_id) or "unscoped"
    if await db.sicon_external_links.find_one({**base, "source_company": company}, {"_id": 1}):
        return {**base, "source_company": company}
    legacy = {**base, "source_company": {"$exists": False}}
    if organization_id:
        legacy["organization_id"] = organization_id
    if await db.sicon_external_links.find_one(legacy, {"_id": 1}):
        return legacy  # keep using the legacy link (no duplicate) until the audited migration scopes it
    return {**base, "source_company": company}


async def upsert_link(external_entity_type: str, external_id: str,
                      pulse_entity_type: str, pulse_entity_id: str,
                      organization_id: Optional[str] = None,
                      source_updated_at: Optional[str] = None,
                      sync_status: str = "linked",
                      extra: Optional[Dict[str, Any]] = None,
                      source_company: Optional[str] = None, reassign: bool = False) -> Dict[str, Any]:
    """Create or update a Sicon→Pulse link. Idempotent. Syncs never reassign an established link to another record;
    only an explicit admin decision (reassign=True) or clearing (empty id) may."""
    now = _now()
    key = await _key_for_write(external_entity_type, external_id, organization_id, source_company)
    existing = await db.sicon_external_links.find_one(key, {"_id": 0, "pulse_entity_id": 1, "sync_status": 1})
    if not reassign and pulse_entity_id and existing and existing.get("pulse_entity_id") \
            and existing["pulse_entity_id"] != str(pulse_entity_id):
        await db.sicon_external_links.update_one(key, {"$set": {"sync_status": "conflict", "last_synced_at": now,
                                                                "status_reason": f"Also claimed by {pulse_entity_type} {pulse_entity_id}"}})
        logger.warning("sicon link %s/%s already linked to %s; not reassigned", external_entity_type, external_id,
                       existing["pulse_entity_id"])
        return {**key, **existing, "sync_status": "conflict"}
    doc = {
        "integration_source": SOURCE, "external_entity_type": external_entity_type, "external_id": str(external_id),
        "organization_id": organization_id,
        "pulse_entity_type": pulse_entity_type,
        "pulse_entity_id": str(pulse_entity_id),
        "last_synced_at": now,
        "sync_status": sync_status,
    }
    if isinstance(key.get("source_company"), str):
        doc["source_company"] = key["source_company"]
    if source_updated_at:
        doc["source_updated_at"] = source_updated_at
    if extra:
        doc.update(extra)
    from pymongo.errors import DuplicateKeyError
    try:
        await db.sicon_external_links.update_one(key, {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True)
    except DuplicateKeyError:  # a concurrent writer inserted the same key first: re-run the conflict check against it
        return await upsert_link(external_entity_type, external_id, pulse_entity_type, pulse_entity_id, organization_id,
                                 source_updated_at, sync_status, extra, source_company, reassign)
    return doc


async def reserve_link(external_entity_type: str, external_id: str, pulse_entity_type: str, pulse_entity_id: str,
                       organization_id: Optional[str] = None) -> str:
    """Atomically claim an external id for a record about to be created. Returns the owning Pulse id: ours if we won,
    otherwise the record that already holds it (the caller must then link, not create)."""
    from pymongo.errors import DuplicateKeyError
    key = await _key_for_write(external_entity_type, external_id, organization_id, None)
    existing = await db.sicon_external_links.find_one(key, {"_id": 0, "pulse_entity_id": 1})
    if existing and existing.get("pulse_entity_id"):
        return existing["pulse_entity_id"]
    try:
        res = await db.sicon_external_links.update_one(
            {**key, "pulse_entity_id": {"$in": [None, ""]}},
            {"$set": {**{k: v for k, v in key.items() if isinstance(v, str)}, "organization_id": organization_id,
                      "pulse_entity_type": pulse_entity_type, "pulse_entity_id": str(pulse_entity_id),
                      "sync_status": "reserving", "last_synced_at": _now()}, "$setOnInsert": {"created_at": _now()}},
            upsert=True)
    except DuplicateKeyError:
        res = None
    if res is not None and (res.upserted_id is not None or res.modified_count):
        return str(pulse_entity_id)
    cur = await db.sicon_external_links.find_one(key, {"_id": 0, "pulse_entity_id": 1}) or {}
    return cur.get("pulse_entity_id") or str(pulse_entity_id)


async def release_reservation(external_entity_type: str, external_id: str, pulse_entity_id: str,
                              organization_id: Optional[str] = None) -> None:
    key = await _key_for_write(external_entity_type, external_id, organization_id, None)
    await db.sicon_external_links.update_one({**key, "pulse_entity_id": str(pulse_entity_id), "sync_status": "reserving"},
                                             {"$set": {"pulse_entity_id": "", "sync_status": "unlinked"}})


async def set_status(external_entity_type: str, external_id: str, sync_status: str,
                     reason: str = "", organization_id: Optional[str] = None) -> None:
    """Flag a link's state (e.g. 'conflict', 'failed', 'ignored') without linking."""
    now = _now()
    key = await _key_for_write(external_entity_type, external_id, organization_id, None)
    setdoc: Dict[str, Any] = {"sync_status": sync_status, "last_synced_at": now}
    if isinstance(key.get("source_company"), str):
        setdoc["source_company"] = key["source_company"]
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
