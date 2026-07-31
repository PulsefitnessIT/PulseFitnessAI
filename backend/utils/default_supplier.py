"""Pulse Fitness Ltd — the built-in default supplier for every organisation.

Every org on PulseFitness.ai gets Pulse Fitness Ltd as a locked default supplier
so that ANY logged fault always reaches Pulse, even when a machine has no
specific supplier assigned. Commercial orgs route to service.dept@pulsefitness.com;
MOD orgs route to MODService@pulsefitness.com.

The default row is:
  • always present (ensured on read + org create + one-time backfill),
  • non-deletable and non-editable (email/name/phone are locked to Pulse),
  • the final fallback in fault dispatch when no other supplier resolves.

Pro/Full orgs can add further suppliers; Lite orgs keep only this default.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from utils.database import db
from utils.module_access import is_mod_org

PULSE_DEFAULT_SUPPLIER_NAME = "Pulse Fitness Ltd"
COMMERCIAL_SERVICE_EMAIL = "service.dept@pulsefitness.com"
MOD_SERVICE_EMAIL = "MODService@pulsefitness.com"
DEFAULT_CONTACT_PERSON = "Pulse Fitness Service Team"


def default_supplier_email(org: dict | None) -> str:
    """MOD orgs use the MOD Service inbox; everyone else the commercial desk."""
    return MOD_SERVICE_EMAIL if is_mod_org(org) else COMMERCIAL_SERVICE_EMAIL


async def ensure_default_supplier(org_id: str, org: dict | None = None) -> dict | None:
    """Idempotently create/repair the locked Pulse Fitness default supplier for
    an org. Returns the supplier doc (without _id) or None when org_id missing."""
    if not org_id:
        return None
    if org is None:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
    email = default_supplier_email(org)

    existing = await db.suppliers.find_one(
        {"organization_id": org_id, "is_default_pulse": True}, {"_id": 0})
    if existing:
        # Keep the locked fields correct (e.g. if the org later became MOD).
        fixes = {}
        if existing.get("email") != email:
            fixes["email"] = email
        if existing.get("name") != PULSE_DEFAULT_SUPPLIER_NAME:
            fixes["name"] = PULSE_DEFAULT_SUPPLIER_NAME
        if not existing.get("locked"):
            fixes["locked"] = True
        if fixes:
            await db.suppliers.update_one(
                {"organization_id": org_id, "is_default_pulse": True}, {"$set": fixes})
            existing.update(fixes)
        return existing

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": PULSE_DEFAULT_SUPPLIER_NAME,
        "email": email,
        "phone": "",
        "contact_person": DEFAULT_CONTACT_PERSON,
        "address": "",
        "notes": "Default Pulse Fitness service contact. Faults on any machine "
                 "without a specific supplier are routed here automatically.",
        "supplier_types": ["service"],
        "supplier_type": "service",
        "manufacturer_keywords": [],
        "callout_fee": 0, "labour_rate_per_hour": 0, "mileage_rate": 0, "parts_markup_pct": 0,
        "custom_items": [],
        "is_default_pulse": True,
        "locked": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.suppliers.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_default_pulse_supplier(org_id: str) -> dict | None:
    """Return the org's Pulse Fitness default supplier, creating it if needed."""
    return await ensure_default_supplier(org_id)


def can_add_extra_suppliers(user: dict, org: dict | None) -> bool:
    """Pro/Full (and Pulse admins / MOD-estate) orgs may add extra suppliers;
    Lite orgs keep only the locked Pulse Fitness default."""
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return True
    at = str((org or {}).get("account_type") or "").lower()
    return at != "lite"
