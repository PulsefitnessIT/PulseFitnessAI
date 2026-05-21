"""Iter 216h276 — Auto-mirror Pulse tenants into the master CRM.

Customer ask (verbatim): *"Pulse Fitness Limited are on Pulse Pro
with all modules unlocked but they are not showing as an
organisation on CRM."*

### Why we mirror

Pulse Fitness Limited (the customer who paid for the platform)
is a TENANT org in `organizations` — but the master admin's CRM
Companies list reads from `crm_v2_companies`, a separate
collection scoped per-CRM-org. The master admin can't see their
own paying customers in the CRM because the two worlds never met.

This iter:
* On boot, mirrors every Pulse-branded tenant (`subscription_tier`
  in `pulse_lite` / `pulse_pro` / `pulse_pro_plus`) into the master
  admin's CRM as a `crm_v2_companies` record.
* Tags each mirrored doc with `source="tenant_mirror"` + the
  source `tenant_org_id` so we can find/update without dupes.
* Updates push tenant-side changes (name, website, country) into
  the mirrored CRM record on every boot — so renames + new
  Companies House info flow forward automatically.
* Mirrors are visible in the CRM Companies list AND link back
  to the tenant via the `tenant_org_id` so reps can jump from
  "Pulse Fitness Limited (CRM company)" → master admin → tenant
  panel in one click.

NOT done here (deliberately) — keep the surface small:
* No reverse sync (CRM edits don't push to the tenant org).
* No auto-deletion: if a tenant org is deleted, the mirror keeps
  the CRM company with `status="former"` for historical reporting.
* Mirrors are NOT created for non-Pulse tenants (e.g. MOD orgs,
  GymAxis Master Admin's own home org).

### What this iter is NOT solving

The bigger "dirty org build-up" ask is still parked. h276 is
narrowly about surfacing real paying tenants in the CRM. The
LIVE_DATA_ONLY env gate / org integrity tile will come next.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from utils.database import db


logger = logging.getLogger(__name__)


# Pulse subscription tiers that map onto CRM companies. Other tiers
# (full GymAxis enterprise, MOD/Army, master) are NOT mirrored — they
# wouldn't make sense as "customer" rows in the master admin's CRM.
PULSE_TIERS: tuple[str, ...] = ("pulse_lite", "pulse_pro", "pulse_pro_plus")

# Org `account_type` values that also qualify (some orgs carry the
# label here instead of `subscription_tier`).
PULSE_ACCOUNT_TYPES: tuple[str, ...] = ("pulse_lite", "pulse_pro", "lite", "pulse_pro_plus")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_pulse_tenant(org: dict) -> bool:
    """A tenant org qualifies for CRM mirroring if it's on a Pulse
    plan AND it's not the master admin's own home org."""
    if not org or not org.get("id"):
        return False
    if org.get("is_master_admin_home") or org.get("is_master_org"):
        return False
    if org.get("subscription_tier") in PULSE_TIERS:
        return True
    if org.get("account_type") in PULSE_ACCOUNT_TYPES:
        return True
    return False


async def _resolve_master_crm_org_id() -> str | None:
    """Find the master admin's home org. We mirror INTO that org's
    `crm2_companies` scope so the master sees the mirrored rows
    in their CRM Companies list."""
    # Prefer the explicitly-flagged master org; fall back to the
    # email lookup so this works on fresh / legacy DBs.
    master_user = await db.users.find_one(
        {"is_master_admin": True}, {"_id": 0, "organization_id": 1},
    )
    if master_user:
        return master_user.get("organization_id")
    return None


def _project_org_to_company(org: dict, master_org_id: str) -> dict[str, Any]:
    """Map a tenant org doc onto the `crm2_companies` shape. Only
    the fields we want to keep in sync from the tenant side; CRM
    enrichment (sector, owner, territory, etc.) is preserved
    on update."""
    return {
        "organization_id": master_org_id,            # scope: master CRM
        "source": "tenant_mirror",                    # marker for the audit + UI badge
        "tenant_org_id": org.get("id"),               # back-reference
        "tenant_subscription_tier": org.get("subscription_tier") or org.get("account_type") or "",
        "tenant_account_type": org.get("account_type") or "",
        "name": org.get("name") or "Untitled tenant",
        "website": org.get("website") or org.get("website_url") or "",
        "phone": org.get("phone") or "",
        "email": org.get("contact_email") or "",
        "country": org.get("country") or "United Kingdom",
        "type": "customer",                           # paying tenant → customer
        "status": "active",
    }


async def mirror_pulse_tenants_to_crm() -> dict:
    """One-shot reconciliation. Idempotent — safe to run on every
    boot. Returns {created, updated, marked_former, skipped} so
    ops can see what happened in the logs.
    """
    master_org_id = await _resolve_master_crm_org_id()
    if not master_org_id:
        logger.info("[tenant-mirror] no master admin found — skipping mirror")
        return {"created": 0, "updated": 0, "marked_former": 0, "skipped": 0}

    # All Pulse-branded tenants
    pulse_orgs: list[dict] = []
    async for o in db.organizations.find({}, {"_id": 0}):
        if _is_pulse_tenant(o):
            pulse_orgs.append(o)
    pulse_tenant_ids: set[str] = {o["id"] for o in pulse_orgs}

    created = 0
    updated = 0
    for org in pulse_orgs:
        proj = _project_org_to_company(org, master_org_id)
        existing = await db.crm2_companies.find_one(
            {"organization_id": master_org_id,
             "tenant_org_id": org["id"]},
            {"_id": 0, "id": 1, "name": 1, "website": 1, "phone": 1},
        )
        if existing:
            # Update only the tenant-driven fields; preserve CRM enrichment
            update_doc = {**proj, "updated_at": _now()}
            res = await db.crm2_companies.update_one(
                {"id": existing["id"]},
                {"$set": update_doc},
            )
            if res.modified_count:
                updated += 1
        else:
            new_company = {
                **proj,
                "id": f"tenant-{org['id'][:24]}",   # deterministic id from tenant id
                "sector": "Fitness",
                "type": "customer",
                "created_at": _now(),
                "updated_at": _now(),
            }
            try:
                await db.crm2_companies.insert_one(new_company)
                created += 1
            except Exception:
                # race: another worker just created it — fall back to update
                logger.exception("[tenant-mirror] duplicate insert for %s — retrying as update", org["id"])
                await db.crm2_companies.update_one(
                    {"organization_id": master_org_id, "tenant_org_id": org["id"]},
                    {"$set": {**proj, "updated_at": _now()}},
                    upsert=True,
                )

    # Mark previously-mirrored companies as former if their tenant
    # org has disappeared (cleanly closed or wiped).
    marked_former = 0
    async for c in db.crm2_companies.find(
        {"organization_id": master_org_id,
         "source": "tenant_mirror",
         "status": {"$ne": "former"}},
        {"_id": 0, "id": 1, "tenant_org_id": 1},
    ):
        if c.get("tenant_org_id") not in pulse_tenant_ids:
            await db.crm2_companies.update_one(
                {"id": c["id"]},
                {"$set": {"status": "former", "updated_at": _now()}},
            )
            marked_former += 1

    skipped = max(0, len(pulse_orgs) - created - updated)
    summary = {
        "created": created, "updated": updated,
        "marked_former": marked_former, "skipped": skipped,
        "pulse_tenants_found": len(pulse_orgs),
    }
    logger.info("[tenant-mirror] reconciliation complete %s", summary)
    return summary


async def mirror_single_tenant(tenant_org_id: str) -> dict:
    """Mirror (or refresh the mirror for) a single tenant. Called
    when the master admin edits an org so the CRM company stays
    in sync with the tenant's display name etc."""
    org = await db.organizations.find_one({"id": tenant_org_id}, {"_id": 0})
    if not org:
        return {"status": "tenant_not_found"}
    if not _is_pulse_tenant(org):
        return {"status": "not_a_pulse_tenant"}
    master_org_id = await _resolve_master_crm_org_id()
    if not master_org_id:
        return {"status": "no_master_org"}

    proj = _project_org_to_company(org, master_org_id)
    res = await db.crm2_companies.update_one(
        {"organization_id": master_org_id, "tenant_org_id": tenant_org_id},
        {"$set": {**proj, "updated_at": _now()},
         "$setOnInsert": {
             "id": f"tenant-{tenant_org_id[:24]}",
             "sector": "Fitness", "type": "customer",
             "created_at": _now(),
         }},
        upsert=True,
    )
    return {
        "status": "ok",
        "matched": res.matched_count,
        "modified": res.modified_count,
        "upserted_id": str(res.upserted_id) if res.upserted_id else None,
    }


async def ensure_tenant_mirror_indexes() -> None:
    """Partial unique index on (organization_id, tenant_org_id) so a
    tenant can't be mirrored twice.

    Iter 216h276 — switched from `sparse=True` to `partialFilterExpression`
    because sparse treats explicit `null` values as duplicates, and the
    crm2_companies collection has thousands of manually-created rows
    with `tenant_org_id: null`. The partial filter only indexes rows
    where the field is a real string, sidestepping the collision.
    """
    try:
        await db.crm2_companies.create_index(
            [("organization_id", 1), ("tenant_org_id", 1)],
            unique=True,
            partialFilterExpression={"tenant_org_id": {"$type": "string"}},
            name="crm2_companies_tenant_mirror_uniq",
        )
    except Exception:
        logger.exception("[tenant-mirror] index create failed (non-fatal)")
