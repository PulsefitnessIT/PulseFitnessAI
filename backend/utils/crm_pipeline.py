"""Org-scoped CRM pipeline helpers (SEC-008).

Historically `crm_pipelines` held a single GLOBAL document (no
``organization_id``) shared by every tenant, so editing it affected all of
them. This module makes pipelines per-tenant:

* every org gets its own default pipeline document,
* reads/writes are scoped by ``organization_id``,
* :func:`backfill_org_pipelines` migrates legacy data idempotently.

The default stage ids are kept as the legacy string ids ("lead"…"lost") so
existing deals (which store ``stage`` as those strings) keep resolving.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from utils.database import db

# Shared stage template. NOTE: stage *ids* are intentionally the same strings
# across tenants — each org still owns its own pipeline DOCUMENT, so editing
# one org's pipeline never touches another's.
DEFAULT_PIPELINE_STAGES = [
    {"id": "lead", "name": "New Lead", "order": 0, "color": "#007AFF"},
    {"id": "qualified", "name": "Qualified", "order": 1, "color": "#AF52DE"},
    {"id": "proposal", "name": "Proposal Sent", "order": 2, "color": "#FFCC00"},
    {"id": "negotiation", "name": "Negotiation", "order": 3, "color": "#FF9500"},
    {"id": "won", "name": "Won", "order": 4, "color": "#34C759"},
    {"id": "lost", "name": "Lost", "order": 5, "color": "#FF3B30"},
]


def build_default_pipeline(org_id: str, created_by: Optional[str] = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": "Sales Pipeline",
        "stages": [dict(s) for s in DEFAULT_PIPELINE_STAGES],
        "is_default": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
    }


async def get_or_create_default_pipeline(org_id: Optional[str], created_by: Optional[str] = None) -> Optional[dict]:
    """Return the org's default pipeline, creating it from the template if the
    org has none. Returns ``None`` only when ``org_id`` is falsy."""
    if not org_id:
        return None
    existing = (
        await db.crm_pipelines.find_one({"organization_id": org_id, "is_default": True}, {"_id": 0})
        or await db.crm_pipelines.find_one({"organization_id": org_id}, {"_id": 0})
    )
    if existing:
        return existing
    doc = build_default_pipeline(org_id, created_by)
    await db.crm_pipelines.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def backfill_org_pipelines() -> dict:
    """Idempotent migration:

    1. Any org-less ("global") pipeline is re-scoped to the org of a deal that
       references it, or deleted if nothing references it (a fresh per-org
       default is created in step 2).
    2. Every org with CRM presence is guaranteed a default pipeline.
    """
    reassigned = deleted = created = 0

    orphans = await db.crm_pipelines.find(
        {"$or": [{"organization_id": {"$exists": False}}, {"organization_id": None}]},
        {"_id": 0, "id": 1},
    ).to_list(500)
    for p in orphans:
        deal = await db.crm_deals.find_one({"pipeline_id": p["id"]}, {"_id": 0, "organization_id": 1})
        target = (deal or {}).get("organization_id")
        if target:
            await db.crm_pipelines.update_one({"id": p["id"]}, {"$set": {"organization_id": target}})
            reassigned += 1
        else:
            await db.crm_pipelines.delete_one({"id": p["id"]})
            deleted += 1

    orgs: set[str] = set()
    for coll in ("crm_users", "crm_deals", "crm_contacts", "crm_companies"):
        orgs |= set(await db[coll].distinct("organization_id"))
    for org_id in [o for o in orgs if o]:
        before = await db.crm_pipelines.count_documents({"organization_id": org_id})
        await get_or_create_default_pipeline(org_id)
        if before == 0:
            created += 1

    return {"reassigned": reassigned, "deleted": deleted, "created": created}
